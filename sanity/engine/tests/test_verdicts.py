import pytest

from sanity import ValidationResult, ValidationVerdict, ok, failed, not_applicable, ignored_result, just_ignored, skipped


class TestValidationVerdict:
    def test_values(self):
        assert ValidationVerdict.PASSED == "PASSED"
        assert ValidationVerdict.FAILED == "FAILED"
        assert ValidationVerdict.SKIPPED == "SKIPPED"
        assert ValidationVerdict.NOT_APPLICABLE == "NOT_APPLICABLE"
        assert ValidationVerdict.INTERNAL_ERROR == "INTERNAL_ERROR"

    def test_is_str(self):
        assert isinstance(ValidationVerdict.PASSED, str)


class TestValidationResult:
    def test_creation(self):
        result = ValidationResult(verdict=ValidationVerdict.PASSED, reason="test")
        assert result.verdict == ValidationVerdict.PASSED
        assert result.reason == "test"
        assert result.ignored is False

    def test_frozen(self):
        result = ValidationResult(verdict=ValidationVerdict.PASSED, reason="test")
        with pytest.raises(AttributeError):
            result.verdict = ValidationVerdict.FAILED


class TestHelperFunctions:
    def test_ok_default_reason(self):
        result = ok()
        assert result.verdict == ValidationVerdict.PASSED
        assert result.reason == ""

    def test_ok_with_reason(self):
        result = ok("all good")
        assert result.verdict == ValidationVerdict.PASSED
        assert result.reason == "all good"

    def test_failed(self):
        result = failed("something broke")
        assert result.verdict == ValidationVerdict.FAILED
        assert result.reason == "something broke"

    def test_not_applicable_default_reason(self):
        result = not_applicable()
        assert result.verdict == ValidationVerdict.NOT_APPLICABLE
        assert result.reason == ""

    def test_not_applicable_with_reason(self):
        result = not_applicable("n/a")
        assert result.verdict == ValidationVerdict.NOT_APPLICABLE
        assert result.reason == "n/a"

    def test_skipped(self):
        result = skipped("not needed")
        assert result.verdict == ValidationVerdict.SKIPPED
        assert result.reason == "not needed"
        assert result.ignored is False

    def test_ignored_result(self):
        original = failed("not relevant")
        result = ignored_result(original)
        assert result.verdict == ValidationVerdict.FAILED
        assert result.ignored is True
        assert result.reason == "not relevant"

    def test_ignored_result_preserves_verdict(self):
        original = ok("all good")
        result = ignored_result(original)
        assert result.verdict == ValidationVerdict.PASSED
        assert result.ignored is True

    def test_just_ignored(self):
        result = just_ignored("skipping this")
        assert result.verdict == ValidationVerdict.SKIPPED
        assert result.reason == "skipping this"
        assert result.ignored is True
