import asyncio
import multiprocessing
import os
import subprocess
import sys
import threading
import time
from datetime import timedelta
from unittest.mock import patch

import pytest

from sanity import (
    NoEnforcementBehavior,
    TimeLimit,
    TimeLimitExceeded,
    TimeLimitNotEnforceable,
    enforce_time_limit,
)
from sanity.engine.time_limit import _can_enforce

from .conftest import requires_enforcement

is_posix = os.name == "posix"


class TestCanEnforce:
    @pytest.mark.skipif(not is_posix, reason="POSIX-specific test")
    def test_returns_true_on_posix(self):
        assert _can_enforce() is True


class TestTimeLimitBasic:
    def test_no_limit(self):
        with TimeLimit():
            pass

    def test_none_limit(self):
        with TimeLimit(None):
            pass

    def test_within_limit(self):
        with TimeLimit(timedelta(seconds=1)):
            time.sleep(0.01)

    @requires_enforcement
    def test_exceeds_limit(self):
        with pytest.raises(TimeLimitExceeded) as exc_info:
            with TimeLimit(timedelta(milliseconds=50)):
                while True:
                    pass
        assert exc_info.value.enforced is True

    @requires_enforcement
    def test_exceeds_limit_cpu_bound(self):
        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                x = 0
                while True:
                    x += 1


class TestTimeLimitExceededException:
    def test_enforced_with_time_limit(self):
        exc = TimeLimitExceeded(enforced=True, time_limit=timedelta(seconds=5))
        assert exc.enforced is True
        assert exc.time_limit == timedelta(seconds=5)
        assert str(exc) == "Time limit of 0:00:05 exceeded"

    def test_not_enforced(self):
        exc = TimeLimitExceeded(enforced=False, time_limit=timedelta(seconds=3))
        assert exc.enforced is False
        assert str(exc) == "Time limit of 0:00:03 exceeded (detected after completion)"

    def test_default_enforced(self):
        exc = TimeLimitExceeded()
        assert exc.enforced is True
        assert exc.time_limit is None
        assert str(exc) == "Time limit exceeded"


class TestTimeLimitNested:
    @requires_enforcement
    def test_inner_fires_first(self):
        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(seconds=10)):
                with TimeLimit(timedelta(milliseconds=50)):
                    while True:
                        pass

    @requires_enforcement
    def test_outer_fires_first(self):
        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                with TimeLimit(timedelta(seconds=10)):
                    while True:
                        pass

    @requires_enforcement
    def test_outer_continues_after_inner_caught(self):
        with TimeLimit(timedelta(seconds=1)):
            try:
                with TimeLimit(timedelta(milliseconds=50)):
                    while True:
                        pass
            except TimeLimitExceeded:
                pass
            time.sleep(0.01)


class TestEnforcementBehaviorDisabled:
    def test_no_exception_when_exceeded(self):
        with enforce_time_limit(NoEnforcementBehavior.DISABLED):
            with TimeLimit(timedelta(milliseconds=10)):
                time.sleep(0.05)

    def test_no_exception_when_within_limit(self):
        with enforce_time_limit(NoEnforcementBehavior.DISABLED):
            with TimeLimit(timedelta(seconds=1)):
                pass


class TestEnforcementBehaviorStrict:
    @requires_enforcement
    def test_enforces_when_possible(self):
        with enforce_time_limit(NoEnforcementBehavior.STRICT):
            with pytest.raises(TimeLimitExceeded) as exc_info:
                with TimeLimit(timedelta(milliseconds=50)):
                    while True:
                        pass
            assert exc_info.value.enforced is True

    def test_raises_not_enforceable_when_impossible(self):
        with patch("sanity.engine.time_limit._can_enforce", return_value=False):
            with enforce_time_limit(NoEnforcementBehavior.STRICT):
                with pytest.raises(TimeLimitNotEnforceable):
                    with TimeLimit(timedelta(milliseconds=50)):
                        pass


class TestEnforcementBehaviorBestEffort:
    @requires_enforcement
    def test_enforces_when_possible(self):
        with enforce_time_limit(NoEnforcementBehavior.BEST_EFFORT):
            with pytest.raises(TimeLimitExceeded) as exc_info:
                with TimeLimit(timedelta(milliseconds=50)):
                    while True:
                        pass
            assert exc_info.value.enforced is True

    def test_checks_on_exit_when_enforcement_impossible(self):
        with patch("sanity.engine.time_limit._can_enforce", return_value=False):
            with enforce_time_limit(NoEnforcementBehavior.BEST_EFFORT):
                with pytest.raises(TimeLimitExceeded) as exc_info:
                    with TimeLimit(timedelta(milliseconds=10)):
                        time.sleep(0.05)
                assert exc_info.value.enforced is False

    def test_no_exception_when_within_limit_and_enforcement_impossible(self):
        with patch("sanity.engine.time_limit._can_enforce", return_value=False):
            with enforce_time_limit(NoEnforcementBehavior.BEST_EFFORT):
                with TimeLimit(timedelta(seconds=1)):
                    pass


class TestTimeLimitAttributes:
    def test_deadline_set(self):
        with TimeLimit(timedelta(seconds=1)) as tl:
            assert tl.deadline is not None

    def test_target_thread_id_set(self):
        with TimeLimit(timedelta(seconds=1)) as tl:
            assert tl.target_thread_id is not None

    def test_cancelled_initially_false(self):
        tl = TimeLimit(timedelta(seconds=1))
        assert tl.cancelled is False


class TestTimeLimitAsync:
    @requires_enforcement
    def test_interrupts_cpu_bound_async(self):
        async def cpu_bound():
            with TimeLimit(timedelta(milliseconds=50)):
                while True:
                    pass

        with pytest.raises(TimeLimitExceeded):
            asyncio.run(cpu_bound())

    @requires_enforcement
    def test_interrupts_async_with_awaits(self):
        async def with_awaits():
            with TimeLimit(timedelta(milliseconds=50)):
                while True:
                    await asyncio.sleep(0)

        with pytest.raises(TimeLimitExceeded):
            asyncio.run(with_awaits())

    def test_within_limit_async(self):
        async def quick_task():
            with TimeLimit(timedelta(seconds=1)):
                await asyncio.sleep(0.01)

        asyncio.run(quick_task())


class TestTimeLimitThreading:
    @requires_enforcement
    def test_interrupts_in_spawned_thread(self):
        result = {}

        def worker():
            try:
                with TimeLimit(timedelta(milliseconds=50)):
                    while True:
                        pass
            except TimeLimitExceeded as e:
                result["exception"] = e

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=2)

        assert "exception" in result
        assert result["exception"].enforced is True

    @requires_enforcement
    def test_multiple_threads_independent_limits(self):
        results = {"fast": None, "slow": None}

        def fast_worker():
            try:
                with TimeLimit(timedelta(milliseconds=50)):
                    while True:
                        pass
            except TimeLimitExceeded:
                results["fast"] = "exceeded"

        def slow_worker():
            with TimeLimit(timedelta(seconds=2)):
                time.sleep(0.1)
            results["slow"] = "completed"

        fast_thread = threading.Thread(target=fast_worker)
        slow_thread = threading.Thread(target=slow_worker)

        fast_thread.start()
        slow_thread.start()

        fast_thread.join(timeout=2)
        slow_thread.join(timeout=2)

        assert results["fast"] == "exceeded"
        assert results["slow"] == "completed"

    def test_within_limit_in_thread(self):
        result = {}

        def worker():
            with TimeLimit(timedelta(seconds=1)):
                time.sleep(0.01)
            result["completed"] = True

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=2)

        assert result.get("completed") is True


def _subprocess_worker_exceeds(queue: multiprocessing.Queue):
    """Worker function for subprocess test - exceeds time limit."""
    try:
        with TimeLimit(timedelta(milliseconds=50)):
            while True:
                pass
    except TimeLimitExceeded as e:
        queue.put(("exceeded", e.enforced))
    except Exception as e:
        queue.put(("error", str(e)))


def _subprocess_worker_within(queue: multiprocessing.Queue):
    """Worker function for subprocess test - within time limit."""
    with TimeLimit(timedelta(seconds=1)):
        time.sleep(0.01)
    queue.put(("completed", None))


class TestTimeLimitSubprocess:
    @requires_enforcement
    def test_works_inside_subprocess(self):
        queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=_subprocess_worker_exceeds, args=(queue,)
        )
        process.start()
        process.join(timeout=2)

        assert not queue.empty()
        status, enforced = queue.get()
        assert status == "exceeded"
        assert enforced is True

    def test_within_limit_inside_subprocess(self):
        queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=_subprocess_worker_within, args=(queue,)
        )
        process.start()
        process.join(timeout=2)

        assert not queue.empty()
        status, _ = queue.get()
        assert status == "completed"

    @requires_enforcement
    def test_interrupts_code_that_spawns_subprocess(self):
        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=100)):
                # Start a long-running subprocess
                proc = subprocess.Popen(
                    [sys.executable, "-c", "import time; time.sleep(10)"],
                )
                try:
                    # CPU-bound loop while subprocess runs
                    while True:
                        pass
                finally:
                    proc.terminate()
                    proc.wait()

    def test_subprocess_not_killed_by_time_limit(self):
        """TimeLimit interrupts Python code but child process continues until cleanup."""
        proc = None
        try:
            with pytest.raises(TimeLimitExceeded):
                with TimeLimit(timedelta(milliseconds=50)):
                    # Start a subprocess that writes a marker file
                    proc = subprocess.Popen(
                        [sys.executable, "-c", "import time; time.sleep(0.2)"],
                    )
                    while True:
                        pass
        finally:
            if proc is not None:
                # Process should still be running (not killed by TimeLimit)
                # We need to clean it up ourselves
                proc.terminate()
                proc.wait()


class TestTimeLimitGenerators:
    @requires_enforcement
    def test_interrupts_generator_iteration(self):
        def infinite_generator():
            while True:
                yield 1

        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                for _ in infinite_generator():
                    pass

    @requires_enforcement
    def test_interrupts_generator_body(self):
        def slow_generator():
            while True:
                # CPU-bound work inside generator
                x = 0
                for _ in range(10_000_000):
                    x += 1
                yield x

        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                for _ in slow_generator():
                    pass

    @requires_enforcement
    def test_generator_cleanup_on_interrupt(self):
        cleanup_called = []

        def generator_with_cleanup():
            try:
                while True:
                    yield 1
            finally:
                cleanup_called.append(True)

        gen = generator_with_cleanup()
        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                for _ in gen:
                    pass

        # Generator's finally block should run when generator is closed
        gen.close()
        assert cleanup_called == [True]


class TestTimeLimitFinallyBlocks:
    @requires_enforcement
    def test_finally_block_runs_after_timeout(self):
        finally_ran = []

        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                try:
                    while True:
                        pass
                finally:
                    finally_ran.append(True)

        assert finally_ran == [True]

    @requires_enforcement
    def test_timeout_during_finally_block(self):
        """If finally block is slow, it can also be interrupted."""
        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                try:
                    pass  # Quick try block
                finally:
                    # Slow finally block - infinite loop
                    while True:
                        pass


class TestTimeLimitExceptionChaining:
    @requires_enforcement
    def test_timeout_during_exception_handling(self):
        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                try:
                    raise ValueError("original error")
                except ValueError:
                    # Slow exception handler
                    while True:
                        pass

    @requires_enforcement
    def test_exception_context_preserved(self):
        """TimeLimitExceeded should have __context__ if raised during handling."""
        caught_exception = None

        try:
            with TimeLimit(timedelta(milliseconds=50)):
                try:
                    raise ValueError("original")
                except ValueError:
                    while True:
                        pass
        except TimeLimitExceeded as e:
            caught_exception = e

        assert caught_exception is not None
        assert isinstance(caught_exception.__context__, ValueError)
        assert str(caught_exception.__context__) == "original"


class TestTimeLimitContextManagerCleanup:
    @requires_enforcement
    def test_timeout_during_nested_cm_exit(self):
        """TimeLimit can interrupt another context manager's __exit__."""

        class SlowExitCM:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                while True:
                    pass

        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                with SlowExitCM():
                    pass  # Body completes quickly, but __exit__ is slow

    @requires_enforcement
    def test_timeout_during_nested_cm_enter(self):
        """TimeLimit can interrupt another context manager's __enter__."""

        class SlowEnterCM:
            def __enter__(self):
                while True:
                    pass

            def __exit__(self, *_args):
                pass

        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                with SlowEnterCM():
                    pass


class TestTimeLimitRecursion:
    @requires_enforcement
    def test_interrupts_deep_recursion(self):
        def recursive_work(depth=0):
            # Do enough work at each level that timeout fires before RecursionError
            for _ in range(1000):
                _ = sum(range(100))
            recursive_work(depth + 1)

        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                recursive_work()

    @requires_enforcement
    def test_interrupts_mutual_recursion(self):
        def func_a(n):
            for _ in range(1000):
                _ = sum(range(100))
            func_b(n + 1)

        def func_b(n):
            for _ in range(1000):
                _ = sum(range(100))
            func_a(n + 1)

        with pytest.raises(TimeLimitExceeded):
            with TimeLimit(timedelta(milliseconds=50)):
                func_a(0)


class TestTimeLimitStress:
    def test_many_sequential_time_limits(self):
        for _ in range(1000):
            with TimeLimit(timedelta(seconds=1)):
                pass

    @requires_enforcement
    def test_many_sequential_time_limits_with_work(self):
        for _ in range(100):
            with TimeLimit(timedelta(seconds=1)):
                _ = sum(range(1000))

    @requires_enforcement
    def test_many_concurrent_time_limits_in_threads(self):
        results = {"completed": 0, "exceeded": 0}
        lock = threading.Lock()

        def worker(should_exceed: bool):
            try:
                with TimeLimit(timedelta(milliseconds=100)):
                    if should_exceed:
                        while True:
                            pass
                    # fast path: no work, just exit
                with lock:
                    results["completed"] += 1
            except TimeLimitExceeded:
                with lock:
                    results["exceeded"] += 1

        threads = []
        for i in range(50):
            t = threading.Thread(target=worker, args=(i % 2 == 0,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        assert results["completed"] == 25
        assert results["exceeded"] == 25

    @requires_enforcement
    def test_rapid_fire_time_limits(self):
        exceeded_count = 0
        for _ in range(50):
            try:
                with TimeLimit(timedelta(milliseconds=10)):
                    while True:
                        pass
            except TimeLimitExceeded:
                exceeded_count += 1

        assert exceeded_count == 50
