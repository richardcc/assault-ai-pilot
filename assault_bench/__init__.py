__all__ = ["run_benchmark"]


def run_benchmark(*args, **kwargs):
    # Lazy import avoids runpy warning when executing module with -m.
    from assault_bench.runner import run_benchmark as _run_benchmark

    return _run_benchmark(*args, **kwargs)
