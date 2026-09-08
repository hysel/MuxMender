#!/usr/bin/env python3
"""MuxMender: safely analyze and optimize media libraries."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
import uuid
from runtime_support import TerminalProgress
from mux_integrity import INTERLEAVE_MICROSECONDS, verify_startup_interleaving
import mux_integrity as nvidia_mux
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
    "dovibaker": "https://github.com/erazortt/DoViBaker",
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
    dolby_vision_profile: int | None = None
    dolby_vision_compatibility_id: int | None = None
    dolby_vision_rpu_present: bool = False
    dolby_vision_el_present: bool = False
    mastering_display_metadata: bool = False
    content_light_metadata: bool = False
    recommendation: str = ""
    reason: str = ""
    dolby_preservation: dict[str, Any] | None = None


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
            and '.muxmender-work' not in (part.lower() for part in path.parts)
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
        timeout=60,
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

    dovi_data = next(
        (
            item for item in side_data
            if "dovi" in str(item.get("side_data_type", "")).lower()
            or "dolby vision" in str(item.get("side_data_type", "")).lower()
        ),
        {},
    )

    def optional_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    dovi_profile = optional_int(dovi_data.get("dv_profile"))
    dovi_compatibility = optional_int(dovi_data.get("dv_bl_signal_compatibility_id"))
    dovi_rpu_present = optional_int(dovi_data.get("rpu_present_flag")) == 1
    dovi_el_present = optional_int(dovi_data.get("el_present_flag")) == 1
    mastering_display = "mastering display" in side_text
    content_light = "content light" in side_text

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
        dolby_vision_profile=dovi_profile,
        dolby_vision_compatibility_id=dovi_compatibility,
        dolby_vision_rpu_present=dovi_rpu_present,
        dolby_vision_el_present=dovi_el_present,
        mastering_display_metadata=mastering_display,
        content_light_metadata=content_light,
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


def ffmpeg_filter_names(ffmpeg: str = "ffmpeg") -> set[str]:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-filters"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "could not list FFmpeg filters")
    names: set[str] = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 2:
            names.add(parts[1])
    return names


def dolby_vision_gpu_preflight(
    ffmpeg: str = "ffmpeg",
    timeout: float = 15.0,
) -> tuple[bool, str]:
    """Exercise one tiny generated Vulkan frame before opening source media."""
    try:
        if "libplacebo" not in ffmpeg_filter_names(ffmpeg):
            return False, "FFmpeg does not include the libplacebo filter"
        command = [
            ffmpeg, "-hide_banner", "-v", "error",
            "-init_hw_device", "vulkan=vk:0", "-filter_hw_device", "vk",
            "-f", "lavfi", "-i", "color=size=64x64:rate=1:duration=1",
            "-vf",
            (
                "format=yuv420p10le,hwupload,"
                "libplacebo=colorspace=bt709:color_primaries=bt709:"
                "color_trc=bt709:range=tv,hwdownload,format=yuv420p10le"
            ),
            "-frames:v", "1", "-f", "null", os.devnull,
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"Dolby Vision GPU preflight timed out after {timeout:.0f} seconds"
    except OSError as exc:
        return False, f"Dolby Vision GPU preflight could not start: {exc}"
    if result.returncode:
        details = result.stderr.strip().splitlines()
        actionable = next(
            (
                line.strip() for line in details
                if "VK_ERROR" in line
                or "vulkan_pool_alloc" in line
                or "Failed to allocate frame" in line
            ),
            details[-1].strip() if details else f"FFmpeg exited with status {result.returncode}",
        )
        return False, actionable
    return True, "libplacebo Vulkan frame upload and download succeeded"


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
        f"{selection.label} failed. Retry this file using CPU? [y/N/d=driver page]: "
    ).strip().lower()
    if answer == "d":
        webbrowser.open(DOWNLOAD_URLS[selection.vendor])
        return False
    return answer in {"y", "yes"}


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


def assess_dolby_preservation(info: MediaInfo) -> dict[str, Any] | None:
    """Conservative planning only: metadata signaling is not content validation."""
    if not info.dolby_vision:
        return None
    route = "inspect-unsupported-profile"
    reason = "Unknown or unsupported Dolby Vision configuration; preserve the original bitstream."
    if not info.dolby_vision_rpu_present:
        route = "inspect-missing-rpu"
        reason = "Dolby Vision signaling has no confirmed RPU; inspect before any conversion."
    elif info.dolby_vision_el_present or info.dolby_vision_profile == 7:
        route = "preserve-enhancement-layer"
        reason = "Enhancement-layer preservation requires a separate validated path; do not discard it."
    elif info.dolby_vision_profile == 5:
        route = "profile5-color-pipeline-required"
        reason = "Profile 5 requires its own color-aware preservation path; do not inject its original RPU into the converted PQ output."
    elif (
        info.dolby_vision_profile == 8
        and info.dolby_vision_compatibility_id == 1
        and info.video_codec == "hevc"
        and info.bit_depth == 10
        and info.color_transfer == "smpte2084"
        and info.color_primaries == "bt2020"
    ):
        route = "profile8.1-research-candidate"
        reason = "Candidate for opt-in --preserve-dolby-vision with AMD/Intel HEVC; full RPU, frame, track, decode and savings checks are required."
    return {
        "route": route,
        "reason": reason,
        "reencode_supported": False,
        "safe_current_action": "keep original or copy video bitstream unchanged",
        "requires": ["exact resolution and frame timeline", "RPU content and frame alignment verification",
                     "profile and layer verification", "audio/subtitle/chapters preservation",
                     "Dolby Vision playback and visual comparison"],
    }


def recommend(
    info: MediaInfo,
    target_codec: str,
    resolution: str = "keep",
    dolby_vision_policy: str = "skip",
    reencode_efficient: bool = False,
) -> MediaInfo:
    info.dolby_preservation = assess_dolby_preservation(info)
    target_width, target_height = output_dimensions(info, resolution)
    resizing = (target_width, target_height) != (info.width, info.height)
    if info.dolby_vision and dolby_vision_policy == "sdr-preview" and not resizing:
        info.recommendation = "preview"
        info.reason = (
            "create a short BT.709 SDR sidecar after a synthetic Dolby-aware GPU preflight"
        )
    elif info.dolby_vision and dolby_vision_policy == "copy" and not resizing:
        info.recommendation = "keep" if "matroska" in info.container else "remux"
        info.reason = (
            "Dolby Vision video is already in MKV; preserve it unchanged"
            if info.recommendation == "keep"
            else "copy the Dolby Vision bitstream and every other stream without video encoding"
        )
    elif info.dolby_vision:
        info.recommendation = "skip"
        if resizing:
            info.reason = (
                "Dolby Vision cannot be resized in copy-only mode; choose a separately "
                "validated HDR10 or SDR conversion workflow"
            )
        else:
            profile = (
                f" Profile {info.dolby_vision_profile}"
                if info.dolby_vision_profile is not None else ""
            )
            info.reason = (
                f"Dolby Vision{profile} blocked by the color-safety gate; "
                "use --dolby-vision-policy copy only to preserve the video bitstream unchanged"
            )
    elif resizing:
        info.recommendation = "transcode"
        info.reason = (
            f"user requested {resolution}: downscale {info.width}x{info.height} to "
            f"{target_width}x{target_height}; encode video as {target_codec}; copy all audio streams"
        )
    elif reencode_efficient and info.video_codec in {'hevc', 'av1'}:
        info.recommendation = 'transcode'
        info.reason = 'Explicit efficient-codec re-encode; normal savings and preservation checks apply'
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


def clean_media_name(source: Path) -> str:
    """Remove release suffixes without guessing titles from an online service."""
    name = re.sub(r'[._]+', ' ', source.stem).strip()
    # A release boundary requires a distinct token, not a substring of a title.
    boundary = re.search(r'(?i)(?:^|[\s\[(-])(?:480[pi]|576[pi]|720p|1080[pi]|2160p|4320p|'
                         r'WEB[ -]?DL|WEBRip|Blu[ -]?Ray|BDRip|HDTV|REMUX|'
                         r'x26[45]|H[ .]?26[45]|HEVC|AV1|AMZN|DDP)(?=$|[\s\].)-])', name)
    if boundary:
        name = name[:boundary.start()].strip(' -([.')
    episode = re.search(r'(?i)\bS\d{1,3}E\d{1,3}(?:E\d{1,3})*\b', name)
    if episode:
        title = name[:episode.start()].strip(' -')
        suffix = name[episode.end():].strip(' -')
        name = title + ' - ' + episode.group().upper() + (' - ' + suffix if suffix else '')
    else:
        year = re.search(r'\(((?:19|20)\d{2})\)$', name)
        if not year:
            year = re.search(r'(?<!\d)((?:19|20)\d{2})$', name)
            if year and int(year.group(1)) > time.localtime().tm_year + 1:
                year = None
        if year and name[:year.start()].strip(' ('):
            name = name[:year.start()].strip(' (') + ' (' + year.group(1) + ')'
    name = re.sub(r'[<>:"/\\|?*]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip(' .-')
    if not name or name.upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(n) for n in range(1,10)), *('LPT'+str(n) for n in range(1,10))}:
        raise RuntimeError('Cannot determine a safe media title; clean up the input name first')
    return name + '.mkv'


def output_path(source: Path, root: Path, output_dir: Path | None) -> Path:
    if output_dir:
        relative = source.relative_to(root)
        candidate = output_dir / relative
        return candidate.with_suffix('.mkv')
    return source.parent / 'MuxMender' / source.with_suffix('.mkv').name


def rename_identity(path):
    value = path.stat()
    return dict(size=value.st_size, mtime_ns=value.st_mtime_ns,
                device=value.st_dev, inode=value.st_ino)


def check_rename_path(path):
    """Do not follow links/junctions while planning or applying renames."""
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError(f'Rename does not follow links or junctions: {part}')


def rename_release_suffix(source, title):
    """Keep the original release tail verbatim; retain uncertain abbreviations whole."""
    stem = source.stem
    if stem.startswith(title + ' - '):
        return stem[len(title) + 3:]
    prefix = re.match(r'(?i)^([a-z0-9]{2,9})-', stem)
    if prefix and not re.match(re.escape(prefix.group(1)) + r'(?:\b|_)', title, re.I):
        return stem
    match = re.search(r'(?i)(?<![a-z0-9])(?:480[pi]?|576[pi]?|720p?|1080[pi]?|2160p?|4320p?|'
                      r'REPACK|PROPER|WEB[ .-]?DL|WEBRip|Blu[ .-]?Ray|BDRip|HDTV|REMUX|'
                      r'x26[45]|H[ .]?26[45]|HEVC|AV1|AMZN|DDP)(?![a-z0-9])', stem)
    year = re.search(r'(?<!\d)(?:19|20)\d{2}(?!\d)\)?', stem)
    if year and (not match or year.end() <= match.start()) and re.search(r'\((?:19|20)\d{2}\)$', title):
        return stem[year.end():].lstrip(' ._-')
    if match:
        return stem[match.start():]
    # Keep an unclassified suffix after an explicit year instead of discarding it.
    return stem[year.end():].lstrip(' ._-') if year else ''


def create_rename_plan(target, title=None, sidecars=False):
    target = Path(os.path.abspath(target))
    check_rename_path(target)
    if not target.exists():
        raise ValueError('Rename target does not exist')
    if title and not target.is_file():
        raise ValueError('--rename-title requires a single video file')
    root = target.parent if target.is_file() else target
    files = []
    if target.is_file():
        files = [target]
    else:
        for directory, folders, names in os.walk(root, followlinks=False):
            folders[:] = [n for n in folders if not (Path(directory)/n).is_symlink()
                          and not getattr((Path(directory)/n).lstat(), 'st_file_attributes', 0) & 0x400]
            files.extend(Path(directory)/n for n in names if Path(n).suffix.lower() in MEDIA_EXTENSIONS)
    entries = []
    for source in sorted(files):
        if source.suffix.lower() not in MEDIA_EXTENSIONS:
            raise ValueError('Rename target must be a supported video file')
        check_rename_path(source)
        siblings = [p for p in source.parent.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS]
        filename = Path(clean_media_name(source)).stem
        folder = Path(clean_media_name(Path(source.parent.name + '.mkv'))).stem
        dated = lambda value: bool(re.search(r'\((?:19|20)\d{2}\)$', value))
        episode = bool(re.search(r'(?i)\bS\d{1,3}E\d{1,3}', filename))
        reason, name = 'Identity is ambiguous; supply --rename-title for this single file', None
        if title:
            name, reason = Path(clean_media_name(Path(title + '.mkv'))).stem, 'Explicit user-provided title'
        elif episode:
            name, reason = filename, 'Episode identity from filename'
        elif len(siblings) == 1 and dated(folder):
            if dated(filename) and filename[-6:] != folder[-6:]:
                reason = 'Folder and filename years disagree; review required'
            else:
                name, reason = folder, 'Single-video folder title/year; verify identity in preview'
        elif dated(filename) and not re.match(r'(?i)^[a-z0-9]{2,9}-', source.stem):
            name, reason = filename, 'Title/year from filename'
        release = rename_release_suffix(source, name) if name else ''
        destination = source.with_name(name + (' - ' + release if release else '') + source.suffix) if name else None
        entry = dict(source=str(source), destination=str(destination) if destination else None,
                     identity=rename_identity(source), reason=reason, release_suffix=release,
                     status='ready' if destination and destination != source else 'unchanged' if destination else 'needs-review')
        entries.append(entry)
        if sidecars and destination and destination != source:
            for companion in sorted(source.parent.iterdir()):
                if (companion.is_file() and companion.suffix.lower() in {'.srt','.ass','.ssa','.vtt','.sub','.idx','.jpg','.jpeg','.png','.webp'}
                        and companion.name.startswith(source.stem + '.')):
                    check_rename_path(companion)
                    entries.append(dict(source=str(companion), destination=str(companion.with_name(destination.stem + companion.name[len(source.stem):])),
                        identity=rename_identity(companion), parent_source=str(source), reason='Same-basename subtitle/artwork companion', status='ready'))
    destinations = {}
    for entry in entries:
        if entry['status'] != 'ready':
            continue
        destination = Path(entry['destination'])
        key = str(destination).casefold()
        destinations.setdefault(key, []).append(entry)
        if destination.exists():
            entry.update(status='blocked', reason='Destination already exists; no overwrite')
    for group in destinations.values():
        if len(group) > 1:
            for entry in group:
                entry.update(status='blocked', reason='Multiple files would use the same destination')
    states = {e['source']: e['status'] for e in entries}
    for entry in entries:
        if entry.get('parent_source') and states[entry['parent_source']] != 'ready':
            entry.update(status='blocked', reason='Companion video rename is blocked')
    return dict(schema='muxmender-rename-v1', root=str(root), entries=entries,
                note='Preview only. No online identity lookup. Review every ready entry before explicit apply. No folder renames.')


def apply_rename_plan(plan_path):
    plan_path = plan_path.resolve()
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    if plan.get('schema') != 'muxmender-rename-v1':
        raise ValueError('Unsupported rename plan')
    root = Path(plan['root'])
    check_rename_path(root)
    if not root.is_absolute() or not root.is_dir():
        raise ValueError('Rename root must be an existing absolute directory')
    ready = [e for e in plan['entries'] if e['status'] == 'ready']
    ready_sources = {e['source'] for e in ready}
    seen_sources, seen_targets = set(), set()
    for entry in ready:
        source, destination = Path(entry['source']), Path(entry['destination'])
        if entry.get('parent_source') and entry['parent_source'] not in ready_sources:
            raise ValueError('Companion rename requires its video rename in the same plan')
        check_rename_path(source)
        if not source.is_absolute() or not destination.is_absolute() or source.parent != destination.parent:
            raise ValueError('Rename must stay in the same directory')
        source.resolve().relative_to(root.resolve())
        if not source.is_file() or rename_identity(source) != entry['identity']:
            raise ValueError(f'Source changed since preview: {source}')
        if source.suffix != destination.suffix or destination.name.rstrip(' .') != destination.name or re.search(r'[<>:"|?*]', destination.name):
            raise ValueError('Invalid destination or changed file extension')
        if destination.name.split('.')[0].upper() in {'CON','PRN','AUX','NUL', *('COM'+str(n) for n in range(1,10)), *('LPT'+str(n) for n in range(1,10))}:
            raise ValueError('Reserved destination filename')
        if str(source).casefold() in seen_sources or str(destination).casefold() in seen_targets or destination.exists():
            raise ValueError('Duplicate action or destination collision; nothing renamed')
        seen_sources.add(str(source).casefold()); seen_targets.add(str(destination).casefold())
    # Create the durable result journal before any mutation; partial failures are explicit.
    journal = plan_path.with_name(plan_path.stem + '.applied-' + uuid.uuid4().hex[:8] + '.jsonl')
    with journal.open('x', encoding='utf-8') as log:
        for entry in ready:
            source, destination = Path(entry['source']), Path(entry['destination'])
            log.write(json.dumps({'status':'starting','source':str(source),'destination':str(destination)})+'\n')
            log.flush(); os.fsync(log.fileno())
            try:
                check_rename_path(source)
                if rename_identity(source) != entry['identity']:
                    raise ValueError('Source changed after preflight')
                if os.name == 'nt':
                    os.rename(source, destination)  # Windows rejects existing destinations.
                else:
                    os.link(source, destination)  # Exclusive creation; never replaces a target.
                    source.unlink()
                log.write(json.dumps({'status':'renamed','source':str(source),'destination':str(destination)})+'\n')
                log.flush(); os.fsync(log.fileno())
            except Exception as exc:
                log.write(json.dumps({'status':'failed','source':str(source),'destination':str(destination),'error':str(exc)})+'\n')
                raise RuntimeError(f'Rename stopped; review journal {journal}: {exc}') from exc
    return len(ready), journal


def copy_matching_artwork(source: Path, destination: Path, video_only: bool = False) -> list[dict]:
    """Copy basename-matched artwork alongside an accepted output, never overwrite."""
    results = []
    if video_only:
        return results
    try:
        candidates = sorted(source.parent.iterdir())
    except OSError as exc:
        return [{'status': 'failed', 'error': str(exc)}]
    for artwork in candidates:
        if artwork.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
            continue
        suffix = artwork.stem[len(source.stem):]
        if not artwork.stem.lower().startswith(source.stem.lower()) or suffix.lower() not in {'', '-poster', '-fanart', '-banner', '-thumb'}:
            continue
        target = destination.with_name(destination.stem + suffix + artwork.suffix)
        entry = {'source': str(artwork), 'output': str(target)}
        try:
            if artwork.is_symlink() or getattr(artwork.lstat(), 'st_file_attributes', 0) & 0x400 or not artwork.is_file():
                entry['status'] = 'skipped'
            elif target.exists():
                entry['status'] = 'existing-preserved'
            else:
                with artwork.open('rb') as original, target.open('xb') as copied:
                    shutil.copyfileobj(original, copied)
                entry['status'] = 'copied'
        except OSError as exc:
            entry.update(status='failed', error=str(exc))
        results.append(entry)
    return results


def encoder_options(
    codec: str,
    quality: str,
    info: MediaInfo,
    encoder: str | None = None,
    *, experimental_av1_hdr: bool = False,
) -> list[str]:
    encoder = encoder or SOFTWARE_ENCODERS[codec]
    ten_bit = info.bit_depth > 8 or info.hdr
    if experimental_av1_hdr and (encoder != 'av1_qsv' or not info.hdr or info.dolby_vision):
        raise ValueError('AV1 HDR research requires Intel AV1 HDR10 without Dolby Vision')
    if encoder == "av1_qsv" and (info.hdr or info.mastering_display_metadata) and not experimental_av1_hdr:
        raise ValueError("Intel AV1 mastering-display preservation requires the integrated repair and full-verification route; direct unchecked encoding is blocked.")

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
        if encoder == "hevc_qsv":
            # QSV reordering duplicates PTS on irregular tails; preserve the input timeline.
            options += ["-bf", "0"]
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
    *, experimental_av1_hdr: bool = False,
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
            *encoder_options(codec, quality, info, encoder, experimental_av1_hdr=experimental_av1_hdr),
            "-c:a", "copy", "-c:s", "copy", "-c:d", "copy", "-c:t", "copy",
        ]
    )
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-n", "-i", str(source),
        "-map", "0", "-map_metadata", "0", "-map_chapters", "0",
        *video_options,
        "-max_muxing_queue_size", "4096",
        "-max_interleave_delta", str(INTERLEAVE_MICROSECONDS), str(temporary),
    ]


def dolby_sdr_preview_path(destination: Path, seconds: float) -> Path:
    duration_label = f"{seconds:g}".replace(".", "p")
    return destination.with_name(f"{destination.stem}.dolby-sdr-preview-{duration_label}s.mkv")


def build_dolby_sdr_preview_command(
    source: Path,
    temporary: Path,
    start_seconds: float,
    duration_seconds: float,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-n",
        "-init_hw_device", "vulkan=vk:0", "-filter_hw_device", "vk",
        "-ss", f"{start_seconds:g}", "-i", str(source), "-t", f"{duration_seconds:g}",
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf",
        (
            "hwupload,libplacebo=colorspace=bt709:color_primaries=bt709:"
            "color_trc=bt709:range=tv:apply_dolbyvision=1,"
            "hwdownload,format=yuv420p10le"
        ),
        "-c:v", "libx265", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p10le", "-color_primaries", "bt709",
        "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
        "-c:a", "copy", str(temporary),
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
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, check=False, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
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
    display = TerminalProgress()
    last_advanced = -1.0
    last_progress_at = time.monotonic()
    lines: queue.Queue[str | None] = queue.Queue()
    assert process.stdout is not None

    def read_progress() -> None:
        for output_line in process.stdout:
            lines.put(output_line)
        lines.put(None)

    threading.Thread(target=read_progress, daemon=True).start()
    stalled = False
    try:
        eof = False
        while not eof or process.poll() is None:
            from runtime_support import guard_ordered_mux_memory
            guard_ordered_mux_memory(process, progress_command)
            if stall_timeout > 0 and process.poll() is None and time.monotonic() - last_progress_at >= stall_timeout:
                stalled = True
                print(f"Encoder stalled for {stall_timeout:.0f}s; stopping owned process. Partial output retained.", flush=True)
                break
            try:
                line = lines.get(timeout=0.5)
            except queue.Empty:
                continue
            if line is None:
                eof = True
                continue
            percent = progress_percent(line, duration_seconds)
            if percent is not None:
                if percent > last_advanced:
                    last_progress_at = time.monotonic()
                    last_advanced = percent
                display.update(min(percent, 99))
                import job_tracking
                job_tracking.stage_progress(min(percent, 99), display.eta_seconds)
    finally:
        if process.poll() is None:
            stop_process_tree(process)
        process.wait(timeout=10)
        process.stdout.close()
    return_code = process.returncode
    if return_code == 0 and not stalled:
        display.update(100)
    return return_code, stalled


def verify_output(
    source_info: MediaInfo,
    output: Path,
    ffprobe: str,
    min_savings: float,
    expected_video_codec: str,
    enforce_min_savings: bool = True,
    expected_dimensions: tuple[int, int] | None = None,
    additional_audio: bool = False,
    playback_audio_codecs: list[str] | None = None,
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
    expected_audio = source_info.audio_codecs + (['eac3'] if additional_audio else [])
    if playback_audio_codecs is not None:
        expected_audio = playback_audio_codecs
    if len(result.audio_codecs) != len(expected_audio):
        return False, "audio stream count changed"
    if result.audio_codecs != expected_audio:
        return False, "one or more audio codecs changed"
    if result.subtitle_codecs != source_info.subtitle_codecs:
        return False, "subtitle streams changed"
    if source_info.hdr and not result.hdr:
        return False, "HDR signaling was lost"
    if source_info.hdr and result.bit_depth < 10:
        return False, f"HDR output is only {result.bit_depth}-bit; expected at least 10-bit"
    if source_info.dolby_vision:
        if not result.dolby_vision:
            return False, "Dolby Vision signaling/RPU was lost"
        if (
            source_info.dolby_vision_profile is not None
            and result.dolby_vision_profile != source_info.dolby_vision_profile
        ):
            return False, (
                "Dolby Vision profile changed from "
                f"{source_info.dolby_vision_profile} to {result.dolby_vision_profile}"
            )
        if (
            source_info.dolby_vision_compatibility_id is not None
            and result.dolby_vision_compatibility_id
            != source_info.dolby_vision_compatibility_id
        ):
            return False, "Dolby Vision base-layer compatibility changed"
        if source_info.dolby_vision_rpu_present and not result.dolby_vision_rpu_present:
            return False, "Dolby Vision RPU metadata was lost"
        if source_info.dolby_vision_el_present and not result.dolby_vision_el_present:
            return False, "Dolby Vision enhancement layer was lost"
    if source_info.mastering_display_metadata and not result.mastering_display_metadata:
        return False, "HDR mastering-display metadata was lost"
    if source_info.content_light_metadata and not result.content_light_metadata:
        return False, "HDR content-light metadata was lost"
    for label, before, after in (
        ("color primaries", source_info.color_primaries, result.color_primaries),
        ("color transfer", source_info.color_transfer, result.color_transfer),
        ("color space", source_info.color_space, result.color_space),
        ("color range", source_info.color_range, result.color_range),
    ):
        if before != "unknown" and before != after:
            return False, f"{label} changed from {before} to {after}"
    saved = 100.0 * (source_info.size_bytes - result.size_bytes) / source_info.size_bytes
    if enforce_min_savings and result.size_bytes >= source_info.size_bytes:
        return False, "output is larger than or equal to the source; keep original"
    if enforce_min_savings and saved < min_savings:
        return False, f"only saved {saved:.1f}% (minimum is {min_savings:.1f}%)"
    if not enforce_min_savings:
        label = 'verified remux with added lossy compatibility audio' if additional_audio else 'verified lossless remux'
        return True, f"{label} (size change: {saved:+.1f}%)"
    return True, f"saved {saved:.1f}% ({human_size(source_info.size_bytes - result.size_bytes)})"


def verify_dolby_sdr_preview(
    source_info: MediaInfo,
    output: Path,
    ffprobe: str,
    expected_duration: float,
) -> tuple[bool, str]:
    result = probe(output, ffprobe)
    if result.video_codec != "hevc":
        return False, f"preview codec is {result.video_codec}; expected hevc"
    if (result.width, result.height) != (source_info.width, source_info.height):
        return False, "preview resolution changed"
    if result.dolby_vision or result.hdr:
        return False, "preview is still tagged as Dolby Vision/HDR instead of SDR"
    if result.bit_depth < 10:
        return False, f"preview is only {result.bit_depth}-bit"
    for label, value in (
        ("color primaries", result.color_primaries),
        ("color transfer", result.color_transfer),
        ("color space", result.color_space),
    ):
        if value != "bt709":
            return False, f"preview {label} is {value}; expected bt709"
    if source_info.audio_codecs and result.audio_codecs != source_info.audio_codecs[:1]:
        return False, "preview audio was not copied unchanged"
    if abs(result.duration_seconds - expected_duration) > 2.0:
        return False, "preview duration differs by more than two seconds"
    if result.size_bytes <= 0:
        return False, "preview is empty"
    return True, "verified full-resolution BT.709 SDR preview with copied audio"


def delete_original_allowed(args: argparse.Namespace) -> bool:
    if not args.delete_originals:
        return False
    raise ValueError("Original deletion is disabled. MuxMender never deletes original media.")


def fresh_partial(destination: Path) -> Path:
    return destination.with_name(f".{destination.stem}.{uuid.uuid4().hex}.partial.mkv")


def publish_output(temporary: Path, destination: Path) -> None:
    # Atomic no-clobber publication; retain the recovery link. Fail closed on
    # filesystems without hard links rather than risking an existing file.
    os.link(temporary, destination)
    print(f"  Recovery file retained: {temporary}")


def print_info(info: MediaInfo) -> None:
    if info.dolby_vision:
        profile = f" P{info.dolby_vision_profile}" if info.dolby_vision_profile is not None else ""
        hdr = f" Dolby Vision{profile}"
    else:
        hdr = " HDR" if info.hdr else ""
    print(f"\n{info.path}")
    print(
        f"  {human_size(info.size_bytes)} | {info.width}x{info.height} | "
        f"{info.video_codec} {info.bit_depth}-bit{hdr} | audio: {', '.join(info.audio_codecs) or 'none'}"
    )
    print(f"  {info.recommendation.upper()}: {info.reason}")
    if info.dolby_preservation:
        print(f"  DV PRESERVATION: {info.dolby_preservation['reason']}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recursively analyze and safely optimize media for direct playback.",
        epilog="Dry-run is the default. Use --execute to create optimized sidecar files.",
    )
    parser.add_argument("folder", type=Path, nargs="?", help="media file or library folder")
    parser.add_argument('--rename-plan', type=Path, help='Write a new JSON preview for existing-file renames; never apply')
    parser.add_argument('--rename-title', help='Explicit title/year override for a single-file rename preview')
    parser.add_argument('--rename-sidecars', action='store_true', help='Include same-basename subtitle/artwork files in rename preview')
    parser.add_argument('--apply-rename-plan', type=Path, help='Apply ready entries from a reviewed plan; requires --execute --confirm-rename RENAME')
    parser.add_argument('--confirm-rename', default='', help='Explicit existing-file rename confirmation: RENAME')
    parser.add_argument('--cleanup-plan', type=Path, help='Preview NFO cleanup beside the supplied main video; never delete during preview')
    parser.add_argument('--cleanup-samples', action='store_true', help='Also nominate explicitly named sample videos; requires --cleanup-plan and review')
    parser.add_argument('--apply-cleanup-plan', type=Path, help='Permanently delete ready files from a reviewed cleanup plan; requires --execute --confirm-cleanup CLEANUP')
    parser.add_argument('--confirm-cleanup', default='', help='Explicit reviewed cleanup confirmation: CLEANUP')
    parser.add_argument("--check-dependencies", action="store_true", help="check tools and encoder availability without opening media or initializing GPU encoding")
    parser.add_argument("--native-delivery-test", action="store_true",
                        help="bounded DV-to-PQ HDR workflow with encoding, copied audio/subtitles, and original-segment comparison")
    parser.add_argument("--streaming-delivery-test", action="store_true", help="experimental 1..60 second DV-to-PQ test piped directly to HEVC; no lossless disk intermediates")
    parser.add_argument("--full-file-streaming", action="store_true", help="explicit whole-file DV5-to-PQ conversion; requires hdr-preview and d3d11; originals always retained")
    parser.add_argument("--preserve-dolby-vision", action="store_true", help="opt-in full-file Profile 8.1 preservation; single file, AMD/Intel HEVC, no resizing")
    parser.add_argument("--dovi-tool", default=str(Path(__file__).resolve().parent.parent / "tools/dovi_tool-2.3.3/dovi_tool.exe"), help="path to dovi_tool for opt-in Dolby Vision preservation")
    parser.add_argument("--dv-qp-i", type=int, default=21)
    parser.add_argument("--dv-qp-p", type=int, default=23)
    parser.add_argument("--max-runtime-hours", type=float, default=12, help="streaming encoding time limit (default: 12 hours)")
    parser.add_argument("--dolby-preview-backend", choices=("vulkan", "d3d11"), default="vulkan",
                        help="explicit experimental D3D11 backend: single-file, video-only SDR diagnostic")
    parser.add_argument("--d3d11-helper", type=Path,
                        default=Path(__file__).resolve().parent.parent / "native/muxmender-d3d11/build/preview/muxmender-dv-preview.exe")
    parser.add_argument("--codec", choices=("auto", "hevc", "av1"), default="auto")
    parser.add_argument('--reencode-efficient', action='store_true', help='Explicitly re-encode HEVC/AV1 inputs; retains normal color/DV safety and minimum savings checks')
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
    parser.add_argument(
        "--dolby-vision-policy",
        choices=("skip", "copy", "sdr-preview", "hdr-preview"),
        default="skip",
        help=(
            "skip Dolby Vision by default; copy permits only an unchanged video-bitstream "
            "remux; sdr-preview requires a successful synthetic libplacebo runtime test"
        ),
    )
    parser.add_argument(
        "--preview-start", type=float, default=300.0, metavar="SECONDS",
        help="start time for a Dolby Vision SDR preview (default: 300)",
    )
    parser.add_argument(
        "--preview-seconds", type=float, default=10.0, metavar="SECONDS",
        help="length of a Dolby Vision SDR preview (default: 10)",
    )
    parser.add_argument("--quality", choices=("transparent", "balanced", "compact"), default="balanced")
    parser.add_argument('--compatibility-audio', choices=('preserve', 'eac3'), default='preserve',
                        help='Opt-in: retain original tracks and make EAC3 compatibility audio default')
    parser.add_argument('--compatibility-audio-track', type=int,
                        help='Zero-based source audio track; otherwise use a unique default or only audio track')
    parser.add_argument('--default-subtitle-track', type=int,
                        help='Zero-based embedded subtitle to mark default; preserve all subtitles and forced flags')
    parser.add_argument("--execute", action="store_true", help="run ffmpeg; otherwise only show the plan")
    parser.add_argument("--dry-run", action="store_true", help="explicitly request the default dry-run behavior")
    parser.add_argument("--output-dir", type=Path, help="mirror optimized files under this directory")
    parser.add_argument('--video-only-folder', action='store_true', help='Publish only video files; exclude artwork and external subtitles at every depth, retain embedded tracks and source files. Keep working files separately.')
    parser.add_argument("--report", type=Path, help="write the analysis report as JSON")
    parser.add_argument("--min-savings", type=float, default=5.0, metavar="PERCENT")
    parser.add_argument("--overwrite-output", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--delete-originals", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--confirm-delete", default="", help=argparse.SUPPRESS)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    parsed = parser.parse_args(argv)
    raw = sys.argv[1:] if argv is None else argv
    parsed.preview_range_explicit = any(item.split('=', 1)[0] in ('--preview-start', '--preview-seconds') for item in raw)
    return parsed


def run_native_dolby_preview(args: argparse.Namespace, source: Path) -> int:
    """Explicit diagnostic path. Never deletes or replaces any file."""
    if args.dolby_vision_policy not in {"sdr-preview", "hdr-preview"} or not source.is_file():
        print("error: D3D11 diagnostic requires a single file and sdr-preview or hdr-preview policy")
        return 2
    if args.resolution != "keep" or args.delete_originals or args.overwrite_output or args.report:
        print("error: native diagnostic disallows resizing, deletion, overwrite, and report-file writes")
        return 2
    if not (0 <= args.preview_start < float("inf") and 1 <= args.preview_seconds <= 10):
        print("error: native preview requires finite nonnegative start and 1..10 seconds")
        return 2
    helper = args.d3d11_helper.resolve()
    if not helper.is_file():
        print(f"error: native helper is not built: {helper}; see native/muxmender-d3d11/README.md")
        return 3
    destination = dolby_sdr_preview_path(
        output_path(source, source.parent, args.output_dir.resolve() if args.output_dir else None),
        args.preview_seconds,
    )
    hdr = args.dolby_vision_policy == "hdr-preview"
    if hdr:
        destination = destination.with_name(destination.name.replace(".dolby-sdr-preview-", ".dolby-hdr-pq-preview-"))
    if destination.exists() or destination.resolve() == source.resolve():
        print(f"error: refusing existing output: {destination}")
        return 2
    command = [str(helper), "--input", str(source), "--output", str(destination),
               "--start", f"{args.preview_start:g}", "--seconds", f"{args.preview_seconds:g}",
               "--hdr-preview" if hdr else "--sdr-preview", "--progress-machine"]
    if not args.execute:
        command.append("--dry-run")
    color_label = "HDR BT.2020/PQ (not Dolby Vision)" if hdr else "SDR BT.709"
    print(f"D3D11 diagnostic: {color_label}, original dimensions, video only; no audio/subtitles or AMF encoding.", flush=True)
    print(f"OUTPUT: {destination}\nCOMMAND: {command_text(command)}", flush=True)
    try:
        if args.execute:
            if shutil.which(args.ffprobe) is None:
                print("error: ffprobe is required to verify the preview")
                return 3
            source_info = probe(source, args.ffprobe)
            color_test = helper.with_name("muxmender-color-test.exe")
            # Inherit terminal handles so the end user sees the actual progress.
            preflight = subprocess.run([str(color_test)], timeout=30, check=False)
            if preflight.returncode:
                print("error: generated-color preflight failed; no preview created")
                return 4
            destination.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(command, timeout=120, check=False)
        if result.returncode or not args.execute:
            return result.returncode
        output = probe(destination, args.ffprobe)
        valid = (
            output.video_codec == "ffv1" and output.bit_depth >= 10
            and (output.width, output.height) == (source_info.width, source_info.height)
            and not output.dolby_vision and output.hdr == hdr
            and (output.color_primaries, output.color_transfer, output.color_space) == (("bt2020", "smpte2084", "bt2020nc") if hdr else ("bt709",) * 3)
            and not output.audio_codecs
            and abs(output.duration_seconds - args.preview_seconds) <= 0.15
        )
        if not valid:
            print("REJECTED: preview verification failed; output retained for inspection, original untouched")
            return 4
        print(f"VERIFIED: full-resolution {color_label} diagnostic: {destination}")
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"error: native preview failed: {exc}; any partial output retained, original untouched")
        return 4


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.cleanup_plan or args.apply_cleanup_plan or args.cleanup_samples or args.confirm_cleanup:
        try:
            from library_planner import create_cleanup_plan, apply_cleanup_plan
            if (args.rename_plan or args.apply_rename_plan or args.rename_title or args.rename_sidecars or args.confirm_rename
                    or args.delete_originals or args.overwrite_output or args.output_dir or args.report or args.check_dependencies
                    or args.preserve_dolby_vision or args.native_delivery_test or args.streaming_delivery_test or args.full_file_streaming):
                raise ValueError('Cleanup cannot be combined with rename, conversion, reporting or original-deletion modes')
            if args.cleanup_plan:
                if args.apply_cleanup_plan or args.execute or args.confirm_cleanup or args.folder is None:
                    raise ValueError('Preview requires the main video and --cleanup-plan; no execute or confirmation')
                if args.cleanup_plan.suffix.lower() != '.json':
                    raise ValueError('Cleanup preview must be a new .json file')
                plan = create_cleanup_plan(args.folder, args.cleanup_samples)
                with args.cleanup_plan.open('x',encoding='utf-8') as output:
                    json.dump(plan,output,indent=2)
                for entry in plan['entries']:
                    print(f"REVIEW: {entry['source']} | {entry['reason']}")
                print(f'Cleanup preview: {args.cleanup_plan}; {len(plan["entries"])} candidates. No files changed.')
                return 0
            if not args.apply_cleanup_plan or not args.execute or args.dry_run or args.confirm_cleanup != 'CLEANUP' or args.folder or args.cleanup_samples:
                raise ValueError('Apply requires --apply-cleanup-plan PLAN --execute --confirm-cleanup CLEANUP; review plan first')
            count,journal = apply_cleanup_plan(args.apply_cleanup_plan)
            print(f'Deleted {count} reviewed cleanup files. Main video/subtitles retained. Journal: {journal}')
            return 0
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
            print(f'Cleanup error: {exc}',file=sys.stderr)
            return 2
    if args.rename_plan or args.apply_rename_plan:
        try:
            if args.delete_originals or args.overwrite_output or args.output_dir or args.report or args.check_dependencies or args.preserve_dolby_vision or args.native_delivery_test or args.streaming_delivery_test or args.full_file_streaming:
                raise ValueError('Rename mode cannot be combined with conversion, reporting or deletion modes')
            if args.rename_plan:
                if args.apply_rename_plan or args.execute or args.confirm_rename or args.folder is None:
                    raise ValueError('Preview requires a file/folder and --rename-plan only; no execute or confirmation')
                plan = create_rename_plan(args.folder, args.rename_title, args.rename_sidecars)
                if args.rename_plan.suffix.lower() != '.json':
                    raise ValueError('Rename preview must be a new .json file')
                with args.rename_plan.open('x', encoding='utf-8') as stream:
                    json.dump(plan, stream, indent=2)
                for entry in plan['entries']:
                    print(f"{entry['status'].upper()}: {entry['source']} -> {entry['destination'] or '(review needed)'} | {entry['reason']}")
                print(f'Rename preview saved: {args.rename_plan}. No media changed.')
                return 0
            if not args.execute or args.dry_run or args.confirm_rename != 'RENAME' or args.folder or args.rename_title or args.rename_sidecars:
                raise ValueError('Apply requires --apply-rename-plan PLAN --execute --confirm-rename RENAME; review plan first')
            count, journal = apply_rename_plan(args.apply_rename_plan)
            print(f'Renamed {count} files. Journal: {journal}. Non-ready entries were not applied.')
            return 0
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            print(f'Rename error: {exc}', file=sys.stderr)
            return 2
    if args.rename_title or args.rename_sidecars or args.confirm_rename:
        print('error: rename options require --rename-plan or --apply-rename-plan', file=sys.stderr)
        return 2
    if args.compatibility_audio == 'preserve' and (args.compatibility_audio_track is not None or args.default_subtitle_track is not None):
        print('error: playback track choices require --compatibility-audio eac3', file=sys.stderr)
        return 2
    if args.compatibility_audio != 'preserve' and (args.preserve_dolby_vision or args.streaming_delivery_test or args.full_file_streaming or args.native_delivery_test or args.dolby_preview_backend == 'd3d11'):
        print('error: compatibility audio is not validated for experimental Dolby delivery modes', file=sys.stderr)
        return 2
    if args.delete_originals or args.overwrite_output:
        print("error: deletion and overwrite are disabled; choose a fresh output directory", file=sys.stderr)
        return 2
    if not math.isfinite(args.min_savings) or not 0 <= args.min_savings < 100 or not math.isfinite(args.hardware_stall_timeout) or args.hardware_stall_timeout < 5:
        print("error: savings must be finite in [0,100); stall timeout must be finite and at least 5 seconds", file=sys.stderr)
        return 2
    if args.check_dependencies:
        from runtime_support import check_dependencies
        return check_dependencies(args)
    if args.folder is None:
        print("error: provide a media file/folder or --check-dependencies", file=sys.stderr)
        return 2
    if args.report and (args.report.exists() or args.report.suffix.lower() != ".json"):
        print("error: report must be a new .json file; nothing overwritten", file=sys.stderr)
        return 2
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
    if args.preserve_dolby_vision:
        from dv_full_file import run_integrated
        return run_integrated(args, target)
    if args.streaming_delivery_test or args.full_file_streaming:
        if args.native_delivery_test or (args.streaming_delivery_test and args.full_file_streaming):
            print("error: choose only one delivery test mode", file=sys.stderr)
            return 2
        from streaming_pipeline import run
        return run(args, target)
    if args.dolby_preview_backend == "d3d11":
        if args.native_delivery_test:
            from native_pipeline import run
            return run(args, target)
        return run_native_dolby_preview(args, target)
    if args.native_delivery_test:
        print("error: native delivery test requires --dolby-preview-backend d3d11")
        return 2
    if args.dolby_vision_policy == "hdr-preview":
        print("error: HDR preview currently requires --dolby-preview-backend d3d11")
        return 2
    if args.min_savings < 0 or args.min_savings >= 100:
        print("error: --min-savings must be between 0 and 100", file=sys.stderr)
        return 2
    if args.hardware_stall_timeout < 5:
        print("error: --hardware-stall-timeout must be at least 5 seconds", file=sys.stderr)
        return 2
    if not math.isfinite(args.preview_start) or not math.isfinite(args.preview_seconds) or args.preview_start < 0 or args.preview_seconds <= 0 or args.preview_seconds > 120:
        print("error: preview start must be non-negative and duration must be 0-120 seconds", file=sys.stderr)
        return 2
    try:
        delete_original_allowed(args)
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

    color_preflight_message = "not requested"
    if args.execute and args.dolby_vision_policy == "sdr-preview":
        print("Dolby Vision preflight: testing one generated 64x64 frame", flush=True)
        preflight_ok, color_preflight_message = dolby_vision_gpu_preflight(args.ffmpeg)
        if not preflight_ok:
            payload = {
                "backend": "libplacebo-vulkan",
                "message": color_preflight_message,
                "cpu_available": False,
                "cpu_backend": "DoViBaker/AviSynth+",
                "download_url": DOWNLOAD_URLS["dovibaker"],
            }
            emit_action("MUXMENDER_COLOR_PIPELINE_FAILURE", payload)
            print(f"BLOCKED: Dolby Vision GPU preflight failed: {color_preflight_message}")
            print("No source media was opened and no output file was created.")
            return 4

    import job_tracking
    if not args.execute:
        job_tracking.progress('Finding media files', unit='files', detail='Read-only enumeration; file count is not yet known.')
    found = [target] if target.is_file() else list(media_files(root))
    print(f"MuxMender {'EXECUTE' if args.execute else 'DRY RUN'}")
    print(f"Found {len(found)} media file(s); target: {target_codec}/MKV, quality: {args.quality}")
    print(f"Resolution policy: {args.resolution} (upscaling disabled)")
    print(f"Dolby Vision policy: {args.dolby_vision_policy} (re-encoding blocked)")
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
        "dolby_vision_policy": args.dolby_vision_policy,
        "requested_hardware": args.hardware,
        "detected_gpu_vendors": detected_vendors,
        "selected_encoder": asdict(selection),
        "files": [],
        "errors": [],
    }

    scan_started = time.monotonic()
    for file_index, source in enumerate(found):
        if not args.execute:
            job_tracking.progress('Inspecting media', file_index, len(found), unit='files',
                                  detail=str(source))
        try:
            info = recommend(
                probe(source, args.ffprobe),
                target_codec,
                args.resolution,
                args.dolby_vision_policy,
                args.reencode_efficient,
            )
            print_info(info)
            entry: dict[str, Any] = asdict(info)
            entry["status"] = info.recommendation
            playback = None
            if args.compatibility_audio == 'eac3':
                if info.dolby_vision or info.recommendation == 'preview':
                    raise ValueError('Compatibility preparation is not validated for Dolby Vision; preservation gate unchanged')
                playback_probe = run_json([args.ffprobe, '-v', 'error', '-show_streams', '-show_chapters', '-of', 'json', str(source)])
                playback = nvidia_mux.playback_plan(playback_probe, args.compatibility_audio_track, args.default_subtitle_track)
                entry['playback_plan'] = playback
                if info.recommendation == 'keep':
                    info.recommendation = 'remux'
                    entry['recommendation'] = 'remux'
                    entry['reason'] = 'Explicit playback preparation; copied video, original tracks retained'
                print('  PLAYBACK: retain original tracks; default EAC3 audio; subtitle defaults ' +
                      ('unchanged' if args.default_subtitle_track is None else f'track {args.default_subtitle_track}'))
            if info.recommendation == "transcode":
                from mux_integrity import conversion_preflight
                preflight = conversion_preflight(info, args.ffprobe, run_json)
                entry["preflight"] = preflight
                if preflight["status"] == "needs-review":
                    entry["status"] = "needs-review"
                    entry["reason"] = "; ".join(preflight["reasons"])
                    print(f"  NEEDS REVIEW: {entry['reason']}; no encoding or media output created")
                    report["files"].append(entry)
                    continue
            if info.recommendation == "preview":
                base_destination = output_path(
                    source, root, args.output_dir.resolve() if args.output_dir else None
                )
                destination = dolby_sdr_preview_path(base_destination, args.preview_seconds)
                temporary = fresh_partial(destination)
                if args.video_only_folder:
                    temporary = destination.parent.parent / '.MuxMender-work' / uuid.uuid4().hex / temporary.name
                command = build_dolby_sdr_preview_command(
                    source, temporary, args.preview_start, args.preview_seconds, args.ffmpeg
                )
                entry["output"] = str(destination)
                entry["recovery_files"] = [str(temporary)]
                entry["command"] = command
                print(f"  OUTPUT: {destination}")
                if not args.execute:
                    print("  PREFLIGHT: synthetic 64x64 Vulkan/libplacebo frame")
                    print(f"  COMMAND: {command_text(command)}")
                    entry["status"] = "planned-preview"
                    report["files"].append(entry)
                    continue
                if destination.exists() or temporary.exists():
                    print("  SKIPPED: preview or partial output already exists; nothing overwritten")
                    entry["status"] = "output-exists"
                    report["files"].append(entry)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary.parent.mkdir(parents=True, exist_ok=True)
                return_code, stalled = run_ffmpeg(
                    command, args.preview_seconds, args.hardware_stall_timeout
                )
                if return_code:
                    print("  FAILED: preview conversion failed; any partial output was retained")
                    entry["status"] = "preview-failed"
                    report["files"].append(entry)
                    continue
                valid, message = verify_dolby_sdr_preview(
                    info, temporary, args.ffprobe, args.preview_seconds
                )
                if not valid:
                    print(f"  REJECTED: {message}; partial output retained")
                    entry["status"] = "rejected"
                    entry["result"] = message
                    report["files"].append(entry)
                    continue
                publish_output(temporary, destination)
                print(f"  COMPLETE: {message}")
                entry["status"] = "complete"
                entry["result"] = message
                report["files"].append(entry)
                continue
            if info.recommendation not in {"transcode", "remux"}:
                report["files"].append(entry)
                continue

            destination = output_path(source, root, args.output_dir.resolve() if args.output_dir else None)
            if info.recommendation == 'transcode' and selection.encoder == 'av1_qsv' and (info.hdr or info.mastering_display_metadata):
                from validate_nvidia import run_av1_hdr_integrated
                entry['encoder'] = asdict(selection)
                entry.update(run_av1_hdr_integrated(args, source, destination))
                if args.execute:
                    entry['artwork'] = copy_matching_artwork(source, destination, args.video_only_folder)
                    entry['video_only_folder'] = args.video_only_folder
                report['files'].append(entry)
                continue
            temporary = fresh_partial(destination)
            if args.video_only_folder:
                temporary = destination.parent.parent / '.MuxMender-work' / uuid.uuid4().hex / temporary.name
            video_stage = None
            command = build_ffmpeg_command(
                source, temporary, info, target_codec, args.quality, args.ffmpeg,
                selection.encoder, args.resolution,
            )
            if playback is not None and info.recommendation == 'remux':
                command[command.index('-i'):command.index('-i')] = ['-copyts']
                flags = []
                for i, stream in enumerate(playback_probe['streams']):
                    disposition = '+'.join(k for k, v in stream.get('disposition', {}).items() if v) or '0'
                    flags += [f'-disposition:{i}', disposition]
                command[-1:-1] = ['-avoid_negative_ts', 'disabled', *flags]
            if info.recommendation == 'transcode' and selection.encoder in {'hevc_nvenc', 'av1_nvenc', 'hevc_qsv', 'av1_qsv'}:
                video_stage = fresh_partial(temporary.with_name(temporary.stem + '.video-stage.mkv'))
                command[-1] = str(video_stage)
                command = nvidia_mux.video_stage_command(command)
            entry["output"] = str(destination)
            entry["recovery_files"] = [str(temporary)]
            if video_stage is not None:
                entry['recovery_files'].append(str(video_stage))
            entry["command"] = command
            entry["encoder"] = asdict(selection)
            print(f"  OUTPUT: {destination}")
            if not args.execute:
                print(f"  COMMAND: {command_text(command)}")
                if playback is not None:
                    print('  PLAYBACK FINALIZE: copy video/original tracks, prepare EAC3 default, verify packets and timing; include added audio in savings')
                if video_stage is not None:
                    print('  FINALIZE: stream-copy encoded video with original audio, subtitles, metadata and chapters; validate before publication')
                entry["status"] = "planned"
                report["files"].append(entry)
                continue
            if destination.exists():
                print("  SKIPPED: output exists; choose a fresh output directory to retry")
                entry["status"] = "output-exists"
                report["files"].append(entry)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary.parent.mkdir(parents=True, exist_ok=True)
            if video_stage is not None:
                required_free = 2 * info.size_bytes + 512 * 1024**2
                available_free = shutil.disk_usage(destination.parent).free
                if available_free < required_free:
                    raise RuntimeError(f'Two-stage hardware output requires at least {human_size(required_free)} free; only {human_size(available_free)} available. Original unchanged.')
            print(f"  Recovery/partial output: {temporary}")
            job_tracking.progress('Encoding video' if video_stage is not None else 'Processing media', file_index, len(found), unit='files', detail=source.name)
            return_code, stalled = run_ffmpeg(
                command,
                info.duration_seconds,
                args.hardware_stall_timeout if selection.hardware else 0,
            )
            if return_code and selection.hardware:
                print(f"  Failed GPU output retained: {temporary}")
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
                    temporary = fresh_partial(temporary)
                    entry["recovery_files"].append(str(temporary))
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
                raise RuntimeError(f"ffmpeg exited with status {return_code}; partial retained: {temporary}")
            if video_stage is not None and selection.encoder in {'hevc_nvenc', 'av1_nvenc', 'hevc_qsv', 'av1_qsv'}:
                source_probe = run_json([args.ffprobe, '-v', 'error', '-show_streams', '-of', 'json', str(source)])
                mux_command = nvidia_mux.finalize_command(video_stage, source, temporary, source_probe, args.ffmpeg)
                entry['finalize_command'] = mux_command
                print('  Finalizing hardware video with original audio, subtitles and metadata', flush=True)
                job_tracking.progress('Finalizing hardware output', file_index, len(found), unit='files', detail='Copying original tracks; no second video encode')
                return_code, _ = run_ffmpeg(mux_command, info.duration_seconds, args.hardware_stall_timeout)
                if return_code:
                    raise RuntimeError(f'Final mux failed; video stage and partial retained: {temporary}')
            if playback is not None:
                before_playback = temporary
                required = before_playback.stat().st_size + int(info.duration_seconds * 80000) + 512 * 1024**2
                if shutil.disk_usage(before_playback.parent).free < required:
                    raise RuntimeError('Insufficient free space for separately saved playback output; original retained')
                prepared = fresh_partial(temporary.with_name(temporary.stem + '.playback.mkv'))
                entry['recovery_files'].append(str(prepared))
                before_probe = run_json([args.ffprobe, '-v', 'error', '-show_streams', '-show_chapters', '-of', 'json', str(before_playback)])
                playback = nvidia_mux.playback_plan(before_probe, args.compatibility_audio_track, args.default_subtitle_track)
                original_streams = {s['index']: s for s in before_probe['streams']}
                playback_audio_codecs = [('eac3' if index is None else original_streams[index]['codec_name'])
                                         for index in playback['output_order']
                                         if index is None or original_streams[index]['codec_type'] == 'audio']
                playback_cmd = nvidia_mux.playback_command(before_playback, prepared, before_probe, playback, args.ffmpeg)
                entry['playback_command'] = playback_cmd
                job_tracking.progress('Preparing default compatibility audio', file_index, len(found), unit='files', detail='Original tracks retained; no video encode')
                code, _ = run_ffmpeg(playback_cmd, info.duration_seconds, args.hardware_stall_timeout)
                if code:
                    raise RuntimeError('Compatibility preparation failed; outputs retained')
                after_probe = run_json([args.ffprobe, '-v', 'error', '-show_streams', '-show_chapters', '-of', 'json', str(prepared)])
                job_tracking.progress('Verifying playback tracks and timestamps', file_index, len(found), unit='files')
                entry['playback_verification'] = nvidia_mux.verify_playback_copy(before_playback, prepared, before_probe, after_probe, playback, args.ffprobe)
                decode = [args.ffmpeg, '-v', 'error', '-xerror', '-nostdin', '-i', str(prepared), '-map', '0:v', '-map', '0:a', '-f', 'null', '-']
                code, _ = run_ffmpeg(decode, info.duration_seconds, args.hardware_stall_timeout)
                if code:
                    raise RuntimeError('Compatibility output decode failed; outputs retained')
                temporary = prepared
            expected_codec = target_codec if info.recommendation == "transcode" else info.video_codec
            valid, message = verify_output(
                info,
                temporary,
                args.ffprobe,
                args.min_savings,
                expected_codec,
                enforce_min_savings=info.recommendation == "transcode",
                expected_dimensions=output_dimensions(info, args.resolution),
                additional_audio=bool(playback and playback['added_audio']),
                playback_audio_codecs=playback_audio_codecs if playback is not None else None,
            )
            if valid:
                interleaved, detail = verify_startup_interleaving(temporary, args.ffprobe)
                entry['startup_interleaving'] = {'passed': interleaved, 'detail': detail}
                if not interleaved:
                    valid, message = False, detail
            if valid and (video_stage is not None or playback is not None):
                duration = info.duration_seconds
                positions = sorted({0.0, min(60.0, max(0.0, duration-5)), duration/2, max(0.0, duration-60)})
                seek_ok, seek_checks = nvidia_mux.verify_seek_interleaving(temporary, args.ffprobe, positions)
                entry['seek_interleaving'] = {'passed': seek_ok, 'checks': seek_checks}
                if not seek_ok:
                    valid, message = False, 'Seek interleaving failed; output retained for review'
            if not valid:
                print(f"  REJECTED: {message}; original and partial retained: {temporary}")
                entry["status"] = "rejected"
                entry["result"] = message
                report["files"].append(entry)
                continue
            publish_output(temporary, destination)
            print(f"  COMPLETE: {message}")
            entry["status"] = "complete"
            entry["output_size_bytes"] = destination.stat().st_size
            entry['artwork'] = copy_matching_artwork(source, destination, args.video_only_folder)
            entry['video_only_folder'] = args.video_only_folder
            entry["result"] = message
            report["files"].append(entry)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"\n{source}\n  ERROR: {exc}", file=sys.stderr)
            report["errors"].append({"path": str(source), "error": str(exc)})
        finally:
            if not args.execute:
                count = file_index + 1
                job_tracking.progress('Inspecting media', count, len(found), unit='files',
                                      detail=f'{count:,} inspected; {len(report["errors"])} errors. Original media unchanged.')
                if count % 100 == 0 or count == len(found):
                    print(f'Scan: {count:,}/{len(found):,} files | {len(report["errors"])} errors | elapsed {time.monotonic()-scan_started:.0f}s', flush=True)
            else:
                job_tracking.progress('Processed media', file_index + 1, len(found), unit='files',
                                      detail=f'{file_index + 1:,} processed; originals retained.')

    from mux_integrity import savings_summary, savings_summary_text
    report['savings_summary'] = savings_summary(
        (entry['size_bytes'], entry['output_size_bytes'])
        for entry in report['files'] if entry.get('status') == 'complete' and 'output_size_bytes' in entry)
    if args.execute:
        print(savings_summary_text(report['savings_summary']))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as report_file:
            json.dump(report, report_file, indent=2)
        print(f"\nReport written to {args.report.resolve()}")
    if not args.execute:
        job_tracking.progress('Scan complete', len(found), len(found), unit='files',
                              detail=f'{len(report["files"]):,} analyzed; {len(report["errors"])} errors. No conversions run.',
                              completion_state='completed-with-errors' if report['errors'] else 'completed')
    return 1 if report["errors"] or any(entry.get("status") in {"preview-failed", "rejected", "needs-review"} for entry in report["files"]) else 0


def cli():
    from job_tracking import tracked_call
    return tracked_call(main, 'Media scan / optimization')


if __name__ == "__main__":
    try:
        raise SystemExit(cli())
    except KeyboardInterrupt:
        print("\nCancelled. Originals and partial outputs retained.", file=sys.stderr)
        raise SystemExit(130)
