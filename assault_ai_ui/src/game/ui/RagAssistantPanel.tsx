import { useEffect, useMemo, useRef, useState } from "react";
import { apiUrl } from "../../config/backend";
import { unitImages } from "../config/unitImages";

type Citation = {
  source_type: string;
  source_id: string;
  snippet: string;
};

type SituationResult = {
  situation_summary: string;
  priorities: string[];
  risks: string[];
  opportunities?: string[];
  key_unit_alerts?: string[];
  citations: Citation[];
  limitations: string[];
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
    "qwen2.5:7b",
    "qwen2.5:14b",
    "qwen2.5-coder:14b",
    "llama3.1:8b",
    "mistral:7b",
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
    ollamaReachable == null ? "#f6c945" : ollamaReachable ? "#22c55e" : "#ef4444";
  const statusText =
    ollamaReachable == null ? "Comprobando LLM..." : ollamaReachable ? "Ollama Activo" : "Modo Determinista";

  const counterPreview = useMemo(() => findCounterPreview(rulesResult, query), [rulesResult, query]);

  // Explain situation action
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
      setSituationError(`Error al analizar situación: ${String(e)}`);
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
      const res = await fetch(apiUrl("/api/rag/query"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: q,
          mode: retrievalMode === "auto" ? null : retrievalMode,
          context: {
            llm_model: model,
            conversation_id: conversationIdRef.current,
            assistant_scope: "manual",
            state_snapshot: gameData || null,
            ai_observability: gameData?.ai_observability || null,
          },
        }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const json = (await res.json()) as QueryResult;
      setRulesResult(json);
    } catch (e) {
      setRulesResult(null);
      setRulesError(`Error al consultar manual: ${String(e)}`);
    } finally {
      setRulesLoading(false);
    }
  }

  const quickChips = [
    { label: "🏰 Búnker / Casamata", q: "¿Qué reglas aplican para cruzar, ocupar y atacar un búnker o pillbox?" },
    { label: "💥 Morteros e Indirecto", q: "¿Cómo funciona el fuego indirecto de morteros y qué requisitos de LOS tiene?" },
    { label: "👁️ Línea de Visión (LOS)", q: "¿Cómo se calcula la línea de visión y qué obstáculos bloquean la visión?" },
    { label: "⚔️ Asalto y Brecha", q: "¿Cuáles son las condiciones y modificadores para un asalto cuerpo a cuerpo?" },
    { label: "🛡️ Supresión / HMG", q: "¿Qué alcance tiene la ametralladora pesada y qué efectos tiene el fuego de apoyo?" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 11 }}>
      {/* Top Header with Tab Switch and LLM Status */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.12)", paddingBottom: 8 }}>
        <div style={{ display: "flex", gap: 4 }}>
          <button
            onClick={() => setActiveTab("situation")}
            style={{
              padding: "4px 10px",
              fontSize: 11,
              fontWeight: activeTab === "situation" ? "bold" : "normal",
              background: activeTab === "situation" ? "rgba(59, 130, 246, 0.25)" : "rgba(255,255,255,0.05)",
              color: activeTab === "situation" ? "#60a5fa" : "var(--text-secondary)",
              border: activeTab === "situation" ? "1px solid #3b82f6" : "1px solid rgba(255,255,255,0.1)",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >
            📋 Situación Táctica
          </button>
          <button
            onClick={() => setActiveTab("rules")}
            style={{
              padding: "4px 10px",
              fontSize: 11,
              fontWeight: activeTab === "rules" ? "bold" : "normal",
              background: activeTab === "rules" ? "rgba(59, 130, 246, 0.25)" : "rgba(255,255,255,0.05)",
              color: activeTab === "rules" ? "#60a5fa" : "var(--text-secondary)",
              border: activeTab === "rules" ? "1px solid #3b82f6" : "1px solid rgba(255,255,255,0.1)",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >
            📖 Manual & Reglas
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: "var(--text-secondary)" }}>
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: statusColor,
              boxShadow: `0 0 5px ${statusColor}`,
              display: "inline-block",
            }}
          />
          <span>{statusText}</span>
        </div>
      </div>

      {/* TAB 1: SITUATION */}
      {activeTab === "situation" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "var(--text-secondary)" }}>Diagnóstico táctico del turno actual:</span>
            <button
              className="btn-tactical"
              onClick={explainSituation}
              disabled={situationLoading || !gameData}
              style={{ fontSize: 11, padding: "3px 8px" }}
            >
              {situationLoading ? "Analizando posición..." : "⚡ Explicar situación"}
            </button>
          </div>

          {situationError && (
            <div style={{ padding: 6, background: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: 4, color: "#fca5a5" }}>
              {situationError}
            </div>
          )}

          {situationResult && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, background: "rgba(0,0,0,0.3)", padding: 8, borderRadius: 6, border: "1px solid rgba(255,255,255,0.08)" }}>
              <div>
                <strong style={{ color: "#60a5fa" }}>Resumen:</strong> {situationResult.situation_summary}
              </div>
              <div>
                <strong style={{ color: "#34d399" }}>Prioridades:</strong>{" "}
                {situationResult.priorities.length ? situationResult.priorities.join(" | ") : "Mantener posición"}
              </div>
              {situationResult.opportunities && situationResult.opportunities.length > 0 && (
                <div>
                  <strong style={{ color: "#fbbf24" }}>Oportunidades:</strong>{" "}
                  {situationResult.opportunities.join(" | ")}
                </div>
              )}
              {situationResult.risks.length > 0 && (
                <div>
                  <strong style={{ color: "#f87171" }}>Riesgos:</strong>{" "}
                  {situationResult.risks.join(" | ")}
                </div>
              )}
              {situationResult.key_unit_alerts && situationResult.key_unit_alerts.length > 0 && (
                <div>
                  <strong style={{ color: "#c084fc" }}>Alertas unidad:</strong>{" "}
                  {situationResult.key_unit_alerts.join(" | ")}
                </div>
              )}
              {situationResult.citations.length > 0 && (
                <div style={{ marginTop: 4, paddingTop: 4, borderTop: "1px solid rgba(255,255,255,0.06)", fontSize: 10, color: "var(--text-secondary)" }}>
                  <strong>Citas de Reglas:</strong>{" "}
                  {situationResult.citations.slice(0, 3).map((c) => `[${c.source_type}:${c.source_id}]`).join(" ")}
                </div>
              )}
            </div>
          )}

          {/* AI OBSERVABILITY (EFFICIENTZERO V2 - NO SB3) */}
          <div style={{ background: "rgba(0,0,0,0.25)", padding: 8, borderRadius: 6, border: "1px solid rgba(255,255,255,0.06)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <strong style={{ color: "#38bdf8" }}>🧠 Motor IA Activo: EfficientZero V2 (MCTS)</strong>
              <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>CUDA / GPU</span>
            </div>

            {gameData?.ai_observability ? (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, fontSize: 10 }}>
                <div>
                  <span style={{ color: "var(--text-secondary)" }}>Decisiones MCTS:</span>{" "}
                  <strong>{Number(gameData.ai_observability.total_decisions || 0)}</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-secondary)" }}>Correcciones:</span>{" "}
                  <strong>{Number(gameData.ai_observability.corrected_count || 0)}</strong>
                </div>
                <div style={{ gridColumn: "span 2" }}>
                  <span style={{ color: "var(--text-secondary)" }}>Fuentes:</span>{" "}
                  {Object.entries(gameData.ai_observability.by_source || {})
                    .map(([k, v]) => `${k}:${v}`)
                    .join(" | ") || "Inferencia activa"}
                </div>
                {Array.isArray(gameData.ai_observability.recent_decisions) &&
                  gameData.ai_observability.recent_decisions.length > 0 && (
                    <div style={{ gridColumn: "span 2", marginTop: 2, paddingTop: 4, borderTop: "1px solid rgba(255,255,255,0.06)", color: "#a5b4fc" }}>
                      <strong>Última jugada IA:</strong>{" "}
                      {(() => {
                        const d = gameData.ai_observability.recent_decisions[
                          gameData.ai_observability.recent_decisions.length - 1
                        ];
                        return `${d?.side || "?"} T${d?.turn ?? "?"} ${d?.unit_id || "?"} -> ${
                          d?.action_id || d?.action || "?"
                        } [${d?.source || "EZV2"}]`;
                      })()}
                    </div>
                  )}
              </div>
            ) : (
              <div style={{ color: "var(--text-secondary)", fontSize: 10 }}>Esperando primer movimiento de IA...</div>
            )}
          </div>
        </div>
      )}

      {/* TAB 2: RULES */}
      {activeTab === "rules" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {/* Quick chip suggestions */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {quickChips.map((chip, idx) => (
              <button
                key={idx}
                onClick={() => runQuery(chip.q)}
                style={{
                  fontSize: 10,
                  padding: "2px 6px",
                  background: "rgba(255,255,255,0.06)",
                  border: "1px solid rgba(255,255,255,0.12)",
                  borderRadius: 12,
                  color: "#cbd5e1",
                  cursor: "pointer",
                }}
              >
                {chip.label}
              </button>
            ))}
          </div>

          {/* Query input */}
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                runQuery();
              }
            }}
            placeholder="Pregunta por el manual (reglas, excepciones, alcance, modificadores)..."
            rows={2}
            style={{
              width: "100%",
              resize: "vertical",
              background: "rgba(0,0,0,0.35)",
              color: "var(--text-primary)",
              border: "1px solid rgba(255,255,255,0.14)",
              borderRadius: 6,
              padding: 6,
              fontSize: 11,
              boxSizing: "border-box",
            }}
          />

          {/* Controls: Mode & Model */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
            <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <span style={{ color: "var(--text-secondary)", fontSize: 10 }}>Modo:</span>
              {(["rules", "hybrid", "data"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setRetrievalMode(m)}
                  style={{
                    fontSize: 9,
                    padding: "2px 6px",
                    borderRadius: 3,
                    background: retrievalMode === m ? "#3b82f6" : "rgba(255,255,255,0.06)",
                    color: retrievalMode === m ? "#fff" : "var(--text-secondary)",
                    border: "none",
                    cursor: "pointer",
                  }}
                >
                  {m.toUpperCase()}
                </button>
              ))}
            </div>

            <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                style={{
                  fontSize: 10,
                  background: "rgba(0,0,0,0.5)",
                  color: "var(--text-primary)",
                  border: "1px solid rgba(255,255,255,0.15)",
                  borderRadius: 4,
                  padding: "2px 4px",
                }}
              >
                {modelOptions.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>

              <button
                className="btn-tactical"
                onClick={() => runQuery()}
                disabled={rulesLoading || !query.trim()}
                style={{ fontSize: 10, padding: "3px 8px" }}
              >
                {rulesLoading ? "Buscando..." : "Consultar"}
              </button>
            </div>
          </div>

          {rulesError && (
            <div style={{ padding: 6, background: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: 4, color: "#fca5a5" }}>
              {rulesError}
            </div>
          )}

          {/* Rules Result Card */}
          {rulesResult && (
            <div style={{ background: "rgba(0,0,0,0.35)", padding: 8, borderRadius: 6, border: "1px solid rgba(255,255,255,0.08)", display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ color: "#f1f5f9", lineHeight: 1.4 }}>
                {rulesResult.answer}
              </div>

              {/* Counter Preview if unit referenced */}
              {counterPreview && (
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: 6, background: "rgba(255,255,255,0.05)", borderRadius: 4 }}>
                  <img
                    src={counterPreview.imagePath}
                    alt={counterPreview.label}
                    style={{ width: 36, height: 36, objectFit: "contain" }}
                  />
                  <div>
                    <strong style={{ color: "#fbbf24" }}>{counterPreview.label}</strong>
                    <div style={{ fontSize: 9, color: "var(--text-secondary)" }}>{counterPreview.unitKey}</div>
                  </div>
                </div>
              )}

              {/* Citations */}
              {rulesResult.citations && rulesResult.citations.length > 0 && (
                <div style={{ marginTop: 4, paddingTop: 4, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                  <div style={{ color: "var(--text-secondary)", fontSize: 10, marginBottom: 2 }}>
                    Citas y Evidencia Oficial:
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    {rulesResult.citations.slice(0, 3).map((c, i) => (
                      <div key={i} style={{ fontSize: 9, color: "#94a3b8", background: "rgba(0,0,0,0.2)", padding: 4, borderRadius: 3 }}>
                        <span style={{ color: "#60a5fa" }}>[{c.source_type.toUpperCase()}] {c.source_id}:</span> {c.snippet.slice(0, 160)}...
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
