import json
import os
import time

from kyros.gpu_lock import GPULock, LockHolder

# Liveness is checked against real OS processes, so tests that need a "live"
# holder use this process's own pid rather than an arbitrary made-up number.
SELF_PID = os.getpid()


def test_acquire_when_free_and_release(tmp_path):
    lock = GPULock(lock_path=tmp_path / "gpu.lock", min_free_mib=0)
    assert lock.acquire("job-a", pid=SELF_PID)
    assert lock.status() is not None
    assert lock.release(pid=SELF_PID)
    assert lock.status() is None


def test_second_acquire_refused_while_held(tmp_path):
    lock = GPULock(lock_path=tmp_path / "gpu.lock", min_free_mib=0)
    assert lock.acquire("job-a", pid=SELF_PID)
    assert not lock.acquire("job-b", pid=SELF_PID + 1)


def test_force_overrides_existing_holder(tmp_path):
    lock = GPULock(lock_path=tmp_path / "gpu.lock", min_free_mib=0)
    lock.acquire("job-a", pid=SELF_PID)
    assert lock.acquire("job-b", pid=SELF_PID, force=True)


def test_stale_lock_from_dead_pid_is_cleared(tmp_path):
    lock_path = tmp_path / "gpu.lock"
    # PID 999999 should not correspond to a real running process.
    lock_path.write_text(json.dumps({"owner": "dead-job", "pid": 999999, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}))
    lock = GPULock(lock_path=lock_path, min_free_mib=0)
    assert lock.status() is None
    assert lock.acquire("job-b", pid=222)


def test_release_by_non_holder_is_a_noop(tmp_path):
    lock = GPULock(lock_path=tmp_path / "gpu.lock", min_free_mib=0)
    lock.acquire("job-a", pid=SELF_PID)
    assert not lock.release(pid=SELF_PID + 1)
    assert lock.status() is not None
