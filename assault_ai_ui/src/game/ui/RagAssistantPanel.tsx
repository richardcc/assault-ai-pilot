import { useEffect, useMemo, useRef, useState } from "react";
import { apiUrl } from "../../config/backend";
import { unitImages } from "../config/unitImages";

type Citation = {
  source_type: string;
  source_id: string;
  snippet: string;
};

type TerrainIntel = {
  scenario_name: string;
  urban_pct: number;
  forest_pct: number;
  open_pct: number;
  defilade_corridors_count: number;
  dominant_terrain_desc: string;
};

type ForcesOob = {
  own_side: string;
  enemy_side: string;
  own_total: number;
  enemy_total: number;
  own_roles: Record<string, number>;
  enemy_roles: Record<string, number>;
  own_suppressed: number;
  enemy_suppressed: number;
  own_critical_hp: number;
  enemy_critical_hp: number;
};

type NeuralAssessment = {
  active_brain: string;
  win_probability: number;
  root_value: number;
  total_decisions: number;
  corrections: number;
  strategic_outlook: string;
};

type SituationResult = {
  situation_summary: string;
  priorities: string[];
  risks: string[];
  opportunities?: string[];
  key_unit_alerts?: string[];
  citations: Citation[];
  limitations: string[];
  terrain_intel?: TerrainIntel;
  forces_oob?: ForcesOob;
  neural_assessment?: NeuralAssessment;
};

type QueryResult = {
  mode?: string;
  answer: string;
  citations: Citation[];
  limitations: string[];
  llm_model?: string;
};

type CounterPreview = {
  unitKey: string;
  label: string;
  imagePath: string;
};

function normalizeToken(value: string): string {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function findCounterPreview(result: QueryResult | null, query: string): CounterPreview | null {
  if (!result) return null;
  const catalog = unitImages as Record<string, { label?: string; full?: string }>;
  const byKey = new Map<string, string>(Object.keys(catalog).map((k) => [normalizeToken(k), k]));

  const candidateTokens = new Set<string>();
  for (const c of result.citations || []) {
    candidateTokens.add(normalizeToken(c.source_id));
    const snippetTokens = String(c.snippet || "").match(/[A-Za-z0-9_]+/g) || [];
    for (const t of snippetTokens) {
      candidateTokens.add(normalizeToken(t));
    }
  }
  const queryTokens = String(query || "").match(/[A-Za-z0-9_]+/g) || [];
  for (const t of queryTokens) {
    candidateTokens.add(normalizeToken(t));
  }

  for (const token of candidateTokens) {
    const direct = byKey.get(token);
    if (direct && catalog[direct]?.full) {
      return {
        unitKey: direct,
        label: catalog[direct]?.label || direct,
        imagePath: catalog[direct].full!,
      };
    }
  }

  const loweredSearch = `${query} ${result.answer} ${(result.citations || []).map((c) => c.snippet).join(" ")}`.toLowerCase();
  for (const [unitKey, def] of Object.entries(catalog)) {
    if (!def?.full) continue;
    const label = String(def.label || "").toLowerCase();
    const key = unitKey.toLowerCase().replace(/_/g, " ");
    if (label && loweredSearch.includes(label)) {
      return { unitKey, label: def.label || unitKey, imagePath: def.full };
    }
    if (key && loweredSearch.includes(key)) {
      return { unitKey, label: def.label || unitKey, imagePath: def.full };
    }
  }

  return null;
}

export function RagAssistantPanel({ gameData }: { gameData?: any }) {
  const [activeTab, setActiveTab] = useState<"situation" | "rules">("situation");

  // Situation state
  const [situationLoading, setSituationLoading] = useState(false);
  const [situationError, setSituationError] = useState<string | null>(null);
  const [situationResult, setSituationResult] = useState<SituationResult | null>(null);

  // Rules state
  const [query, setQuery] = useState("");
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [rulesResult, setRulesResult] = useState<QueryResult | null>(null);
  const [model, setModel] = useState("qwen2.5:14b");
  const [retrievalMode, setRetrievalMode] = useState<"auto" | "rules" | "data" | "hybrid">("rules");
  const [liveModels, setLiveModels] = useState<string[]>([]);
  const [ollamaReachable, setOllamaReachable] = useState<boolean | null>(null);
  const conversationIdRef = useRef<string>(
    `rag-unified-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  );

  const fallbackModels = [
    "qwen2.5:14b",
    "qwen2.5-coder:14b",
    "llama3.1:8b",
    "deepseek-r1:14b",
  ];
  const modelOptions = useMemo(
    () => (liveModels.length ? liveModels : fallbackModels),
    [liveModels]
  );

  useEffect(() => {
    const loadOllamaStatus = async () => {
      try {
        const res = await fetch(apiUrl("/api/rag/ollama/status"));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const models = Array.isArray(data?.models)
          ? data.models.filter((m: unknown) => typeof m === "string" && m.trim().length > 0)
          : [];
        setOllamaReachable(Boolean(data?.reachable));
        if (models.length) {
          setLiveModels(models);
          setModel((prev) => (models.includes(prev) ? prev : String(data?.default_model || models[0])));
        } else if (typeof data?.default_model === "string" && data.default_model.trim()) {
          setModel((prev) => prev || data.default_model);
        }
      } catch {
        setOllamaReachable(false);
      }
    };
    void loadOllamaStatus();
  }, []);

  const statusColor =
    ollamaReachable == null ? "#f6c945" : ollamaReachable ? "#22c55e" : "#38bdf8";
  const statusText =
    ollamaReachable == null
      ? "Checking LLM..."
      : ollamaReachable
      ? "Ollama Active"
      : "Deterministic XAI Engine";

  const counterPreview = useMemo(() => findCounterPreview(rulesResult, query), [rulesResult, query]);

  // Explain situation action leveraging complete XAI stack
  const explainSituation = async () => {
    if (!gameData) return;
    setSituationLoading(true);
    setSituationError(null);
    try {
      const res = await fetch(apiUrl("/api/rag/explain_situation"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state_snapshot: gameData }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const json = (await res.json()) as SituationResult;
      setSituationResult(json);
    } catch (e) {
      setSituationError(`SitRep analysis error: ${String(e)}`);
      setSituationResult(null);
    } finally {
      setSituationLoading(false);
    }
  };

  // Run rule query
  async function runQuery(customQuery?: string) {
    const q = (customQuery ?? query).trim();
    if (!q) return;
    if (customQuery) setQuery(customQuery);
    setRulesLoading(true);
    setRulesError(null);
    try {
      const payload: Record<string, unknown> = {
        query: q,
        conversation_id: conversationIdRef.current,
        llm_model: model,
      };
      if (retrievalMode !== "auto") {
        payload.mode = retrievalMode;
      }
      const res = await fetch(apiUrl("/api/rag/query"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = (await res.json()) as QueryResult;
      setRulesResult(data);
    } catch (e) {
      setRulesError(`Doctrinal search error: ${String(e)}`);
      setRulesResult(null);
    } finally {
      setRulesLoading(false);
    }
  }

  // Auto-generate SitRep when first opened or when gameData becomes available
  useEffect(() => {
    if (gameData && !situationResult && !situationLoading) {
      void explainSituation();
    }
  }, [gameData?.turn, gameData?.active_side]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 11, padding: "2px 0" }}>
      {/* Top Header with Tab Switch and LLM Status */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.12)", paddingBottom: 8 }}>
        <div style={{ display: "flex", gap: 6 }}>
          <button
            onClick={() => setActiveTab("situation")}
            style={{
              padding: "5px 12px",
              fontSize: 11,
              fontWeight: activeTab === "situation" ? 700 : 500,
              background: activeTab === "situation" ? "rgba(0, 240, 255, 0.18)" : "rgba(255,255,255,0.04)",
              color: activeTab === "situation" ? "var(--neon-cyan)" : "var(--text-secondary)",
              border: activeTab === "situation" ? "1px solid rgba(0, 240, 255, 0.4)" : "1px solid rgba(255,255,255,0.08)",
              borderRadius: 5,
              cursor: "pointer",
              transition: "all 0.2s ease",
            }}
          >
            📋 Tactical Situation
          </button>
          <button
            onClick={() => setActiveTab("rules")}
            style={{
              padding: "5px 12px",
              fontSize: 11,
              fontWeight: activeTab === "rules" ? 700 : 500,
              background: activeTab === "rules" ? "rgba(0, 240, 255, 0.18)" : "rgba(255,255,255,0.04)",
              color: activeTab === "rules" ? "var(--neon-cyan)" : "var(--text-secondary)",
              border: activeTab === "rules" ? "1px solid rgba(0, 240, 255, 0.4)" : "1px solid rgba(255,255,255,0.08)",
              borderRadius: 5,
              cursor: "pointer",
              transition: "all 0.2s ease",
            }}
          >
            📖 Rules & Doctrine
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, color: "var(--text-secondary)" }}>
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: statusColor,
              boxShadow: `0 0 6px ${statusColor}`,
              display: "inline-block",
            }}
          />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>{statusText}</span>
        </div>
      </div>

      {/* TAB 1: SITUATION (TACTICAL SITREP WITH FULL XAI) */}
      {activeTab === "situation" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {/* Action Ribbon */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--text-muted)", fontSize: 10.5, fontWeight: 600 }}>
              Live Battlefield SitRep & IPB Intel:
            </span>
            <button
              className="btn-tactical"
              onClick={explainSituation}
              disabled={situationLoading || !gameData}
              style={{ fontSize: 10.5, padding: "4px 10px", fontWeight: 700 }}
            >
              {situationLoading ? "Analyzing Battlefield Intel..." : "⚡ Generate SitRep"}
            </button>
          </div>

          {situationError && (
            <div style={{ padding: "8px 10px", background: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: 6, color: "#fca5a5" }}>
              {situationError}
            </div>
          )}

          {/* 1. NEURAL ASSESSMENT CARD */}
          <div style={{ background: "rgba(10, 14, 26, 0.8)", border: "1px solid rgba(0, 240, 255, 0.22)", borderRadius: 7, padding: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 13 }}>🧠</span>
                <span style={{ fontFamily: "var(--font-tech)", fontWeight: 700, fontSize: 11, color: "var(--neon-cyan)", letterSpacing: 0.5 }}>
                  Active AI Brain: {situationResult?.neural_assessment?.active_brain || "EfficientZero V2 (MCTS PUCT 253x)"}
                </span>
              </div>
              <span style={{ fontSize: 9.5, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                CUDA / Tensor Cores
              </span>
            </div>

            {situationResult?.neural_assessment && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 4 }}>
                {/* Win Prob Bar */}
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--text-muted)", marginBottom: 2 }}>
                    <span>Projected Win Probability:</span>
                    <strong style={{ color: situationResult.neural_assessment.win_probability >= 50 ? "#4ade80" : "#f87171", fontFamily: "var(--font-mono)" }}>
                      {situationResult.neural_assessment.win_probability}%
                    </strong>
                  </div>
                  <div style={{ width: "100%", height: 5, background: "#1e293b", borderRadius: 3, overflow: "hidden" }}>
                    <div
                      style={{
                        width: `${Math.max(5, Math.min(95, situationResult.neural_assessment.win_probability))}%`,
                        height: "100%",
                        background: situationResult.neural_assessment.win_probability >= 50
                          ? "linear-gradient(90deg, #16a34a, #22c55e)"
                          : "linear-gradient(90deg, #dc2626, #ef4444)",
                        transition: "width 0.3s ease",
                      }}
                    />
                  </div>
                </div>

                {/* Metrics Row */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, fontSize: 10, marginTop: 4 }}>
                  <div style={{ background: "rgba(0,0,0,0.3)", padding: "4px 6px", borderRadius: 4, border: "1px solid rgba(255,255,255,0.06)" }}>
                    <span style={{ color: "var(--text-muted)", display: "block", fontSize: 9 }}>Root Value V(s):</span>
                    <strong style={{ color: situationResult.neural_assessment.root_value >= 0 ? "#4ade80" : "#f87171", fontFamily: "var(--font-mono)" }}>
                      {situationResult.neural_assessment.root_value >= 0 ? `+${situationResult.neural_assessment.root_value.toFixed(2)}` : situationResult.neural_assessment.root_value.toFixed(2)}
                    </strong>
                  </div>
                  <div style={{ background: "rgba(0,0,0,0.3)", padding: "4px 6px", borderRadius: 4, border: "1px solid rgba(255,255,255,0.06)" }}>
                    <span style={{ color: "var(--text-muted)", display: "block", fontSize: 9 }}>MCTS Decisions:</span>
                    <strong style={{ color: "var(--text-primary)", fontFamily: "var(--font-mono)" }}>
                      {situationResult.neural_assessment.total_decisions || Number(gameData?.ai_observability?.total_decisions || 0)}
                    </strong>
                  </div>
                  <div style={{ background: "rgba(0,0,0,0.3)", padding: "4px 6px", borderRadius: 4, border: "1px solid rgba(255,255,255,0.06)" }}>
                    <span style={{ color: "var(--text-muted)", display: "block", fontSize: 9 }}>Outlook:</span>
                    <strong style={{ color: "#38bdf8", fontSize: 9.5 }}>
                      {situationResult.neural_assessment.strategic_outlook.split(" ")[0]}
                    </strong>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 2. TOPOGRAPHY & BATTLEFIELD IPB INTEL */}
          {situationResult?.terrain_intel && (
            <div style={{ background: "rgba(10, 14, 26, 0.75)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: 7, padding: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontFamily: "var(--font-tech)", fontWeight: 700, fontSize: 10.5, color: "#38bdf8", letterSpacing: 0.5 }}>
                  🗺️ Topographical Terrain Intel (IPB)
                </span>
                <span style={{ fontSize: 9.5, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  {situationResult.terrain_intel.scenario_name}
                </span>
              </div>

              {/* Terrain Chips Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 6 }}>
                <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "4px 6px", borderRadius: 4, border: "1px solid rgba(255, 255, 255, 0.05)", fontSize: 10 }}>
                  <span style={{ color: "var(--text-muted)" }}>🏛️ Urban Structures:</span>{" "}
                  <strong style={{ color: "#f59e0b" }}>{situationResult.terrain_intel.urban_pct}%</strong>
                </div>
                <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "4px 6px", borderRadius: 4, border: "1px solid rgba(255, 255, 255, 0.05)", fontSize: 10 }}>
                  <span style={{ color: "var(--text-muted)" }}>🌲 Forest & Cover:</span>{" "}
                  <strong style={{ color: "#10b981" }}>{situationResult.terrain_intel.forest_pct}%</strong>
                </div>
                <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "4px 6px", borderRadius: 4, border: "1px solid rgba(255, 255, 255, 0.05)", fontSize: 10 }}>
                  <span style={{ color: "var(--text-muted)" }}>🌾 Open Ground:</span>{" "}
                  <strong style={{ color: "#94a3b8" }}>{situationResult.terrain_intel.open_pct}%</strong>
                </div>
                <div style={{ background: "rgba(255, 255, 255, 0.03)", padding: "4px 6px", borderRadius: 4, border: "1px solid rgba(255, 255, 255, 0.05)", fontSize: 10 }}>
                  <span style={{ color: "var(--text-muted)" }}>🛡️ Defilade Corridors:</span>{" "}
                  <strong style={{ color: "var(--neon-cyan)" }}>{situationResult.terrain_intel.defilade_corridors_count}</strong>
                </div>
              </div>

              <div style={{ fontSize: 10.5, lineHeight: 1.4, color: "var(--text-secondary)", fontStyle: "italic", borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: 5 }}>
                {situationResult.terrain_intel.dominant_terrain_desc}
              </div>
            </div>
          )}

          {/* 3. FORCES ORDER OF BATTLE (OOB) BY ROLE */}
          {situationResult?.forces_oob && (
            <div style={{ background: "rgba(10, 14, 26, 0.75)", border: "1px solid rgba(255, 255, 255, 0.08)", borderRadius: 7, padding: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontFamily: "var(--font-tech)", fontWeight: 700, fontSize: 10.5, color: "#818cf8", letterSpacing: 0.5 }}>
                  ⚔️ Order of Battle (OOB) & Tactical Roles
                </span>
                <span style={{ fontSize: 9.5, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  {situationResult.forces_oob.own_total} Friendly vs {situationResult.forces_oob.enemy_total} Hostile
                </span>
              </div>

              {/* Roles Breakdown */}
              <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                <div>
                  <span style={{ fontSize: 9.5, color: "var(--text-muted)", display: "block", marginBottom: 3 }}>
                    Friendly Force Composition ({situationResult.forces_oob.own_side}):
                  </span>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {Object.entries(situationResult.forces_oob.own_roles).map(([role, cnt]) => (
                      <span key={role} style={{ fontSize: 9.5, background: "rgba(99, 102, 241, 0.15)", color: "#a5b4fc", border: "1px solid rgba(99, 102, 241, 0.3)", padding: "1px 6px", borderRadius: 3 }}>
                        {role}: <strong>{cnt}</strong>
                      </span>
                    ))}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: 9.5, color: "var(--text-muted)", display: "block", marginBottom: 3 }}>
                    Hostile Force Composition ({situationResult.forces_oob.enemy_side}):
                  </span>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {Object.entries(situationResult.forces_oob.enemy_roles).map(([role, cnt]) => (
                      <span key={role} style={{ fontSize: 9.5, background: "rgba(239, 68, 68, 0.12)", color: "#fca5a5", border: "1px solid rgba(239, 68, 68, 0.25)", padding: "1px 6px", borderRadius: 3 }}>
                        {role}: <strong>{cnt}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* 4. EXECUTIVE SUMMARY & TACTICAL VECTORS */}
          {situationResult && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {/* Executive Summary */}
              <div style={{ background: "rgba(15, 23, 42, 0.9)", borderLeft: "3px solid var(--neon-cyan)", padding: "8px 12px", borderRadius: "0 6px 6px 0", fontSize: 11, lineHeight: 1.5, color: "var(--text-bright)" }}>
                <strong style={{ color: "var(--neon-cyan)", display: "block", fontSize: 10, letterSpacing: 0.8, textTransform: "uppercase", marginBottom: 2 }}>
                  Executive SitRep Summary
                </strong>
                {situationResult.situation_summary}
              </div>

              {/* Tactical Priorities */}
              {situationResult.priorities && situationResult.priorities.length > 0 && (
                <div style={{ background: "rgba(16, 185, 129, 0.06)", border: "1px solid rgba(16, 185, 129, 0.25)", borderRadius: 6, padding: "8px 10px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 5, color: "#34d399", fontWeight: 700, fontSize: 10.5, marginBottom: 5 }}>
                    <span>🎯</span>
                    <span>Tactical Priorities</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {situationResult.priorities.map((p, idx) => (
                      <div key={idx} style={{ display: "flex", gap: 6, fontSize: 10.5, color: "var(--text-primary)", lineHeight: 1.4 }}>
                        <span style={{ color: "#34d399", fontWeight: 700 }}>•</span>
                        <span>{p}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Operational Opportunities */}
              {situationResult.opportunities && situationResult.opportunities.length > 0 && (
                <div style={{ background: "rgba(0, 240, 255, 0.06)", border: "1px solid rgba(0, 240, 255, 0.25)", borderRadius: 6, padding: "8px 10px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--neon-cyan)", fontWeight: 700, fontSize: 10.5, marginBottom: 5 }}>
                    <span>💡</span>
                    <span>Operational Opportunities</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {situationResult.opportunities.map((o, idx) => (
                      <div key={idx} style={{ display: "flex", gap: 6, fontSize: 10.5, color: "var(--text-primary)", lineHeight: 1.4 }}>
                        <span style={{ color: "var(--neon-cyan)", fontWeight: 700 }}>•</span>
                        <span>{o}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Identified Risks */}
              {situationResult.risks && situationResult.risks.length > 0 && (
                <div style={{ background: "rgba(239, 68, 68, 0.06)", border: "1px solid rgba(239, 68, 68, 0.25)", borderRadius: 6, padding: "8px 10px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 5, color: "#f87171", fontWeight: 700, fontSize: 10.5, marginBottom: 5 }}>
                    <span>⚠️</span>
                    <span>Identified Tactical Risks</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {situationResult.risks.map((r, idx) => (
                      <div key={idx} style={{ display: "flex", gap: 6, fontSize: 10.5, color: "var(--text-primary)", lineHeight: 1.4 }}>
                        <span style={{ color: "#f87171", fontWeight: 700 }}>•</span>
                        <span>{r}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Key Unit Alerts */}
              {situationResult.key_unit_alerts && situationResult.key_unit_alerts.length > 0 && (
                <div style={{ background: "rgba(192, 132, 252, 0.06)", border: "1px solid rgba(192, 132, 252, 0.25)", borderRadius: 6, padding: "8px 10px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 5, color: "#c084fc", fontWeight: 700, fontSize: 10.5, marginBottom: 5 }}>
                    <span>🚨</span>
                    <span>Key Squad Alerts</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {situationResult.key_unit_alerts.map((a, idx) => (
                      <div key={idx} style={{ display: "flex", gap: 6, fontSize: 10.5, color: "var(--text-primary)", lineHeight: 1.4 }}>
                        <span style={{ color: "#c084fc", fontWeight: 700 }}>•</span>
                        <span>{a}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Regulatory Citations */}
              {situationResult.citations && situationResult.citations.length > 0 && (
                <div style={{ marginTop: 4 }}>
                  <span style={{ color: "var(--text-muted)", fontSize: 10, display: "block", marginBottom: 4 }}>
                    Doctrinal & Regulatory Citations:
                  </span>
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    {situationResult.citations.slice(0, 3).map((c, i) => (
                      <div key={i} style={{ fontSize: 9.5, color: "var(--text-muted)", background: "rgba(0,0,0,0.25)", padding: "3px 6px", borderRadius: 4 }}>
                        <span style={{ color: "var(--neon-cyan)", fontWeight: 600 }}>[{c.source_id}]</span> {c.snippet}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: RULES & DOCTRINE */}
      {activeTab === "rules" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--text-secondary)", fontSize: 10 }}>
              Query Official Rules & Unit Dossiers:
            </span>
            <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <select
                value={retrievalMode}
                onChange={(e) => setRetrievalMode(e.target.value as any)}
                style={{ fontSize: 10, background: "rgba(0,0,0,0.4)", color: "var(--text-primary)", border: "1px solid rgba(255,255,255,0.15)", borderRadius: 3, padding: "2px 4px" }}
              >
                <option value="rules">Rules Only</option>
                <option value="data">Unit Catalog</option>
                <option value="hybrid">Hybrid (Rules + Data)</option>
              </select>
            </div>
          </div>

          {/* Search Input */}
          <div style={{ display: "flex", gap: 6 }}>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runQuery()}
              placeholder="Ask a tactical or doctrinal question..."
              style={{
                flex: 1,
                padding: "6px 10px",
                fontSize: 11,
                background: "rgba(0, 0, 0, 0.4)",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                borderRadius: 4,
                color: "var(--text-primary)",
              }}
            />
            <button
              className="btn-tactical"
              onClick={() => runQuery()}
              disabled={rulesLoading || !query.trim()}
              style={{ fontSize: 11, padding: "4px 10px" }}
            >
              {rulesLoading ? "Searching..." : "Submit"}
            </button>
          </div>

          {/* Quick doctrinal prompts */}
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {[
              "Bunker & fortification defense rules",
              "How does HEAVY_WEIGHT work?",
              "Mortar indirect fire & smoke rules",
              "Low silhouette spotting modifier",
            ].map((prompt, i) => (
              <button
                key={i}
                onClick={() => runQuery(prompt)}
                style={{
                  fontSize: 9.5,
                  padding: "2px 6px",
                  background: "rgba(255, 255, 255, 0.04)",
                  border: "1px solid rgba(255, 255, 255, 0.08)",
                  borderRadius: 3,
                  color: "var(--text-secondary)",
                  cursor: "pointer",
                }}
              >
                {prompt}
              </button>
            ))}
          </div>

          {rulesError && (
            <div style={{ padding: 6, background: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: 4, color: "#fca5a5" }}>
              {rulesError}
            </div>
          )}

          {/* Unit counter preview if identified */}
          {counterPreview && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, background: "rgba(0, 240, 255, 0.06)", border: "1px solid rgba(0, 240, 255, 0.2)", borderRadius: 6, padding: "6px 10px" }}>
              <img
                src={encodeURI(counterPreview.imagePath)}
                alt={counterPreview.label}
                style={{ width: 42, height: 42, objectFit: "contain", borderRadius: 4, background: "rgba(0,0,0,0.3)" }}
              />
              <div>
                <span style={{ fontSize: 9.5, color: "var(--neon-cyan)", textTransform: "uppercase", letterSpacing: 0.5, display: "block" }}>
                  Identified Unit Dossier
                </span>
                <strong style={{ fontSize: 11, color: "var(--text-bright)" }}>{counterPreview.label}</strong>
              </div>
            </div>
          )}

          {/* Query Result */}
          {rulesResult && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, background: "rgba(0, 0, 0, 0.35)", padding: 10, borderRadius: 6, border: "1px solid rgba(255, 255, 255, 0.08)" }}>
              <div>
                <strong style={{ color: "var(--neon-cyan)", display: "block", marginBottom: 4, fontSize: 10.5, letterSpacing: 0.5 }}>
                  Doctrinal Advisory Briefing:
                </strong>
                <div style={{ fontSize: 11, lineHeight: 1.5, color: "var(--text-primary)", whiteSpace: "pre-wrap" }}>
                  {rulesResult.answer}
                </div>
              </div>

              {rulesResult.citations && rulesResult.citations.length > 0 && (
                <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: 6 }}>
                  <strong style={{ color: "var(--text-muted)", fontSize: 9.5, display: "block", marginBottom: 3 }}>
                    Regulatory Citations ({rulesResult.citations.length}):
                  </strong>
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    {rulesResult.citations.map((c, idx) => (
                      <div key={idx} style={{ fontSize: 9.5, color: "var(--text-muted)", background: "rgba(0,0,0,0.25)", padding: "3px 6px", borderRadius: 3 }}>
                        <span style={{ color: "#38bdf8", fontWeight: 600 }}>[{c.source_id}]</span> {c.snippet}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
