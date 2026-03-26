from collections.abc import Iterable

from sanity import Runner, ValidationResult, ValidationVerdict, Validator, ok, failed


class CountingValidator(Validator[int]):
    def __init__(self, targets: list[int]):
        self._targets = targets

    def validate(self, target: int) -> ValidationResult:
        return ok(f"validated {target}")

    def targets_in_scope(self) -> Iterable[int]:
        return self._targets


class FailingOnOddValidator(Validator[int]):
    def __init__(self, targets: list[int]):
        self._targets = targets

    def validate(self, target: int) -> ValidationResult:
        if target % 2 == 1:
            return failed(f"{target} is odd")
        return ok(f"{target} is even")

    def targets_in_scope(self) -> Iterable[int]:
        return self._targets


class TestRunner:
    def test_run_once_empty_validators(self):
        runner = Runner([])
        results = list(runner.run_once())
        assert results == []

    def test_run_once_empty_targets(self):
        runner = Runner([CountingValidator([])])
        results = list(runner.run_once())
        assert results == []

    def test_run_once_single_validator_single_target(self):
        runner = Runner([CountingValidator([1])])
        results = list(runner.run_once())

        assert len(results) == 1
        assert results[0].target == 1
        assert results[0].verdict == ValidationVerdict.PASSED
        assert results[0].reason == "validated 1"

    def test_run_once_single_validator_multiple_targets(self):
        runner = Runner([CountingValidator([1, 2, 3])])
        results = list(runner.run_once())

        assert len(results) == 3
        assert [r.target for r in results] == [1, 2, 3]

    def test_run_once_multiple_validators(self):
        runner = Runner([
            CountingValidator([1, 2]),
            FailingOnOddValidator([3, 4]),
        ])
        results = list(runner.run_once())

        assert len(results) == 4
        assert [r.target for r in results] == [1, 2, 3, 4]
        assert results[0].verdict == ValidationVerdict.PASSED
        assert results[1].verdict == ValidationVerdict.PASSED
        assert results[2].verdict == ValidationVerdict.FAILED
        assert results[3].verdict == ValidationVerdict.PASSED

    def test_run_yields_continuously(self):
        runner = Runner([CountingValidator([1])])
        iterator = runner.run()

        results = []
        for _ in range(5):
            results.append(next(iterator))

        assert len(results) == 5
        assert all(r.target == 1 for r in results)

    def test_run_once_preserves_order(self):
        runner = Runner([
            CountingValidator([1]),
            CountingValidator([2]),
            CountingValidator([3]),
        ])
        results = list(runner.run_once())

        assert [r.target for r in results] == [1, 2, 3]
