"""Bounded DV profile 5 -> PQ HDR test workflow. Never replaces/removes files.

All writes are inside a newly, exclusively created run directory. Failed and
successful intermediates are deliberately retained. Not a full-library encoder.
"""
from __future__ import annotations

import json
import math
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from runtime_support import TerminalProgress


def checked_json(command, timeout=60):
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-2000:])
    return json.loads(result.stdout)


def progress(line, seconds):
    if line.startswith("MUXMENDER_PROGRESS="):
        return min(100.0, max(0.0, float(line.split("=", 1)[1])))
    if line.startswith("out_time_us="):
        try:
            return min(100.0, max(0.0, float(line.split("=", 1)[1]) / (seconds * 10000)))
        except ValueError:
            return None
    return None


def stage(command, seconds, offset=0, span=0, timeout=120, stall=30, guard=None):
    """Stream logs/progress to caller; cap both stalls and total elapsed time."""
    from muxmender import stop_process_tree
    from job_tracking import stage_progress
    from runtime_support import guard_ordered_mux_memory
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
    lines = queue.Queue()
    def read():
        try:
            for line in child.stdout:
                lines.put(line)
        finally:
            lines.put(None)
    threading.Thread(target=read, daemon=True).start()
    started = advanced = time.monotonic()
    last = -1.0
    log = []
    display = TerminalProgress(label=f"Stage ({offset:g}-{offset + span:g}% overall)", machine=False)
    try:
        eof = False
        while not eof or child.poll() is None:
            guard_ordered_mux_memory(child, command)
            if guard:
                guard()
            now = time.monotonic()
            if now - started > timeout or (stall and now - advanced > stall):
                raise RuntimeError(f"Stage timed out (total limit {timeout}s; progress stall limit {stall}s)")
            try:
                line = lines.get(timeout=0.2)
            except queue.Empty:
                continue
            if line is None:
                eof = True
                continue
            log.append(line)
            if len(log) > 200:
                log.pop(0)
            value = progress(line.strip(), seconds)
            if value is not None:
                if value > last:
                    advanced = now
                    last = value
                if span:
                    display.update(min(value, 99))
                    stage_progress(min(value, 99), display.eta_seconds)
                    print(f"MUXMENDER_PROGRESS={offset + span * value / 100:.1f}", flush=True)
            elif not re.match(r"^(frame|fps|stream_\d+_\d+_q|bitrate|total_size|out_time|dup_frames|drop_frames|speed|progress)=", line):
                print(line.rstrip(), flush=True)
        if child.returncode:
            raise RuntimeError(f"Stage failed ({child.returncode}): {''.join(log)[-1600:]}")
        if span:
            display.update(100)
            stage_progress(100, 0)
            print(f"MUXMENDER_PROGRESS={offset + span:.1f}", flush=True)
        return "".join(log)
    finally:
        if child.poll() is None:
            stop_process_tree(child)
        # taskkill can be denied or fail. Terminate the owned process directly
        # as a fallback, without masking the original timeout with wait().
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
        child.stdout.close()


def remux_command(ffmpeg, original, reference, output, start, seconds):
    # Keep absolute source timestamps through input seek, then trim/rebase at
    # output. This drops keyframe seek preroll without shifting video/audio.
    return [ffmpeg, "-hide_banner", "-nostdin", "-n", "-copyts", "-ss", f"{start:g}", "-i", str(original),
            "-itsoffset", f"{start:g}", "-i", str(reference), "-ss", f"{start:g}", "-t", f"{seconds:g}",
            "-map", "1:v:0", "-map", "0:a?", "-map", "0:s?", "-map", "0:t?", "-map_metadata", "0",
            "-map_chapters", "-1", "-c", "copy", "-avoid_negative_ts", "disabled",
            "-progress", "pipe:1", "-nostats", str(output)]


def encode_command(ffmpeg, source, output, info, encoder, quality):
    from muxmender import encoder_options
    return [ffmpeg, "-hide_banner", "-nostdin", "-n", "-i", str(source), "-map", "0", "-map_metadata", "0",
            *encoder_options("hevc", quality, info, encoder), "-c:a", "copy", "-c:s", "copy", "-c:t", "copy",
            "-progress", "pipe:1", "-nostats", str(output)]


def packet_signatures(ffprobe, path, selector, timeout=60):
    result = checked_json([ffprobe, "-v", "error", "-select_streams", selector, "-show_packets", "-show_data_hash", "sha256",
                           "-show_entries", "packet=stream_index,pts_time,duration_time,data_hash", "-of", "json", str(path)], timeout=timeout)
    return result.get("packets", [])


def packet_summary(ffprobe, path, interval=None, timeout=60):
    cmd = [ffprobe, "-v", "error"]
    if interval:
        cmd += ["-read_intervals", interval]
    return checked_json([*cmd, "-show_streams", "-show_packets", "-show_entries",
                         "stream=index,codec_type:packet=stream_index,pts_time,size", "-of", "json", str(path)], timeout=timeout)


def video_payload(summary, start=None, end=None):
    video = next(s["index"] for s in summary["streams"] if s["codec_type"] == "video")
    packets = [p for p in summary.get("packets", []) if p["stream_index"] == video
               and (start is None or start <= float(p.get("pts_time", "-inf")) < end)]
    return len(packets), sum(int(p["size"]) for p in packets)


def comparison_window(start, seconds):
    # Demux order differs from presentation order (e.g. HEVC B frames).
    # Read beyond both boundaries, then filter by PTS, never by read count.
    return f"{max(0, start - 5):g}%{start + seconds + 5:g}"


def matching_timeline(source, output, start, end):
    def timestamps(summary, lower=None, upper=None):
        video = next(s["index"] for s in summary["streams"] if s["codec_type"] == "video")
        return sorted(float(p["pts_time"]) for p in summary.get("packets", [])
                      if p["stream_index"] == video and "pts_time" in p
                      and (lower is None or lower <= float(p["pts_time"]) < upper))
    src, dst = timestamps(source, start, end), timestamps(output)
    return bool(src) and len(src) == len(dst) and len(set(src)) == len(src) and all(
        abs((a - src[0]) - (b - dst[0])) <= 0.002 for a, b in zip(src, dst))


def validate_options(args, source, max_seconds=10):
    if not math.isfinite(args.min_savings) or not 0 <= args.min_savings < 100 or not math.isfinite(args.hardware_stall_timeout) or args.hardware_stall_timeout < 5:
        raise ValueError("Savings and stall timeout must be finite and within supported bounds")
    if not source.is_file() or args.dolby_vision_policy != "hdr-preview" or args.dolby_preview_backend != "d3d11":
        raise ValueError("Delivery test requires one file, --dolby-vision-policy hdr-preview, and --dolby-preview-backend d3d11")
    if args.resolution != "keep" or args.delete_originals or args.overwrite_output or args.report:
        raise ValueError("Delivery test forbids resizing, deletion, overwrite, and external report writes")
    if not math.isfinite(args.preview_start) or args.preview_start < 0 or not 1 <= args.preview_seconds <= max_seconds:
        raise ValueError(f"Delivery test requires finite nonnegative start and duration 1..{max_seconds} seconds")
    if args.codec not in ("auto", "hevc"):
        raise ValueError("Delivery test currently validates HEVC only")


def allow_cpu(args, message, available, failed_vendor="amd"):
    from muxmender import emit_action, DOWNLOAD_URLS
    emit_action("MUXMENDER_HARDWARE_FAILURE", {"message": message, "cpu_available": available,
                "download_url": DOWNLOAD_URLS.get(failed_vendor, DOWNLOAD_URLS["ffmpeg"]), "native_delivery": True})
    if not available:
        return False
    if args.hardware_fallback == "cpu":
        return True
    if args.hardware_fallback == "ask" and sys.stdin.isatty():
        return input("Hardware failed. Use CPU for this test? [y/N] ").strip().lower() == "y"
    return False


def run(args, source):
    import muxmender as mm
    run_dir = None
    report = {"status": "initializing", "source": str(source), "originals_untouched": True,
              "scope": "bounded HDR PQ test; Dolby Vision dynamic metadata is not retained"}
    try:
        validate_options(args, source)
        helper = args.d3d11_helper.resolve()
        for tool in (args.ffmpeg, args.ffprobe):
            if shutil.which(tool) is None:
                mm.offer_requirement(mm.HardwareRequirementError("ffmpeg", f"Missing required executable: {tool}", mm.DOWNLOAD_URLS["ffmpeg"]), False)
                return 3
        if not helper.is_file() or not helper.with_name("muxmender-color-test.exe").is_file():
            mm.emit_action("MUXMENDER_REQUIREMENT", {"component": "native-runtime", "cpu_available": False,
                "message": "Native runtime missing. Build/package it with native/muxmender-d3d11/build-native.ps1 and package-runtime.py; or select an extracted runtime via --d3d11-helper.",
                "download_url": ""})
            return 3
        info = mm.probe(source, args.ffprobe)
        if info.dolby_vision_profile != 5 or info.dolby_vision_el_present:
            raise ValueError("Only single-layer Dolby Vision profile 5 is validated")
        available = mm.ffmpeg_encoder_names(args.ffmpeg)
        vendors = mm.gpu_vendors()
        try:
            selection = mm.select_encoder("hevc", args.hardware, available, vendors)
        except mm.HardwareRequirementError as exc:
            if not args.execute:
                print(f"Dry-run dependency check: {exc}; no GPU or output started", flush=True)
                return 3
            if not allow_cpu(args, str(exc), "libx265" in available, args.hardware):
                return 3
            selection = mm.EncoderSelection("cpu", "libx265")
        # No silent CPU selection when hardware auto-detection failed.
        if selection.vendor == "cpu" and args.hardware != "cpu" and not vendors:
            if not args.execute or not allow_cpu(args, "No supported GPU detected", "libx265" in available, "ffmpeg"):
                print("Select --hardware cpu explicitly if CPU testing is desired.")
                return 3
        report["encoder"] = selection.encoder
        print(f"PLAN: {args.preview_seconds:g}s at {info.width}x{info.height}; native PQ HDR -> {selection.encoder}; audio/subtitles copied", flush=True)
        print("Dolby Vision metadata is intentionally not retained. Original remains untouched.", flush=True)
        if not args.execute:
            print("DRY RUN: no GPU initialized, no outputs created. Stages: preflight, reconstruct, align streams, encode, verify, compare.")
            return 0
        before = source.stat()
        stage([str(helper.with_name("muxmender-color-test.exe"))], 1, timeout=30, stall=0)
        if selection.vendor != "cpu":
            synthetic = [args.ffmpeg, "-hide_banner", "-nostdin", "-f", "lavfi", "-i", "testsrc2=size=256x144:rate=24",
                         "-frames:v", "24", *mm.encoder_options("hevc", args.quality, replace(info, dolby_vision=False), selection.encoder),
                         "-progress", "pipe:1", "-nostats", "-f", "null", "-"]
            try:
                stage(synthetic, 1, timeout=30, stall=20)
            except RuntimeError as exc:
                if not allow_cpu(args, str(exc), "libx265" in available, selection.vendor):
                    return 4
                selection = mm.EncoderSelection("cpu", "libx265")
                report["encoder"] = selection.encoder
        parent = args.output_dir.resolve() if args.output_dir else source.parent / "muxmender-tests"
        parent.mkdir(parents=True, exist_ok=True)
        # Conservative room for two retained lossless intermediates.
        required = max(1024**3, int(info.width * info.height * 8 * 60 * args.preview_seconds * 2))
        if shutil.disk_usage(parent).free < required:
            raise RuntimeError(f"Insufficient free space for retained intermediates: allow {required / 1024**3:.1f} GiB")
        run_dir = parent / ("hdr-test-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        run_dir.mkdir(exist_ok=False)
        print(f"RUN DIRECTORY: {run_dir}", flush=True)
        reference = run_dir / "reference-pq.mkv"
        aligned = run_dir / "aligned-reference.mkv"
        output = run_dir / "preview-hevc.mkv"
        start, seconds = args.preview_start, args.preview_seconds
        stage([str(helper), "--input", str(source), "--output", str(reference), "--start", f"{start:g}",
               "--seconds", f"{seconds:g}", "--hdr-preview", "--progress-machine"], seconds, 0, 45, timeout=240, stall=40)
        stage(remux_command(args.ffmpeg, source, reference, aligned, start, seconds), seconds, 45, 10, stall=30)
        aligned_info = mm.probe(aligned, args.ffprobe)
        try:
            stage(encode_command(args.ffmpeg, aligned, output, aligned_info, selection.encoder, args.quality), seconds, 55, 30,
                  timeout=240, stall=args.hardware_stall_timeout)
        except RuntimeError as exc:
            if selection.vendor == "cpu" or not allow_cpu(args, str(exc), "libx265" in available, selection.vendor):
                raise
            # Never reuse or overwrite the failed GPU output.
            output = run_dir / "preview-hevc-cpu.mkv"
            selection = mm.EncoderSelection("cpu", "libx265")
            report["encoder"] = selection.encoder
            stage(encode_command(args.ffmpeg, aligned, output, aligned_info, selection.encoder, args.quality), seconds, 55, 30, timeout=300, stall=60)
        actual = mm.probe(output, args.ffprobe)
        ok, reason = mm.verify_output(aligned_info, output, args.ffprobe, 0, "hevc", enforce_min_savings=False)
        if not ok or (actual.color_primaries, actual.color_transfer, actual.color_space) != ("bt2020", "smpte2084", "bt2020nc"):
            raise RuntimeError(f"Output verification failed: {reason}")
        for kind in ("a", "s"):
            if packet_signatures(args.ffprobe, aligned, kind) != packet_signatures(args.ffprobe, output, kind):
                raise RuntimeError(f"{kind} packet payloads/timestamps changed")
        stage([args.ffmpeg, "-v", "error", "-nostdin", "-xerror", "-i", str(output), "-f", "null", "-"], seconds, timeout=120, stall=0)
        print("MUXMENDER_PROGRESS=90", flush=True)
        source_packets = packet_summary(args.ffprobe, source, comparison_window(start, seconds))
        output_packets = packet_summary(args.ffprobe, output)
        src_count, src_bytes = video_payload(source_packets, start, start + seconds)
        dst_count, dst_bytes = video_payload(output_packets)
        ref_count, _ = video_payload(packet_summary(args.ffprobe, reference))
        if ref_count != dst_count:
            raise RuntimeError("Video frame/packet count changed")
        timeline_matches = matching_timeline(source_packets, output_packets, start, start + seconds)
        comparable = src_count == dst_count and src_bytes > 0 and timeline_matches
        saving = (1 - dst_bytes / src_bytes) * 100 if comparable else None
        report["comparison"] = {"source_video_packets": src_count, "output_video_packets": dst_count,
            "source_video_payload_bytes": src_bytes, "output_video_payload_bytes": dst_bytes,
            "video_payload_saving_percent": saving, "comparable_packet_counts": src_count == dst_count,
            "matching_presentation_timeline": timeline_matches,
            "note": "Compare original compressed video payload in the same interval, NOT the FFV1 intermediate or whole-file size."}
        metric = stage([args.ffmpeg, "-hide_banner", "-nostdin", "-i", str(reference), "-i", str(output), "-filter_complex",
            "[0:v]format=yuv420p10le,setpts=PTS-STARTPTS[ref];[1:v]setpts=PTS-STARTPTS[enc];[ref][enc]ssim", "-an", "-f", "null", "-"], seconds, timeout=120, stall=0)
        match = re.search(r"All:([0-9.]+)", metric)
        report["ssim_reconstructed_pq_reference"] = float(match[1]) if match else None
        report["quality_caveat"] = "SSIM after matched chroma sampling does not prove identical perceptual quality or Dolby Vision preservation. Review playback."
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError("Source size/mtime changed externally during test; stop and investigate")
        report.update(status="verified-test", output=str(output), width=actual.width, height=actual.height,
                      audio_subtitle_packets_unchanged=True, original_stat_unchanged=True,
                      min_savings_met=comparable and saving >= args.min_savings)
        print(f"VERIFIED: {output}", flush=True)
        print(f"Original segment video-payload savings: {saving:.2f}%" if comparable else "Original comparison inconclusive: packet counts or presentation timestamps differ", flush=True)
        print("MUXMENDER_PROGRESS=100", flush=True)
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report.update(status="failed", error=str(exc))
        print(f"FAILED: {exc}. Originals untouched; all outputs retained.", flush=True)
        return 4
    finally:
        if run_dir:
            with (run_dir / "validation.json").open("x", encoding="utf-8") as out:
                json.dump(report, out, indent=2)
            print(f"Validation report: {run_dir / 'validation.json'}", flush=True)
