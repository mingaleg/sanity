from collections.abc import Iterable, Iterator
from typing import Any

from sanity.engine import DetailedValidationResult, Validator


class Runner:
    """Runs validators continuously, yielding results.

    Example:
        >>> runner = Runner([MyValidator(), OtherValidator()])
        >>> for result in runner.run():
        ...     print(f"{result.target}: {result.verdict}")
    """

    def __init__(self, validators: Iterable[Validator[Any]]):
        self._validators = list(validators)

    def run(self) -> Iterator[DetailedValidationResult[Any]]:
        """Run all validators continuously, yielding results.

        Iterates through each validator, gets its targets via targets_in_scope(),
        validates each target, and yields the result. Repeats forever.
        """
        while True:
            yield from self.run_once()

    def run_once(self) -> Iterator[DetailedValidationResult[Any]]:
        """Run all validators once through all their targets."""
        for validator in self._validators:
            for target in validator.targets_in_scope():
                yield validator.get_detailed_validation_result(target)
