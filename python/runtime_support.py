"""Standalone terminal UX and non-mutating dependency inspection."""
import shutil
import subprocess
import sys
import time
from collections import deque
import os
import ctypes
import math
import re
from pathlib import Path


def frame_evidence_percent(path, duration):
    """Read only a bounded tail of an in-progress JSON/compact ffprobe audit."""
    if not duration or not math.isfinite(duration) or duration <= 0:
        return None
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell()-65536))
            tail = stream.read().decode('utf-8', errors='replace')
        matches = re.findall(r'best_effort_timestamp_time["=:\s]+([0-9]+(?:\.[0-9]+)?)(?=["|\s,])', tail)
        return min(99.9, max(0., 100*float(matches[-1])/duration)) if matches else None
    except OSError:
        return None  # Telemetry must never interrupt validation.


def process_memory_bytes(process):
    """Measured resident high-water mark; None if unavailable on this platform."""
    if os.name == 'nt':
        from ctypes import wintypes
        class Memory(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (n, ctypes.c_size_t) for n in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        memory = Memory(); memory.cb = ctypes.sizeof(memory)
        query = ctypes.WinDLL('psapi').GetProcessMemoryInfo
        query.argtypes = [ctypes.c_void_p, ctypes.POINTER(Memory), ctypes.c_ulong]
        if query(int(process._handle), ctypes.byref(memory), ctypes.sizeof(memory)):
            return max(memory.PeakWorkingSetSize, memory.PeakPagefileUsage)
    elif sys.platform.startswith('linux'):
        try:
            values = dict(line.split(':', 1) for line in Path(f'/proc/{process.pid}/status').read_text().splitlines() if ':' in line)
            return max(int(values[k].split()[0])*1024 for k in ('VmRSS', 'VmHWM'))
        except (OSError, KeyError, ValueError):
            pass
    return None


def guard_ordered_mux_memory(process, command, limit=1024**3):
    if '-max_interleave_delta' not in command or command[command.index('-max_interleave_delta')+1] != '0':
        return
    used = process_memory_bytes(process)
    if used is None and process.poll() is None:
        raise RuntimeError('Ordered mux memory monitoring unavailable; partial retained')
    if used is not None and used > limit:
        raise RuntimeError('Ordered mux exceeded 1 GiB memory guard; partial retained')


class TerminalProgress:
    def __init__(self, label="Encoding", stream=None, machine=True):
        self.stream = stream or sys.stdout
        self.label = label
        self.started = time.monotonic()
        self.last = -1
        self.machine = machine
        self.samples = deque()
        self.last_print = self.started
        self.eta_seconds = None

    def update(self, percent):
        percent = max(0.0, min(100.0, percent))
        now = time.monotonic()
        if self.samples and percent < self.samples[-1][1]:
            self.samples.clear()
        self.samples.append((now, percent))
        while len(self.samples) > 1 and self.samples[0][0] < now - 120:
            self.samples.popleft()
        span = now - self.samples[0][0]
        advance = percent - self.samples[0][1]
        self.eta_seconds = (100 - percent) * span / advance if span >= 10 and advance > 0 else None
        if percent >= 100:
            self.eta_seconds = 0
        if int(percent) <= self.last and now - self.last_print < 5:
            return
        self.last = int(percent)
        self.last_print = now
        elapsed = now - self.started
        eta = f"{self.eta_seconds:.0f}s" if self.eta_seconds is not None else "estimating"
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
