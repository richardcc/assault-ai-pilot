__all__ = ["run_benchmark"]


def run_benchmark(*args, **kwargs):
    # Lazy import through orchestrator keeps runner internals decoupled.
    from assault_bench.benchmark_orchestrator import run_benchmark as _run_benchmark

    return _run_benchmark(*args, **kwargs)
