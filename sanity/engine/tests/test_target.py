from collections.abc import Collection

from sanity import ValidationTarget, ValidationTargetIdResolver


class ConcreteTarget(ValidationTarget):
    def __init__(self, id_value: str, tags: Collection[str]):
        self._id = id_value
        self._tags = tags

    def sanity_validation_target_id(self) -> str:
        return self._id

    def sanity_validation_target_tags(self) -> Collection[str]:
        return self._tags


class ConcreteResolver(ValidationTargetIdResolver):
    def sanity_validation_taget_from_id(self, target_id: str) -> ValidationTarget:
        return ConcreteTarget(target_id, [])


class TestValidationTarget:
    def test_target_id(self):
        target = ConcreteTarget("my-id", ["tag1"])
        assert target.sanity_validation_target_id() == "my-id"

    def test_target_tags(self):
        target = ConcreteTarget("id", ["a", "b", "c"])
        assert list(target.sanity_validation_target_tags()) == ["a", "b", "c"]


class TestValidationTargetIdResolver:
    def test_from_id(self):
        resolver = ConcreteResolver()
        target = resolver.sanity_validation_taget_from_id("restored-id")
        assert target.sanity_validation_target_id() == "restored-id"
