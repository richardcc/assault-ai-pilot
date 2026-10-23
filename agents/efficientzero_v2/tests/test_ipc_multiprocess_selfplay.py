import torch
import torch.multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

from agents.efficientzero_v2.core.inference_service import (
    InferenceService,
    IPCInferenceBridge,
    IPCProcessInferenceClient,
)


class SimpleInferenceModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder_type = "cnn"
        self.observation_channels = 38
        self.observation_height = 16
        self.observation_width = 16
        self.action_dim = 32
        self.conv = torch.nn.Conv2d(38, 16, kernel_size=1)
        self.fc_p = torch.nn.Linear(16 * 16 * 16, 32)
        self.fc_v = torch.nn.Linear(16 * 16 * 16, 1)

    def initial_inference(self, obs, return_aux=False):
        b = obs.shape[0]
        feat = torch.relu(self.conv(obs))
        flat = feat.view(b, -1)
        logits = self.fc_p(flat)
        vals = self.fc_v(flat)
        return feat, logits, vals, 0.0, {}

    def recurrent_inference(self, hidden, action, return_aux=False):
        b = hidden.shape[0]
        flat = hidden.view(b, -1)
        logits = self.fc_p(flat)
        vals = self.fc_v(flat)
        return hidden, logits, vals, 0.0, {}


def _test_worker_init(counter, req_q, resp_qs):
    global _TEST_CLIENT
    with counter.get_lock():
        w_id = int(counter.value)
        counter.value += 1
    _TEST_CLIENT = IPCProcessInferenceClient(
        worker_id=w_id,
        request_queue=req_q,
        response_queue=resp_qs[w_id],
        model_metadata={
            "encoder_type": "cnn",
            "observation_channels": 38,
            "observation_height": 16,
            "observation_width": 16,
            "action_dim": 32,
        },
    )


def _test_worker_task(n_calls: int):
    global _TEST_CLIENT
    results = []
    for _ in range(n_calls):
        obs = torch.randn(1, 38, 16, 16)
        hidden, logits, val, rew, aux = _TEST_CLIENT.initial_inference(obs)
        assert logits.shape == (1, 32)
        results.append(float(val[0, 0].item()))
    return len(results)


def test_ipc_multiprocess_inference_bridge():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SimpleInferenceModel().to(device)
    service = InferenceService(model=model, device=device, max_batch_size=8, batch_wait_ms=1.5)
    service.start()

    num_workers = 2
    req_q = mp.Queue()
    resp_qs = [mp.Queue() for _ in range(num_workers)]
    counter = mp.Value("i", 0)

    bridge = IPCInferenceBridge(service=service, request_queue=req_q, response_queues=resp_qs)
    bridge.start()

    try:
        mp_ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(
            max_workers=num_workers,
            mp_context=mp_ctx,
            initializer=_test_worker_init,
            initargs=(counter, req_q, resp_qs),
        ) as executor:
            futures = [executor.submit(_test_worker_task, 15) for _ in range(num_workers)]
            counts = [f.result(timeout=15.0) for f in futures]
            assert counts == [15, 15]
    finally:
        bridge.stop()
        service.stop()
