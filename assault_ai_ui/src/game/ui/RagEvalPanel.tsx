import { useState } from "react";
import { apiUrl } from "../../config/backend";

type Citation = {
  source_type: string;
  source_id: string;
  snippet: string;
};

type EvalAnalysisResult = {
  patterns: string[];
  metrics: Record<string, unknown>;
  examples: Array<Record<string, unknown>>;
  recommendations: string[];
  citations: Citation[];
  limitations: string[];
};

const ENABLE_RAG_EVAL_PANEL =
  String(import.meta.env.VITE_ENABLE_RAG_EVAL_PANEL || "true").toLowerCase() !== "false";

export function RagEvalPanel() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EvalAnalysisResult | null>(null);

  const runEvalAnalysis = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const traceRes = await fetch(apiUrl("/api/game/trace?limit=5000"));
      if (!traceRes.ok) {
        throw new Error(`trace HTTP ${traceRes.status}`);
      }
      const tracePayload = await traceRes.json();
      const events = Array.isArray(tracePayload?.events) ? tracePayload.events : [];
      if (!events.length) {
        throw new Error("No hay eventos de trace para analizar");
      }

      const analysisRes = await fetch(apiUrl("/api/rag/training_analysis"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          runs: [{ run_id: "ui_live_trace", events }],
        }),
      });
      if (!analysisRes.ok) {
        throw new Error(`analysis HTTP ${analysisRes.status}`);
      }
      const payload = (await analysisRes.json()) as EvalAnalysisResult;
      setResult(payload);
    } catch (e) {
      setError(`RAG eval no disponible: ${String(e)}`);
    } finally {
      setLoading(false);
    }
  };

  if (!ENABLE_RAG_EVAL_PANEL) {
    return (
      <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
        Panel RAG Eval desactivado por flag (`VITE_ENABLE_RAG_EVAL_PANEL=false`).
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
        RAG Eval (copiloto) - analiza la traza actual sin afectar reglas/turnos.
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button className="btn-tactical" onClick={runEvalAnalysis} disabled={loading}>
          {loading ? "Analizando..." : "Analizar eval actual"}
        </button>
      </div>

      {error && <div style={{ fontSize: 11, color: "#ff8f8f" }}>{error}</div>}

      {result && (
        <div style={{ display: "grid", gap: 6, fontSize: 11 }}>
          <div>
            <strong>Patterns:</strong> {result.patterns?.length ? result.patterns.join(" | ") : "n/a"}
          </div>
          <div>
            <strong>Recommendations:</strong>{" "}
            {result.recommendations?.length ? result.recommendations.join(" | ") : "n/a"}
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
                  [{c.source_type}] {c.source_id}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
