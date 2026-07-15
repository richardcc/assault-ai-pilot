from __future__ import annotations

from typing import Any

__all__ = ["build_reporting_catalog"]


def build_reporting_catalog(*args: Any, **kwargs: Any):
    # Lazy import avoids runpy RuntimeWarning when executing
    # `python -m mlops.reporting.build_catalog`.
    from mlops.reporting.build_catalog import build_reporting_catalog as _impl

    return _impl(*args, **kwargs)
