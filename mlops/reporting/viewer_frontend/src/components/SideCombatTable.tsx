import type { Dict, EvalResultRow } from "../types";

interface SideCombatStats {
  side: string;
  // Survival & Casualties
  avgUnitsAlive: number;
  avgUnitsLost: number;
  avgEnemyEliminated: number;
  avgDamageDealt: number;
  kdRatio: number;
  // Defensive Fire
  reactionWindows: number;
  reactionFired: number;
  reactionActivationRate: number;
  reactionKills: number;
  reactionDamage: number;
  // Melee & Assault
  meleeAttempts: number;
  meleeSuccessRate: number;
  meleeKills: number;
  meleeDamage: number;
  assaultFavorable: number;
  assaultUnfavorable: number;
  // Policy & Tactics
  policyConfidence: number;
  policyMargin: number;
  vpApproachRate: number;
  vpTakeRate: number;
}

export function SideCombatTable({
  results,
  filterSide,
}: {
  results: EvalResultRow[];
  filterSide?: string;
}) {
  if (!results.length) return null;

  // Accumulate KPIs and seed games across all provided results
  const kpisBySide: Record<string, Dict> = {};
  const allSeedGames: Dict[] = [];
  const sideSet = new Set<string>();

  for (const r of results) {
    const rKpis = (r.phase_2_9_eval_kpis_by_side || {}) as Record<string, Dict>;
    for (const [s, kpi] of Object.entries(rKpis)) {
      sideSet.add(s);
      if (!kpisBySide[s]) {
        kpisBySide[s] = { ...kpi };
      }
    }
    const rGames = (r.seed_games || []) as Dict[];
    for (const sg of rGames) {
      allSeedGames.push(sg);
      const sm = (sg.side_metrics || {}) as Record<string, Dict>;
      for (const s of Object.keys(sm)) {
        sideSet.add(s);
      }
    }
    if (r.tracked_side) {
      sideSet.add(r.tracked_side);
    }
  }

  let sides = Array.from(sideSet).sort();
  if (filterSide && filterSide !== "all") {
    sides = sides.filter((s) => s.toUpperCase() === filterSide.toUpperCase());
  }
  if (!sides.length) {
    return (
      <div className="muted" style={{ margin: "16px 0", fontStyle: "italic" }}>
        No hay métricas de combate registradas para el bando seleccionado: <b>{filterSide}</b>
      </div>
    );
  }

  // Aggregate stats per side
  const statsList: SideCombatStats[] = sides.map((side) => {
    const kpi = (kpisBySide[side] || {}) as Record<string, unknown>;

    // Aggregates from seed_games
    let totalAlive = 0;
    let totalLost = 0;
    let totalEliminated = 0;
    let totalDamage = 0;
    let gameCount = 0;

    for (const sg of allSeedGames) {
      const sm = (sg.side_metrics || {}) as Record<string, Dict>;
      const sideStat = sm[side] as Dict | undefined;
      if (sideStat) {
        totalAlive += Number(sideStat.units_alive_final || 0);
        totalLost += Number(sideStat.units_lost || 0);
        totalEliminated += Number(sideStat.enemy_units_eliminated || 0);
        totalDamage += Number(sideStat.damage_dealt || 0);
        gameCount += 1;
      }
    }

    const nGames = Math.max(1, gameCount || allSeedGames.length || 1);
    const avgAlive = totalAlive / nGames;
    const avgLost = totalLost / nGames;
    const avgEliminated = totalEliminated / nGames;
    const avgDamage = totalDamage / nGames;
    const kdRatio = avgLost > 0 ? avgEliminated / avgLost : avgEliminated;

    return {
      side,
      avgUnitsAlive: avgAlive,
      avgUnitsLost: avgLost,
      avgEnemyEliminated: avgEliminated,
      avgDamageDealt: avgDamage,
      kdRatio,
      reactionWindows: Number(kpi.reaction_window_count || 0),
      reactionFired: Number(kpi.reaction_fire_count || 0),
      reactionActivationRate: Number(kpi.reaction_fire_activation_rate || 0),
      reactionKills: Number(kpi.reaction_fire_kill_conversions || 0),
      reactionDamage: Number(kpi.reaction_fire_damage_sum || 0),
      meleeAttempts: Number(kpi.melee_attempts || 0),
      meleeSuccessRate: Number(kpi.melee_success_rate || 0),
      meleeKills: Number(kpi.melee_kills_sum || 0),
      meleeDamage: Number(kpi.melee_damage_sum || 0),
      assaultFavorable: Number(kpi.assault_favorable_count || 0),
      assaultUnfavorable: Number(kpi.assault_unfavorable_count || 0),
      policyConfidence: Number(kpi.xai_policy_confidence_mean || 0),
      policyMargin: Number(kpi.xai_policy_margin_mean || 0),
      vpApproachRate: Number(kpi.vp_approach_rate || 0),
      vpTakeRate: Number(kpi.xai_vp_capture_take_rate || 0),
    };
  });

  return (
    <div style={{ margin: "20px 0" }}>
      <h3 style={{ margin: "0 0 6px 0", color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
        <span>⚔️</span> Desglose Táctico y Efectividad de Combate por Bando
      </h3>
      <div className="muted" style={{ marginBottom: 12 }}>
        Métricas agregadas a nivel táctico: Fuego de reacción (defensivo), combate cuerpo a cuerpo (melee), ratio de bajas y eficiencia decisoria.
      </div>

      <table>
        <thead>
          <tr>
            <th rowSpan={2}>Bando</th>
            <th rowSpan={2}>Oponente</th>
            <th colSpan={5} style={{ textAlign: "center", background: "#1e3a8a", color: "#93c5fd" }}>
              Bajas y Supervivencia (Promedio / Partida)
            </th>
            <th colSpan={4} style={{ textAlign: "center", background: "#701a75", color: "#f0abfc" }}>
              Fuego de Reacción (Defensivo)
            </th>
            <th colSpan={3} style={{ textAlign: "center", background: "#7c2d12", color: "#fdba74" }}>
              Asaltos y Melee
            </th>
            <th colSpan={2} style={{ textAlign: "center", background: "#065f46", color: "#6ee7b7" }}>
              Decisión Táctica
            </th>
          </tr>
          <tr>
            <th>Vivas</th>
            <th>Perdidas</th>
            <th>Eliminadas</th>
            <th>K/D</th>
            <th>Daño</th>
            <th>Ventanas</th>
            <th>Disparos</th>
            <th>Activación %</th>
            <th>Bajas Reacc.</th>
            <th>Intentos</th>
            <th>Éxito %</th>
            <th>Fav / Desfav</th>
            <th>Confianza</th>
            <th>Margen</th>
          </tr>
        </thead>
        <tbody>
          {statsList.map((st) => {
            const oppSide = st.side === "US" ? "IT" : st.side === "IT" ? "US" : st.side === "GE" ? "US" : "-";
            const oppLabel = oppSide === "US" ? "🇺🇸 US" : oppSide === "IT" ? "🇮🇹 IT" : oppSide === "GE" ? "🇩🇪 GE" : oppSide;
            const oppColor = oppSide === "US" ? "#60a5fa" : oppSide === "IT" ? "#34d399" : oppSide === "GE" ? "#f87171" : "#cbd5e1";

            return (
              <tr key={st.side}>
                <td>
                  <b style={{ fontSize: "13px", color: st.side === "US" ? "#60a5fa" : st.side === "IT" ? "#34d399" : "#f87171" }}>
                    {st.side === "US" ? "🇺🇸 US" : st.side === "IT" ? "🇮🇹 IT" : st.side === "GE" ? "🇩🇪 GE" : st.side}
                  </b>
                </td>
                <td>
                  <span style={{ fontSize: "12px", color: oppColor, fontWeight: 600 }}>
                    {oppLabel}
                  </span>
                </td>
              {/* Survival */}
              <td>{st.avgUnitsAlive > 0 ? st.avgUnitsAlive.toFixed(1) : "-"}</td>
              <td style={{ color: st.avgUnitsLost > 3 ? "#f87171" : "#e2e8f0" }}>
                {st.avgUnitsLost > 0 ? st.avgUnitsLost.toFixed(1) : "-"}
              </td>
              <td style={{ color: "#34d399", fontWeight: 600 }}>
                {st.avgEnemyEliminated > 0 ? st.avgEnemyEliminated.toFixed(1) : "-"}
              </td>
              <td style={{ fontWeight: 700, color: st.kdRatio >= 1.0 ? "#22c55e" : "#ef4444" }}>
                {st.kdRatio.toFixed(2)}
              </td>
              <td>{st.avgDamageDealt > 0 ? st.avgDamageDealt.toFixed(1) : "-"}</td>

              {/* Reaction */}
              <td>{st.reactionWindows.toLocaleString()}</td>
              <td>{st.reactionFired.toLocaleString()}</td>
              <td style={{ color: st.reactionActivationRate > 0.5 ? "#60a5fa" : "#94a3b8" }}>
                {(st.reactionActivationRate * 100).toFixed(1)}%
              </td>
              <td style={{ color: "#34d399", fontWeight: 600 }}>
                {st.reactionKills.toLocaleString()}
              </td>

              {/* Melee */}
              <td>{st.meleeAttempts.toLocaleString()}</td>
              <td style={{ color: st.meleeSuccessRate >= 0.5 ? "#22c55e" : "#fbbf24" }}>
                {(st.meleeSuccessRate * 100).toFixed(1)}%
              </td>
              <td style={{ fontSize: "11px" }}>
                <span style={{ color: "#22c55e" }}>{st.assaultFavorable}</span> / <span style={{ color: "#f87171" }}>{st.assaultUnfavorable}</span>
              </td>

              {/* Policy */}
              <td>{(st.policyConfidence * 100).toFixed(1)}%</td>
              <td>{(st.policyMargin * 100).toFixed(1)}%</td>
            </tr>
          );
        })}
        </tbody>
      </table>
    </div>
  );
}
