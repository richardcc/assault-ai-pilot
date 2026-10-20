"""
Hot-Loop Telemetry Probe Profiler and Lazy Evaluation Architecture.

Adheres strictly to:
1. Zero-Mock / Zero-Inference: Authentic timing measurements with high-precision
   time.perf_counter_ns(). No fake overhead percentages or synthesized durations.
2. Overhead Budget: Validates that telemetry probes consume < 1.5% of total step
   execution time.
3. Lazy Evaluation: Defers expensive spatial map probes (e.g. threat maps, reachable
   hexes) until accessed, caching results for subsequent consumers.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
import math
import time
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, TypeVar


@dataclass
class ProbeMetric:
    """Statistical metric for a single telemetry probe."""

    name: str
    count: int = 0
    total_ns: int = 0
    min_ns: int = 0
    max_ns: int = 0

    def record(self, duration_ns: int) -> None:
        self.count += 1
        self.total_ns += duration_ns
        if self.count == 1:
            self.min_ns = duration_ns
            self.max_ns = duration_ns
        else:
            if duration_ns < self.min_ns:
                self.min_ns = duration_ns
            if duration_ns > self.max_ns:
                self.max_ns = duration_ns

    @property
    def total_us(self) -> float:
        return self.total_ns / 1_000.0

    @property
    def mean_us(self) -> float:
        return (self.total_ns / self.count / 1_000.0) if self.count > 0 else 0.0

    @property
    def min_us(self) -> float:
        return self.min_ns / 1_000.0

    @property
    def max_us(self) -> float:
        return self.max_ns / 1_000.0


@dataclass
class ProbeProfilingSummary:
    """Aggregated report of probe telemetry overhead."""

    total_step_count: int
    total_step_time_us: float
    total_probe_time_us: float
    probe_overhead_pct: float
    probes: Dict[str, ProbeMetric] = field(default_factory=dict)
    budget_exceeded: bool = False
    budget_target_pct: float = 1.5

    def format_report(self) -> str:
        lines = [
            "=" * 78,
            "HOT-LOOP TELEMETRY PROBE PROFILING REPORT",
            "=" * 78,
            f"Steps Profiled: {self.total_step_count}",
            f"Total Step Execution Time: {self.total_step_time_us:.2f} us",
            f"Total Probe Telemetry Time: {self.total_probe_time_us:.2f} us",
            f"Telemetry Overhead: {self.probe_overhead_pct:.4f}% (Budget Target: < {self.budget_target_pct:.2f}%)",
            f"Budget Status: {'[EXCEEDED]' if self.budget_exceeded else '[OK - WITHIN BUDGET]'}",
            "-" * 78,
            f"{'Probe Name':<38} | {'Calls':<6} | {'Mean (us)':<10} | {'Total (us)':<11} | {'Step %':<8}",
            "-" * 78,
        ]
        for name, metric in sorted(self.probes.items(), key=lambda kv: kv[1].total_ns, reverse=True):
            pct_step = (
                (metric.total_us / self.total_step_time_us * 100.0)
                if self.total_step_time_us > 0
                else 0.0
            )
            lines.append(
                f"{name:<38} | {metric.count:<6} | {metric.mean_us:<10.2f} | {metric.total_us:<11.2f} | {pct_step:<7.3f}%"
            )
        lines.append("=" * 78)
        return "\n".join(lines)


class ProbeProfiler:
    """
    High-precision microsecond profiler for measuring probe overhead in hot loops.
    Zero-mock: captures real time.perf_counter_ns() without mock values.
    """

    def __init__(self, enabled: bool = True, budget_target_pct: float = 1.5) -> None:
        self.enabled = enabled
        self.budget_target_pct = budget_target_pct
        self._probes: Dict[str, ProbeMetric] = {}
        self._total_step_ns: int = 0
        self._step_count: int = 0

    def reset(self) -> None:
        self._probes.clear()
        self._total_step_ns = 0
        self._step_count = 0

    def record_probe(self, name: str, duration_ns: int) -> None:
        if not self.enabled:
            return
        if name not in self._probes:
            self._probes[name] = ProbeMetric(name=name)
        self._probes[name].record(duration_ns)

    def record_step(self, duration_ns: int) -> None:
        if not self.enabled:
            return
        self._total_step_ns += duration_ns
        self._step_count += 1

    @contextlib.contextmanager
    def time_probe(self, name: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        t0 = time.perf_counter_ns()
        try:
            yield
        finally:
            t1 = time.perf_counter_ns()
            self.record_probe(name, t1 - t0)

    @contextlib.contextmanager
    def time_step(self) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        t0 = time.perf_counter_ns()
        try:
            yield
        finally:
            t1 = time.perf_counter_ns()
            self.record_step(t1 - t0)

    def get_summary(self) -> ProbeProfilingSummary:
        total_probe_ns = sum(p.total_ns for p in self._probes.values())
        total_probe_us = total_probe_ns / 1_000.0
        total_step_us = self._total_step_ns / 1_000.0
        overhead_pct = (
            (total_probe_us / total_step_us * 100.0)
            if total_step_us > 0
            else 0.0
        )
        return ProbeProfilingSummary(
            total_step_count=self._step_count,
            total_step_time_us=total_step_us,
            total_probe_time_us=total_probe_us,
            probe_overhead_pct=overhead_pct,
            probes=dict(self._probes),
            budget_exceeded=(overhead_pct > self.budget_target_pct),
            budget_target_pct=self.budget_target_pct,
        )

    def assert_overhead_within_budget(self, max_overhead_pct: Optional[float] = None) -> None:
        budget = max_overhead_pct if max_overhead_pct is not None else self.budget_target_pct
        summary = self.get_summary()
        if summary.probe_overhead_pct > budget:
            raise AssertionError(
                f"Telemetry probe overhead {summary.probe_overhead_pct:.3f}% exceeds maximum budget "
                f"of {budget:.2f}%. Breakdown:\n{summary.format_report()}"
            )


T = TypeVar("T")


class LazyProbeSnapshot(Mapping[str, Any]):
    """
    Lazy evaluated container for expensive telemetry probes (e.g. spatial maps,
    threat projections, reachability graphs).

    Defers evaluation until accessed (e.g. when serializing to Parquet or XAI export).
    Once resolved, caches the value and behaves transparently like the underlying dictionary.
    """

    def __init__(self, factory: Callable[[], Mapping[str, Any]], probe_name: str = "lazy_probe") -> None:
        self._factory = factory
        self._probe_name = probe_name
        self._resolved_value: Optional[Mapping[str, Any]] = None
        self._evaluated: bool = False

    def is_evaluated(self) -> bool:
        return self._evaluated

    def get_value(self) -> Mapping[str, Any]:
        if not self._evaluated:
            prof = get_global_probe_profiler()
            if prof and prof.enabled:
                with prof.time_probe(self._probe_name):
                    res = self._factory()
            else:
                res = self._factory()
            self._resolved_value = dict(res or {})
            self._evaluated = True
        return self._resolved_value or {}

    def to_dict(self) -> dict[str, Any]:
        return dict(self.get_value())

    # Mapping contract implementation:
    def __getitem__(self, key: str) -> Any:
        return self.get_value()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.get_value())

    def __len__(self) -> int:
        return len(self.get_value())

    def __contains__(self, key: object) -> bool:
        return key in self.get_value()

    def keys(self):
        return self.get_value().keys()

    def values(self):
        return self.get_value().values()

    def items(self):
        return self.get_value().items()

    def copy(self) -> dict[str, Any]:
        return dict(self.get_value())

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, LazyProbeSnapshot):
            return self.get_value() == other.get_value()
        if isinstance(other, Mapping):
            return self.get_value() == other
    def __reduce__(self):
        val = dict(self.get_value())
        return (_restore_lazy_probe_snapshot, (val, self._probe_name))

    def __repr__(self) -> str:
        state = "evaluated" if self._evaluated else "deferred"
        return f"<LazyProbeSnapshot probe={self._probe_name} state={state}>"


def _restore_lazy_probe_snapshot(data: dict[str, Any], probe_name: str = "") -> "LazyProbeSnapshot":
    obj = LazyProbeSnapshot.__new__(LazyProbeSnapshot)
    obj._factory = None
    obj._probe_name = str(probe_name or "")
    obj._resolved_value = dict(data or {})
    obj._evaluated = True
    return obj


# Global thread/process probe profiler instance:
_GLOBAL_PROFILER: Optional[ProbeProfiler] = None


def get_global_probe_profiler() -> Optional[ProbeProfiler]:
    return _GLOBAL_PROFILER


def set_global_probe_profiler(profiler: Optional[ProbeProfiler]) -> None:
    global _GLOBAL_PROFILER
    _GLOBAL_PROFILER = profiler


# Reusable no-op context for zero-overhead hot loops when profiling is inactive:
_NOOP_CONTEXT = contextlib.nullcontext()


def profile_probe(name: str):
    prof = _GLOBAL_PROFILER
    if prof is not None and prof.enabled:
        return prof.time_probe(name)
    return _NOOP_CONTEXT
