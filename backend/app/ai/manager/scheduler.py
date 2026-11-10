"""Two-Tier Cross-Process Shared GPU Concurrency Scheduler.

Provides centralized GPU scheduling guaranteeing that at most one heavy GPU
workload holds the execution lease at any time across:
- Asyncio tasks within an event loop
- Multiple threads within a process
- Multiple Uvicorn workers
- Independent backend processes

Architecture:
- Tier 1: In-process prioritized FIFO queuing (Interactive Reasoning > VTON Diffusion > Warmup)
- Tier 2: Inter-process POSIX kernel advisory locking (fcntl.flock)
"""

from __future__ import annotations

import asyncio
import errno
import fcntl
import inspect
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.ai.manager.types import (
    GPUSchedulerLease,
    GPUResourceQuarantinedError,
    LeaseState,
    SchedulerQueueFullError,
    SchedulerShutdownError,
    SchedulerTimeoutError,
    WorkloadType,
    WorkloadUncertainError,
)

logger = logging.getLogger("app.ai.manager.scheduler")

DEFAULT_LOCKFILE_PATH = "/tmp/fansivibe_gpu_scheduler.lock"
DEFAULT_METADATA_PATH = "/tmp/fansivibe_gpu_lease.json"
DEFAULT_QUARANTINE_PATH = "/tmp/fansivibe_gpu_quarantine.json"
DEFAULT_MAX_QUEUE_DEPTH = 10
DEFAULT_LEASE_TIMEOUT_S = 30.0
DEFAULT_POLL_INTERVAL_S = 0.05
DEFAULT_GRACE_PERIOD_S = 5.0


@dataclass(order=True)
class _QueueEntry:
    priority: int
    enqueued_at: float
    seq: int
    lease_id: str = field(compare=False)
    model_id: str = field(compare=False)
    workload_type: WorkloadType = field(compare=False)
    timeout_s: float = field(compare=False)
    future: Optional[asyncio.Future] = field(default=None, compare=False)
    event: Optional[threading.Event] = field(default=None, compare=False)
    cancelled: bool = field(default=False, compare=False)


class _AsyncLeaseContextManager:
    """Async context manager for acquiring, holding, and releasing a GPU lease."""

    def __init__(
        self,
        scheduler: "GPUResourceScheduler",
        model_id: str,
        workload_type: WorkloadType,
        priority: int,
        timeout_s: float,
        acquisition_timeout_s: Optional[float] = None,
        abort_fn: Optional[Callable[[], Any]] = None,
        is_workload_stopped: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.scheduler = scheduler
        self.model_id = model_id
        self.workload_type = workload_type
        self.priority = priority
        self.timeout_s = timeout_s
        self.acquisition_timeout_s = (
            acquisition_timeout_s if acquisition_timeout_s is not None else timeout_s
        )
        self.abort_fn = abort_fn
        self.is_workload_stopped = is_workload_stopped
        self.lease: Optional[GPUSchedulerLease] = None
        self._timeout_cm: Optional[Any] = None

    async def __aenter__(self) -> GPUSchedulerLease:
        self.lease = await self.scheduler._do_acquire_async(
            model_id=self.model_id,
            workload_type=self.workload_type,
            priority=self.priority,
            timeout_s=self.timeout_s,
            acquisition_timeout_s=self.acquisition_timeout_s,
            abort_fn=self.abort_fn,
            is_workload_stopped=self.is_workload_stopped,
        )
        self.lease.state = LeaseState.RUNNING
        self.scheduler._write_metadata_atomically(self.lease)
        if self.timeout_s is not None and self.timeout_s > 0:
            self._timeout_cm = asyncio.timeout(self.timeout_s)
            await self._timeout_cm.__aenter__()
        return self.lease

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            if self.lease is not None:
                await self.scheduler._do_release_async(
                    self.lease,
                    exc_type=exc_type,
                    exc_val=exc_val,
                    exc_tb=exc_tb,
                )
        finally:
            if self._timeout_cm is not None:
                await self._timeout_cm.__aexit__(exc_type, exc_val, exc_tb)
        return False

    def __await__(self):
        return self.__aenter__().__await__()


class _SyncLeaseContextManager:
    """Synchronous context manager for threads and synchronous execution."""

    def __init__(
        self,
        scheduler: "GPUResourceScheduler",
        model_id: str,
        workload_type: WorkloadType,
        priority: int,
        timeout_s: float,
        acquisition_timeout_s: Optional[float] = None,
        abort_fn: Optional[Callable[[], Any]] = None,
        is_workload_stopped: Optional[Callable[[], Any]] = None,
    ) -> None:
        self.scheduler = scheduler
        self.model_id = model_id
        self.workload_type = workload_type
        self.priority = priority
        self.timeout_s = timeout_s
        self.acquisition_timeout_s = (
            acquisition_timeout_s if acquisition_timeout_s is not None else timeout_s
        )
        self.abort_fn = abort_fn
        self.is_workload_stopped = is_workload_stopped
        self.lease: Optional[GPUSchedulerLease] = None

    def __enter__(self) -> GPUSchedulerLease:
        self.lease = self.scheduler._do_acquire_sync(
            model_id=self.model_id,
            workload_type=self.workload_type,
            priority=self.priority,
            timeout_s=self.timeout_s,
            acquisition_timeout_s=self.acquisition_timeout_s,
            abort_fn=self.abort_fn,
            is_workload_stopped=self.is_workload_stopped,
        )
        self.lease.state = LeaseState.RUNNING
        self.scheduler._write_metadata_atomically(self.lease)
        return self.lease

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self.lease is not None:
            self.scheduler._do_release_sync(
                self.lease,
                exc_type=exc_type,
                exc_val=exc_val,
                exc_tb=exc_tb,
            )
        return False


class GPUResourceScheduler:
    """Two-tier cross-process arbiter for exclusive GPU workload scheduling.

    Coordinates concurrent access to the shared GPU resource:
    - Tier 1: In-process priority queue ensuring high-priority requests
      (interactive reasoning/vision) are served ahead of background diffusion
      or warmup.
    - Tier 2: Kernel-level advisory locking (fcntl.flock) guaranteeing that
      at most one process/worker in the operating system holds the GPU lease.
    """

    def __init__(
        self,
        lockfile_path: Optional[str] = None,
        metadata_path: Optional[str] = None,
        quarantine_path: Optional[str] = None,
        max_queue_depth: int = DEFAULT_MAX_QUEUE_DEPTH,
        default_timeout_s: float = DEFAULT_LEASE_TIMEOUT_S,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        grace_period_s: float = DEFAULT_GRACE_PERIOD_S,
        lifecycle_manager: Optional[Any] = None,
    ) -> None:
        self.lockfile_path = (
            lockfile_path
            or os.environ.get("FANSIVIBE_GPU_LOCKFILE", DEFAULT_LOCKFILE_PATH)
        )
        self.metadata_path = (
            metadata_path
            or os.environ.get("FANSIVIBE_GPU_LEASE_FILE", DEFAULT_METADATA_PATH)
        )
        self.quarantine_path = (
            quarantine_path
            or os.environ.get("FANSIVIBE_GPU_QUARANTINE_FILE", DEFAULT_QUARANTINE_PATH)
        )
        self.max_queue_depth = max(1, max_queue_depth)
        self.default_timeout_s = max(0.1, default_timeout_s)
        self.poll_interval_s = max(0.005, poll_interval_s)
        self.grace_period_s = max(0.01, grace_period_s)
        self.lifecycle_manager = lifecycle_manager

        self._creator_pid = os.getpid()
        self._thread_lock = threading.Lock()
        self._queue: list[_QueueEntry] = []
        self._seq_counter = 0
        self._tier1_active_entry: Optional[_QueueEntry] = None
        self._active_lease: Optional[GPUSchedulerLease] = None
        self._quarantined: bool = False
        self._quarantine_evidence: Optional[dict[str, Any]] = None
        self._is_shutting_down: bool = False

        # Register fork handler for fork safety across Uvicorn workers
        if hasattr(os, "register_at_fork"):
            try:
                os.register_at_fork(after_in_child=self._handle_fork)
            except Exception:
                pass

    def _next_seq(self) -> int:
        with self._thread_lock:
            self._seq_counter += 1
            return self._seq_counter

    def _handle_fork(self) -> None:
        """Handle post-fork initialization in child process."""
        current_pid = os.getpid()
        if current_pid != self._creator_pid:
            logger.info(
                "Process fork detected (old_pid=%s, new_pid=%s); resetting scheduler state",
                self._creator_pid,
                current_pid,
            )
            self._creator_pid = current_pid
            with self._thread_lock:
                self._queue.clear()
                self._tier1_active_entry = None
                # If child inherited an active lease descriptor, close its copy without unlocking
                if self._active_lease and self._active_lease._lock_fd is not None:
                    try:
                        os.close(self._active_lease._lock_fd)
                    except OSError:
                        pass
                self._active_lease = None

    def _check_fork(self) -> None:
        """Verify process has not forked since initialization."""
        if os.getpid() != self._creator_pid:
            self._handle_fork()

    def _open_lockfile(self) -> int:
        """Open or create lockfile with restrictive 0o600 permissions."""
        dir_name = os.path.dirname(self.lockfile_path) or "/tmp"
        os.makedirs(dir_name, exist_ok=True)
        fd = os.open(self.lockfile_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            os.fchmod(fd, 0o600)
        except OSError:
            pass
        return fd

    def _write_metadata_atomically(self, lease: Optional[GPUSchedulerLease]) -> None:
        """Write lease metadata atomically via write-and-replace."""
        try:
            dir_name = os.path.dirname(self.metadata_path) or "/tmp"
            os.makedirs(dir_name, exist_ok=True)
            tmp_path = (
                f"{self.metadata_path}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
            )
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.fchmod(fd, 0o600)
                data = (
                    lease.to_metadata()
                    if lease
                    else {"state": "RELEASED", "timestamp": time.time()}
                )
                payload = json.dumps(data, indent=2).encode("utf-8")
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp_path, self.metadata_path)
        except Exception as exc:
            logger.warning("Failed to write lease metadata atomically: %s", exc)

    def _write_quarantine_atomically(self, evidence: dict[str, Any]) -> None:
        """Write quarantine evidence atomically via write-and-replace."""
        try:
            dir_name = os.path.dirname(self.quarantine_path) or "/tmp"
            os.makedirs(dir_name, exist_ok=True)
            tmp_path = (
                f"{self.quarantine_path}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
            )
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.fchmod(fd, 0o600)
                payload = json.dumps(
                    {"quarantined": True, "evidence": evidence}, indent=2
                ).encode("utf-8")
                os.write(fd, payload)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp_path, self.quarantine_path)
        except Exception as exc:
            logger.error("Failed to write quarantine evidence atomically: %s", exc)

    def _release_kernel_lock(self, lease: GPUSchedulerLease) -> None:
        """Release POSIX fcntl.flock and close file descriptor."""
        fd = lease._lock_fd
        if fd is not None:
            lease._lock_fd = None
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError as exc:
                logger.debug("fcntl.flock unlock notice: %s", exc)
            try:
                os.close(fd)
            except OSError as exc:
                logger.debug("os.close lock fd notice: %s", exc)

    def _maybe_dispatch_next_locked(self) -> None:
        """Dispatch highest priority waiter if Tier 1 slot is open (lock held)."""
        if self._tier1_active_entry is not None:
            return
        if self._quarantined:
            return
        while self._queue:
            candidate = self._queue.pop(0)
            if candidate.cancelled:
                continue
            if candidate.future is not None and not candidate.future.done():
                self._tier1_active_entry = candidate
                candidate.future.set_result(None)
                return
            elif candidate.event is not None and not candidate.event.is_set():
                self._tier1_active_entry = candidate
                candidate.event.set()
                return

    async def _invoke_callable_async(self, fn: Callable[[], Any]) -> Any:
        """Invoke callable whether it is sync or async."""
        if inspect.iscoroutinefunction(fn):
            return await fn()
        res = fn()
        if inspect.isawaitable(res):
            return await res
        return res

    def _invoke_callable_sync(self, fn: Callable[[], Any]) -> Any:
        """Invoke callable synchronously."""
        res = fn()
        if inspect.isawaitable(res):
            # In sync mode, cannot await async coroutine without loop
            loop = None
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                pass
            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(res, loop)
                return future.result()
            return asyncio.run(res)
        return res

    # ---------------------------------------------------------------------------
    # Public Lease Interface
    # ---------------------------------------------------------------------------

    def acquire_lease(
        self,
        model_id: str,
        workload_type: WorkloadType = WorkloadType.REASONING_VISION,
        priority: int = 1,
        timeout_s: Optional[float] = None,
        acquisition_timeout_s: Optional[float] = None,
        abort_fn: Optional[Callable[[], Any]] = None,
        is_workload_stopped: Optional[Callable[[], Any]] = None,
    ) -> _AsyncLeaseContextManager:
        """Acquire an exclusive GPU execution lease asynchronously.

        Can be used as:
        ```python
        async with scheduler.acquire_lease("qwen3-vl:4b-instruct") as lease:
            # perform inference
        ```
        or:
        ```python
        lease = await scheduler.acquire_lease("qwen3-vl:4b-instruct")
        try:
            ...
        finally:
            await scheduler.release_lease(lease)
        ```
        """
        to_s = timeout_s if timeout_s is not None else self.default_timeout_s
        return _AsyncLeaseContextManager(
            scheduler=self,
            model_id=model_id,
            workload_type=workload_type,
            priority=priority,
            timeout_s=to_s,
            acquisition_timeout_s=acquisition_timeout_s,
            abort_fn=abort_fn,
            is_workload_stopped=is_workload_stopped,
        )

    def acquire_lease_sync(
        self,
        model_id: str,
        workload_type: WorkloadType = WorkloadType.REASONING_VISION,
        priority: int = 1,
        timeout_s: Optional[float] = None,
        acquisition_timeout_s: Optional[float] = None,
        abort_fn: Optional[Callable[[], Any]] = None,
        is_workload_stopped: Optional[Callable[[], Any]] = None,
    ) -> _SyncLeaseContextManager:
        """Acquire an exclusive GPU execution lease synchronously (for threads/sync code)."""
        to_s = timeout_s if timeout_s is not None else self.default_timeout_s
        return _SyncLeaseContextManager(
            scheduler=self,
            model_id=model_id,
            workload_type=workload_type,
            priority=priority,
            timeout_s=to_s,
            acquisition_timeout_s=acquisition_timeout_s,
            abort_fn=abort_fn,
            is_workload_stopped=is_workload_stopped,
        )

    async def _do_acquire_async(
        self,
        model_id: str,
        workload_type: WorkloadType,
        priority: int,
        timeout_s: float,
        acquisition_timeout_s: float,
        abort_fn: Optional[Callable[[], Any]],
        is_workload_stopped: Optional[Callable[[], Any]],
    ) -> GPUSchedulerLease:
        self._check_fork()

        if self.is_quarantined():
            evidence = self.get_quarantine_evidence() or {}
            reason = evidence.get("reason", "unresponsive workload")
            raise GPUResourceQuarantinedError(
                f"GPU resource is currently quarantined: {reason}",
                evidence=evidence,
            )

        if self._is_shutting_down:
            raise SchedulerShutdownError("Scheduler is shutting down; cannot grant new leases")

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        lease_id = f"lease-{uuid.uuid4().hex[:8]}"
        seq = self._next_seq()

        entry = _QueueEntry(
            priority=priority,
            enqueued_at=time.monotonic(),
            seq=seq,
            lease_id=lease_id,
            model_id=model_id,
            workload_type=workload_type,
            timeout_s=timeout_s,
            future=future,
        )

        with self._thread_lock:
            active_count = sum(1 for e in self._queue if not e.cancelled)
            if active_count >= self.max_queue_depth:
                raise SchedulerQueueFullError(
                    f"GPU scheduler queue full ({active_count}/{self.max_queue_depth})",
                    current_depth=active_count,
                    max_depth=self.max_queue_depth,
                )
            self._queue.append(entry)
            self._queue.sort()
            self._maybe_dispatch_next_locked()

        acq_deadline = time.monotonic() + acquisition_timeout_s

        # Wait for Tier 1 dispatch
        try:
            wait_remaining = acq_deadline - time.monotonic()
            if wait_remaining <= 0:
                raise asyncio.TimeoutError()
            await asyncio.wait_for(future, timeout=wait_remaining)
        except asyncio.TimeoutError:
            with self._thread_lock:
                entry.cancelled = True
                if entry in self._queue:
                    self._queue.remove(entry)
                if self._tier1_active_entry is entry:
                    self._tier1_active_entry = None
                    self._maybe_dispatch_next_locked()
            raise SchedulerTimeoutError(
                f"Lease acquisition timed out waiting in queue after {acquisition_timeout_s}s",
                phase="acquisition",
                timeout_s=acquisition_timeout_s,
            )
        except asyncio.CancelledError:
            with self._thread_lock:
                entry.cancelled = True
                if entry in self._queue:
                    self._queue.remove(entry)
                if self._tier1_active_entry is entry:
                    self._tier1_active_entry = None
                    self._maybe_dispatch_next_locked()
            raise

        # Tier 1 acquired; now contend for Tier 2 Linux kernel advisory lock
        fd: Optional[int] = None
        while True:
            self._check_fork()
            if self.is_quarantined():
                with self._thread_lock:
                    self._tier1_active_entry = None
                    self._maybe_dispatch_next_locked()
                evidence = self.get_quarantine_evidence() or {}
                raise GPUResourceQuarantinedError(
                    f"GPU quarantined while contending for lock: {evidence.get('reason')}",
                    evidence=evidence,
                )

            remaining = acq_deadline - time.monotonic()
            if remaining <= 0:
                with self._thread_lock:
                    self._tier1_active_entry = None
                    self._maybe_dispatch_next_locked()
                raise SchedulerTimeoutError(
                    f"Timed out acquiring cross-process kernel lock after {acquisition_timeout_s}s",
                    phase="acquisition",
                    timeout_s=acquisition_timeout_s,
                )

            fd = self._open_lockfile()
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Successfully acquired kernel lock!
                break
            except (BlockingIOError, OSError) as exc:
                os.close(fd)
                fd = None
                if getattr(exc, "errno", None) not in (
                    errno.EACCES,
                    errno.EAGAIN,
                    errno.EWOULDBLOCK,
                ):
                    with self._thread_lock:
                        self._tier1_active_entry = None
                        self._maybe_dispatch_next_locked()
                    raise
                sleep_s = min(self.poll_interval_s, remaining)
                try:
                    await asyncio.sleep(sleep_s)
                except asyncio.CancelledError:
                    with self._thread_lock:
                        self._tier1_active_entry = None
                        self._maybe_dispatch_next_locked()
                    raise

        lease = GPUSchedulerLease(
            lease_id=lease_id,
            model_id=model_id,
            workload_type=workload_type,
            priority=priority,
            holder_pid=os.getpid(),
            acquired_at=time.time(),
            timeout_s=timeout_s,
            state=LeaseState.ACQUIRED,
            _lock_fd=fd,
            _abort_fn=abort_fn,
            _is_stopped_fn=is_workload_stopped,
        )
        self._active_lease = lease
        self._write_metadata_atomically(lease)
        self.on_lease_acquired(lease)
        return lease

    def _do_acquire_sync(
        self,
        model_id: str,
        workload_type: WorkloadType,
        priority: int,
        timeout_s: float,
        acquisition_timeout_s: float,
        abort_fn: Optional[Callable[[], Any]],
        is_workload_stopped: Optional[Callable[[], Any]],
    ) -> GPUSchedulerLease:
        """Synchronous acquisition implementation for threads/subprocesses."""
        self._check_fork()

        if self.is_quarantined():
            evidence = self.get_quarantine_evidence() or {}
            raise GPUResourceQuarantinedError(
                f"GPU resource is currently quarantined: {evidence.get('reason')}",
                evidence=evidence,
            )

        if self._is_shutting_down:
            raise SchedulerShutdownError("Scheduler is shutting down")

        event = threading.Event()
        lease_id = f"lease-{uuid.uuid4().hex[:8]}"
        seq = self._next_seq()

        entry = _QueueEntry(
            priority=priority,
            enqueued_at=time.monotonic(),
            seq=seq,
            lease_id=lease_id,
            model_id=model_id,
            workload_type=workload_type,
            timeout_s=timeout_s,
            event=event,
        )

        with self._thread_lock:
            active_count = sum(1 for e in self._queue if not e.cancelled)
            if active_count >= self.max_queue_depth:
                raise SchedulerQueueFullError(
                    f"GPU scheduler queue full ({active_count}/{self.max_queue_depth})",
                    current_depth=active_count,
                    max_depth=self.max_queue_depth,
                )
            self._queue.append(entry)
            self._queue.sort()
            self._maybe_dispatch_next_locked()

        acq_deadline = time.monotonic() + acquisition_timeout_s

        # Wait on event
        remaining = acq_deadline - time.monotonic()
        if remaining <= 0 or not event.wait(timeout=max(0.001, remaining)):
            with self._thread_lock:
                entry.cancelled = True
                if entry in self._queue:
                    self._queue.remove(entry)
                if self._tier1_active_entry is entry:
                    self._tier1_active_entry = None
                    self._maybe_dispatch_next_locked()
            raise SchedulerTimeoutError(
                f"Lease acquisition timed out waiting in queue after {acquisition_timeout_s}s",
                phase="acquisition",
                timeout_s=acquisition_timeout_s,
            )

        # Tier 2 kernel lock polling
        fd: Optional[int] = None
        while True:
            self._check_fork()
            if self.is_quarantined():
                with self._thread_lock:
                    self._tier1_active_entry = None
                    self._maybe_dispatch_next_locked()
                evidence = self.get_quarantine_evidence() or {}
                raise GPUResourceQuarantinedError(
                    f"GPU quarantined while contending for lock: {evidence.get('reason')}",
                    evidence=evidence,
                )

            remaining = acq_deadline - time.monotonic()
            if remaining <= 0:
                with self._thread_lock:
                    self._tier1_active_entry = None
                    self._maybe_dispatch_next_locked()
                raise SchedulerTimeoutError(
                    f"Timed out acquiring kernel lock after {acquisition_timeout_s}s",
                    phase="acquisition",
                    timeout_s=acquisition_timeout_s,
                )

            fd = self._open_lockfile()
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError) as exc:
                os.close(fd)
                fd = None
                if getattr(exc, "errno", None) not in (
                    errno.EACCES,
                    errno.EAGAIN,
                    errno.EWOULDBLOCK,
                ):
                    with self._thread_lock:
                        self._tier1_active_entry = None
                        self._maybe_dispatch_next_locked()
                    raise
                time.sleep(min(self.poll_interval_s, remaining))

        lease = GPUSchedulerLease(
            lease_id=lease_id,
            model_id=model_id,
            workload_type=workload_type,
            priority=priority,
            holder_pid=os.getpid(),
            acquired_at=time.time(),
            timeout_s=timeout_s,
            state=LeaseState.ACQUIRED,
            _lock_fd=fd,
            _abort_fn=abort_fn,
            _is_stopped_fn=is_workload_stopped,
        )
        self._active_lease = lease
        self._write_metadata_atomically(lease)
        self.on_lease_acquired(lease)
        return lease

    async def release_lease(
        self,
        lease: GPUSchedulerLease,
        aborted: bool = False,
        force_quarantine: bool = False,
    ) -> None:
        """Explicitly release an active GPU lease."""
        await self._do_release_async(
            lease,
            aborted=aborted,
            force_quarantine=force_quarantine,
        )

    async def _do_release_async(
        self,
        lease: GPUSchedulerLease,
        exc_type: Optional[type] = None,
        exc_val: Optional[BaseException] = None,
        exc_tb: Optional[Any] = None,
        aborted: bool = False,
        force_quarantine: bool = False,
    ) -> None:
        if lease.state == LeaseState.RELEASED:
            return

        is_failure_or_cancelled = (
            aborted
            or force_quarantine
            or exc_type is not None
            or lease.state == LeaseState.CANCELLING
        )

        if is_failure_or_cancelled and not lease._workload_completed:
            lease.state = LeaseState.CANCELLING
            self._write_metadata_atomically(lease)
            cancel_reason = (
                f"{exc_type.__name__}: {exc_val}"
                if exc_type
                else ("Aborted" if aborted else "Uncertain workload")
            )
            self.on_lease_cancelled(lease, cancel_reason)

            # Invoke abort handler if registered
            if lease._abort_fn is not None:
                try:
                    await self._invoke_callable_async(lease._abort_fn)
                except Exception as exc:
                    logger.warning("Abort handler raised an exception: %s", exc)

            # Active termination verification loop up to grace_period_s
            confirmed_stopped = False
            if lease._is_stopped_fn is not None:
                grace_deadline = time.monotonic() + self.grace_period_s
                while time.monotonic() < grace_deadline:
                    try:
                        res = await self._invoke_callable_async(lease._is_stopped_fn)
                        if res is True:
                            confirmed_stopped = True
                            break
                    except Exception as check_exc:
                        logger.warning("Termination check error: %s", check_exc)
                    await asyncio.sleep(self.poll_interval_s)
            else:
                confirmed_stopped = False

            if not confirmed_stopped or force_quarantine:
                # Critical safety invariant: Workload termination unconfirmed -> QUARANTINE!
                lease.state = LeaseState.QUARANTINED
                lease._quarantine_reason = (
                    f"Workload termination unconfirmed within {self.grace_period_s}s grace period"
                    if not confirmed_stopped
                    else "Forced quarantine"
                )
                evidence = {
                    "quarantined_at": time.time(),
                    "lease_id": lease.lease_id,
                    "holder_pid": lease.holder_pid,
                    "model_id": lease.model_id,
                    "workload_type": (
                        lease.workload_type.value
                        if hasattr(lease.workload_type, "value")
                        else str(lease.workload_type)
                    ),
                    "reason": lease._quarantine_reason,
                    "exception_type": exc_type.__name__ if exc_type else None,
                    "grace_period_s": self.grace_period_s,
                }
                self._quarantined = True
                self._quarantine_evidence = evidence
                self._write_quarantine_atomically(evidence)
                self.on_quarantined(evidence)
                # Do NOT unlock kernel descriptor to waiting workloads!
                with self._thread_lock:
                    self._tier1_active_entry = None
                return

        # Normal completion or confirmed termination: release lock cleanly
        lease.state = LeaseState.RELEASED
        lease._released_at = time.time()
        self._write_metadata_atomically(None)
        self._release_kernel_lock(lease)

        duration_s = (
            lease._released_at - lease.acquired_at if lease._released_at else 0.0
        )
        self.on_lease_released(lease, duration_s)

        if self._active_lease is lease:
            self._active_lease = None

        with self._thread_lock:
            self._tier1_active_entry = None
            self._maybe_dispatch_next_locked()

    def _do_release_sync(
        self,
        lease: GPUSchedulerLease,
        exc_type: Optional[type] = None,
        exc_val: Optional[BaseException] = None,
        exc_tb: Optional[Any] = None,
        aborted: bool = False,
        force_quarantine: bool = False,
    ) -> None:
        """Synchronous release implementation for threads/subprocesses."""
        if lease.state == LeaseState.RELEASED:
            return

        is_failure_or_cancelled = (
            aborted
            or force_quarantine
            or exc_type is not None
            or lease.state == LeaseState.CANCELLING
        )

        if is_failure_or_cancelled and not lease._workload_completed:
            lease.state = LeaseState.CANCELLING
            self._write_metadata_atomically(lease)
            cancel_reason = (
                f"{exc_type.__name__}: {exc_val}"
                if exc_type
                else ("Aborted" if aborted else "Uncertain workload")
            )
            self.on_lease_cancelled(lease, cancel_reason)

            if lease._abort_fn is not None:
                try:
                    self._invoke_callable_sync(lease._abort_fn)
                except Exception as exc:
                    logger.warning("Abort handler raised an exception: %s", exc)

            confirmed_stopped = False
            if lease._is_stopped_fn is not None:
                grace_deadline = time.monotonic() + self.grace_period_s
                while time.monotonic() < grace_deadline:
                    try:
                        res = self._invoke_callable_sync(lease._is_stopped_fn)
                        if res is True:
                            confirmed_stopped = True
                            break
                    except Exception:
                        pass
                    time.sleep(self.poll_interval_s)
            else:
                confirmed_stopped = False

            if not confirmed_stopped or force_quarantine:
                lease.state = LeaseState.QUARANTINED
                lease._quarantine_reason = (
                    f"Workload termination unconfirmed within {self.grace_period_s}s grace period"
                    if not confirmed_stopped
                    else "Forced quarantine"
                )
                evidence = {
                    "quarantined_at": time.time(),
                    "lease_id": lease.lease_id,
                    "holder_pid": lease.holder_pid,
                    "model_id": lease.model_id,
                    "workload_type": (
                        lease.workload_type.value
                        if hasattr(lease.workload_type, "value")
                        else str(lease.workload_type)
                    ),
                    "reason": lease._quarantine_reason,
                    "exception_type": exc_type.__name__ if exc_type else None,
                    "grace_period_s": self.grace_period_s,
                }
                self._quarantined = True
                self._quarantine_evidence = evidence
                self._write_quarantine_atomically(evidence)
                self.on_quarantined(evidence)
                with self._thread_lock:
                    self._tier1_active_entry = None
                return

        lease.state = LeaseState.RELEASED
        lease._released_at = time.time()
        self._write_metadata_atomically(None)
        self._release_kernel_lock(lease)

        duration_s = (
            lease._released_at - lease.acquired_at if lease._released_at else 0.0
        )
        self.on_lease_released(lease, duration_s)

        if self._active_lease is lease:
            self._active_lease = None

        with self._thread_lock:
            self._tier1_active_entry = None
            self._maybe_dispatch_next_locked()

    # ---------------------------------------------------------------------------
    # Quarantine & Diagnostics Interface
    # ---------------------------------------------------------------------------

    def is_quarantined(self) -> bool:
        """Check whether GPU is quarantined locally or cross-process."""
        if self._quarantined:
            return True
        if os.path.exists(self.quarantine_path):
            try:
                with open(self.quarantine_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("quarantined", False):
                        self._quarantined = True
                        self._quarantine_evidence = data.get("evidence")
                        return True
            except Exception:
                pass
        return False

    def get_quarantine_evidence(self) -> Optional[dict[str, Any]]:
        """Return diagnostic evidence explaining why GPU was quarantined."""
        if not self.is_quarantined():
            return None
        if self._quarantine_evidence:
            return self._quarantine_evidence
        if os.path.exists(self.quarantine_path):
            try:
                with open(self.quarantine_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("evidence")
            except Exception:
                pass
        return None

    def clear_quarantine(
        self,
        force: bool = False,
        hardware_check: Optional[Callable[[], bool | Awaitable[bool]]] = None,
    ) -> bool:
        """Clear quarantine state with explicit recovery verification.

        - If hardware_check is provided, executes it.
        - If hardware_check returns False and force is False, quarantine remains.
        - If force is True or hardware_check returns True, lifts quarantine and removes file.
        """
        if not self.is_quarantined():
            return True

        if hardware_check is not None:
            ok = self._invoke_callable_sync(hardware_check)
            if not ok and not force:
                logger.warning("Hardware verification check failed; GPU remains quarantined")
                return False
        elif not force:
            logger.warning(
                "Attempted to clear quarantine without hardware verification or force=True; rejected"
            )
            return False

        self._quarantined = False
        evidence = self._quarantine_evidence
        self._quarantine_evidence = None

        # If holding a quarantined kernel lock fd, release it now
        if self._active_lease and self._active_lease.state == LeaseState.QUARANTINED:
            self._release_kernel_lock(self._active_lease)
            self._active_lease = None

        try:
            if os.path.exists(self.quarantine_path):
                os.unlink(self.quarantine_path)
        except OSError:
            pass

        self.on_quarantine_cleared(evidence)

        with self._thread_lock:
            self._tier1_active_entry = None
            self._maybe_dispatch_next_locked()

        return True

    def get_queue_status(self) -> dict[str, Any]:
        """Return current queue depth, active lease, and quarantine state."""
        with self._thread_lock:
            queue_len = sum(1 for e in self._queue if not e.cancelled)
            waiting_ids = [e.lease_id for e in self._queue if not e.cancelled]

        metadata = None
        if os.path.exists(self.metadata_path):
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except Exception:
                pass

        return {
            "is_quarantined": self.is_quarantined(),
            "quarantine_evidence": self.get_quarantine_evidence(),
            "queue_depth": queue_len,
            "waiting_lease_ids": waiting_ids,
            "tier1_active": self._tier1_active_entry is not None,
            "has_local_active_lease": self._active_lease is not None,
            "active_lease": (
                self._active_lease.to_metadata() if self._active_lease else None
            ),
            "cross_process_metadata": metadata,
            "pid": os.getpid(),
            "lockfile_path": self.lockfile_path,
        }

    # ---------------------------------------------------------------------------
    # Shutdown & Telemetry
    # ---------------------------------------------------------------------------

    async def shutdown(self, timeout_s: float = 5.0) -> None:
        """Cancel queued requests and cleanly release scheduler state."""
        self._is_shutting_down = True
        with self._thread_lock:
            for entry in self._queue:
                entry.cancelled = True
                if entry.future and not entry.future.done():
                    entry.future.set_exception(
                        SchedulerShutdownError("Scheduler is shutting down")
                    )
                if entry.event and not entry.event.is_set():
                    entry.event.set()
            self._queue.clear()

        if self._active_lease and self._active_lease.state == LeaseState.RUNNING:
            deadline = time.monotonic() + timeout_s
            while self._active_lease and time.monotonic() < deadline:
                await asyncio.sleep(0.05)

        if self._active_lease and self._active_lease._lock_fd is not None:
            self._release_kernel_lock(self._active_lease)
            self._active_lease = None

    def on_lease_acquired(self, lease: GPUSchedulerLease) -> None:
        """Telemetry hook: invoked upon lease acquisition."""
        logger.info(
            "GPU lease %s ACQUIRED by pid=%s for model=%s (priority=%s, timeout=%.1fs)",
            lease.lease_id,
            lease.holder_pid,
            lease.model_id,
            lease.priority,
            lease.timeout_s,
        )

    def on_lease_released(self, lease: GPUSchedulerLease, duration_s: float) -> None:
        """Telemetry hook: invoked upon lease release."""
        logger.info(
            "GPU lease %s RELEASED by pid=%s (duration=%.3fs)",
            lease.lease_id,
            lease.holder_pid,
            duration_s,
        )

    def on_lease_cancelled(self, lease: GPUSchedulerLease, reason: str) -> None:
        """Telemetry hook: invoked when a lease is cancelled during execution."""
        logger.warning(
            "GPU lease %s CANCELLING by pid=%s: %s",
            lease.lease_id,
            lease.holder_pid,
            reason,
        )

    def on_quarantined(self, evidence: dict[str, Any]) -> None:
        """Telemetry hook: invoked when GPU enters quarantine."""
        logger.critical(
            "GPU RESOURCE QUARANTINED (pid=%s, lease=%s): %s",
            evidence.get("holder_pid"),
            evidence.get("lease_id"),
            evidence.get("reason"),
        )

    def on_quarantine_cleared(self, evidence: Optional[dict[str, Any]]) -> None:
        """Telemetry hook: invoked when GPU quarantine is cleared."""
        logger.info("GPU RESOURCE QUARANTINE CLEARED: %s", evidence)
