"""Dump logs from a connected Android device with ADB."""
import subprocess
from pathlib import Path

BUFFERS = ["main", "system", "crash", "radio"]


def _adb(args: list[str], serial: str | None, runner) -> subprocess.CompletedProcess:
    command = ["adb"] + (["-s", serial] if serial else []) + args
    try:
        return runner(command, capture_output=True, timeout=120)
    except FileNotFoundError as error:
        raise RuntimeError("adb was not found. Install Android platform-tools and add it to PATH.") from error


def collect(out_file: str | Path, serial: str | None = None, runner=subprocess.run) -> Path:
    """Save the current log buffers into one file, in time order. Device logs are not cleared."""
    state = _adb(["get-state"], serial, runner)
    if state.returncode != 0 or b"device" not in state.stdout:
        detail = state.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"No usable device. {detail}")

    buffer_args = [arg for name in BUFFERS for arg in ("-b", name)]
    dump = _adb(["logcat", *buffer_args, "-d", "-v", "threadtime"], serial, runner)
    if dump.returncode != 0:
        raise RuntimeError(f"adb logcat failed: {dump.stderr.decode(errors='replace').strip()}")

    path = Path(out_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dump.stdout)
    return path
