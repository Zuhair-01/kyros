"""Shared-GPU mutex for a single-card machine running multiple AI jobs.

One lock file, one holder at a time. A holder whose process has died
(crashed without releasing) is detected via `tasklist` and cleared
automatically, so a crash can't leave the card permanently locked.

This is the real coordination primitive Kyros uses in production: several
independent local-AI processes (a video-clipping pipeline, a chat model,
a vision model) share one 8GB card, and nothing may load a model onto it
without acquiring this lock first.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LOCK_PATH = Path(os.environ.get("KYROS_GPU_LOCK_PATH", "./.gpu.lock"))
MIN_FREE_MIB = int(os.environ.get("KYROS_GPU_MIN_FREE_MIB", "7000"))


@dataclass(frozen=True, slots=True)
class LockHolder:
    owner: str
    pid: int
    ts: str


def _pid_alive(pid: int) -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        return str(pid) in out
    except Exception:
        return False


class GPULock:
    """File-based mutex over a single GPU, scoped to `lock_path`."""

    def __init__(self, lock_path: Path = DEFAULT_LOCK_PATH, min_free_mib: int = MIN_FREE_MIB):
        self.lock_path = Path(lock_path)
        self.min_free_mib = min_free_mib

    def _read(self) -> LockHolder | None:
        if not self.lock_path.exists():
            return None
        try:
            data = json.loads(self.lock_path.read_text())
            if not _pid_alive(data["pid"]):
                self.lock_path.unlink(missing_ok=True)  # stale: holder crashed
                return None
            return LockHolder(**data)
        except Exception:
            self.lock_path.unlink(missing_ok=True)  # corrupt: treat as stale
            return None

    def free_vram_mib(self) -> int | None:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            return int(out.splitlines()[0])
        except Exception:
            return None

    def status(self) -> LockHolder | None:
        return self._read()

    def acquire(self, owner: str, pid: int, force: bool = False) -> bool:
        held = self._read()
        if held and not force:
            return False

        free = self.free_vram_mib()
        if free is not None and free < self.min_free_mib and not force:
            return False

        self.lock_path.write_text(json.dumps({
            "owner": owner, "pid": pid, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }))
        return True

    def release(self, pid: int) -> bool:
        held = self._read()
        if held and held.pid == pid:
            self.lock_path.unlink(missing_ok=True)
            return True
        return False


def _main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    owner = sys.argv[2] if len(sys.argv) > 2 else "unknown"
    force = "--force" in sys.argv
    pid = int(sys.argv[sys.argv.index("--pid") + 1]) if "--pid" in sys.argv else os.getpid()

    lock = GPULock()
    if cmd == "status":
        held = lock.status()
        free = lock.free_vram_mib()
        print(f"free VRAM: {free} MiB" if free is not None else "free VRAM: unknown (nvidia-smi not found)")
        print(f"lock held by: {held}" if held else "lock: free")
    elif cmd == "acquire":
        ok = lock.acquire(owner, pid, force=force)
        print(f"LOCK ACQUIRED by '{owner}' (pid {pid})" if ok else "REFUSED: lock held or insufficient free VRAM")
        sys.exit(0 if ok else 1)
    elif cmd == "release":
        ok = lock.release(pid)
        print("LOCK RELEASED" if ok else "not releasing: no lock held by this pid")
    else:
        print("usage: gpu_lock.py [status|acquire <owner>|release] [--force] [--pid <N>]")
        sys.exit(2)


if __name__ == "__main__":
    _main()
