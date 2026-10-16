import type { Dict } from "../../types";

export function ReplayTab({
  selectedEvalSourcePath,
  replayLog,
  replaySteps,
  stepIndex
}: {
  selectedEvalSourcePath: string;
  replayLog: Dict | null;
  replaySteps: Dict | null;
  stepIndex: number;
}) {
  if (!selectedEvalSourcePath) return <div className="muted">No replay log source path available.</div>;
  const lines = Array.isArray(replayLog?.lines) ? (replayLog!.lines as unknown[]) : [];
  const steps = Array.isArray(replaySteps?.steps) ? (replaySteps!.steps as Record<string, unknown>[]) : [];
  const s = steps[Math.max(0, Math.min(stepIndex, Math.max(0, steps.length - 1)))] || {};
  return (
    <div>
      <div className="muted">eval_source_path: {selectedEvalSourcePath}</div>
      <h3 style={{ marginTop: 10 }}>Selected step details</h3>
      <table>
        <tbody>
          <tr><td>step_index</td><td>{String(s.step_index ?? stepIndex)}</td></tr>
          <tr><td>to_play</td><td>{String(s.to_play ?? "-")}</td></tr>
          <tr><td>action_id</td><td>{String(s.action_id ?? "-")}</td></tr>
          <tr><td>unit_id</td><td>{String(s.unit_id ?? "-")}</td></tr>
          <tr><td>target_qr</td><td>{`${String(s.target_q ?? "-")},${String(s.target_r ?? "-")}`}</td></tr>
          <tr><td>reward</td><td>{Number(s.reward || 0).toFixed(4)}</td></tr>
          <tr><td>damage/kills</td><td>{`${Number(s.damage_dealt || 0).toFixed(3)} / ${Number(s.kills_dealt || 0).toFixed(0)}`}</td></tr>
          <tr><td>mcts_total_visits</td><td>{String(s.mcts_total_visits ?? "N/A")}</td></tr>
          <tr><td>mcts_active_actions</td><td>{String(s.mcts_active_actions ?? "N/A")}</td></tr>
          <tr><td>telemetry_coverage</td><td>{String(s.telemetry_coverage_status ?? "N/A")}</td></tr>
        </tbody>
      </table>
      <h3 style={{ marginTop: 10 }}>Replay log lines</h3>
      {!lines.length ? (
        <div className="muted">No replay lines available.</div>
      ) : (
        <div className="panel" style={{ maxHeight: 420 }}>
          <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
            {lines.map((x) => String(x ?? "")).join("\n")}
          </pre>
        </div>
      )}
    </div>
  );
}
