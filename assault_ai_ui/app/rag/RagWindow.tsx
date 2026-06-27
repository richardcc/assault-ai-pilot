import { useState } from "react";

type Citation = {
  source_type: string;
  source_id: string;
  snippet: string;
};

type QueryResult = {
  answer: string;
  citations: Citation[];
  limitations: string[];
};

const API_BASE = "http://127.0.0.1:8000";

export default function RagWindow() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runQuery() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/rag/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, mode: "hybrid" }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const json = (await res.json()) as QueryResult;
      setResult(json);
    } catch (e) {
      setError(`RAG query failed: ${String(e)}`);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ padding: 12, display: "grid", gap: 10 }}>
      <h3 style={{ margin: 0 }}>RAG Copilot</h3>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Pregunta sobre reglas, unidades o escenarios..."
        rows={4}
      />
      <button onClick={runQuery} disabled={loading || !query.trim()}>
        {loading ? "Consultando..." : "Consultar"}
      </button>

      {error && <div>{error}</div>}

      {result && (
        <div style={{ display: "grid", gap: 8 }}>
          <div>
            <strong>Respuesta:</strong> {result.answer}
          </div>
          <div>
            <strong>Limitaciones:</strong>{" "}
            {result.limitations.length ? result.limitations.join(", ") : "ninguna"}
          </div>
          <div>
            <strong>Citas:</strong>
            <ul>
              {result.citations.map((c, i) => (
                <li key={`${c.source_type}-${c.source_id}-${i}`}>
                  [{c.source_type}] {c.source_id}: {c.snippet}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
