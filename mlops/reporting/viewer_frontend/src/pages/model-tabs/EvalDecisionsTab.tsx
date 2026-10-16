import type { EvalResultRow } from "../../types";

type RowAgg = { action_kind: string; side: string; count: number; damage: number; kills: number };

function pct(value: number, total: number): string {
  if (!Number.isFinite(value) || !Number.isFinite(total) || total <= 0) return "N/A";
  return `${((100 * value) / total).toFixed(1)}%`;
}

export function EvalDecisionsTab({ mainResult }: { mainResult: EvalResultRow | null }) {
  if (!mainResult) return <div className="muted">No decision data available for this evaluation result.</div>;

  const summary = (mainResult.eval_decision_summary || {}) as Record<string, unknown>;
  const by = (summary.by_action_kind_and_side || {}) as Record<string, Record<string, unknown>>;
  const own = (summary.decision_ownership_by_side || {}) as Record<string, Record<string, unknown>>;
  const tops = Array.isArray(mainResult.eval_decisions_top) ? (mainResult.eval_decisions_top as Record<string, unknown>[]) : [];

  const rows: RowAgg[] = Object.values(by).map((src) => ({
    action_kind: String(src.action_kind || "UNKNOWN"),
    side: String(src.unit_side || "UNK"),
    count: Number(src.count || 0),
    damage: Number(src.damage_sum || 0),
    kills: Number(src.kills_sum || 0),
  }));
  rows.sort((a, b) => b.count - a.count);

  const sides = Array.from(new Set(rows.map((r) => r.side))).sort();
  const actions = Array.from(new Set(rows.map((r) => r.action_kind))).sort((a, b) => {
    const sa = rows.filter((r) => r.action_kind === a).reduce((n, r) => n + r.count, 0);
    const sb = rows.filter((r) => r.action_kind === b).reduce((n, r) => n + r.count, 0);
    return sb - sa;
  });

  const totalBySide = new Map<string, { count: number; damage: number; kills: number }>();
  for (const s of sides) totalBySide.set(s, { count: 0, damage: 0, kills: 0 });
  for (const r of rows) {
    const t = totalBySide.get(r.side) || { count: 0, damage: 0, kills: 0 };
    t.count += r.count;
    t.damage += r.damage;
    t.kills += r.kills;
    totalBySide.set(r.side, t);
  }

  const pivot = new Map<string, RowAgg>();
  for (const r of rows) pivot.set(`${r.action_kind}::${r.side}`, r);

  const ownRows = Object.entries(own).map(([side, src]) => ({
    side,
    rows: Number(src.rows || 0),
    policy_kept: Number(src.policy_kept || 0),
    overwritten: Number(src.overwritten || 0),
    override_signal_rows: Number(src.override_signal_rows || 0),
    unknown_override_rows: Number(src.unknown_override_rows || 0),
  }));
  ownRows.sort((a, b) => a.side.localeCompare(b.side));

  const topRows = tops
    .map((t) => ({
      action_id: String(t.action_id || ""),
      action_kind: String(t.action_kind || ""),
      side: String(t.unit_side || ""),
      count: Number(t.count || 0),
      damage: Number(t.damage_sum || 0),
      kills: Number(t.kills_sum || 0),
    }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 25);

  return (
    <div>
      <h3 style={{ margin: "0 0 6px 0" }}>Table A: Action Kind x Side (Canonical Pivot)</h3>
      <div className="muted" style={{ marginBottom: 8 }}>
        Distribution of action types, execution counts, damage dealt, and kills by side.
      </div>
      <table style={{ marginBottom: 16 }}>
        <thead>
          <tr>
            <th rowSpan={2}>action_kind</th>
            {sides.map((s) => (
              <th key={s} colSpan={6} style={{ textAlign: "center", background: "#1e293b" }}>
                {s}
              </th>
            ))}
          </tr>
          <tr>
            {sides.flatMap((s) => [
              <th key={`${s}-c`}>count</th>,
              <th key={`${s}-cp`}>% count</th>,
              <th key={`${s}-d`}>dmg</th>,
              <th key={`${s}-dp`}>% dmg</th>,
              <th key={`${s}-k`}>kills</th>,
              <th key={`${s}-kp`}>% kills</th>,
            ])}
          </tr>
        </thead>
        <tbody>
          {!actions.length ? (
            <tr><td colSpan={1 + sides.length * 6} className="muted">No decision rows available.</td></tr>
          ) : (
            actions.map((a) => (
              <tr key={a}>
                <td><b>{a}</b></td>
                {sides.flatMap((s) => {
                  const r = pivot.get(`${a}::${s}`);
                  const t = totalBySide.get(s) || { count: 0, damage: 0, kills: 0 };
                  if (!r) {
                    return [
                      <td key={`${a}-${s}-c`} className="muted">-</td>,
                      <td key={`${a}-${s}-cp`} className="muted">-</td>,
                      <td key={`${a}-${s}-d`} className="muted">-</td>,
                      <td key={`${a}-${s}-dp`} className="muted">-</td>,
                      <td key={`${a}-${s}-k`} className="muted">-</td>,
                      <td key={`${a}-${s}-kp`} className="muted">-</td>,
                    ];
                  }
                  return [
                    <td key={`${a}-${s}-c`}>{r.count}</td>,
                    <td key={`${a}-${s}-cp`}>{pct(r.count, t.count)}</td>,
                    <td key={`${a}-${s}-d`}>{r.damage.toFixed(2)}</td>,
                    <td key={`${a}-${s}-dp`}>{pct(r.damage, t.damage)}</td>,
                    <td key={`${a}-${s}-k`}>{r.kills.toFixed(0)}</td>,
                    <td key={`${a}-${s}-kp`}>{pct(r.kills, t.kills)}</td>,
                  ];
                })}
              </tr>
            ))
          )}
        </tbody>
      </table>

      <h3 style={{ margin: "14px 0 6px 0" }}>Table B: Decision Ownership by Side</h3>
      <div className="muted" style={{ marginBottom: 8 }}>
        Source: canonical policy-overridden-by-MCTS telemetry.
      </div>
      <table style={{ marginBottom: 16 }}>
        <thead>
          <tr>
            <th>side</th>
            <th>total_rows</th>
            <th>policy_kept</th>
            <th>overwritten (MCTS)</th>
            <th>override_signal_rows</th>
            <th>unknown_override_rows</th>
          </tr>
        </thead>
        <tbody>
          {!ownRows.length ? (
            <tr><td colSpan={6} className="muted">No ownership rows available.</td></tr>
          ) : (
            ownRows.map((r) => (
              <tr key={r.side}>
                <td><b>{r.side}</b></td>
                <td>{r.rows}</td>
                <td>{r.policy_kept} ({pct(r.policy_kept, r.rows)})</td>
                <td style={{ color: r.overwritten > 0 ? "#38bdf8" : undefined }}>
                  {r.overwritten} ({pct(r.overwritten, r.rows)})
                </td>
                <td>{r.override_signal_rows}</td>
                <td>{r.unknown_override_rows}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <h3 style={{ margin: "14px 0 6px 0" }}>Table C: Top Actions Executed</h3>
      <table>
        <thead>
          <tr>
            <th>action_id</th>
            <th>kind</th>
            <th>side</th>
            <th>count</th>
            <th>damage</th>
            <th>kills</th>
          </tr>
        </thead>
        <tbody>
          {!topRows.length ? (
            <tr><td colSpan={6} className="muted">No top actions recorded.</td></tr>
          ) : (
            topRows.map((r) => (
              <tr key={r.action_id}>
                <td><code>{r.action_id}</code></td>
                <td><b>{r.action_kind}</b></td>
                <td>{r.side}</td>
                <td>{r.count}</td>
                <td>{r.damage.toFixed(2)}</td>
                <td>{r.kills.toFixed(0)}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
