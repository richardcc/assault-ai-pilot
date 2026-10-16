async function fetchJson(url) {
  const res = await fetch(url);
  const txt = await res.text();
  const payload = txt ? JSON.parse(txt) : {};
  if (!res.ok) {
    const msg = payload && payload.message ? String(payload.message) : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return payload;
}

export async function getCatalog() {
  return await fetchJson("/api/v2/catalog");
}

export async function getCurriculumTraceability(limit = 400) {
  return await fetchJson(`/api/v2/curriculum-traceability?limit=${encodeURIComponent(String(limit))}`);
}

export async function getModel(engine, modelId) {
  const q = new URLSearchParams({ engine: String(engine || ""), model: String(modelId || "") });
  return await fetchJson(`/api/v2/model?${q.toString()}`);
}

export async function getModelTrains(engine, modelId, offset = 0, limit = 128) {
  const q = new URLSearchParams({
    engine: String(engine || ""),
    model: String(modelId || ""),
    offset: String(offset),
    limit: String(limit),
  });
  return await fetchJson(`/api/v2/model/trains?${q.toString()}`);
}

export async function getModelEvals(engine, modelId, trainRunId, scenarioId = "__all__", offset = 0, limit = 128) {
  const q = new URLSearchParams({
    engine: String(engine || ""),
    model: String(modelId || ""),
    train_run_id: String(trainRunId || ""),
    scenario_id: String(scenarioId || "__all__"),
    include_payload: "1",
    offset: String(offset),
    limit: String(limit),
  });
  return await fetchJson(`/api/v2/model/evals?${q.toString()}`);
}
