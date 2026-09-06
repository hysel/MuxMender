"""Standalone terminal UX and non-mutating dependency inspection."""
import shutil
import subprocess
import sys
import time


class TerminalProgress:
    def __init__(self, label="Encoding", stream=None, machine=True):
        self.stream = stream or sys.stdout
        self.label = label
        self.started = time.monotonic()
        self.last = -1
        self.machine = machine

    def update(self, percent):
        percent = max(0.0, min(100.0, percent))
        if int(percent) <= self.last:
            return
        self.last = int(percent)
        elapsed = time.monotonic() - self.started
        eta = f"{elapsed * (100 - percent) / percent:.0f}s" if percent > 0 else "estimating"
        filled = int(percent / 5)
        print(f"{self.label} [{'=' * filled}{' ' * (20 - filled)}] {percent:5.1f}% | elapsed {elapsed:.0f}s | ETA {eta}",
              file=self.stream, flush=True)
        # Keep the existing machine protocol for optional integrations.
        if self.machine:
            print(f"MUXMENDER_PROGRESS={percent:.1f}", file=self.stream, flush=True)


def check_dependencies(args):
    import muxmender as mm
    failures = []
    print("MuxMender dependency check (no media opened, no GPU encoding or installation)")
    for label, executable in (("FFmpeg", args.ffmpeg), ("FFprobe", args.ffprobe)):
        resolved = shutil.which(executable)
        if not resolved:
            failures.append(f"{label} not found: {executable}")
            continue
        try:
            result = subprocess.run([resolved, "-version"], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=15)
            if result.returncode:
                raise RuntimeError(result.stderr[-500:])
            print(f"{label}: {resolved}\n  {result.stdout.splitlines()[0]}")
        except (OSError, RuntimeError, subprocess.TimeoutExpired, IndexError) as exc:
            failures.append(f"{label}: {exc}")
    if not failures:
        try:
            available = mm.ffmpeg_encoder_names(args.ffmpeg)
            vendors = mm.gpu_vendors()
            print("Detected GPU vendors: " + (", ".join(vendors) or "none"))
            for vendor, codecs in mm.HARDWARE_ENCODERS.items():
                print(f"{vendor}: " + ", ".join(f"{name}={'listed' if name in available else 'missing'}" for name in codecs.values()))
            selection = mm.select_encoder(mm.choose_target_codec(args.codec), args.hardware, available, vendors)
            print(f"Requested selection: {selection.label}")
            print("Listed encoders do not prove that the GPU/driver can run them; execution must validate that separately.")
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            failures.append(str(exc))
    if args.dolby_preview_backend == "d3d11":
        helper = args.d3d11_helper.resolve()
        try:
            if not helper.with_name("muxmender-color-test.exe").is_file():
                raise RuntimeError("native color-test helper is missing")
            result = subprocess.run([str(helper), "--help"], capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=15)
            if result.returncode:
                raise RuntimeError(f"native helper exited {result.returncode}; check adjacent DLLs/runtime")
            print(f"Native runtime load check: OK ({helper}); GPU color preflight is performed only on execution")
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            failures.append(f"Native runtime: {exc}")
    for failure in failures:
        print(f"MISSING/FAILED: {failure}")
    if failures:
        print(f"FFmpeg/FFprobe official download: {mm.DOWNLOAD_URLS['ffmpeg']}")
        print("Native runtime: build/package native/muxmender-d3d11 or select an extracted runtime with --d3d11-helper.")
        print("No software was installed. Install only the missing component, then repeat this check.")
    return 3 if failures else 0
