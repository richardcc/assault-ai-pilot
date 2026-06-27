import { useState } from "react";
import { apiUrl } from "../../config/backend";

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

export function RagSituationPanel({ gameData }: { gameData: any }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SituationResult | null>(null);

  const explainSituation = async () => {
    if (!gameData) return;
    setLoading(true);
    setError(null);
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
      setResult(json);
    } catch (e) {
      setError(`RAG situation failed: ${String(e)}`);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ marginTop: 12, borderTop: "1px solid rgba(120,120,120,0.3)", paddingTop: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <strong style={{ fontSize: 12 }}>Asistente de Situacion</strong>
        <button
          className="btn-tactical"
          onClick={explainSituation}
          disabled={loading || !gameData}
          style={{ fontSize: 11, padding: "4px 8px" }}
        >
          {loading ? "Analizando..." : "Explicar situación"}
        </button>
      </div>

      {error && <div style={{ marginTop: 8, fontSize: 11 }}>{error}</div>}

      {result && (
        <div style={{ marginTop: 8, fontSize: 11, display: "grid", gap: 6 }}>
          <div><strong>Resumen:</strong> {result.situation_summary}</div>
          <div><strong>Prioridades:</strong> {result.priorities.length ? result.priorities.join(" | ") : "n/a"}</div>
          <div><strong>Oportunidades:</strong> {result.opportunities?.length ? result.opportunities.join(" | ") : "n/a"}</div>
          <div><strong>Riesgos:</strong> {result.risks.length ? result.risks.join(" | ") : "n/a"}</div>
          <div><strong>Alertas unidad:</strong> {result.key_unit_alerts?.length ? result.key_unit_alerts.join(" | ") : "n/a"}</div>
          <div><strong>Limitaciones:</strong> {result.limitations.length ? result.limitations.join(", ") : "ninguna"}</div>
          <div>
            <strong>Citas:</strong>
            <ul style={{ margin: "6px 0 0 16px", padding: 0 }}>
              {result.citations.slice(0, 3).map((c, i) => (
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
