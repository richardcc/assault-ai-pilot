import type { Dict, EvalRow, ModelPayload, ReplayMetaPayload, ScenarioDetailPayload } from "./types";

async function getJson(url: string): Promise<Dict> {
  const res = await fetch(url);
  const txt = await res.text();
  const payload = txt ? JSON.parse(txt) : {};
  if (!res.ok) {
    throw new Error(String((payload as Dict).message || `HTTP ${res.status}`));
  }
  return payload as Dict;
}

export function fetchCatalog(): Promise<Dict> {
  return getJson("/api/v2/catalog");
}

export function fetchTraceability(limit = 400): Promise<Dict> {
  return getJson(`/api/v2/curriculum-traceability?limit=${encodeURIComponent(String(limit))}`);
}

export function fetchModel(engine: string, model: string): Promise<ModelPayload> {
  const q = new URLSearchParams({ engine, model });
  return getJson(`/api/v2/model?${q.toString()}`) as Promise<ModelPayload>;
}

export function fetchModelEvals(engine: string, model: string, trainRunId: string, scenarioId: string): Promise<{ rows?: EvalRow[] } & Dict> {
  const q = new URLSearchParams({
    engine,
    model,
    train_run_id: trainRunId,
    scenario_id: scenarioId,
    include_payload: "1",
    offset: "0",
    limit: "128"
  });
  return getJson(`/api/v2/model/evals?${q.toString()}`) as Promise<{ rows?: EvalRow[] } & Dict>;
}

export function fetchCurriculumCompareLatest(limit = 300): Promise<Dict> {
  return getJson(`/api/v2/curriculum-compare-latest?limit=${encodeURIComponent(String(limit))}`);
}

export function fetchReplayMeta(evalSourcePath: string): Promise<ReplayMetaPayload> {
  const q = new URLSearchParams({ eval_source_path: String(evalSourcePath || "") });
  return getJson(`/api/v2/replay/meta?${q.toString()}`) as Promise<ReplayMetaPayload>;
}

export function fetchReplaySteps(evalSourcePath: string, episodeId: string, fromStep = 0, toStep = 79): Promise<Dict> {
  const q = new URLSearchParams({
    eval_source_path: String(evalSourcePath || ""),
    episode_id: String(episodeId || "episode_0"),
    from_step: String(fromStep),
    to_step: String(toStep),
  });
  return getJson(`/api/v2/replay/steps?${q.toString()}`);
}

export function fetchReplayLog(evalSourcePath: string, episodeIndex = 0, uptoStep = 0, fullEpisodeLog = false): Promise<Dict> {
  const q = new URLSearchParams({
    eval_source_path: String(evalSourcePath || ""),
    replay_path: "",
    episode_index: String(episodeIndex),
    upto_step: String(uptoStep),
    full_episode_log: fullEpisodeLog ? "1" : "0",
  });
  return getJson(`/api/replay-log?${q.toString()}`);
}

export function fetchTrainSummary(runId: string): Promise<Dict> {
  const q = new URLSearchParams({ run_id: String(runId || "") });
  return getJson(`/api/train-summary?${q.toString()}`);
}

export function fetchScenario(scenarioId: string): Promise<ScenarioDetailPayload> {
  const q = new URLSearchParams({ id: String(scenarioId || "") });
  return getJson(`/api/v2/scenario?${q.toString()}`) as Promise<ScenarioDetailPayload>;
}

export function fetchChannelAttribution(runId: string): Promise<Dict> {
  const q = new URLSearchParams({ run_id: String(runId || "") });
  return getJson(`/api/channel-attribution?${q.toString()}`);
}

export async function runChannelAttribution(runId: string): Promise<Dict> {
  const url = `/api/channel-attribution/run?run_id=${encodeURIComponent(runId)}`;
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId }),
    });
  } catch (err: any) {
    // If POST is blocked by proxy or environment, fallback to GET
    res = await fetch(url, { method: "GET" });
  }

  const txt = await res.text();
  let payload: any = {};
  try {
    payload = txt ? JSON.parse(txt) : {};
  } catch {
    payload = { error: `El servidor no devolvió JSON (HTTP ${res.status}): ${txt.slice(0, 120)}` };
  }

  if (!res.ok) {
    throw new Error(String(payload?.error || payload?.message || `HTTP ${res.status}`));
  }
  return payload as Dict;
}


