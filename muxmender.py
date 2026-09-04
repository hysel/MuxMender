#!/usr/bin/env python3
"""MuxMender: safely analyze and optimize media libraries."""

from __future__ import annotations

import argparse
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


MEDIA_EXTENSIONS = {
    ".3gp", ".avi", ".flv", ".m2ts", ".m4v", ".mkv", ".mov",
    ".mp4", ".mpeg", ".mpg", ".mts", ".ts", ".webm", ".wmv",
}
SOFTWARE_ENCODERS = {"hevc": "libx265", "av1": "libsvtav1"}
HARDWARE_ENCODERS = {
    "amd": {"hevc": "hevc_amf", "av1": "av1_amf"},
    "nvidia": {"hevc": "hevc_nvenc", "av1": "av1_nvenc"},
    "intel": {"hevc": "hevc_qsv", "av1": "av1_qsv"},
}
VENDOR_LABELS = {"amd": "AMD", "nvidia": "NVIDIA", "intel": "Intel", "cpu": "CPU"}
DOWNLOAD_URLS = {
    "ffmpeg": "https://ffmpeg.org/download.html",
    "amd": "https://www.amd.com/en/support/download/drivers.html",
    "nvidia": "https://www.nvidia.com/Download/index.aspx",
    "intel": "https://www.intel.com/content/www/us/en/support/detect.html",
}
RESOLUTION_LIMITS = {
    "2160p": (3840, 2160),
    "1080p": (1920, 1080),
    "720p": (1280, 720),
    "480p": (854, 480),
}
KNOWN_HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


@dataclass
class MediaInfo:
    path: str
    size_bytes: int
    duration_seconds: float
    container: str
    video_codec: str
    width: int
    height: int
    pixel_format: str
    bit_depth: int
    color_primaries: str
    color_transfer: str
    color_space: str
    color_range: str
    hdr: bool
    dolby_vision: bool
    audio_codecs: list[str]
    subtitle_codecs: list[str]
    recommendation: str = ""
    reason: str = ""


@dataclass(frozen=True)
class EncoderSelection:
    vendor: str
    encoder: str

    @property
    def hardware(self) -> bool:
        return self.vendor != "cpu"

    @property
    def label(self) -> str:
        return f"{VENDOR_LABELS[self.vendor]} ({self.encoder})"


class HardwareRequirementError(RuntimeError):
    def __init__(self, component: str, message: str, download_url: str):
        super().__init__(message)
        self.component = component
        self.download_url = download_url


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TiB"


def media_files(folder: Path) -> Iterable[Path]:
    for path in sorted(folder.rglob("*")):
        if (
            path.is_file()
            and path.suffix.lower() in MEDIA_EXTENSIONS
            and ".muxmender" not in path.stem.lower()
            and ".partial" not in path.name.lower()
        ):
            yield path


def run_json(command: list[str]) -> dict[str, Any]:
    # FFprobe emits UTF-8 JSON. Explicit decoding avoids Windows' legacy
    # code-page decoder crashing on international filenames or metadata.
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(message)
    return json.loads(result.stdout)


def probe(path: Path, ffprobe: str = "ffprobe") -> MediaInfo:
    data = run_json([
        ffprobe, "-v", "error", "-show_format", "-show_streams",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height,pix_fmt,bits_per_raw_sample,"
        "color_primaries,color_transfer,color_space,color_range,side_data_list:"
        "format=format_name,duration",
        "-of", "json", str(path),
    ])
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise RuntimeError("no video stream found")

    pixel_format = video.get("pix_fmt") or "unknown"
    raw_depth = str(video.get("bits_per_raw_sample") or "")
    if raw_depth.isdigit():
        bit_depth = int(raw_depth)
    elif "10" in pixel_format:
        bit_depth = 10
    elif "12" in pixel_format:
        bit_depth = 12
    else:
        bit_depth = 8

    side_data = video.get("side_data_list") or []
    side_text = json.dumps(side_data).lower()
    transfer = video.get("color_transfer") or "unknown"
    dolby_vision = "dovi" in side_text or "dolby vision" in side_text
    hdr = transfer in KNOWN_HDR_TRANSFERS or "mastering display" in side_text or dolby_vision

    audio = [s.get("codec_name", "unknown") for s in streams if s.get("codec_type") == "audio"]
    subtitles = [s.get("codec_name", "unknown") for s in streams if s.get("codec_type") == "subtitle"]
    fmt = data.get("format", {})
    try:
        duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0

    return MediaInfo(
        path=str(path.resolve()),
        size_bytes=path.stat().st_size,
        duration_seconds=duration,
        container=fmt.get("format_name") or "unknown",
        video_codec=video.get("codec_name") or "unknown",
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        pixel_format=pixel_format,
        bit_depth=bit_depth,
        color_primaries=video.get("color_primaries") or "unknown",
        color_transfer=transfer,
        color_space=video.get("color_space") or "unknown",
        color_range=video.get("color_range") or "unknown",
        hdr=hdr,
        dolby_vision=dolby_vision,
        audio_codecs=audio,
        subtitle_codecs=subtitles,
    )


def choose_target_codec(requested: str) -> str:
    # HEVC is the safer universal recommendation; AV1 remains opt-in.
    return "hevc" if requested == "auto" else requested


def ffmpeg_encoder_names(ffmpeg: str = "ffmpeg") -> set[str]:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "could not list FFmpeg encoders")
    names: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] == "V":
            names.add(parts[1])
    return names


def gpu_vendors() -> list[str]:
    """Detect display-adapter vendors without initializing an encoder."""
    commands: list[list[str]] = []
    if platform.system() == "Windows":
        commands.append([
            "powershell", "-NoProfile", "-NonInteractive", "-Command",
            "(Get-CimInstance Win32_VideoController).Name",
        ])
    elif platform.system() == "Linux" and shutil.which("lspci"):
        commands.append(["lspci"])
    elif platform.system() == "Darwin":
        commands.append(["system_profiler", "SPDisplaysDataType"])

    text = ""
    for command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=10,
            )
            text += "\n" + result.stdout.lower()
        except (OSError, subprocess.TimeoutExpired):
            continue

    detected: list[str] = []
    if any(name in text for name in ("nvidia", "geforce", "quadro")):
        detected.append("nvidia")
    if any(name in text for name in ("amd", "radeon", "advanced micro devices")):
        detected.append("amd")
    if any(name in text for name in ("intel", "arc", "iris", "uhd graphics")):
        detected.append("intel")
    return detected


def select_encoder(
    codec: str,
    requested_hardware: str,
    available_encoders: set[str],
    detected_vendors: list[str],
) -> EncoderSelection:
    software = SOFTWARE_ENCODERS[codec]
    if requested_hardware == "cpu":
        if software not in available_encoders:
            raise HardwareRequirementError(
                "ffmpeg",
                f"FFmpeg does not provide the required CPU encoder {software}.",
                DOWNLOAD_URLS["ffmpeg"],
            )
        return EncoderSelection("cpu", software)

    candidates = detected_vendors if requested_hardware == "auto" else [requested_hardware]
    if requested_hardware != "auto" and requested_hardware not in detected_vendors:
        raise HardwareRequirementError(
            requested_hardware,
            f"No {VENDOR_LABELS[requested_hardware]} GPU was detected. Install its official driver or choose CPU.",
            DOWNLOAD_URLS[requested_hardware],
        )

    for vendor in candidates:
        encoder = HARDWARE_ENCODERS[vendor][codec]
        if encoder in available_encoders:
            return EncoderSelection(vendor, encoder)

    if candidates:
        vendor_names = ", ".join(VENDOR_LABELS[vendor] for vendor in candidates)
        expected = ", ".join(HARDWARE_ENCODERS[vendor][codec] for vendor in candidates)
        raise HardwareRequirementError(
            "ffmpeg",
            f"Detected {vendor_names}, but FFmpeg is missing the required hardware encoder ({expected}).",
            DOWNLOAD_URLS["ffmpeg"],
        )

    if software not in available_encoders:
        raise HardwareRequirementError(
            "ffmpeg",
            f"No supported GPU was detected and FFmpeg is missing {software} for CPU fallback.",
            DOWNLOAD_URLS["ffmpeg"],
        )
    return EncoderSelection("cpu", software)


def emit_action(marker: str, payload: dict[str, Any]) -> None:
    print(f"{marker}={json.dumps(payload, separators=(',', ':'))}", flush=True)


def offer_requirement(error: HardwareRequirementError, allow_cpu: bool) -> bool:
    payload = {
        "component": error.component,
        "message": str(error),
        "download_url": error.download_url,
        "cpu_available": allow_cpu,
    }
    emit_action("MUXMENDER_REQUIREMENT", payload)
    print(f"Requirement: {error}")
    print(f"Official download: {error.download_url}")
    if not sys.stdin.isatty():
        return False
    choices = "[D]ownload/install page, [C]PU fallback, [Q]uit" if allow_cpu else "[D]ownload/install page, [Q]uit"
    answer = input(f"{choices}: ").strip().lower()
    if answer == "d":
        webbrowser.open(error.download_url)
        return False
    return allow_cpu and answer == "c"


def offer_cpu_fallback(selection: EncoderSelection, message: str) -> bool:
    payload = {
        "vendor": selection.vendor,
        "encoder": selection.encoder,
        "message": message,
        "download_url": DOWNLOAD_URLS[selection.vendor],
    }
    emit_action("MUXMENDER_HARDWARE_FAILURE", payload)
    if not sys.stdin.isatty():
        return False
    answer = input(
        f"{selection.label} failed. Retry this file using CPU? [Y/n/d=driver page]: "
    ).strip().lower()
    if answer == "d":
        webbrowser.open(DOWNLOAD_URLS[selection.vendor])
        return False
    return answer in {"", "y", "yes"}


def output_dimensions(info: MediaInfo, resolution: str = "keep") -> tuple[int, int]:
    """Return aspect-preserving even dimensions, never larger than the source."""
    if resolution == "keep" or not info.width or not info.height:
        return info.width, info.height
    max_width, max_height = RESOLUTION_LIMITS[resolution]
    scale = min(max_width / info.width, max_height / info.height, 1.0)
    if scale >= 1.0:
        return info.width, info.height
    width = max(2, int(info.width * scale) // 2 * 2)
    height = max(2, int(info.height * scale) // 2 * 2)
    return width, height


def recommend(info: MediaInfo, target_codec: str, resolution: str = "keep") -> MediaInfo:
    target_width, target_height = output_dimensions(info, resolution)
    resizing = (target_width, target_height) != (info.width, info.height)
    if info.dolby_vision:
        info.recommendation = "skip"
        info.reason = "Dolby Vision conversion may discard dynamic metadata; manual review required"
    elif resizing:
        info.recommendation = "transcode"
        info.reason = (
            f"user requested {resolution}: downscale {info.width}x{info.height} to "
            f"{target_width}x{target_height}; encode video as {target_codec}; copy all audio streams"
        )
    elif info.video_codec == target_codec:
        info.recommendation = "keep" if "matroska" in info.container else "remux"
        info.reason = (
            f"video is already {target_codec}; another lossy encode is unlikely to help"
            if info.recommendation == "keep"
            else f"video is already {target_codec}; copy streams into the unified MKV container"
        )
    elif info.video_codec in {"av1", "hevc"} and target_codec == "hevc":
        info.recommendation = "keep" if "matroska" in info.container else "remux"
        info.reason = (
            f"video already uses efficient codec {info.video_codec}"
            if info.recommendation == "keep"
            else f"keep efficient {info.video_codec} video and copy streams into MKV"
        )
    else:
        info.recommendation = "transcode"
        info.reason = f"encode {info.video_codec} video as {target_codec}; copy all audio streams"
    return info


def output_path(source: Path, root: Path, output_dir: Path | None) -> Path:
    if output_dir:
        relative = source.relative_to(root)
        candidate = output_dir / relative
        return candidate.with_name(f"{candidate.name}.muxmender.mkv")
    return source.with_name(f"{source.name}.muxmender.mkv")


def encoder_options(
    codec: str,
    quality: str,
    info: MediaInfo,
    encoder: str | None = None,
) -> list[str]:
    encoder = encoder or SOFTWARE_ENCODERS[codec]
    ten_bit = info.bit_depth > 8 or info.hdr

    if encoder == "libx265":
        crf = {"transparent": "18", "balanced": "21", "compact": "24"}[quality]
        options = ["-c:v", "libx265", "-preset", "slow", "-crf", crf]
        if ten_bit:
            options += ["-pix_fmt", "yuv420p10le", "-profile:v", "main10"]
    elif encoder == "libsvtav1":
        crf = {"transparent": "24", "balanced": "28", "compact": "32"}[quality]
        options = ["-c:v", "libsvtav1", "-preset", "6", "-crf", crf]
        if ten_bit:
            options += ["-pix_fmt", "yuv420p10le"]
    elif encoder.endswith("_nvenc"):
        cq = {"transparent": "18", "balanced": "21", "compact": "25"}[quality]
        preset = {"transparent": "p7", "balanced": "p6", "compact": "p5"}[quality]
        options = [
            "-c:v", encoder, "-preset", preset, "-tune", "hq",
            "-rc", "vbr", "-cq", cq, "-b:v", "0",
        ]
        if ten_bit:
            options += ["-pix_fmt", "p010le"]
    elif encoder.endswith("_amf"):
        qp_i = {"transparent": "18", "balanced": "21", "compact": "24"}[quality]
        qp_p = {"transparent": "20", "balanced": "23", "compact": "26"}[quality]
        preset = {"transparent": "quality", "balanced": "balanced", "compact": "speed"}[quality]
        options = [
            "-c:v", encoder, "-usage", "transcoding", "-quality", preset,
            "-rc", "cqp", "-qp_i", qp_i, "-qp_p", qp_p,
        ]
        if ten_bit:
            options += ["-pix_fmt", "p010le"]
    elif encoder.endswith("_qsv"):
        quality_value = {"transparent": "18", "balanced": "21", "compact": "25"}[quality]
        preset = {"transparent": "veryslow", "balanced": "slower", "compact": "medium"}[quality]
        options = ["-c:v", encoder, "-preset", preset, "-global_quality", quality_value]
        if ten_bit:
            options += ["-pix_fmt", "p010le"]
    else:
        raise ValueError(f"unsupported encoder: {encoder}")

    color_flags = {
        "-color_primaries": info.color_primaries,
        "-color_trc": info.color_transfer,
        "-colorspace": info.color_space,
        "-color_range": info.color_range,
    }
    for flag, value in color_flags.items():
        if value != "unknown":
            options += [flag, value]
    return options


def build_ffmpeg_command(
    source: Path,
    temporary: Path,
    info: MediaInfo,
    codec: str,
    quality: str,
    ffmpeg: str = "ffmpeg",
    encoder: str | None = None,
    resolution: str = "keep",
) -> list[str]:
    target_width, target_height = output_dimensions(info, resolution)
    scale_options = (
        ["-vf", f"scale={target_width}:{target_height}:flags=lanczos"]
        if (target_width, target_height) != (info.width, info.height)
        else []
    )
    video_options = (
        ["-c", "copy"]
        if info.recommendation == "remux"
        else [
            *scale_options,
            *encoder_options(codec, quality, info, encoder),
            "-c:a", "copy", "-c:s", "copy", "-c:d", "copy", "-c:t", "copy",
        ]
    )
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y", "-i", str(source),
        "-map", "0", "-map_metadata", "0", "-map_chapters", "0",
        *video_options,
        "-max_muxing_queue_size", "4096", str(temporary),
    ]


def command_text(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def progress_percent(line: str, duration_seconds: float) -> float | None:
    if duration_seconds <= 0 or "=" not in line:
        return None
    key, value = line.strip().split("=", 1)
    if key not in {"out_time_us", "out_time_ms"}:
        return None
    try:
        elapsed_seconds = int(value) / 1_000_000
    except ValueError:
        return None
    return min(100.0, max(0.0, elapsed_seconds * 100.0 / duration_seconds))


def stop_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def run_ffmpeg(
    command: list[str],
    duration_seconds: float,
    stall_timeout: float = 0,
) -> tuple[int, bool]:
    progress_command = [*command[:-1], "-progress", "pipe:1", "-nostats", command[-1]]
    process = subprocess.Popen(
        progress_command,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    last_reported = -1
    last_progress_at = time.monotonic()
    lines: queue.Queue[str | None] = queue.Queue()
    assert process.stdout is not None

    def read_progress() -> None:
        for output_line in process.stdout:
            lines.put(output_line)
        lines.put(None)

    threading.Thread(target=read_progress, daemon=True).start()
    stalled = False
    while True:
        try:
            line = lines.get(timeout=0.5)
        except queue.Empty:
            if (
                stall_timeout > 0
                and process.poll() is None
                and time.monotonic() - last_progress_at >= stall_timeout
            ):
                stalled = True
                print(
                    f"Hardware encoder made no progress for {stall_timeout:.0f} seconds; stopping it.",
                    file=sys.stderr,
                    flush=True,
                )
                stop_process_tree(process)
                break
            continue
        if line is None:
            break
        percent = progress_percent(line, duration_seconds)
        if percent is not None:
            if percent > max(0, last_reported):
                last_progress_at = time.monotonic()
            if int(percent) > last_reported:
                last_reported = int(percent)
                print(f"MUXMENDER_PROGRESS={percent:.1f}", flush=True)
    return_code = process.wait()
    if return_code == 0 and last_reported < 100:
        print("MUXMENDER_PROGRESS=100.0", flush=True)
    return return_code, stalled


def verify_output(
    source_info: MediaInfo,
    output: Path,
    ffprobe: str,
    min_savings: float,
    expected_video_codec: str,
    enforce_min_savings: bool = True,
    expected_dimensions: tuple[int, int] | None = None,
) -> tuple[bool, str]:
    result = probe(output, ffprobe)
    if result.video_codec != expected_video_codec:
        return False, f"expected {expected_video_codec} video but found {result.video_codec}"
    expected_dimensions = expected_dimensions or (source_info.width, source_info.height)
    if (result.width, result.height) != expected_dimensions:
        return False, (
            f"resolution is {result.width}x{result.height}; expected "
            f"{expected_dimensions[0]}x{expected_dimensions[1]}"
        )
    if source_info.duration_seconds and abs(result.duration_seconds - source_info.duration_seconds) > 2.0:
        return False, "duration differs by more than two seconds"
    if len(result.audio_codecs) != len(source_info.audio_codecs):
        return False, "audio stream count changed"
    if result.audio_codecs != source_info.audio_codecs:
        return False, "one or more audio codecs changed"
    if result.subtitle_codecs != source_info.subtitle_codecs:
        return False, "subtitle streams changed"
    if source_info.hdr and not result.hdr:
        return False, "HDR signaling was lost"
    for label, before, after in (
        ("color primaries", source_info.color_primaries, result.color_primaries),
        ("color transfer", source_info.color_transfer, result.color_transfer),
        ("color space", source_info.color_space, result.color_space),
    ):
        if before != "unknown" and before != after:
            return False, f"{label} changed from {before} to {after}"
    saved = 100.0 * (source_info.size_bytes - result.size_bytes) / source_info.size_bytes
    if enforce_min_savings and saved < min_savings:
        return False, f"only saved {saved:.1f}% (minimum is {min_savings:.1f}%)"
    if not enforce_min_savings:
        return True, f"verified lossless remux (size change: {saved:+.1f}%)"
    return True, f"saved {saved:.1f}% ({human_size(source_info.size_bytes - result.size_bytes)})"


def delete_original_allowed(args: argparse.Namespace) -> bool:
    if not args.delete_originals:
        return False
    if args.confirm_delete != "DELETE_ORIGINALS":
        raise ValueError("--delete-originals requires --confirm-delete DELETE_ORIGINALS")
    return True


def print_info(info: MediaInfo) -> None:
    hdr = " HDR" if info.hdr else ""
    print(f"\n{info.path}")
    print(
        f"  {human_size(info.size_bytes)} | {info.width}x{info.height} | "
        f"{info.video_codec} {info.bit_depth}-bit{hdr} | audio: {', '.join(info.audio_codecs) or 'none'}"
    )
    print(f"  {info.recommendation.upper()}: {info.reason}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recursively analyze and safely optimize media for direct playback.",
        epilog="Dry-run is the default. Use --execute to create optimized sidecar files.",
    )
    parser.add_argument("folder", type=Path, help="media file or library folder")
    parser.add_argument("--codec", choices=("auto", "hevc", "av1"), default="auto")
    parser.add_argument(
        "--resolution",
        choices=("keep", "2160p", "1080p", "720p", "480p"),
        default="keep",
        help="keep source resolution by default, or explicitly set a downscale ceiling; never upscales",
    )
    parser.add_argument(
        "--hardware",
        choices=("auto", "amd", "nvidia", "intel", "cpu"),
        default="auto",
        help="prefer a detected GPU by default; choose cpu to disable hardware encoding",
    )
    parser.add_argument(
        "--hardware-fallback",
        choices=("ask", "cpu", "never"),
        default="ask",
        help="what to do when a hardware encoder fails (default: ask)",
    )
    parser.add_argument(
        "--hardware-stall-timeout",
        type=float,
        default=20.0,
        metavar="SECONDS",
        help="stop a hardware encoder that makes no progress (default: 20)",
    )
    parser.add_argument("--quality", choices=("transparent", "balanced", "compact"), default="balanced")
    parser.add_argument("--execute", action="store_true", help="run ffmpeg; otherwise only show the plan")
    parser.add_argument("--dry-run", action="store_true", help="explicitly request the default dry-run behavior")
    parser.add_argument("--output-dir", type=Path, help="mirror optimized files under this directory")
    parser.add_argument("--report", type=Path, help="write the analysis report as JSON")
    parser.add_argument("--min-savings", type=float, default=5.0, metavar="PERCENT")
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--delete-originals", action="store_true", help="delete originals only after verification")
    parser.add_argument("--confirm-delete", default="", help=argparse.SUPPRESS)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target = args.folder.resolve()
    if not target.exists():
        print(f"error: path does not exist: {target}", file=sys.stderr)
        return 2
    if target.is_file() and target.suffix.lower() not in MEDIA_EXTENSIONS:
        print(f"error: unsupported media file: {target}", file=sys.stderr)
        return 2
    root = target.parent if target.is_file() else target
    if args.execute and args.dry_run:
        print("error: --execute and --dry-run cannot be used together", file=sys.stderr)
        return 2
    if args.min_savings < 0 or args.min_savings >= 100:
        print("error: --min-savings must be between 0 and 100", file=sys.stderr)
        return 2
    if args.hardware_stall_timeout < 5:
        print("error: --hardware-stall-timeout must be at least 5 seconds", file=sys.stderr)
        return 2
    try:
        may_delete = delete_original_allowed(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for tool in (args.ffprobe, args.ffmpeg):
        if shutil.which(tool) is None:
            error = HardwareRequirementError(
                "ffmpeg",
                f"Required executable was not found: {tool}.",
                DOWNLOAD_URLS["ffmpeg"],
            )
            offer_requirement(error, allow_cpu=False)
            return 3

    target_codec = choose_target_codec(args.codec)
    try:
        available_encoders = ffmpeg_encoder_names(args.ffmpeg)
        detected_vendors = gpu_vendors()
        selection = select_encoder(
            target_codec, args.hardware, available_encoders, detected_vendors
        )
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        if isinstance(exc, HardwareRequirementError):
            error = exc
        else:
            error = HardwareRequirementError(
                "ffmpeg",
                f"Could not inspect FFmpeg hardware support: {exc}",
                DOWNLOAD_URLS["ffmpeg"],
            )
        cpu_available = SOFTWARE_ENCODERS[target_codec] in locals().get("available_encoders", set())
        if offer_requirement(error, allow_cpu=cpu_available):
            selection = EncoderSelection("cpu", SOFTWARE_ENCODERS[target_codec])
        else:
            return 3

    found = [target] if target.is_file() else list(media_files(root))
    print(f"MuxMender {'EXECUTE' if args.execute else 'DRY RUN'}")
    print(f"Found {len(found)} media file(s); target: {target_codec}/MKV, quality: {args.quality}")
    print(f"Resolution policy: {args.resolution} (upscaling disabled)")
    detected_text = ", ".join(VENDOR_LABELS[vendor] for vendor in detected_vendors) or "none"
    print(f"Detected GPU vendor(s): {detected_text}")
    print(f"Selected encoder: {selection.label}")
    report: dict[str, Any] = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(target),
        "mode": "execute" if args.execute else "dry-run",
        "target_codec": target_codec,
        "quality": args.quality,
        "resolution": args.resolution,
        "requested_hardware": args.hardware,
        "detected_gpu_vendors": detected_vendors,
        "selected_encoder": asdict(selection),
        "files": [],
        "errors": [],
    }

    for source in found:
        try:
            info = recommend(probe(source, args.ffprobe), target_codec, args.resolution)
            print_info(info)
            entry: dict[str, Any] = asdict(info)
            entry["status"] = info.recommendation
            if info.recommendation not in {"transcode", "remux"}:
                report["files"].append(entry)
                continue

            destination = output_path(source, root, args.output_dir.resolve() if args.output_dir else None)
            temporary = destination.with_name(f".{destination.stem}.partial.mkv")
            command = build_ffmpeg_command(
                source, temporary, info, target_codec, args.quality, args.ffmpeg,
                selection.encoder, args.resolution,
            )
            entry["output"] = str(destination)
            entry["command"] = command
            entry["encoder"] = asdict(selection)
            print(f"  OUTPUT: {destination}")
            if not args.execute:
                print(f"  COMMAND: {command_text(command)}")
                entry["status"] = "planned"
                report["files"].append(entry)
                continue
            if destination.exists() and not args.overwrite_output:
                print("  SKIPPED: output exists (use --overwrite-output to replace it)")
                entry["status"] = "output-exists"
                report["files"].append(entry)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary.unlink(missing_ok=True)
            return_code, stalled = run_ffmpeg(
                command,
                info.duration_seconds,
                args.hardware_stall_timeout if selection.hardware else 0,
            )
            if return_code and selection.hardware:
                temporary.unlink(missing_ok=True)
                failure = (
                    f"{selection.label} stalled"
                    if stalled
                    else f"{selection.label} exited with status {return_code}"
                )
                retry_cpu = args.hardware_fallback == "cpu"
                if args.hardware_fallback == "ask":
                    retry_cpu = offer_cpu_fallback(selection, failure)
                else:
                    emit_action("MUXMENDER_HARDWARE_FAILURE", {
                        "vendor": selection.vendor,
                        "encoder": selection.encoder,
                        "message": failure,
                        "download_url": DOWNLOAD_URLS[selection.vendor],
                    })
                if retry_cpu:
                    software_encoder = SOFTWARE_ENCODERS[target_codec]
                    if software_encoder not in available_encoders:
                        raise RuntimeError(
                            f"CPU fallback is unavailable because FFmpeg lacks {software_encoder}"
                        )
                    selection = EncoderSelection("cpu", software_encoder)
                    print(f"  RETRYING WITH CPU: {selection.encoder}")
                    command = build_ffmpeg_command(
                        source, temporary, info, target_codec, args.quality,
                        args.ffmpeg, selection.encoder, args.resolution,
                    )
                    entry["hardware_command"] = entry["command"]
                    entry["command"] = command
                    entry["encoder"] = asdict(selection)
                    return_code, stalled = run_ffmpeg(command, info.duration_seconds)
            if return_code:
                temporary.unlink(missing_ok=True)
                raise RuntimeError(f"ffmpeg exited with status {return_code}")
            expected_codec = target_codec if info.recommendation == "transcode" else info.video_codec
            valid, message = verify_output(
                info,
                temporary,
                args.ffprobe,
                args.min_savings,
                expected_codec,
                enforce_min_savings=info.recommendation == "transcode",
                expected_dimensions=output_dimensions(info, args.resolution),
            )
            if not valid:
                temporary.unlink(missing_ok=True)
                print(f"  REJECTED: {message}; original retained")
                entry["status"] = "rejected"
                entry["result"] = message
                report["files"].append(entry)
                continue
            if destination.exists():
                destination.unlink()
            os.replace(temporary, destination)
            print(f"  COMPLETE: {message}")
            entry["status"] = "complete"
            entry["result"] = message
            if may_delete:
                source.unlink()
                print("  ORIGINAL DELETED: explicitly requested and output verified")
                entry["original_deleted"] = True
            report["files"].append(entry)
        except (OSError, RuntimeError, json.JSONDecodeError) as exc:
            print(f"\n{source}\n  ERROR: {exc}", file=sys.stderr)
            report["errors"].append({"path": str(source), "error": str(exc)})

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport written to {args.report.resolve()}")
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
