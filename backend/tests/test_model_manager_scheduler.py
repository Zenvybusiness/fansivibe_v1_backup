"""Comprehensive test suite for Phase 2 Batch 1: Two-Tier Shared GPU Scheduler.

Verifies:
- Concurrent asyncio tasks mutual exclusion
- Multiple threads mutual exclusion
- Cross-process mutual exclusion via real subprocesses
- Priority ordering (P1 > P2 > P3) and FIFO ordering for equal priority
- Queue depth limits and saturation rejection
- Acquisition timeout handling
- Cancellation before acquisition
- Cancellation during execution with confirmed termination
- Quarantine after uncertain termination
- Explicit quarantine recovery procedure
- Process crash and natural kernel lock release
- Atomic metadata file writing and restrictive 0o600 permissions
- Metadata cannot override kernel lock ownership
- Scheduler shutdown handling
- Zero leaked file descriptors across repeated leases
"""

from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
import stat
import subprocess
import sys
import threading
import time
from typing import Any

import pytest

from app.ai.manager.scheduler import GPUResourceScheduler
from app.ai.manager.types import (
    GPUSchedulerLease,
    GPUResourceQuarantinedError,
    LeaseState,
    SchedulerQueueFullError,
    SchedulerShutdownError,
    SchedulerTimeoutError,
    WorkloadType,
)


def _make_scheduler(tmp_path, **kwargs) -> GPUResourceScheduler:
    """Helper to create an isolated GPUResourceScheduler with tmp paths."""
    lockfile = str(tmp_path / "test_gpu.lock")
    metadata = str(tmp_path / "test_gpu_lease.json")
    quarantine = str(tmp_path / "test_gpu_quarantine.json")
    params = {
        "lockfile_path": lockfile,
        "metadata_path": metadata,
        "quarantine_path": quarantine,
        "poll_interval_s": 0.01,
        "grace_period_s": 0.1,
        "default_timeout_s": 2.0,
    }
    params.update(kwargs)
    return GPUResourceScheduler(**params)


# ---------------------------------------------------------------------------
# 1. Asyncio Tasks Concurrency & Mutual Exclusion
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_concurrent_asyncio_tasks_mutual_exclusion(tmp_path):
    """Multiple concurrent coroutines within the same loop must execute sequentially."""
    scheduler = _make_scheduler(tmp_path)
    concurrency_counter = 0
    max_concurrency = 0
    completed = []

    async def worker(task_id: int):
        nonlocal concurrency_counter, max_concurrency
        async with scheduler.acquire_lease("test-model", priority=1) as lease:
            concurrency_counter += 1
            if concurrency_counter > max_concurrency:
                max_concurrency = concurrency_counter
            assert concurrency_counter == 1, "GPU lease was held concurrently by >1 task!"
            await asyncio.sleep(0.04)
            concurrency_counter -= 1
            completed.append(task_id)

    tasks = [asyncio.create_task(worker(i)) for i in range(5)]
    await asyncio.gather(*tasks)

    assert len(completed) == 5
    assert max_concurrency == 1
    assert concurrency_counter == 0


# ---------------------------------------------------------------------------
# 2. Multiple Threads Mutual Exclusion
# ---------------------------------------------------------------------------


def test_multiple_threads_mutual_exclusion(tmp_path):
    """Multiple concurrent OS threads must execute synchronously without overlap."""
    scheduler = _make_scheduler(tmp_path)
    concurrency_counter = 0
    max_concurrency = 0
    lock = threading.Lock()
    completed = []

    def thread_worker(thread_id: int):
        nonlocal concurrency_counter, max_concurrency
        with scheduler.acquire_lease_sync("test-model", priority=1) as lease:
            with lock:
                concurrency_counter += 1
                if concurrency_counter > max_concurrency:
                    max_concurrency = concurrency_counter
            time.sleep(0.03)
            with lock:
                concurrency_counter -= 1
                completed.append(thread_id)

    threads = [threading.Thread(target=thread_worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert len(completed) == 4
    assert max_concurrency == 1
    assert concurrency_counter == 0


# ---------------------------------------------------------------------------
# 3. Cross-Process Mutual Exclusion (Subprocesses)
# ---------------------------------------------------------------------------


def _subprocess_gpu_worker(lockfile: str, metadata: str, quarantine: str, out_file: str, worker_id: int):
    """Subprocess target executing a fake GPU workload."""
    scheduler = GPUResourceScheduler(
        lockfile_path=lockfile,
        metadata_path=metadata,
        quarantine_path=quarantine,
        poll_interval_s=0.01,
        default_timeout_s=5.0,
    )
    with scheduler.acquire_lease_sync("test-model", priority=1) as lease:
        start_time = time.time()
        time.sleep(0.08)
        end_time = time.time()

        record = {
            "worker_id": worker_id,
            "pid": os.getpid(),
            "start": start_time,
            "end": end_time,
            "lease_id": lease.lease_id,
        }
        with open(out_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def test_cross_process_mutual_exclusion_subprocesses(tmp_path):
    """Real separate OS processes must never hold the GPU lease simultaneously."""
    lockfile = str(tmp_path / "proc_gpu.lock")
    metadata = str(tmp_path / "proc_gpu_lease.json")
    quarantine = str(tmp_path / "proc_gpu_quarantine.json")
    out_file = str(tmp_path / "execution_log.jsonl")

    ctx = multiprocessing.get_context("spawn")
    procs = []
    for i in range(4):
        p = ctx.Process(
            target=_subprocess_gpu_worker,
            args=(lockfile, metadata, quarantine, out_file, i),
        )
        procs.append(p)

    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=10.0)
        assert p.exitcode == 0

    # Read records and assert strict non-overlapping execution intervals
    assert os.path.exists(out_file)
    records = []
    with open(out_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    assert len(records) == 4
    records.sort(key=lambda r: r["start"])

    for i in range(len(records) - 1):
        curr_end = records[i]["end"]
        next_start = records[i + 1]["start"]
        # Allow tiny clock granularity margin (<= 0.001s)
        assert curr_end <= next_start + 0.005, (
            f"Overlapping GPU execution detected! Worker {records[i]['worker_id']} ended at {curr_end}, "
            f"but Worker {records[i+1]['worker_id']} started at {next_start}"
        )


# ---------------------------------------------------------------------------
# 4. Priority Ordering and FIFO Ordering
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_priority_ordering(tmp_path):
    """Lower priority integer (Priority 1) must be dispatched ahead of higher integers (P2, P3)."""
    scheduler = _make_scheduler(tmp_path)
    execution_order = []

    # Block scheduler with initial lease
    blocking_lease = await scheduler._do_acquire_async(
        model_id="blocker",
        workload_type=WorkloadType.REASONING_VISION,
        priority=1,
        timeout_s=5.0,
        acquisition_timeout_s=5.0,
        abort_fn=None,
        is_workload_stopped=None,
    )

    async def enqueued_task(name: str, priority: int):
        async with scheduler.acquire_lease("model", priority=priority) as lease:
            execution_order.append(name)

    # Enqueue tasks in reverse priority order: P3 (Warmup), P2 (Diffusion), P1 (Interactive)
    t3 = asyncio.create_task(enqueued_task("P3_warmup", priority=3))
    t2 = asyncio.create_task(enqueued_task("P2_diffusion", priority=2))
    t1 = asyncio.create_task(enqueued_task("P1_interactive", priority=1))

    # Give event loop a moment to enqueue all waiters
    await asyncio.sleep(0.02)

    # Release blocker; Tier 1 should dispatch P1, then P2, then P3
    await scheduler.release_lease(blocking_lease)
    await asyncio.gather(t1, t2, t3)

    assert execution_order == ["P1_interactive", "P2_diffusion", "P3_warmup"]


@pytest.mark.anyio
async def test_fifo_ordering_for_equal_priority(tmp_path):
    """Tasks with identical priority must be dispatched in FIFO order of enqueue."""
    scheduler = _make_scheduler(tmp_path)
    execution_order = []

    blocking_lease = await scheduler._do_acquire_async(
        model_id="blocker",
        workload_type=WorkloadType.REASONING_VISION,
        priority=1,
        timeout_s=5.0,
        acquisition_timeout_s=5.0,
        abort_fn=None,
        is_workload_stopped=None,
    )

    async def enqueued_task(name: str):
        async with scheduler.acquire_lease("model", priority=1) as lease:
            execution_order.append(name)

    t1 = asyncio.create_task(enqueued_task("Task_1"))
    await asyncio.sleep(0.005)
    t2 = asyncio.create_task(enqueued_task("Task_2"))
    await asyncio.sleep(0.005)
    t3 = asyncio.create_task(enqueued_task("Task_3"))

    await asyncio.sleep(0.02)
    await scheduler.release_lease(blocking_lease)
    await asyncio.gather(t1, t2, t3)

    assert execution_order == ["Task_1", "Task_2", "Task_3"]


# ---------------------------------------------------------------------------
# 5. Queue Limits and Saturation Rejection
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_queue_depth_limits(tmp_path):
    """When queue depth reaches max_queue_depth, new requests are rejected immediately."""
    scheduler = _make_scheduler(tmp_path, max_queue_depth=2)

    blocking_lease = await scheduler._do_acquire_async(
        model_id="blocker",
        workload_type=WorkloadType.REASONING_VISION,
        priority=1,
        timeout_s=5.0,
        acquisition_timeout_s=5.0,
        abort_fn=None,
        is_workload_stopped=None,
    )

    async def waiter():
        async with scheduler.acquire_lease("model", priority=1):
            pass

    t1 = asyncio.create_task(waiter())
    t2 = asyncio.create_task(waiter())
    await asyncio.sleep(0.01)

    # Queue currently has 2 waiters (limit reached). 3rd attempt must fail immediately
    with pytest.raises(SchedulerQueueFullError) as exc_info:
        await scheduler._do_acquire_async(
            model_id="overflow",
            workload_type=WorkloadType.REASONING_VISION,
            priority=1,
            timeout_s=1.0,
            acquisition_timeout_s=1.0,
            abort_fn=None,
            is_workload_stopped=None,
        )

    assert exc_info.value.current_depth == 2
    assert exc_info.value.max_depth == 2

    await scheduler.release_lease(blocking_lease)
    await asyncio.gather(t1, t2)


# ---------------------------------------------------------------------------
# 6. Acquisition Timeout Handling
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_acquisition_timeout(tmp_path):
    """When waiting for a lease exceeds acquisition timeout, raises SchedulerTimeoutError."""
    scheduler = _make_scheduler(tmp_path)

    blocking_lease = await scheduler._do_acquire_async(
        model_id="blocker",
        workload_type=WorkloadType.REASONING_VISION,
        priority=1,
        timeout_s=5.0,
        acquisition_timeout_s=5.0,
        abort_fn=None,
        is_workload_stopped=None,
    )

    t0 = time.monotonic()
    with pytest.raises(SchedulerTimeoutError) as exc_info:
        await scheduler._do_acquire_async(
            model_id="timed_out_requester",
            workload_type=WorkloadType.REASONING_VISION,
            priority=1,
            timeout_s=1.0,
            acquisition_timeout_s=0.08,
            abort_fn=None,
            is_workload_stopped=None,
        )

    elapsed = time.monotonic() - t0
    assert 0.05 <= elapsed <= 0.25
    assert exc_info.value.phase == "acquisition"

    # Blocker must still be active and releasable cleanly
    await scheduler.release_lease(blocking_lease)


# ---------------------------------------------------------------------------
# 7. Cancellation Before Acquisition
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cancellation_before_acquisition(tmp_path):
    """Cancelling a task while queued must remove it cleanly without holding locks."""
    scheduler = _make_scheduler(tmp_path)

    blocking_lease = await scheduler._do_acquire_async(
        model_id="blocker",
        workload_type=WorkloadType.REASONING_VISION,
        priority=1,
        timeout_s=5.0,
        acquisition_timeout_s=5.0,
        abort_fn=None,
        is_workload_stopped=None,
    )

    started_wait = asyncio.Event()

    async def waiting_task():
        started_wait.set()
        async with scheduler.acquire_lease("queued-model", priority=1):
            pass

    task = asyncio.create_task(waiting_task())
    await started_wait.wait()
    await asyncio.sleep(0.01)

    assert scheduler.get_queue_status()["queue_depth"] == 1

    # Cancel the waiting task
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Queue depth drops back to 0
    assert scheduler.get_queue_status()["queue_depth"] == 0

    await scheduler.release_lease(blocking_lease)


# ---------------------------------------------------------------------------
# 8. Cancellation During Execution with Confirmed Termination
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cancellation_during_execution_with_confirmed_termination(tmp_path):
    """When cancelled, if workload confirms termination within grace period, releases cleanly."""
    scheduler = _make_scheduler(tmp_path, grace_period_s=0.2)
    aborted_called = False
    stopped_check_called = 0

    def fake_abort():
        nonlocal aborted_called
        aborted_called = True

    def fake_is_stopped():
        nonlocal stopped_check_called
        stopped_check_called += 1
        return True  # Workload confirmed stopped immediately

    task_in_lease = asyncio.Event()

    async def workload():
        async with scheduler.acquire_lease(
            "model",
            abort_fn=fake_abort,
            is_workload_stopped=fake_is_stopped,
        ) as lease:
            task_in_lease.set()
            await asyncio.sleep(10.0)

    task = asyncio.create_task(workload())
    await task_in_lease.wait()

    # Cancel while executing in lease
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert aborted_called is True
    assert stopped_check_called >= 1
    assert scheduler.is_quarantined() is False

    # Next lease must acquire cleanly without quarantine block
    async with scheduler.acquire_lease("model-2") as lease2:
        assert lease2.state == LeaseState.RUNNING


# ---------------------------------------------------------------------------
# 9. Quarantine After Uncertain Termination
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_quarantine_after_uncertain_termination(tmp_path):
    """When cancelled, if workload cannot be verified stopped, transitions to QUARANTINED."""
    scheduler = _make_scheduler(tmp_path, grace_period_s=0.08)

    def stubborn_workload_check():
        return False  # Workload is still running / unconfirmed!

    task_in_lease = asyncio.Event()

    async def stubborn_workload():
        async with scheduler.acquire_lease(
            "model",
            is_workload_stopped=stubborn_workload_check,
        ) as lease:
            task_in_lease.set()
            await asyncio.sleep(10.0)

    task = asyncio.create_task(stubborn_workload())
    await task_in_lease.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Verified invariant: Uncertain workload triggers QUARANTINE!
    assert scheduler.is_quarantined() is True
    evidence = scheduler.get_quarantine_evidence()
    assert evidence is not None
    assert "Workload termination unconfirmed" in evidence["reason"]

    # All future lease acquisitions must be rejected with GPUResourceQuarantinedError
    with pytest.raises(GPUResourceQuarantinedError):
        async with scheduler.acquire_lease("next-model"):
            pass


# ---------------------------------------------------------------------------
# 10. Explicit Quarantine Recovery Procedure
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_explicit_quarantine_recovery_procedure(tmp_path):
    """Quarantine requires explicit, safe recovery check or force=True to be cleared."""
    scheduler = _make_scheduler(tmp_path, grace_period_s=0.05)

    # Force quarantine
    task_in_lease = asyncio.Event()

    async def rogue():
        async with scheduler.acquire_lease("model", is_workload_stopped=lambda: False):
            task_in_lease.set()
            await asyncio.sleep(10.0)

    task = asyncio.create_task(rogue())
    await task_in_lease.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert scheduler.is_quarantined() is True

    # 1. Attempt clearing without hardware check and without force -> Rejected
    res = scheduler.clear_quarantine(force=False)
    assert res is False
    assert scheduler.is_quarantined() is True

    # 2. Hardware check returning False -> Rejected
    res = scheduler.clear_quarantine(force=False, hardware_check=lambda: False)
    assert res is False
    assert scheduler.is_quarantined() is True

    # 3. Hardware check returning True -> Approved and cleared!
    res = scheduler.clear_quarantine(force=False, hardware_check=lambda: True)
    assert res is True
    assert scheduler.is_quarantined() is False

    # New lease succeeds
    async with scheduler.acquire_lease("cleared-model") as lease:
        assert lease.state == LeaseState.RUNNING


# ---------------------------------------------------------------------------
# 11. Process Crash and Natural Kernel Lock Release
# ---------------------------------------------------------------------------


def _crashing_subprocess(lockfile: str, metadata: str, quarantine: str):
    """Subprocess that acquires the kernel lock and abruptly crashes with os._exit."""
    scheduler = GPUResourceScheduler(
        lockfile_path=lockfile,
        metadata_path=metadata,
        quarantine_path=quarantine,
    )
    lease = scheduler._do_acquire_sync(
        model_id="crashing-worker",
        workload_type=WorkloadType.REASONING_VISION,
        priority=1,
        timeout_s=5.0,
        acquisition_timeout_s=5.0,
        abort_fn=None,
        is_workload_stopped=None,
    )
    # Abrupt process crash while holding lock! (os._exit does not run atexit or finally blocks)
    os._exit(42)


def test_process_crash_and_natural_kernel_lock_release(tmp_path):
    """When a process holding the lock dies, the OS kernel naturally drops fcntl.flock."""
    lockfile = str(tmp_path / "crash_test.lock")
    metadata = str(tmp_path / "crash_test.json")
    quarantine = str(tmp_path / "crash_test_quarantine.json")

    ctx = multiprocessing.get_context("spawn")
    p = ctx.Process(
        target=_crashing_subprocess,
        args=(lockfile, metadata, quarantine),
    )
    p.start()
    p.join(timeout=5.0)
    assert p.exitcode == 42

    # Now verify a new scheduler can acquire the lock immediately without deadlock
    scheduler = GPUResourceScheduler(
        lockfile_path=lockfile,
        metadata_path=metadata,
        quarantine_path=quarantine,
        default_timeout_s=1.0,
    )
    with scheduler.acquire_lease_sync("recovered-worker") as lease:
        assert lease.state == LeaseState.RUNNING
        assert lease.holder_pid == os.getpid()


# ---------------------------------------------------------------------------
# 12. Atomic Lease Metadata and Restrictive 0o600 Permissions
# ---------------------------------------------------------------------------


def test_atomic_lease_metadata_and_permissions(tmp_path):
    """Metadata must be written atomically with 0o600 permissions, and lockfile must be 0o600."""
    scheduler = _make_scheduler(tmp_path)

    with scheduler.acquire_lease_sync("qwen3-vl:4b-instruct", priority=1) as lease:
        assert os.path.exists(scheduler.lockfile_path)
        assert os.path.exists(scheduler.metadata_path)

        # Check permissions
        lock_mode = stat.S_IMODE(os.stat(scheduler.lockfile_path).st_mode)
        meta_mode = stat.S_IMODE(os.stat(scheduler.metadata_path).st_mode)
        assert lock_mode == 0o600
        assert meta_mode == 0o600

        # Read metadata and verify content
        with open(scheduler.metadata_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["lease_id"] == lease.lease_id
        assert data["holder_pid"] == os.getpid()
        assert data["model_id"] == "qwen3-vl:4b-instruct"
        assert data["state"] == "RUNNING"

    # After exit, metadata shows RELEASED
    with open(scheduler.metadata_path, "r", encoding="utf-8") as f:
        released_data = json.load(f)
    assert released_data["state"] == "RELEASED"


# ---------------------------------------------------------------------------
# 13. Metadata Cannot Override Kernel Lock Ownership
# ---------------------------------------------------------------------------


def test_metadata_cannot_override_kernel_lock(tmp_path):
    """Kernel flock is authoritative; bogus metadata does not block lock acquisition."""
    scheduler = _make_scheduler(tmp_path)

    # Fabricate fake active metadata
    bogus = {
        "lease_id": "fake-lease",
        "holder_pid": 9999999,
        "state": "RUNNING",
    }
    with open(scheduler.metadata_path, "w", encoding="utf-8") as f:
        json.dump(bogus, f)

    # Since no process holds flock, acquire must succeed immediately
    with scheduler.acquire_lease_sync("real-model") as lease:
        assert lease.state == LeaseState.RUNNING
        assert lease.holder_pid == os.getpid()


# ---------------------------------------------------------------------------
# 14. Scheduler Shutdown Handling
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_scheduler_shutdown(tmp_path):
    """Shutdown cancels queued requests and rejects future leases with SchedulerShutdownError."""
    scheduler = _make_scheduler(tmp_path)

    blocking_lease = await scheduler._do_acquire_async(
        model_id="blocker",
        workload_type=WorkloadType.REASONING_VISION,
        priority=1,
        timeout_s=5.0,
        acquisition_timeout_s=5.0,
        abort_fn=None,
        is_workload_stopped=None,
    )

    waiter_failed = False

    async def waiter():
        nonlocal waiter_failed
        try:
            async with scheduler.acquire_lease("queued"):
                pass
        except SchedulerShutdownError:
            waiter_failed = True

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0.01)

    # Initiate shutdown
    await scheduler.shutdown(timeout_s=0.1)
    await task
    assert waiter_failed is True

    # Future acquire rejected
    with pytest.raises(SchedulerShutdownError):
        async with scheduler.acquire_lease("new-request"):
            pass

    await scheduler.release_lease(blocking_lease)


# ---------------------------------------------------------------------------
# 15. No Leaked File Descriptors Across Leases
# ---------------------------------------------------------------------------


def test_no_leaked_file_descriptors(tmp_path):
    """Repeatedly acquiring and releasing leases must not leak file descriptors."""
    scheduler = _make_scheduler(tmp_path)

    def get_open_fd_count() -> int:
        fd_dir = f"/proc/{os.getpid()}/fd"
        if os.path.exists(fd_dir):
            return len(os.listdir(fd_dir))
        return 0

    initial_fds = get_open_fd_count()

    # Perform 25 sequential acquisitions
    for _ in range(25):
        with scheduler.acquire_lease_sync("leak-check") as lease:
            assert lease.state == LeaseState.RUNNING

    final_fds = get_open_fd_count()
    if initial_fds > 0:
        # Fd count must be completely stable (no growth)
        assert final_fds <= initial_fds + 1


# ---------------------------------------------------------------------------
# 16. Execution Timeout While Inference Running (Confirmed vs Uncertain)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_timeout_while_inference_is_running_with_confirmed_termination(tmp_path):
    """When execution exceeds timeout_s and workload confirms termination, releases cleanly."""
    scheduler = _make_scheduler(tmp_path, grace_period_s=0.2)
    stopped_called = False

    def check_stopped():
        nonlocal stopped_called
        stopped_called = True
        return True

    with pytest.raises(TimeoutError):
        async with scheduler.acquire_lease(
            "timeout-model",
            timeout_s=0.08,
            is_workload_stopped=check_stopped,
        ):
            await asyncio.sleep(2.0)

    assert stopped_called is True
    assert scheduler.is_quarantined() is False

    # Next acquire works cleanly
    async with scheduler.acquire_lease("next-model") as lease:
        assert lease.state == LeaseState.RUNNING


@pytest.mark.anyio
async def test_timeout_while_inference_is_running_with_uncertain_termination_quarantines(tmp_path):
    """When execution exceeds timeout_s and workload cannot confirm termination, quarantines."""
    scheduler = _make_scheduler(tmp_path, grace_period_s=0.08)

    with pytest.raises(TimeoutError):
        async with scheduler.acquire_lease(
            "timeout-model",
            timeout_s=0.08,
            is_workload_stopped=lambda: False,
        ):
            await asyncio.sleep(2.0)

    # Invariant: Never release lease on timeout if workload termination is uncertain
    assert scheduler.is_quarantined() is True
    evidence = scheduler.get_quarantine_evidence()
    assert evidence is not None
    assert "Workload termination unconfirmed" in evidence["reason"]

    # Blocked from acquiring next lease
    with pytest.raises(GPUResourceQuarantinedError):
        async with scheduler.acquire_lease("next-model"):
            pass


# ---------------------------------------------------------------------------
# 17. Fork Safety Resets Child State
# ---------------------------------------------------------------------------


def test_fork_safety_resets_child_state(tmp_path):
    """Child process created via fork must detect fork and not corrupt parent's scheduler state."""
    scheduler = _make_scheduler(tmp_path)

    # Parent acquires lease
    parent_lease = scheduler._do_acquire_sync(
        model_id="parent-model",
        workload_type=WorkloadType.REASONING_VISION,
        priority=1,
        timeout_s=5.0,
        acquisition_timeout_s=5.0,
        abort_fn=None,
        is_workload_stopped=None,
    )
    assert parent_lease._lock_fd is not None

    def child_proc(q):
        # Child checks its state
        scheduler._check_fork()
        child_active = scheduler._active_lease
        q.put(child_active is None)

    q = multiprocessing.Queue()
    ctx = multiprocessing.get_context("fork")
    p = ctx.Process(target=child_proc, args=(q,))
    p.start()
    p.join(timeout=5.0)

    child_cleared = q.get()
    assert child_cleared is True, "Forked child did not reset inherited active lease!"

    # Parent lease is still valid and held
    scheduler._release_kernel_lock(parent_lease)


# ---------------------------------------------------------------------------
# 18. Recovery Without Concurrent GPU Grants
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recovery_without_concurrent_gpu_grants(tmp_path):
    """During and after quarantine clearance, exactly one lease can execute at a time."""
    scheduler = _make_scheduler(tmp_path, grace_period_s=0.05)

    # Quarantine scheduler
    task_in_lease = asyncio.Event()

    async def rogue():
        async with scheduler.acquire_lease("model", is_workload_stopped=lambda: False):
            task_in_lease.set()
            await asyncio.sleep(10.0)

    t = asyncio.create_task(rogue())
    await task_in_lease.wait()
    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t
    assert scheduler.is_quarantined() is True

    # Clear quarantine safely
    assert scheduler.clear_quarantine(force=True) is True

    # Run 3 concurrent tasks; assert strict mutual exclusion
    active_count = 0
    max_active = 0

    async def worker(idx: int):
        nonlocal active_count, max_active
        async with scheduler.acquire_lease(f"model-{idx}"):
            active_count += 1
            if active_count > max_active:
                max_active = active_count
            assert active_count == 1
            await asyncio.sleep(0.03)
            active_count -= 1

    tasks = [asyncio.create_task(worker(i)) for i in range(3)]
    await asyncio.gather(*tasks)

    assert max_active == 1
    assert active_count == 0


# ---------------------------------------------------------------------------
# 19. Finding F-04: Tier 1 Queue Recovery Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_f04_tier1_recovery_on_permission_error_async(tmp_path, monkeypatch):
    """When _open_lockfile raises PermissionError, Tier 1 state must recover cleanly.

    Invariants verified:
    - Failing task receives PermissionError.
    - Tier 1 active slot is freed.
    - Waiting tasks in queue are dispatched and succeed.
    - Zero leaked file descriptors.
    """
    scheduler = _make_scheduler(tmp_path)

    orig_open = scheduler._open_lockfile
    call_count = 0

    def faulty_open():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise PermissionError("EACCES: Injected lockfile permission failure")
        return orig_open()

    monkeypatch.setattr(scheduler, "_open_lockfile", faulty_open)

    task_b_acquired = False

    async def task_a():
        async with scheduler.acquire_lease("model-a"):
            pass

    async def task_b():
        nonlocal task_b_acquired
        async with scheduler.acquire_lease("model-b"):
            task_b_acquired = True

    t_a = asyncio.create_task(task_a())
    await asyncio.sleep(0.005)
    t_b = asyncio.create_task(task_b())

    with pytest.raises(PermissionError, match="Injected lockfile permission failure"):
        await t_a

    await asyncio.wait_for(t_b, timeout=2.0)
    assert task_b_acquired is True
    assert scheduler.get_queue_status()["tier1_active"] is False


def test_f04_tier1_recovery_on_permission_error_sync(tmp_path, monkeypatch):
    """Sync threads: When _open_lockfile raises PermissionError, queue recovers."""
    scheduler = _make_scheduler(tmp_path)

    orig_open = scheduler._open_lockfile
    call_count = 0
    lock = threading.Lock()

    def faulty_open():
        nonlocal call_count
        with lock:
            call_count += 1
            if call_count == 1:
                raise PermissionError("EACCES: Sync injected permission failure")
            return orig_open()

    monkeypatch.setattr(scheduler, "_open_lockfile", faulty_open)

    thread_b_success = False
    thread_a_error: Optional[Exception] = None

    def worker_a():
        nonlocal thread_a_error
        try:
            with scheduler.acquire_lease_sync("model-a"):
                pass
        except Exception as exc:
            thread_a_error = exc

    def worker_b():
        nonlocal thread_b_success
        with scheduler.acquire_lease_sync("model-b"):
            thread_b_success = True

    t_a = threading.Thread(target=worker_a)
    t_b = threading.Thread(target=worker_b)

    t_a.start()
    time.sleep(0.01)
    t_b.start()

    t_a.join(timeout=3.0)
    t_b.join(timeout=3.0)

    assert isinstance(thread_a_error, PermissionError)
    assert thread_b_success is True


@pytest.mark.anyio
async def test_f04_tier1_recovery_on_flock_os_error(tmp_path, monkeypatch):
    """When fcntl.flock raises unexpected OSError, Tier 1 recovers and fd is closed."""
    import errno
    import fcntl

    scheduler = _make_scheduler(tmp_path)

    orig_flock = fcntl.flock
    call_count = 0

    def faulty_flock(fd, op):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError(errno.EIO, "Injected I/O error during flock")
        return orig_flock(fd, op)

    monkeypatch.setattr(fcntl, "flock", faulty_flock)

    task_b_ok = False

    async def task_a():
        async with scheduler.acquire_lease("model-a"):
            pass

    async def task_b():
        nonlocal task_b_ok
        async with scheduler.acquire_lease("model-b"):
            task_b_ok = True

    t_a = asyncio.create_task(task_a())
    await asyncio.sleep(0.005)
    t_b = asyncio.create_task(task_b())

    with pytest.raises(OSError, match="Injected I/O error during flock"):
        await t_a

    await asyncio.wait_for(t_b, timeout=2.0)
    assert task_b_ok is True


@pytest.mark.anyio
async def test_f04_tier1_recovery_on_cancellation_during_tier2_wait(tmp_path):
    """Task cancelled while contending for Tier 2 lock releases Tier 1 for next waiter."""
    scheduler = _make_scheduler(tmp_path)

    lease1_held = asyncio.Event()
    release_lease1 = asyncio.Event()

    async def holder():
        async with scheduler.acquire_lease("holder"):
            lease1_held.set()
            await release_lease1.wait()

    t_holder = asyncio.create_task(holder())
    await lease1_held.wait()

    task_c_acquired = False

    async def task_b():
        async with scheduler.acquire_lease("contender"):
            pass

    async def task_c():
        nonlocal task_c_acquired
        async with scheduler.acquire_lease("waiter-c"):
            task_c_acquired = True

    t_b = asyncio.create_task(task_b())
    await asyncio.sleep(0.02)
    t_c = asyncio.create_task(task_c())
    await asyncio.sleep(0.01)

    t_b.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t_b

    release_lease1.set()
    await t_holder

    await asyncio.wait_for(t_c, timeout=2.0)
    assert task_c_acquired is True


# ---------------------------------------------------------------------------
# 20. Finding F-05: Lock-file Security Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_f05_lockfile_symlink_rejected(tmp_path):
    """A symlink in place of the lockfile is rejected via O_NOFOLLOW without traversing."""
    target_file = tmp_path / "sensitive_target.txt"
    target_file.write_text("SENSITIVE DATA")

    symlink_path = tmp_path / "symlink_gpu.lock"
    os.symlink(str(target_file), str(symlink_path))

    scheduler = GPUResourceScheduler(
        lockfile_path=str(symlink_path),
        metadata_path=str(tmp_path / "meta.json"),
        quarantine_path=str(tmp_path / "quar.json"),
    )

    with pytest.raises(PermissionError, match="symlink"):
        async with scheduler.acquire_lease("model"):
            pass

    assert target_file.read_text() == "SENSITIVE DATA"


@pytest.mark.anyio
async def test_f05_lockfile_fifo_rejected(tmp_path):
    """A FIFO (named pipe) in place of the lockfile is rejected as a non-regular file."""
    fifo_path = tmp_path / "fifo_gpu.lock"
    os.mkfifo(str(fifo_path))

    scheduler = GPUResourceScheduler(
        lockfile_path=str(fifo_path),
        metadata_path=str(tmp_path / "meta.json"),
        quarantine_path=str(tmp_path / "quar.json"),
    )

    with pytest.raises(PermissionError, match="not a regular file"):
        async with scheduler.acquire_lease("model"):
            pass


@pytest.mark.anyio
async def test_f05_lockfile_directory_rejected(tmp_path):
    """A directory in place of the lockfile is rejected as a non-regular file."""
    dir_path = tmp_path / "dir_gpu.lock"
    os.mkdir(str(dir_path))

    scheduler = GPUResourceScheduler(
        lockfile_path=str(dir_path),
        metadata_path=str(tmp_path / "meta.json"),
        quarantine_path=str(tmp_path / "quar.json"),
    )

    with pytest.raises((PermissionError, IsADirectoryError, OSError)):
        async with scheduler.acquire_lease("model"):
            pass


@pytest.mark.anyio
async def test_f05_lockfile_wrong_ownership_rejected(tmp_path, monkeypatch):
    """A lockfile owned by a different UID is rejected."""
    scheduler = _make_scheduler(tmp_path)

    fd = scheduler._open_lockfile()
    os.close(fd)

    real_uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: real_uid + 9999)

    with pytest.raises(PermissionError, match="owned by UID"):
        scheduler._open_lockfile()


@pytest.mark.anyio
async def test_f05_lockfile_insecure_mode_rejected_if_unfixable(tmp_path, monkeypatch):
    """If lockfile has insecure permissions that fchmod cannot fix, open is rejected."""
    scheduler = _make_scheduler(tmp_path)

    orig_fstat = os.fstat

    class FakeStat:
        def __init__(self, real_st):
            self.st_mode = real_st.st_mode | 0o066
            self.st_uid = real_st.st_uid

    monkeypatch.setattr(os, "fchmod", lambda fd, mode: None)

    def fake_fstat(fd):
        real_st = orig_fstat(fd)
        return FakeStat(real_st)

    monkeypatch.setattr(os, "fstat", fake_fstat)

    with pytest.raises(PermissionError, match="insecure permissions"):
        scheduler._open_lockfile()


@pytest.mark.anyio
async def test_f05_lockfile_never_unlinked_or_replaced(tmp_path):
    """Scheduler must never unlink or replace the active lockfile (inode stability)."""
    scheduler = _make_scheduler(tmp_path)

    async with scheduler.acquire_lease("model-1"):
        pass

    initial_inode = os.stat(scheduler.lockfile_path).st_ino

    async with scheduler.acquire_lease("model-2"):
        pass

    assert os.stat(scheduler.lockfile_path).st_ino == initial_inode

    scheduler.clear_quarantine(force=True)
    assert os.stat(scheduler.lockfile_path).st_ino == initial_inode


# ---------------------------------------------------------------------------
# 21. Finding F-06: Cancellation-Safe Release Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_f06_repeated_cancellation_during_release_quarantines_and_preserves_lock(tmp_path):
    """Repeated cancellation during release must NOT unlock kernel lock; must persist quarantine."""
    scheduler = _make_scheduler(tmp_path, grace_period_s=5.0)

    in_stopped_check = asyncio.Event()

    async def slow_stopped_check():
        in_stopped_check.set()
        await asyncio.sleep(10.0)
        return True

    lease = await scheduler._do_acquire_async(
        model_id="test-model",
        workload_type=WorkloadType.REASONING_VISION,
        priority=1,
        timeout_s=10.0,
        acquisition_timeout_s=2.0,
        abort_fn=None,
        is_workload_stopped=slow_stopped_check,
    )

    assert lease._lock_fd is not None
    original_fd = lease._lock_fd

    release_task = asyncio.create_task(
        scheduler._do_release_async(lease, aborted=True)
    )

    await in_stopped_check.wait()

    release_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await release_task

    assert scheduler.is_quarantined() is True
    assert lease.state == LeaseState.QUARANTINED
    assert lease._lock_fd == original_fd

    await scheduler.release_lease(lease)
    assert lease._lock_fd == original_fd

    scheduler._release_kernel_lock(lease)


@pytest.mark.anyio
async def test_f06_shutdown_with_unconfirmed_workload_quarantines_and_preserves_lock(tmp_path):
    """Shutdown with active unconfirmed workload quarantines GPU and preserves lock descriptor."""
    scheduler = _make_scheduler(tmp_path)

    lease = await scheduler._do_acquire_async(
        model_id="hanging-model",
        workload_type=WorkloadType.REASONING_VISION,
        priority=1,
        timeout_s=10.0,
        acquisition_timeout_s=2.0,
        abort_fn=None,
        is_workload_stopped=lambda: False,
    )
    original_fd = lease._lock_fd

    await scheduler.shutdown(timeout_s=0.05)

    assert scheduler.is_quarantined() is True
    assert lease.state == LeaseState.QUARANTINED
    assert lease._lock_fd == original_fd

    scheduler._release_kernel_lock(lease)


@pytest.mark.anyio
async def test_f06_shutdown_cancellation_quarantines_active_workload(tmp_path):
    """When scheduler.shutdown is interrupted by CancelledError, GPU is quarantined and lock preserved."""
    scheduler = _make_scheduler(tmp_path)

    lease = await scheduler._do_acquire_async(
        model_id="active-model",
        workload_type=WorkloadType.REASONING_VISION,
        priority=1,
        timeout_s=10.0,
        acquisition_timeout_s=2.0,
        abort_fn=None,
        is_workload_stopped=lambda: False,
    )
    original_fd = lease._lock_fd

    shutdown_task = asyncio.create_task(scheduler.shutdown(timeout_s=10.0))
    await asyncio.sleep(0.01)

    shutdown_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await shutdown_task

    assert scheduler.is_quarantined() is True
    assert lease.state == LeaseState.QUARANTINED
    assert lease._lock_fd == original_fd

    scheduler._release_kernel_lock(lease)


# ---------------------------------------------------------------------------
# 22. Finding F-07: Recovery Hardening Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_f07_force_does_not_clear_if_workload_check_fails(tmp_path):
    """clear_quarantine(force=True) fails if workload_check explicitly returns False."""
    scheduler = _make_scheduler(tmp_path)

    scheduler._quarantined = True
    scheduler._quarantine_evidence = {"reason": "test failure", "holder_pid": os.getpid()}

    cleared = scheduler.clear_quarantine(force=True, workload_check=lambda: False)
    assert cleared is False
    assert scheduler.is_quarantined() is True


@pytest.mark.anyio
async def test_f07_force_does_not_clear_if_hardware_check_fails(tmp_path):
    """clear_quarantine(force=True) fails if hardware_check explicitly returns False."""
    scheduler = _make_scheduler(tmp_path)

    scheduler._quarantined = True
    scheduler._quarantine_evidence = {"reason": "test failure", "holder_pid": os.getpid()}

    cleared = scheduler.clear_quarantine(force=True, hardware_check=lambda: False)
    assert cleared is False
    assert scheduler.is_quarantined() is True


@pytest.mark.anyio
async def test_f07_force_does_not_clear_if_external_process_alive(tmp_path, monkeypatch):
    """clear_quarantine(force=True) fails if external holder process is still alive."""
    scheduler = _make_scheduler(tmp_path)

    fake_external_pid = 999999
    scheduler._quarantined = True
    scheduler._quarantine_evidence = {
        "reason": "external worker crashed",
        "holder_pid": fake_external_pid,
    }

    monkeypatch.setattr(scheduler, "_is_process_alive", lambda pid: pid == fake_external_pid)

    cleared = scheduler.clear_quarantine(force=True)
    assert cleared is False
    assert scheduler.is_quarantined() is True


@pytest.mark.anyio
async def test_f07_operator_recovery_procedure_full_lifecycle(tmp_path):
    """Documented operator recovery procedure validates operator identity, checks, and audit trail."""
    scheduler = _make_scheduler(tmp_path)

    scheduler._quarantined = True
    scheduler._quarantine_evidence = {
        "reason": "simulated OOM",
        "holder_pid": os.getpid(),
    }

    res1 = scheduler.operator_recover(operator_id="", reason="")
    assert res1["success"] is False
    assert scheduler.is_quarantined() is True

    res2 = scheduler.operator_recover(
        operator_id="ops-admin-1",
        reason="Manual restart attempted",
        hardware_check=lambda: False,
    )
    assert res2["success"] is False
    assert scheduler.is_quarantined() is True

    res3 = scheduler.operator_recover(
        operator_id="ops-admin-1",
        reason="Manual restart attempted",
        hardware_check=lambda: True,
        workload_check=lambda: False,
    )
    assert res3["success"] is False
    assert scheduler.is_quarantined() is True

    res4 = scheduler.operator_recover(
        operator_id="ops-admin-1",
        reason="Verified Ollama process killed and VRAM reset to 15 MiB",
        hardware_check=lambda: True,
        workload_check=lambda: True,
    )
    assert res4["success"] is True
    assert scheduler.is_quarantined() is False
    assert res4["operator_id"] == "ops-admin-1"
    assert res4["cleared_at"] is not None

    async with scheduler.acquire_lease("recovered-model") as lease:
        assert lease.state == LeaseState.RUNNING


# ---------------------------------------------------------------------------
# 15. Sub-Batch 3.1: Singleton Seam, Lifespan Lifecycle, Warmup & Error Helpers
# ---------------------------------------------------------------------------

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.lifecycle import ModelStatus, OllamaLifecycleManager
from app.ai.manager.scheduler import get_gpu_scheduler, reset_gpu_scheduler_for_tests
from app.api.deps import get_gpu_scheduler as deps_get_gpu_scheduler, get_lifecycle_manager
from app.api.errors import (
    gpu_lease_timeout,
    gpu_queue_saturated,
    gpu_quarantined,
    map_scheduler_error_to_api_error,
    register_error_handlers,
)
from app.main import _run_startup_warmup, lifespan


def test_gpu_scheduler_singleton_thread_safety(tmp_path):
    """Concurrent threads requesting the scheduler receive the exact same singleton instance."""
    reset_gpu_scheduler_for_tests()
    try:
        lockfile = str(tmp_path / "singleton.lock")
        metadata = str(tmp_path / "singleton_lease.json")
        quarantine = str(tmp_path / "singleton_quarantine.json")

        def _get():
            return get_gpu_scheduler(
                lockfile_path=lockfile,
                metadata_path=metadata,
                quarantine_path=quarantine,
            )

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(_get) for _ in range(20)]
            instances = [f.result() for f in futures]

        assert len(instances) == 20
        first_instance = instances[0]
        assert all(inst is first_instance for inst in instances), "Multiple scheduler instances created!"
        assert first_instance.lockfile_path == lockfile
    finally:
        reset_gpu_scheduler_for_tests()


def test_gpu_scheduler_reset_for_tests(tmp_path):
    """reset_gpu_scheduler_for_tests allows creating a fresh instance in tests."""
    reset_gpu_scheduler_for_tests()
    try:
        s1 = get_gpu_scheduler(lockfile_path=str(tmp_path / "s1.lock"))
        reset_gpu_scheduler_for_tests()
        s2 = get_gpu_scheduler(lockfile_path=str(tmp_path / "s2.lock"))
        assert s1 is not s2
        assert s2.lockfile_path == str(tmp_path / "s2.lock")
    finally:
        reset_gpu_scheduler_for_tests()


def test_deps_get_gpu_scheduler_returns_same_instance():
    """Dependency provider returns the process-local singleton scheduler instance."""
    reset_gpu_scheduler_for_tests()
    try:
        inst_direct = get_gpu_scheduler()
        inst_dep = deps_get_gpu_scheduler()
        assert inst_dep is inst_direct
    finally:
        reset_gpu_scheduler_for_tests()


def test_error_helpers_contracts_and_retry_after():
    """Standard error helpers produce correct status, error codes, and advisory Retry-After headers."""
    # 1. Queue Saturated (429)
    err_429 = gpu_queue_saturated(retry_after_s=5)
    assert err_429.status_code == 429
    assert err_429.code == "RATE_LIMITED"
    assert "maximum capacity" in err_429.message
    assert err_429.details == {"reason": "gpu_queue_saturated", "retry_after": 5}
    assert err_429.headers.get("Retry-After") == "5"

    # 2. Acquisition Timeout (504)
    err_504_acq = gpu_lease_timeout(phase="acquisition", retry_after_s=5)
    assert err_504_acq.status_code == 504
    assert err_504_acq.code == "TIMEOUT"
    assert "waiting for an available AI processing slot" in err_504_acq.message
    assert err_504_acq.details == {"phase": "acquisition", "retry_after": 5}
    assert err_504_acq.headers.get("Retry-After") == "5"

    # 3. Execution Timeout (504)
    err_504_exec = gpu_lease_timeout(phase="execution")
    assert err_504_exec.status_code == 504
    assert err_504_exec.code == "TIMEOUT"
    assert "timed out while processing your request" in err_504_exec.message
    assert err_504_exec.details == {"phase": "execution"}
    assert "Retry-After" not in err_504_exec.headers

    # 4. Quarantined (503)
    err_503 = gpu_quarantined(retry_after_s=15)
    assert err_503.status_code == 503
    assert err_503.code == "AI_FAILURE"
    assert "temporarily unavailable" in err_503.message
    assert err_503.details == {"reason": "gpu_quarantined", "retry_after": 15}
    assert err_503.headers.get("Retry-After") == "15"


def test_map_scheduler_error_to_api_error():
    """Centralized error mapping converts scheduler exceptions to standard API errors."""
    from app.ai.manager.types import (
        GPUResourceQuarantinedError,
        SchedulerQueueFullError,
        SchedulerShutdownError,
        SchedulerTimeoutError,
        WorkloadUncertainError,
    )

    err1 = map_scheduler_error_to_api_error(SchedulerQueueFullError("Queue full"))
    assert err1.status_code == 429
    assert err1.code == "RATE_LIMITED"
    assert err1.details.get("reason") == "gpu_queue_saturated"

    err2 = map_scheduler_error_to_api_error(SchedulerTimeoutError("Timeout", phase="acquisition"))
    assert err2.status_code == 504
    assert err2.details.get("phase") == "acquisition"

    err3 = map_scheduler_error_to_api_error(SchedulerTimeoutError("Timeout", phase="execution"))
    assert err3.status_code == 504
    assert err3.details.get("phase") == "execution"

    err4 = map_scheduler_error_to_api_error(GPUResourceQuarantinedError("Quarantined"))
    assert err4.status_code == 503
    assert err4.code == "AI_FAILURE"
    assert err4.details.get("reason") == "gpu_quarantined"

    err5 = map_scheduler_error_to_api_error(WorkloadUncertainError("Uncertain"))
    assert err5.status_code == 503
    assert err5.code == "AI_FAILURE"
    assert err5.details.get("reason") == "gpu_quarantined"

    err6 = map_scheduler_error_to_api_error(SchedulerShutdownError("Shutdown"))
    assert err6.status_code == 503
    assert err6.details.get("reason") == "service_shutdown"


@pytest.mark.anyio
async def test_lifespan_initializes_and_shuts_down_scheduler(tmp_path):
    """FastAPI lifespan initializes scheduler, attaches to app.state, and shuts down safely."""
    scheduler = _make_scheduler(tmp_path)
    lifecycle_mock = MagicMock(spec=OllamaLifecycleManager)
    lifecycle_mock.check_availability.return_value = ModelStatus(
        available=False,
        model_present=False,
        model_name="mock",
        host="http://localhost:11434",
        latency_ms=1.0,
        error="disabled",
    )

    test_app = FastAPI(lifespan=lifespan)
    test_app.dependency_overrides[deps_get_gpu_scheduler] = lambda: scheduler
    test_app.dependency_overrides[get_lifecycle_manager] = lambda: lifecycle_mock

    assert scheduler._is_shutting_down is False

    async with lifespan(test_app):
        assert test_app.state.gpu_scheduler is scheduler
        assert scheduler._is_shutting_down is False

    assert scheduler._is_shutting_down is True


@pytest.mark.anyio
async def test_lifespan_shutdown_with_active_lease_does_not_release_lock_prematurely(tmp_path):
    """Shutdown with an active unconfirmed lease does NOT release kernel lock descriptor prematurely."""
    scheduler = _make_scheduler(tmp_path, grace_period_s=0.1, poll_interval_s=0.01)

    # Acquire lease via context manager without exiting (simulates in-flight running workload)
    cm = scheduler.acquire_lease("test-model", priority=1)
    lease = await cm.__aenter__()
    assert lease.state == LeaseState.RUNNING
    assert lease._lock_fd is not None
    assert scheduler.is_quarantined() is False

    # Execute scheduler shutdown with small timeout while lease workload is uncompleted
    await scheduler.shutdown(timeout_s=0.05)

    # Invariant F-06: Unconfirmed workload at shutdown MUST transition to QUARANTINED
    # and MUST NOT release the kernel lock descriptor!
    assert scheduler.is_quarantined() is True
    assert lease.state == LeaseState.QUARANTINED
    # Lock fd is preserved (not None) to keep the kernel flock held
    assert lease._lock_fd is not None

    # Clear quarantine for clean cleanup
    scheduler.clear_quarantine(operator_override=True, operator_reason="test teardown")


@pytest.mark.anyio
async def test_startup_warmup_acquires_priority3_and_completes(tmp_path):
    """Opportunistic startup warmup acquires a Priority 3 lease and finishes cleanly."""
    scheduler = _make_scheduler(tmp_path)
    lifecycle_mock = MagicMock(spec=OllamaLifecycleManager)
    lifecycle_mock.model = "qwen3-vl:4b-instruct"
    lifecycle_mock.warmup.return_value = True

    acquired_priorities = []
    original_on_acquired = scheduler.on_lease_acquired

    def _track(lease):
        acquired_priorities.append(lease.priority)
        original_on_acquired(lease)

    scheduler.on_lease_acquired = _track

    await _run_startup_warmup(scheduler, lifecycle_mock)

    assert lifecycle_mock.warmup.called
    assert 3 in acquired_priorities
    assert scheduler.is_quarantined() is False
    assert scheduler._active_lease is None


@pytest.mark.anyio
async def test_startup_warmup_skips_when_acquisition_times_out(tmp_path):
    """When lock is contended or held, warmup skips cleanly after 0.5s without error or quarantine."""
    scheduler = _make_scheduler(tmp_path, poll_interval_s=0.01)

    # Hold a lease simulating another worker or interactive query
    async with scheduler.acquire_lease("interactive-model", priority=1) as active_lease:
        assert active_lease.state == LeaseState.RUNNING

        lifecycle_mock = MagicMock(spec=OllamaLifecycleManager)
        lifecycle_mock.model = "qwen3-vl:4b-instruct"

        t0 = time.monotonic()
        # Should attempt to acquire with acquisition_timeout_s=0.5, then skip cleanly
        await _run_startup_warmup(scheduler, lifecycle_mock)
        elapsed = time.monotonic() - t0

        # Skipped cleanly
        lifecycle_mock.warmup.assert_not_called()
        assert elapsed >= 0.45, f"Warmup did not respect 0.5s acquisition timeout (elapsed: {elapsed:.3f}s)"
        # GPU was never touched -> zero quarantine!
        assert scheduler.is_quarantined() is False


@pytest.mark.anyio
async def test_startup_warmup_no_second_scheduler_and_no_flag_file(tmp_path):
    """Warmup uses the single passed scheduler instance and creates zero flag files."""
    scheduler = _make_scheduler(tmp_path)
    lifecycle_mock = MagicMock(spec=OllamaLifecycleManager)
    lifecycle_mock.model = "qwen3-vl:4b-instruct"
    lifecycle_mock.warmup.return_value = True

    flag_path = "/tmp/fansivibe_gpu_p1_pending.flag"
    if os.path.exists(flag_path):
        os.unlink(flag_path)

    await _run_startup_warmup(scheduler, lifecycle_mock)

    # Assert flag file was NOT created
    assert not os.path.exists(flag_path)


@pytest.mark.anyio
async def test_startup_warmup_execution_timeout_watchdog_quarantine_retains_lock(tmp_path):
    """Warmup execution timeout without confirmed cessation triggers quarantine and retains lock."""
    scheduler = _make_scheduler(tmp_path, grace_period_s=0.1, poll_interval_s=0.01)

    # Simulate warmup execution that exceeds execution timeout
    with pytest.raises(TimeoutError):
        async with scheduler.acquire_lease(
            model_id="warmup-model",
            priority=3,
            timeout_s=0.05,
            is_workload_stopped=lambda: False,  # Workload unconfirmed
        ) as lease:
            await asyncio.sleep(0.2)

    # Watchdog failed to confirm termination -> Quarantine & lock retained!
    assert scheduler.is_quarantined() is True
    evidence = scheduler.get_quarantine_evidence()
    assert evidence is not None
    assert "Workload termination unconfirmed" in evidence.get("reason", "")

    scheduler.clear_quarantine(operator_override=True, operator_reason="test teardown")


@pytest.mark.anyio
async def test_startup_warmup_uncertain_termination_quarantines_and_retains_lock(tmp_path):
    """Uncertain workload termination in warmup transitions to QUARANTINED and retains lock."""
    scheduler = _make_scheduler(tmp_path, grace_period_s=0.1, poll_interval_s=0.01)

    with pytest.raises(RuntimeError):
        async with scheduler.acquire_lease(
            model_id="warmup-model",
            priority=3,
            timeout_s=2.0,
            is_workload_stopped=None,  # No termination confirmation check
        ) as lease:
            raise RuntimeError("Ollama process crashed or connection reset mid-warmup")

    assert scheduler.is_quarantined() is True
    assert scheduler.get_quarantine_evidence() is not None

    scheduler.clear_quarantine(operator_override=True, operator_reason="test teardown")


def test_api_error_response_format_compatibility():
    """Verify standard error helper responses through FastAPI match frozen error contracts."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/test-429")
    def _test_429():
        raise gpu_queue_saturated(retry_after_s=5)

    @app.get("/test-504-acq")
    def _test_504_acq():
        raise gpu_lease_timeout(phase="acquisition", retry_after_s=5)

    @app.get("/test-504-exec")
    def _test_504_exec():
        raise gpu_lease_timeout(phase="execution")

    @app.get("/test-503-quar")
    def _test_503_quar():
        raise gpu_quarantined(retry_after_s=15)

    client = TestClient(app, raise_server_exceptions=False)

    # 1. Test 429
    r1 = client.get("/test-429")
    assert r1.status_code == 429
    assert r1.headers.get("Retry-After") == "5"
    assert "X-Request-Id" in r1.headers
    body1 = r1.json()
    assert body1["error"]["code"] == "RATE_LIMITED"
    assert body1["error"]["details"]["reason"] == "gpu_queue_saturated"
    assert body1["error"]["details"]["retry_after"] == 5

    # 2. Test 504 acquisition
    r2 = client.get("/test-504-acq")
    assert r2.status_code == 504
    assert r2.headers.get("Retry-After") == "5"
    assert "X-Request-Id" in r2.headers
    body2 = r2.json()
    assert body2["error"]["code"] == "TIMEOUT"
    assert body2["error"]["details"]["phase"] == "acquisition"
    assert body2["error"]["details"]["retry_after"] == 5
    assert "request_id" in body2["error"]["details"]

    # 3. Test 504 execution
    r3 = client.get("/test-504-exec")
    assert r3.status_code == 504
    assert "Retry-After" not in r3.headers
    assert "X-Request-Id" in r3.headers
    body3 = r3.json()
    assert body3["error"]["code"] == "TIMEOUT"
    assert body3["error"]["details"]["phase"] == "execution"
    assert "request_id" in body3["error"]["details"]

    # 4. Test 503 quarantine
    r4 = client.get("/test-503-quar")
    assert r4.status_code == 503
    assert r4.headers.get("Retry-After") == "15"
    assert "X-Request-Id" in r4.headers
    body4 = r4.json()
    assert body4["error"]["code"] == "AI_FAILURE"
    assert body4["error"]["details"]["reason"] == "gpu_quarantined"
    assert body4["error"]["details"]["retry_after"] == 15
    assert "request_id" in body4["error"]["details"]
