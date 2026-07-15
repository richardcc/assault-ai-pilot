from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass
from statistics import mean
from typing import Any

import torch


@dataclass
class _InferenceRequest:
    request_id: str
    method: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    done: threading.Event
    enqueued_at: float
    result: Any = None
    error: Exception | None = None


class InferenceService:
    """
    Centralized GPU inference service with micro-batching.
    """

    def __init__(
        self,
        model: Any,
        device: str = "cuda",
        max_batch_size: int = 16,
        batch_wait_ms: float = 2.0,
    ):
        self.model = model
        self.device = str(device)
        self.max_batch_size = int(max(1, max_batch_size))
        self.batch_wait_s = float(max(0.0, batch_wait_ms)) / 1000.0
        self._q: queue.Queue[_InferenceRequest | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        self._latencies_ms: list[float] = []
        self._queue_waits_ms: list[float] = []
        self._batch_sizes: list[int] = []
        self._requests_total = 0
        self._batches_total = 0
        self._max_queue_depth = 0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="ezv2-inference-service", daemon=True)
        self._thread.start()

    def stop(self, join_timeout_s: float = 5.0) -> None:
        if not self._running:
            return
        self._running = False
        self._q.put(None)
        if self._thread is not None:
            self._thread.join(timeout=float(join_timeout_s))
            self._thread = None

    def create_proxy(self) -> "RemoteInferenceModel":
        return RemoteInferenceModel(self)

    def infer(self, method: str, *args: Any, **kwargs: Any) -> Any:
        req = _InferenceRequest(
            request_id=uuid.uuid4().hex,
            method=str(method),
            args=tuple(args),
            kwargs=dict(kwargs or {}),
            done=threading.Event(),
            enqueued_at=time.perf_counter(),
        )
        self._q.put(req)
        req.done.wait()
        if req.error is not None:
            raise req.error
        return req.result

    def _loop(self) -> None:
        while self._running:
            item = self._q.get()
            if item is None:
                break
            batch = [item]
            t0 = time.perf_counter()
            while len(batch) < self.max_batch_size:
                remaining = self.batch_wait_s - (time.perf_counter() - t0)
                if remaining <= 0.0:
                    break
                try:
                    nxt = self._q.get(timeout=remaining)
                except queue.Empty:
                    break
                if nxt is None:
                    self._q.put(None)
                    break
                if nxt.method != item.method:
                    # Different method: process later to keep tensor shapes simple.
                    self._q.put(nxt)
                    break
                batch.append(nxt)
            self._run_batch(batch)

    def _run_batch(self, batch: list[_InferenceRequest]) -> None:
        method = batch[0].method
        started_at = time.perf_counter()
        queue_wait_ms = [
            max(0.0, (started_at - float(req.enqueued_at)) * 1000.0) for req in batch
        ]
        try:
            with torch.inference_mode():
                if len(batch) == 1:
                    out = self._call_model(method, batch[0].args, batch[0].kwargs)
                    batch[0].result = self._to_cpu_detached(out)
                else:
                    out = self._call_model_batched(method, batch)
                    for req, val in zip(batch, out):
                        req.result = self._to_cpu_detached(val)
        except Exception as exc:  # noqa: BLE001
            for req in batch:
                req.error = exc
        finally:
            elapsed_ms = max(0.0, (time.perf_counter() - started_at) * 1000.0)
            with self._lock:
                self._requests_total += int(len(batch))
                self._batches_total += 1
                self._latencies_ms.append(float(elapsed_ms))
                self._queue_waits_ms.extend(float(v) for v in queue_wait_ms)
                self._batch_sizes.append(int(len(batch)))
                self._max_queue_depth = max(self._max_queue_depth, int(self._q.qsize()))
            for req in batch:
                req.done.set()

    def metrics_snapshot(self) -> dict[str, float]:
        with self._lock:
            latencies = list(self._latencies_ms)
            waits = list(self._queue_waits_ms)
            batch_sizes = list(self._batch_sizes)
            requests_total = int(self._requests_total)
            batches_total = int(self._batches_total)
            max_queue_depth = int(self._max_queue_depth)
        if not latencies:
            return {
                "inference_requests_total": float(requests_total),
                "inference_batches_total": float(batches_total),
                "inference_latency_p50_ms": 0.0,
                "inference_latency_p95_ms": 0.0,
                "inference_latency_mean_ms": 0.0,
                "inference_queue_wait_p95_ms": 0.0,
                "inference_queue_wait_mean_ms": 0.0,
                "inference_batch_size_mean": 0.0,
                "inference_queue_depth": float(self._q.qsize()),
                "inference_queue_depth_max": float(max_queue_depth),
                "inference_staleness_proxy_steps": 0.0,
            }
        return {
            "inference_requests_total": float(requests_total),
            "inference_batches_total": float(batches_total),
            "inference_latency_p50_ms": float(_percentile(latencies, 0.50)),
            "inference_latency_p95_ms": float(_percentile(latencies, 0.95)),
            "inference_latency_mean_ms": float(mean(latencies)),
            "inference_queue_wait_p95_ms": float(_percentile(waits, 0.95)) if waits else 0.0,
            "inference_queue_wait_mean_ms": float(mean(waits)) if waits else 0.0,
            "inference_batch_size_mean": float(mean(batch_sizes)) if batch_sizes else 0.0,
            "inference_queue_depth": float(self._q.qsize()),
            "inference_queue_depth_max": float(max_queue_depth),
            # Queue wait is a practical staleness proxy for actor->inference delay.
            "inference_staleness_proxy_steps": float(_percentile(waits, 0.95)) if waits else 0.0,
        }


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(float(v) for v in values)
    pos = max(0, min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * float(q)))))
    return float(sorted_values[pos])

    def _call_model(self, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        fn = getattr(self.model, method)
        moved_args = tuple(self._to_device(x) for x in args)
        moved_kwargs = {k: self._to_device(v) for k, v in kwargs.items()}
        return fn(*moved_args, **moved_kwargs)

    def _call_model_batched(self, method: str, batch: list[_InferenceRequest]) -> list[Any]:
        # Supports methods where first arg is batch tensor and optional second arg batch tensor.
        fn = getattr(self.model, method)
        arg0 = torch.cat([self._to_device(req.args[0]) for req in batch], dim=0)
        if len(batch[0].args) > 1 and isinstance(batch[0].args[1], torch.Tensor):
            arg1 = torch.cat([self._to_device(req.args[1]) for req in batch], dim=0)
            out = fn(arg0, arg1)
        else:
            out = fn(arg0)
        return self._split_output(out, [req.args[0].shape[0] for req in batch])

    def _to_device(self, x: Any) -> Any:
        if isinstance(x, torch.Tensor):
            return x.to(self.device, non_blocking=True)
        return x

    def _to_cpu_detached(self, x: Any) -> Any:
        if isinstance(x, torch.Tensor):
            return x.detach().to("cpu")
        if isinstance(x, (tuple, list)):
            out = [self._to_cpu_detached(v) for v in x]
            return type(x)(out) if isinstance(x, tuple) else out
        if isinstance(x, dict):
            return {k: self._to_cpu_detached(v) for k, v in x.items()}
        return x

    def _split_output(self, out: Any, sizes: list[int]) -> list[Any]:
        if isinstance(out, torch.Tensor):
            chunks = list(torch.split(out, sizes, dim=0))
            return chunks
        if isinstance(out, (tuple, list)):
            per_field = [self._split_output(v, sizes) for v in out]
            rows: list[Any] = []
            for i in range(len(sizes)):
                if isinstance(out, tuple):
                    rows.append(tuple(field[i] for field in per_field))
                else:
                    rows.append([field[i] for field in per_field])
            return rows
        if isinstance(out, dict):
            per_key = {k: self._split_output(v, sizes) for k, v in out.items()}
            return [{k: per_key[k][i] for k in per_key} for i in range(len(sizes))]
        return [out for _ in sizes]


class RemoteInferenceModel:
    """
    Drop-in model proxy used by selfplay workers.
    """

    def __init__(self, service: InferenceService):
        self._service = service
        src = service.model
        self.encoder_type = getattr(src, "encoder_type", "mlp")
        self.observation_channels = int(getattr(src, "observation_channels", 8))
        self.observation_height = int(getattr(src, "observation_height", 16))
        self.observation_width = int(getattr(src, "observation_width", 16))
        self.action_dim = int(getattr(src, "action_dim", 32))

    def parameters(self):
        # Selfplay helpers only use this to infer a device for observation tensors.
        # We return a CPU placeholder because this proxy marshals calls itself.
        yield torch.empty(1, device="cpu")

    def initial_inference(self, observation: torch.Tensor, **kwargs: Any):
        return self._service.infer("initial_inference", observation, **kwargs)

    def recurrent_inference(self, hidden: torch.Tensor, action: torch.Tensor, **kwargs: Any):
        return self._service.infer("recurrent_inference", hidden, action, **kwargs)
