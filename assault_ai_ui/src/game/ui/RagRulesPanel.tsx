import { useEffect, useMemo, useRef, useState } from "react";
import { apiUrl } from "../../config/backend";
import { unitImages } from "../config/unitImages";

type Citation = {
  source_type: string;
  source_id: string;
  snippet: string;
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

export function RagRulesPanel({ gameData }: { gameData?: any }) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [model, setModel] = useState("qwen2.5:14b");
  const [retrievalMode, setRetrievalMode] = useState<"auto" | "rules" | "data" | "hybrid">("rules");
  const [liveModels, setLiveModels] = useState<string[]>([]);
  const [ollamaReachable, setOllamaReachable] = useState<boolean | null>(null);
  const conversationIdRef = useRef<string>(
    `rag-rules-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  );

  const fallbackModels = [
    "qwen2.5:7b",
    "qwen2.5:14b",
    "qwen2.5:32b",
    "llama3.1:8b",
    "llama3.1:70b",
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
    ollamaReachable == null ? "#f6c945" : ollamaReachable ? "#21d07a" : "#ff5b5b";
  const statusText =
    ollamaReachable == null ? "Comprobando Ollama..." : ollamaReachable ? "Ollama activo" : "Ollama no disponible";
  const counterPreview = useMemo(() => findCounterPreview(result, query), [result, query]);

  async function runQuery() {
    const q = query.trim();
    if (!q) return;

    setLoading(true);
    setError(null);
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
      setResult(json);
    } catch (e) {
      setResult(null);
      setError(`No se pudo consultar reglas: ${String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ marginTop: 10, borderTop: "1px solid rgba(255,255,255,0.12)", paddingTop: 10 }}>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>
        Asistente de Manual
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6, fontSize: 11 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: statusColor,
            boxShadow: `0 0 6px ${statusColor}`,
            display: "inline-block",
          }}
        />
        <span style={{ color: "var(--text-secondary)" }}>{statusText}</span>
      </div>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Pregunta por el manual (regla, excepciones, aplicacion)"
        rows={3}
        style={{
          width: "100%",
          resize: "vertical",
          background: "rgba(0,0,0,0.35)",
          color: "var(--text-primary)",
          border: "1px solid rgba(255,255,255,0.14)",
          borderRadius: 6,
          padding: 8,
          fontSize: 12,
        }}
      />
      <div style={{ marginTop: 6, display: "grid", gap: 4 }}>
        <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>Modo de recuperacion</label>
        <select
          value={retrievalMode}
          onChange={(e) => setRetrievalMode(e.target.value as "auto" | "rules" | "data" | "hybrid")}
          className="btn-tactical"
          style={{ width: "100%" }}
        >
          <option value="auto">Auto</option>
          <option value="rules">Reglas</option>
          <option value="data">Datos</option>
          <option value="hybrid">Hibrido</option>
        </select>
      </div>
      <div style={{ marginTop: 6, display: "grid", gap: 4 }}>
        <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>Modelo Ollama</label>
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="btn-tactical"
          style={{ width: "100%" }}
        >
          {modelOptions.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>
      <div style={{ marginTop: 6, display: "flex", justifyContent: "flex-end" }}>
        <button className="btn-tactical" onClick={runQuery} disabled={loading || !query.trim()}>
          {loading ? "Consultando..." : "Preguntar"}
        </button>
      </div>

      {error && (
        <div style={{ marginTop: 6, fontSize: 11, color: "#ff8f8f" }}>
          {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 8, display: "grid", gap: 6, fontSize: 11 }}>
          <div>
            <strong>Respuesta:</strong> {result.answer}
          </div>
          <div>
            <strong>Modelo:</strong> {result.llm_model || model}
          </div>
          <div>
            <strong>Modo:</strong> {result.mode || retrievalMode}
          </div>
          <div>
            <strong>Limitaciones:</strong>{" "}
            {result.limitations?.length ? result.limitations.join(", ") : "ninguna"}
          </div>
          <div>
            <strong>Citas:</strong>
            <ul style={{ margin: "4px 0 0 14px", padding: 0 }}>
              {(result.citations || []).slice(0, 4).map((c, i) => (
                <li key={`${c.source_type}-${c.source_id}-${i}`}>
                  [{c.source_type}] {c.source_id}: {c.snippet}
                </li>
              ))}
            </ul>
          </div>
          {counterPreview && (
            <div>
              <strong>Counter grafico:</strong>
              <div style={{ marginTop: 6, display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ color: "var(--text-secondary)" }}>
                  {counterPreview.label} ({counterPreview.unitKey})
                </div>
                <img
                  src={counterPreview.imagePath}
                  alt={`Counter ${counterPreview.label}`}
                  style={{
                    width: 120,
                    height: "auto",
                    border: "1px solid rgba(255,255,255,0.14)",
                    borderRadius: 6,
                    background: "rgba(0,0,0,0.3)",
                    padding: 4,
                  }}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
