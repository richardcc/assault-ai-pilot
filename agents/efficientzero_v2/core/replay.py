from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ReplaySample:
    observation: Any
    policy_target: List[float]
    value_target: float
    reward_target: float
    info: Dict[str, Any]


class ReplayBuffer:
    def __init__(
        self,
        capacity: int = 10000,
        recent_fraction: float = 0.0,
        recent_window_ratio: float = 0.0,
    ):
        self.capacity = capacity
        self._items: List[ReplaySample] = []
        self._add_index: int = 0
        self.recent_fraction = float(max(0.0, min(1.0, recent_fraction)))
        self.recent_window_ratio = float(max(0.0, min(1.0, recent_window_ratio)))

    def add(self, sample: ReplaySample) -> None:
        if sample.info is None:
            sample.info = {}
        sample.info["replay_add_index"] = int(self._add_index)
        self._add_index += 1
        self._items.append(sample)
        if len(self._items) > self.capacity:
            self._items.pop(0)

    def extend(self, samples: List[ReplaySample]) -> None:
        for sample in samples:
            self.add(sample)

    def sample(self, batch_size: int) -> List[ReplaySample]:
        if not self._items:
            return []
        size = min(batch_size, len(self._items))
        if self.recent_fraction <= 0.0 or self.recent_window_ratio <= 0.0:
            return random.sample(self._items, size)
        total = len(self._items)
        recent_window = max(size, int(total * self.recent_window_ratio))
        recent_window = min(total, recent_window)
        recent_start = total - recent_window
        k_recent = int(round(size * self.recent_fraction))
        k_recent = min(max(0, k_recent), size, recent_window)

        recent_indices = list(range(recent_start, total))
        sampled_indices: List[int] = []
        if k_recent > 0:
            sampled_indices.extend(random.sample(recent_indices, k_recent))

        remaining = size - len(sampled_indices)
        if remaining > 0:
            taken = set(sampled_indices)
            pool = [i for i in range(total) if i not in taken]
            sampled_indices.extend(random.sample(pool, remaining))
        return [self._items[i] for i in sampled_indices]

    def __len__(self) -> int:
        return len(self._items)

    @property
    def add_index(self) -> int:
        return int(self._add_index)
