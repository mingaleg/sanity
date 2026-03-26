import pytest

from sanity.engine.time_limit import _can_enforce

requires_enforcement = pytest.mark.skipif(
    not _can_enforce(),
    reason="Time limit enforcement not available on this platform",
)
