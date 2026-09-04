#!/usr/bin/env python3
"""MuxMender: safely analyze and optimize media libraries."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


MEDIA_EXTENSIONS = {
    ".3gp", ".avi", ".flv", ".m2ts", ".m4v", ".mkv", ".mov",
    ".mp4", ".mpeg", ".mpg", ".mts", ".ts", ".webm", ".wmv",
}
TARGET_VIDEO_CODECS = {"hevc": "libx265", "av1": "libsvtav1"}
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


def recommend(info: MediaInfo, target_codec: str) -> MediaInfo:
    if info.dolby_vision:
        info.recommendation = "skip"
        info.reason = "Dolby Vision conversion may discard dynamic metadata; manual review required"
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


def encoder_options(codec: str, quality: str, info: MediaInfo) -> list[str]:
    if codec == "hevc":
        crf = {"transparent": "18", "balanced": "21", "compact": "24"}[quality]
        options = ["-c:v", "libx265", "-preset", "slow", "-crf", crf]
        if info.bit_depth > 8 or info.hdr:
            options += ["-pix_fmt", "yuv420p10le", "-profile:v", "main10"]
    else:
        crf = {"transparent": "24", "balanced": "28", "compact": "32"}[quality]
        options = ["-c:v", "libsvtav1", "-preset", "6", "-crf", crf]
        if info.bit_depth > 8 or info.hdr:
            options += ["-pix_fmt", "yuv420p10le"]

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
) -> list[str]:
    video_options = (
        ["-c", "copy"]
        if info.recommendation == "remux"
        else [
            *encoder_options(codec, quality, info),
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


def verify_output(
    source_info: MediaInfo,
    output: Path,
    ffprobe: str,
    min_savings: float,
    expected_video_codec: str,
    enforce_min_savings: bool = True,
) -> tuple[bool, str]:
    result = probe(output, ffprobe)
    if result.video_codec != expected_video_codec:
        return False, f"expected {expected_video_codec} video but found {result.video_codec}"
    if (result.width, result.height) != (source_info.width, source_info.height):
        return False, "resolution changed"
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
    parser.add_argument("folder", type=Path, help="media library folder")
    parser.add_argument("--codec", choices=("auto", "hevc", "av1"), default="auto")
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
    root = args.folder.resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2
    if args.execute and args.dry_run:
        print("error: --execute and --dry-run cannot be used together", file=sys.stderr)
        return 2
    if args.min_savings < 0 or args.min_savings >= 100:
        print("error: --min-savings must be between 0 and 100", file=sys.stderr)
        return 2
    try:
        may_delete = delete_original_allowed(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for tool in (args.ffprobe, args.ffmpeg) if args.execute else (args.ffprobe,):
        if shutil.which(tool) is None:
            print(f"error: required executable not found: {tool}", file=sys.stderr)
            return 2

    target_codec = choose_target_codec(args.codec)
    found = list(media_files(root))
    print(f"MuxMender {'EXECUTE' if args.execute else 'DRY RUN'}")
    print(f"Found {len(found)} media file(s); target: {target_codec}/MKV, quality: {args.quality}")
    report: dict[str, Any] = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "root": str(root),
        "mode": "execute" if args.execute else "dry-run",
        "target_codec": target_codec,
        "quality": args.quality,
        "files": [],
        "errors": [],
    }

    for source in found:
        try:
            info = recommend(probe(source, args.ffprobe), target_codec)
            print_info(info)
            entry: dict[str, Any] = asdict(info)
            destination = output_path(source, root, args.output_dir.resolve() if args.output_dir else None)
            temporary = destination.with_name(f".{destination.stem}.partial.mkv")
            command = build_ffmpeg_command(source, temporary, info, target_codec, args.quality, args.ffmpeg)
            entry["output"] = str(destination)
            entry["command"] = command
            entry["status"] = info.recommendation

            if info.recommendation not in {"transcode", "remux"}:
                report["files"].append(entry)
                continue
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
            result = subprocess.run(command, check=False)
            if result.returncode:
                temporary.unlink(missing_ok=True)
                raise RuntimeError(f"ffmpeg exited with status {result.returncode}")
            expected_codec = target_codec if info.recommendation == "transcode" else info.video_codec
            valid, message = verify_output(
                info,
                temporary,
                args.ffprobe,
                args.min_savings,
                expected_codec,
                enforce_min_savings=info.recommendation == "transcode",
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
