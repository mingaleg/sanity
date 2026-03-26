"""Time limit enforcement for code execution.

This module provides a context manager that enforces time limits on code execution
using a background watchdog thread and exception injection.

Limitations:
    - Exception injection occurs at Python bytecode boundaries. Code executing in
      C extensions (e.g., blocking I/O in native libraries, some numpy operations)
      will not be interrupted until control returns to Python.
    - Child processes spawned by the code are NOT automatically killed when the
      time limit is exceeded. The code must handle cleanup of child processes
      (e.g., in a finally block or exception handler).

Example:
    >>> with TimeLimit(timedelta(seconds=5)):
    ...     do_work()
"""

from __future__ import annotations

import ctypes
import heapq
import threading
from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field as dataclass_field
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from typing import Self


class NoEnforcementBehavior(Enum):
    """Behavior when time limit enforcement is not possible."""

    DISABLED = auto()
    """Proceed without any enforcement."""

    STRICT = auto()
    """Raise TimeLimitNotEnforceable immediately."""

    BEST_EFFORT = auto()
    """Proceed without enforcement, check and raise on exit if exceeded."""


ENFORCE_TIME_LIMIT: ContextVar[NoEnforcementBehavior] = ContextVar(
    "ENFORCE_TIME_LIMIT", default=NoEnforcementBehavior.STRICT
)


@contextmanager
def enforce_time_limit(
    behavior: NoEnforcementBehavior,
) -> Generator[None, None, None]:
    """Temporarily change the time limit enforcement behavior."""
    token = ENFORCE_TIME_LIMIT.set(behavior)
    try:
        yield
    finally:
        ENFORCE_TIME_LIMIT.reset(token)


class TimeLimitError(Exception):
    """Base class for time limit related exceptions."""

    pass


class TimeLimitExceeded(TimeLimitError):
    """Raised when code execution exceeds the time limit.

    Attributes:
        enforced: True if the limit was enforced (interrupted mid-execution),
            False if detected after completion (BEST_EFFORT mode).
        time_limit: The time limit that was exceeded, if known.
    """

    def __init__(
        self,
        *,
        enforced: bool = True,
        time_limit: timedelta | None = None,
    ):
        self.enforced = enforced
        self.time_limit = time_limit
        if time_limit is not None:
            msg = f"Time limit of {time_limit} exceeded"
        else:
            msg = "Time limit exceeded"
        if not enforced:
            msg += " (detected after completion)"
        super().__init__(msg)


class TimeLimitNotEnforceable(TimeLimitError):
    """Raised when time limit enforcement is not possible and behavior is STRICT."""

    pass


@dataclass(frozen=True, order=True)
class _HeapEntry:
    """Entry in the time limit priority queue."""

    deadline: datetime
    counter: int
    limit: TimeLimit = dataclass_field(compare=False)


def _can_enforce() -> bool:
    """Check if we can enforce time limits on this platform."""
    try:
        ctypes.pythonapi.PyThreadState_SetAsyncExc
        return True
    except AttributeError:
        return False


class _TimeLimitManager:
    """Singleton manager for all active time limits.

    Uses a single daemon thread to monitor all registered TimeLimit instances.
    Deadlines are tracked in a priority queue, and the watchdog thread sleeps
    until the earliest deadline or a new registration.
    """

    _instance: _TimeLimitManager | None = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> _TimeLimitManager:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._heap: list[_HeapEntry] = []
        self._counter = 0
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None

    def _ensure_started(self):
        with self._condition:
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()

    def register(self, limit: TimeLimit):
        """Register a TimeLimit to be monitored."""
        self._ensure_started()
        with self._condition:
            self._counter += 1
            heapq.heappush(
                self._heap,
                _HeapEntry(deadline=limit.deadline, counter=self._counter, limit=limit),
            )
            self._condition.notify()

    def unregister(self, limit: TimeLimit):
        """Unregister a TimeLimit (mark as cancelled)."""
        with self._condition:
            limit.cancelled = True
            self._condition.notify()

    def _run(self):
        """Watchdog loop - runs in daemon thread."""
        while True:
            with self._condition:
                # Clean up cancelled entries from top of heap
                while self._heap and self._heap[0].limit.cancelled:
                    heapq.heappop(self._heap)

                if not self._heap:
                    self._condition.wait()
                    continue

                entry = self._heap[0]
                now = datetime.now(UTC)

                if now >= entry.deadline:
                    heapq.heappop(self._heap)
                    if not entry.limit.cancelled:
                        self._fire(entry.limit)
                else:
                    wait_seconds = (entry.deadline - now).total_seconds()
                    self._condition.wait(timeout=wait_seconds)

    def _fire(self, limit: TimeLimit):
        """Inject TimeLimitExceeded into the target thread."""
        if limit._try_fire():
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(limit.target_thread_id),
                ctypes.py_object(TimeLimitExceeded),
            )


_manager = _TimeLimitManager()


class TimeLimit(AbstractContextManager):
    """Context manager that enforces a time limit on code execution.

    Uses a background watchdog thread to monitor execution time and injects
    an exception into the target thread if the limit is exceeded.

    Args:
        time_limit: Maximum duration for the code block. If None, no limit
            is enforced.

    Example:
        >>> with TimeLimit(timedelta(seconds=5)):
        ...     do_work()

    Limitations:
        - Exception injection occurs at Python bytecode boundaries. Code
          executing in C extensions will not be interrupted until control
          returns to Python.
        - Child processes are NOT automatically killed. Clean them up manually
          in a finally block or exception handler.
    """

    def __init__(self, time_limit: timedelta | None = None):
        self._time_limit = time_limit
        self.deadline: datetime | None = None
        self.target_thread_id: int | None = None
        self.cancelled = False
        self._started: datetime | None = None
        self._fire_lock = threading.Lock()
        self._in_exit = False

    def _try_fire(self) -> bool:
        """Attempt to fire the exception. Returns True if fired."""
        with self._fire_lock:
            if self._in_exit:
                return False
            return True

    def __enter__(self) -> Self:
        if self._time_limit is None:
            return self

        behavior = ENFORCE_TIME_LIMIT.get()
        can_enforce = _can_enforce()

        if behavior is NoEnforcementBehavior.STRICT and not can_enforce:
            raise TimeLimitNotEnforceable(
                "Time limit enforcement is not available on this platform. "
                "PyThreadState_SetAsyncExc is not available."
            )

        self._started = datetime.now(UTC)
        self.deadline = self._started + self._time_limit
        self.target_thread_id = threading.current_thread().ident

        if behavior is not NoEnforcementBehavior.DISABLED and can_enforce:
            _manager.register(self)

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: object,
    ) -> bool:
        # Mark that we're in exit to prevent late firing
        with self._fire_lock:
            self._in_exit = True

        if self._time_limit is None:
            return False

        behavior = ENFORCE_TIME_LIMIT.get()
        can_enforce = _can_enforce()

        if behavior is not NoEnforcementBehavior.DISABLED and can_enforce:
            _manager.unregister(self)

        # For BEST_EFFORT when we couldn't enforce, check on exit
        if (
            behavior is NoEnforcementBehavior.BEST_EFFORT
            and not can_enforce
            and self._started is not None
            and exc_type is None  # Don't raise if already an exception
        ):
            elapsed = datetime.now(UTC) - self._started
            if elapsed > self._time_limit:
                raise TimeLimitExceeded(
                    enforced=False, time_limit=self._time_limit
                )

        return False
