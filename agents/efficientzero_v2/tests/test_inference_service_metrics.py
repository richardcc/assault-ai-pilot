import torch

from agents.efficientzero_v2.core.inference_service import InferenceService


class _TinyModel:
    def initial_inference(self, observation: torch.Tensor, **kwargs):
        batch = int(observation.shape[0])
        hidden = torch.zeros(batch, 4, dtype=torch.float32, device=observation.device)
        policy = torch.zeros(batch, 8, dtype=torch.float32, device=observation.device)
        value = torch.zeros(batch, 1, dtype=torch.float32, device=observation.device)
        reward = torch.zeros(batch, 1, dtype=torch.float32, device=observation.device)
        return hidden, policy, value, reward


def test_inference_service_exposes_latency_and_queue_metrics() -> None:
    service = InferenceService(
        model=_TinyModel(),
        device="cpu",
        max_batch_size=4,
        batch_wait_ms=1.0,
    )
    service.start()
    try:
        obs = torch.zeros(1, 4, dtype=torch.float32)
        _ = service.infer("initial_inference", obs)
        metrics = service.metrics_snapshot()
    finally:
        service.stop()
    assert metrics["inference_requests_total"] >= 1.0
    assert "inference_latency_p50_ms" in metrics
    assert "inference_latency_p95_ms" in metrics
    assert "inference_queue_depth" in metrics
    assert "inference_staleness_proxy_steps" in metrics
