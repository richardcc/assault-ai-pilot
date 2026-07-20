import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark all MuZero tests so they can be excluded by default."""
    for item in items:
        item.add_marker("muzero")
