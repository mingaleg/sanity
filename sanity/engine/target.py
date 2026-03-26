from abc import ABC, abstractmethod
from collections.abc import Collection


class ValidationTarget(ABC):
    @abstractmethod
    def sanity_validation_target_id(self) -> str: ...

    @abstractmethod
    def sanity_validation_target_tags(self) -> Collection[str]: ...


class ValidationTargetIdResolver(ABC):
    @abstractmethod
    def sanity_validation_taget_from_id(target_id: str) -> ValidationTarget: ...

