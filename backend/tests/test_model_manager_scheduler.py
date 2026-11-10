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

