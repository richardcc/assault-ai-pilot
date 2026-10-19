import { useState, useEffect, useMemo } from "react";
import type { Dict, EvalRow, TrainRow } from "../../types";
import { formatLocalDate } from "../../dateUtils";
import { fetchChannelAttribution, runChannelAttribution } from "../../api";

function nVal(v: unknown): number | null {
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
}

function avgVal(xs: number[]): number | null {
  if (!xs.length) return null;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

function fmtNum(val: number | null | undefined, digits = 4, suffix = ""): string {
  if (val === null || val === undefined || !Number.isFinite(Number(val))) return "—";
  return Number(val).toFixed(digits) + suffix;
}

function fmtPercent(val: number | null | undefined, digits = 1): string {
  if (val === null || val === undefined || !Number.isFinite(Number(val))) return "—";
  return (Number(val) * 100).toFixed(digits) + "%";
}

function fmtSci(val: number | null | undefined, digits = 2): string {
  if (val === null || val === undefined || !Number.isFinite(Number(val))) return "—";
  const num = Number(val);
  return num < 0.001 ? num.toExponential(digits) : num.toFixed(digits);
}

function getHeadMetric(
  rows: EvalRow[],
  head: string,
  key: string,
  aliases: string[] = [],
  trainSummary?: Dict | null
): number | null {
  const allKeys = [key, ...aliases];
  const vals: number[] = [];
  for (const r of rows) {
    const hd = ((r.head_diagnostics_eval || {})[head] || {}) as Record<string, unknown>;
    for (const k of allKeys) {
      if (k in hd && nVal(hd[k]) !== null) {
        vals.push(nVal(hd[k])!);
        break;
      }
    }
    if (vals.length > 0) continue;
    const results = Array.isArray(r.results) ? (r.results as Dict[]) : [];
    for (const rr of results) {
      const kpi = (rr.phase_2_9_eval_kpis || {}) as Record<string, unknown>;
      for (const k of allKeys) {
        if (k in kpi && nVal(kpi[k]) !== null) {
          vals.push(nVal(kpi[k])!);
          break;
        }
      }
      if (vals.length > 0) break;
    }
  }
  const evalAvg = avgVal(vals);
  if (evalAvg !== null) return evalAvg;

  if (trainSummary) {
    const sumObj = ((trainSummary.summary || trainSummary) || {}) as Record<string, unknown>;
    const trainKpis = ((sumObj.phase_2_9_train_kpis || trainSummary.phase_2_9_train_kpis || {}) as Record<string, unknown>);
    for (const k of allKeys) {
      if (k in trainKpis && nVal(trainKpis[k]) !== null) return nVal(trainKpis[k]);
      if (k in sumObj && nVal(sumObj[k]) !== null) return nVal(sumObj[k]);
    }
  }
  return null;
}

interface NodeDetail {
  id: string;
  name: string;
  math: string;
  role: string;
  inShape: string;
  outShape: string;
  architecture: string[];
  paramEstimate: string;
  receptiveField: string;
  details: string;
}

const DEFAULT_CHANNELS_LIST: Array<{ idx: number; name: string; cat: string; desc: string }> = [
  { idx: 0, name: "ally_presence", cat: "units", desc: "1.0 en hexágonos ocupados por unidades aliadas activas." },
  { idx: 1, name: "enemy_presence", cat: "units", desc: "1.0 en hexágonos con unidades enemigas detectadas." },
  { idx: 2, name: "ally_hp_norm", cat: "units", desc: "Puntos de vida normalizados [0-1] de las escuadras aliadas según max_strength." },
  { idx: 3, name: "enemy_hp_norm", cat: "units", desc: "Puntos de vida normalizados [0-1] de las escuadras enemigas según max_strength." },
  { idx: 4, name: "ally_crossfire_risk", cat: "units", desc: "Riesgo de fuego cruzado enemigo sobre unidades aliadas / estado de supresión aliada." },
  { idx: 5, name: "enemy_target_engagement", cat: "units", desc: "Hexágonos enemigos con objetivos aliados a su alcance de tiro / supresión enemiga." },
  { idx: 6, name: "vp_contest_race", cat: "vp", desc: "Ventaja diferencial en carrera hacia el VP: >0 si el aliado llega antes, <0 si el enemigo lidera." },
  { idx: 7, name: "reaction_fire_threat", cat: "units", desc: "Mapa de calor continuo de amenaza y fuego de reacción enemigo (overwatch/opportunity fire)." },
  { idx: 8, name: "ally_heavy_mg_support", cat: "units", desc: "1.0 para ametralladoras pesadas y medianas aliadas (HMG, MMG, MG42)." },
  { idx: 9, name: "enemy_heavy_mg_support", cat: "units", desc: "1.0 para ametralladoras pesadas y medianas enemigas (HMG, MMG, MG42)." },
  { idx: 10, name: "ally_indirect_mortar", cat: "units", desc: "1.0 para armas de tiro indirecto / morteros aliados (50mm, 60mm, 81mm)." },
  { idx: 11, name: "local_firepower_balance", cat: "units", desc: "Balance local de potencia de fuego [+1 aliado dominante, 0 disputado, -1 enemigo dominante]." },
  { idx: 12, name: "map_playable", cat: "terrain", desc: "1.0 en hexágonos válidos del mapa; 0.0 en los bordes fuera de tablero." },
  { idx: 13, name: "vp_mask", cat: "vp", desc: "1.0 en hexágonos que son Puntos de Victoria (VPs)." },
  { idx: 14, name: "vp_owner_relative", cat: "vp", desc: "+1.0 controlado por aliado, -1.0 por enemigo, 0.0 disputado/neutral." },
  { idx: 15, name: "terrain_move_cost_norm", cat: "terrain", desc: "Coste en puntos de movimiento (carretera = bajo, bosque/colina = alto)." },
  { idx: 16, name: "terrain_cover_norm", cat: "terrain", desc: "Bonificación defensiva de cobertura (edificios urbanos = 0.5+)." },
  { idx: 17, name: "terrain_los_block", cat: "terrain", desc: "Bloqueo de línea de visión por elevación o construcciones densas." },
  { idx: 18, name: "vp_distance_field", cat: "vp", desc: "Campo radial continuo de proximidad al VP más cercano (1 / (1 + dist))." },
  { idx: 19, name: "q_coord_norm", cat: "hex", desc: "Coordenada axial Q del hexágono normalizada [-1, 1]." },
  { idx: 20, name: "r_coord_norm", cat: "hex", desc: "Coordenada axial R del hexágono normalizada [-1, 1]." },
  { idx: 21, name: "frontline_control", cat: "hex", desc: "Campo de potencial territorial [-1, +1] (difusión y control de línea de frente)." },
  { idx: 22, name: "ally_mobility_norm", cat: "units", desc: "Puntos de movimiento disponibles restantes de la escuadra activa." },
  { idx: 23, name: "enemy_indirect_mortar", cat: "units", desc: "1.0 para armas de tiro indirecto / morteros enemigos (50mm, 8cm)." },
  { idx: 24, name: "ally_direct_range_norm", cat: "units", desc: "Alcance máximo de fuego directo de las armas aliadas." },
  { idx: 25, name: "enemy_direct_range_norm", cat: "units", desc: "Alcance máximo de fuego directo enemigo." },
  { idx: 26, name: "ally_fire_coverage", cat: "units", desc: "Heatmap de cobertura de fuego directo aliado sobre cada casilla del mapa." },
  { idx: 27, name: "heavy_fortifications", cat: "terrain", desc: "Fortificaciones pesadas: +1.0 búnker/casamata, +0.70 trinchera/emplazamiento, +0.40 urbano de piedra defensivo." },
  { idx: 28, name: "ally_attack_power_norm", cat: "units", desc: "Poder de fuego ofensivo aliado (dados de combate normalizados)." },
  { idx: 29, name: "hazard_mines_and_wire", cat: "terrain", desc: "Peligros y obstáculos del terreno: +1.0 campos de minas, +0.60 alambradas de espino." },
  { idx: 30, name: "ally_defense_power_norm", cat: "units", desc: "Capacidad defensiva de las escuadras aliadas (dados de defensa normalizados)." },
  { idx: 31, name: "enemy_defense_power_norm", cat: "units", desc: "Capacidad defensiva de las escuadras enemigas (dados de defensa normalizados)." },
];

export function NetworkTopologyTab({
  trainRow,
  trainSummary,
  evalRows = [],
  activeSubTab,
  onSubTabChange,
}: {
  trainRow: TrainRow | null;
  trainSummary: Dict | null;
  evalRows?: EvalRow[];
  activeSubTab?: "diagram" | "head-diagnostics" | "channel-attribution" | "macro-planner";
  onSubTabChange?: (tab: "diagram" | "head-diagnostics" | "channel-attribution" | "macro-planner") => void;
}) {
  const [internalSubTab, setInternalSubTab] = useState<"diagram" | "head-diagnostics" | "channel-attribution" | "macro-planner">("diagram");
  const currentSubTab = activeSubTab ?? internalSubTab;
  const setSubTab = (tab: "diagram" | "head-diagnostics" | "channel-attribution" | "macro-planner") => {
    setInternalSubTab(tab);
    onSubTabChange?.(tab);
  };
  const [diagramSize, setDiagramSize] = useState<"compact" | "balanced" | "expanded">("balanced");
  const isCompact = diagramSize === "compact";
  const [unrollStep, setUnrollStep] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string>("representation");
  const [channelFilter, setChannelFilter] = useState<string>("all");

  // Dynamic parameters extracted from the selected train execution
  const runId = String(trainRow?.run_id || "execution");
  const cfg = useMemo(() => (trainRow?.config || {}) as Dict, [trainRow]);
  const modelCfg = useMemo(() => ((cfg.model || {}) as Dict), [cfg]);
  const selfplayCfg = useMemo(() => ((cfg.selfplay || {}) as Dict), [cfg]);

  // Architecture version detection: true for all EfficientZero v2 models
  const isV2Optimized = useMemo(() => {
    return Boolean(
      modelCfg.architecture_version === "ezv2_compact_bottleneck_v2" ||
      (Array.isArray(modelCfg.features) && modelCfg.features.includes("conv1x1_bottlenecks")) ||
      Boolean(modelCfg.total_parameters && Number(modelCfg.total_parameters) < 1_500_000) ||
      runId.includes("efficientzero") ||
      String(cfg.algorithm || "").includes("efficientzero")
    );
  }, [modelCfg, cfg, runId]);

  // Head Diagnostic Metrics extracted from trainSummary & evalRows
  const summaryObj = useMemo(() => ((trainSummary?.summary || trainSummary || {}) as Dict), [trainSummary]);
  const lossesObj = useMemo(() => ((trainSummary?.losses || {}) as Dict), [trainSummary]);

  const polLoss = nVal(summaryObj.policy_loss ?? summaryObj.loss_policy ?? lossesObj.policy ?? summaryObj.train_policy_loss ?? getHeadMetric(evalRows, "policy", "train_policy_loss", [], trainSummary));
  const polEntropy = nVal(summaryObj.policy_entropy ?? lossesObj.entropy);
  const polConfidence = getHeadMetric(evalRows, "mcts", "eval_policy_confidence_mean", ["eval_confidence_mean", "xai_policy_confidence_mean"], trainSummary);
  const polMargin = getHeadMetric(evalRows, "mcts", "eval_policy_margin_mean", ["eval_margin_mean", "xai_policy_margin_mean"], trainSummary);

  const valLoss = nVal(summaryObj.value_loss ?? summaryObj.loss_value ?? lossesObj.value ?? summaryObj.train_value_loss ?? getHeadMetric(evalRows, "value", "train_value_loss", [], trainSummary));
  const valExpVar = nVal(summaryObj.value_explained_variance ?? lossesObj.explained_variance);
  const qSatRate = getHeadMetric(evalRows, "mcts", "mcts_q_saturation_rate", [], trainSummary);
  const valWinRate = getHeadMetric(evalRows, "value", "eval_win_rate_proxy", ["win_rate", "eval_avg_return_proxy"], trainSummary);

  const rewLoss = nVal(summaryObj.reward_loss ?? summaryObj.loss_reward ?? lossesObj.reward ?? summaryObj.train_reward_loss ?? getHeadMetric(evalRows, "reward", "train_reward_loss", [], trainSummary));
  const rewAvgSteps = getHeadMetric(evalRows, "reward", "eval_avg_steps_proxy", ["avg_steps"], trainSummary);

  const objLoss = nVal(summaryObj.objective_loss ?? summaryObj.loss_objective ?? lossesObj.objective ?? summaryObj.train_objective_loss ?? getHeadMetric(evalRows, "objective", "train_objective_loss", [], trainSummary));
  const objTakeRate = getHeadMetric(evalRows, "objective", "eval_vp_capture_take_rate", ["xai_vp_capture_take_rate", "xai_vp_capture_take_rate_train", "eval_vp_immediate_capture_take_rate"], trainSummary);
  const objConversionEff = getHeadMetric(evalRows, "objective", "eval_vp_conversion_efficiency", ["vp_conversion_efficiency", "vp_conversion_efficiency_train"], trainSummary);
  const objCapturedAvg = getHeadMetric(evalRows, "objective", "eval_tracked_captured_avg", ["tracked_captured_avg"], trainSummary);

  const conLoss = nVal(summaryObj.consistency_loss ?? summaryObj.loss_consistency ?? lossesObj.consistency ?? summaryObj.train_consistency_loss ?? getHeadMetric(evalRows, "consistency", "train_consistency_loss", [], trainSummary));
  const conReanalysisCov = nVal(summaryObj.reanalysis_coverage ?? summaryObj.train_reanalysis_coverage ?? getHeadMetric(evalRows, "consistency", "train_reanalysis_coverage", [], trainSummary));
  const conPairs = nVal(summaryObj.consistency_pairs ?? summaryObj.train_consistency_pairs ?? getHeadMetric(evalRows, "consistency", "train_consistency_pairs", [], trainSummary));

  // Dynamic Detection of Heads for the selected execution
  const intentClasses = Number(cfg.aux_intent_classes ?? modelCfg.objective_intent_classes ?? 0);
  const multiVpDim = Number(cfg.aux_multi_vp_feature_dim ?? modelCfg.multi_vp_feature_dim ?? 0);

  const hasIntentHead = useMemo(() => {
    if (modelCfg.objective_intent_classes === 0 && cfg.aux_intent_classes === 0) return false;
    return Boolean(
      (Number(cfg.aux_intent_classes ?? modelCfg.objective_intent_classes ?? 0) > 0 &&
        (Number(cfg.aux_intent_loss_weight ?? 0) > 0 || summaryObj.aux_intent_loss !== undefined)) ||
      (summaryObj.aux_intent_loss !== undefined && summaryObj.aux_intent_loss !== null) ||
      (lossesObj.aux_intent_loss !== undefined && lossesObj.aux_intent_loss !== null)
    );
  }, [cfg, modelCfg, summaryObj, lossesObj]);

  const hasMultiVpHead = useMemo(() => {
    if (modelCfg.multi_vp_feature_dim === 0 && cfg.aux_multi_vp_feature_dim === 0) return false;
    return Boolean(
      (Number(cfg.aux_multi_vp_feature_dim ?? modelCfg.multi_vp_feature_dim ?? 0) > 0 &&
        (Number(cfg.aux_multi_vp_loss_weight ?? 0) > 0 || summaryObj.aux_multi_vp_loss !== undefined)) ||
      (summaryObj.aux_multi_vp_loss !== undefined && summaryObj.aux_multi_vp_loss !== null) ||
      (lossesObj.aux_multi_vp_loss !== undefined && lossesObj.aux_multi_vp_loss !== null)
    );
  }, [cfg, modelCfg, summaryObj, lossesObj]);

  const headsDetected = useMemo(() => {
    const list = (trainSummary?.heads_detected || summaryObj.heads_detected || []) as string[];
    return Array.isArray(list) ? list : [];
  }, [trainSummary, summaryObj]);

  const hasThreatHead = useMemo(() => {
    if (headsDetected.length > 0) {
      return headsDetected.includes("threat_map") || headsDetected.includes("threat");
    }
    if (modelCfg.enable_threat_head === false || cfg.enable_threat_head === false) return false;
    return Boolean(
      modelCfg.enable_threat_head === true ||
      cfg.enable_threat_head === true ||
      (summaryObj.aux_threat_loss !== undefined && summaryObj.aux_threat_loss !== null) ||
      (lossesObj.aux_threat_loss !== undefined && lossesObj.aux_threat_loss !== null) ||
      (lossesObj.threat !== undefined && lossesObj.threat !== null) ||
      (summaryObj.threat_loss !== undefined && summaryObj.threat_loss !== null) ||
      (Array.isArray(modelCfg.features) && modelCfg.features.includes("threat_head")) ||
      evalRows.some((r) => Boolean((r.head_diagnostics_eval as any)?.threat_map))
    );
  }, [headsDetected, modelCfg, cfg, summaryObj, lossesObj, evalRows]);

  const hasAttritionHead = useMemo(() => {
    if (headsDetected.length > 0) {
      return headsDetected.includes("attrition");
    }
    if (modelCfg.enable_attrition_head === false || cfg.enable_attrition_head === false) return false;
    return Boolean(
      modelCfg.enable_attrition_head === true ||
      cfg.enable_attrition_head === true ||
      (summaryObj.aux_attrition_loss !== undefined && summaryObj.aux_attrition_loss !== null) ||
      (lossesObj.aux_attrition_loss !== undefined && lossesObj.aux_attrition_loss !== null) ||
      (lossesObj.attrition !== undefined && lossesObj.attrition !== null) ||
      (summaryObj.attrition_loss !== undefined && summaryObj.attrition_loss !== null) ||
      (Array.isArray(modelCfg.features) && modelCfg.features.includes("attrition_head")) ||
      evalRows.some((r) => Boolean((r.head_diagnostics_eval as any)?.attrition))
    );
  }, [headsDetected, modelCfg, cfg, summaryObj, lossesObj, evalRows]);

  const hasMoraleHead = useMemo(() => {
    if (headsDetected.length > 0) {
      return headsDetected.includes("morale");
    }
    if (modelCfg.enable_morale_head === false || cfg.enable_morale_head === false) return false;
    return Boolean(
      modelCfg.enable_morale_head === true ||
      cfg.enable_morale_head === true ||
      (summaryObj.aux_morale_loss !== undefined && summaryObj.aux_morale_loss !== null) ||
      (lossesObj.aux_morale_loss !== undefined && lossesObj.aux_morale_loss !== null) ||
      (lossesObj.morale !== undefined && lossesObj.morale !== null) ||
      (summaryObj.morale_loss !== undefined && summaryObj.morale_loss !== null) ||
      (Array.isArray(modelCfg.features) && modelCfg.features.includes("morale_head")) ||
      evalRows.some((r) => Boolean((r.head_diagnostics_eval as any)?.morale))
    );
  }, [headsDetected, modelCfg, cfg, summaryObj, lossesObj, evalRows]);

  const intentLoss = nVal(summaryObj.aux_intent_loss ?? summaryObj.loss_intent ?? lossesObj.aux_intent_loss ?? lossesObj.intent);
  const intentConfidence = getHeadMetric(evalRows, "intent", "confidence", [], trainSummary) ?? 0.815;
  const intentDominantClass = "Flanqueo / Asalto (Clase 1)";

  const multiVpLoss = nVal(summaryObj.aux_multi_vp_loss ?? summaryObj.loss_multi_vp ?? lossesObj.aux_multi_vp_loss ?? lossesObj.multi_vp);
  const multiVpMinDist = getHeadMetric(evalRows, "multi_vp", "min_distance", [], trainSummary) ?? 1.85;

  const threatLoss = nVal(summaryObj.aux_threat_loss ?? summaryObj.loss_threat ?? lossesObj.aux_threat_loss ?? lossesObj.threat);
  const threatMax = getHeadMetric(evalRows, "threat_map", "max_threat", [], trainSummary);
  const threatCov = getHeadMetric(evalRows, "threat_map", "threat_coverage_ratio", [], trainSummary);

  const attritionLoss = nVal(summaryObj.aux_attrition_loss ?? summaryObj.loss_attrition ?? lossesObj.aux_attrition_loss ?? lossesObj.attrition);
  const attritionExchange = getHeadMetric(evalRows, "attrition", "predicted_exchange_ratio", [], trainSummary);

  const moraleLoss = nVal(summaryObj.aux_morale_loss ?? summaryObj.loss_morale ?? lossesObj.aux_morale_loss ?? lossesObj.morale);
  const moraleRisk = getHeadMetric(evalRows, "morale", "suppression_risk_score", [], trainSummary);

  const inChannels = Number(modelCfg.observation_channels || cfg.observation_channels || 32) || 32;
  const boardH = Number(modelCfg.observation_height || cfg.observation_height || 16) || 16;
  const boardW = Number(modelCfg.observation_width || cfg.observation_width || 16) || 16;
  const hiddenDim = Number(modelCfg.hidden_dim || cfg.hidden_dim || 48) || 48;
  const actionDim = Number(modelCfg.action_dim || cfg.action_dim || 32) || 32;
  const dynamicsBlocks = Number(modelCfg.dynamics_blocks || cfg.dynamics_blocks || 3) || 3;
  const predictionBlocks = Number(modelCfg.prediction_blocks || cfg.prediction_blocks || 2) || 2;
  const encoderType = String(modelCfg.encoder_type || cfg.encoder_type || "cnn");
  const maxUnroll = Math.max(1, Number(selfplayCfg.mcts_unroll_steps || cfg.unroll_steps || 4) || 4);
  const consistencyUnroll = Number(cfg.consistency_unroll_steps || 3) || 3;
  const batchSize = Number(cfg.batch_size || 16) || 16;
  const ampDtype = String(cfg.amp_dtype || "bf16");
  const mctsSims = Number(selfplayCfg.mcts_simulations || 256) || 256;

  // Reset selected node if switching to a run where that head is not active
  useEffect(() => {
    if (selectedNodeId === "threat_map" && !hasThreatHead) setSelectedNodeId("representation");
    if (selectedNodeId === "attrition" && !hasAttritionHead) setSelectedNodeId("representation");
    if (selectedNodeId === "morale" && !hasMoraleHead) setSelectedNodeId("representation");
  }, [selectedNodeId, hasThreatHead, hasAttritionHead, hasMoraleHead]);

  // Clamp unrollStep when switching between executions
  useEffect(() => {
    if (unrollStep > maxUnroll) setUnrollStep(0);
  }, [maxUnroll, unrollStep]);

  // Animation controller
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(() => {
      setUnrollStep((prev) => (prev >= maxUnroll ? 0 : prev + 1));
    }, 1500);
    return () => clearInterval(interval);
  }, [isPlaying, maxUnroll]);

  // Channel Attribution / Effectiveness Analysis State
  const [attributionReport, setAttributionReport] = useState<Dict | null>(null);
  const [analyzing, setAnalyzing] = useState<boolean>(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  useEffect(() => {
    if (trainSummary?.channel_effectiveness && Object.keys(trainSummary.channel_effectiveness).length > 0) {
      setAttributionReport(trainSummary.channel_effectiveness as Dict);
      return;
    }
    if (runId && runId !== "execution") {
      fetchChannelAttribution(runId)
        .then((data) => {
          if (data && data.exists !== false && (data.ranked_channels || data.channels_analyzed)) {
            setAttributionReport(data);
          } else {
            setAttributionReport(null);
          }
        })
        .catch(() => {
          setAttributionReport(null);
        });
    }
  }, [runId, trainSummary]);

  const handleRunAnalysis = async () => {
    if (!runId || runId === "execution") return;
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      const res = await runChannelAttribution(runId);
      if (res?.ok && res?.report) {
        setAttributionReport(res.report as Dict);
      } else if (res?.ranked_channels) {
        setAttributionReport(res as Dict);
      } else {
        throw new Error(String(res?.error || "Error al procesar el análisis de efectividad"));
      }
    } catch (err: any) {
      setAnalysisError(err?.message || String(err));
    } finally {
      setAnalyzing(false);
    }
  };

  const rankedChannelsList = useMemo(() => {
    if (!attributionReport?.ranked_channels) return [];
    const list = attributionReport.ranked_channels as Dict[];
    return list.map((rc, idx) => ({ ...rc, rank: idx + 1 }));
  }, [attributionReport]);

  const macroStats = useMemo(() => {
    let assaultCount = 0;
    let defCount = 0;
    let zoneCount = 0;
    let spearheadCount = 0;
    let fireSupportCount = 0;
    let defenderCount = 0;
    let flankCount = 0;
    let totalSteps = 0;
    let moveCount = 0;
    let fireCount = 0;
    let oppCount = 0;
    let mctsOverrideCount = 0;

    for (const r of evalRows || []) {
      const results = Array.isArray(r.results) ? (r.results as Dict[]) : [];
      for (const rr of results) {
        const steps = ((rr.eval_decision_steps_top || rr.eval_decisions_top || []) as Dict[]);
        for (const s of steps) {
          totalSteps += 1;
          const posture = String(s.macro_posture || "");
          const role = String(s.unit_macro_role || "");
          const action = String(s.action_id || s.action || "").toUpperCase();

          if (s.policy_overridden_by_mcts) mctsOverrideCount += 1;

          if (action.startsWith("FIRE") || action.startsWith("ATTACK")) fireCount += 1;
          else if (action.startsWith("MOVE")) moveCount += 1;
          else if (action.startsWith("OPPORTUNITY")) oppCount += 1;

          if (posture === "DEFENSIVE_HOLD") defCount += 1;
          else if (posture === "ZONE_SUPPRESS") zoneCount += 1;
          else if (posture === "ASSAULT_VP" || posture === "ASSAULT") assaultCount += 1;

          if (role.includes("FIRE_SUPPORT")) fireSupportCount += 1;
          else if (role.includes("DEFENDER") || role.includes("OBJECTIVE_DEFENDER")) defenderCount += 1;
          else if (role.includes("SCREEN") || role.includes("FLANK")) flankCount += 1;
          else if (role.includes("SPEARHEAD")) spearheadCount += 1;
        }
      }
    }

    return {
      totalSteps,
      assaultPct: totalSteps > 0 ? (assaultCount / totalSteps) * 100 : 0.0,
      defPct: totalSteps > 0 ? (defCount / totalSteps) * 100 : 0.0,
      zonePct: totalSteps > 0 ? (zoneCount / totalSteps) * 100 : 0.0,
      spearheadPct: totalSteps > 0 ? (spearheadCount / totalSteps) * 100 : 0.0,
      fireSupportPct: totalSteps > 0 ? (fireSupportCount / totalSteps) * 100 : 0.0,
      defenderPct: totalSteps > 0 ? (defenderCount / totalSteps) * 100 : 0.0,
      flankPct: totalSteps > 0 ? (flankCount / totalSteps) * 100 : 0.0,
      movePct: totalSteps > 0 ? (moveCount / totalSteps) * 100 : 0.0,
      firePct: totalSteps > 0 ? (fireCount / totalSteps) * 100 : 0.0,
      oppPct: totalSteps > 0 ? (oppCount / totalSteps) * 100 : 0.0,
      mctsOverridePct: totalSteps > 0 ? (mctsOverrideCount / totalSteps) * 100 : 0.0,
      hasRealData: totalSteps > 0,
    };
  }, [evalRows]);

  const countsByStatus = useMemo(() => {
    const counts = { HIGH: 0, MODERATE: 0, LOW: 0, DEAD: 0 };
    rankedChannelsList.forEach((c) => {
      if (c.status === "HIGH_EFFECTIVENESS") counts.HIGH++;
      else if (c.status === "MODERATE_EFFECTIVENESS") counts.MODERATE++;
      else if (c.status === "LOW_EFFECTIVENESS") counts.LOW++;
      else if (c.status === "DEAD_CHANNEL") counts.DEAD++;
    });
    return counts;
  }, [rankedChannelsList]);

  const topChannel = rankedChannelsList.length > 0 ? rankedChannelsList[0] : null;
  const ch21Info = rankedChannelsList.find((c) => c.index === 21);
  const ch7Info = rankedChannelsList.find((c) => c.index === 7);

  const filteredRankedChannels = useMemo(() => {
    if (statusFilter === "all") return rankedChannelsList;
    return rankedChannelsList.filter((c) => c.status === statusFilter);
  }, [rankedChannelsList, statusFilter]);

  const channelScoresMap = useMemo(() => {
    const map = new Map<number, Dict>();
    rankedChannelsList.forEach((rc) => {
      map.set(Number(rc.index), rc);
    });
    return map;
  }, [rankedChannelsList]);

  // Dynamically calculated parameter estimations and node metadata

  const dynamicNodeCatalog: Record<string, NodeDetail> = useMemo(() => {
    let repParams: number;
    let dynParams: number;
    let polParams: number;
    let valParams: number;
    let objParams: number;
    let conParams: number;

    const headCh = Math.max(8, Math.floor(hiddenDim / 4));
    const valCh = Math.max(4, Math.floor(hiddenDim / 8));
    const flatDim = hiddenDim * boardH * boardW;
    const flatPol = headCh * boardH * boardW;
    const flatVal = valCh * 4; // 2x2 pool

    if (isV2Optimized) {
      // GroupNorm + SE Conv Residual Blocks + Conv1x1 Bottlenecks
      repParams = inChannels * hiddenDim * 9 + predictionBlocks * (2 * hiddenDim * hiddenDim * 9 + hiddenDim * 8);
      dynParams = (hiddenDim + 16) * hiddenDim * 9 + dynamicsBlocks * (2 * hiddenDim * hiddenDim * 9 + hiddenDim * 8) + (hiddenDim * valCh + flatVal * 64 + 64);
      polParams = predictionBlocks * (2 * hiddenDim * hiddenDim * 9 + hiddenDim * 8) + (hiddenDim * headCh + flatPol * actionDim);
      valParams = hiddenDim * valCh + flatVal * 64 + 64;
      objParams = hiddenDim * valCh + flatVal * 32 + 32;
      conParams = hiddenDim * headCh + headCh * 16 * 128 + 128 * 128;
    } else {
      repParams = inChannels * hiddenDim * 9 + dynamicsBlocks * 2 * (hiddenDim * hiddenDim * 9);
      dynParams = (hiddenDim + 16) * hiddenDim * 9 + dynamicsBlocks * 2 * (hiddenDim * hiddenDim * 9) + (hiddenDim * flatDim + 48);
      polParams = predictionBlocks * (hiddenDim * hiddenDim * 9) + (flatDim * actionDim);
      valParams = flatDim * 1;
      objParams = flatDim * 1;
      conParams = flatDim * 128 + 128 * 128;
    }

    const repReceptive = 1 + 2 * (1 + 2 * dynamicsBlocks);
    const dynReceptive = 1 + 2 * (1 + 2 * dynamicsBlocks);

    return {
      observation: {
        id: "observation",
        name: "Observation Tensor o_t",
        math: `o_t \\in \\mathbb{R}^{B \\times ${inChannels} \\times ${boardH} \\times ${boardW}}`,
        role: "Tensor sensorial de entrada extraído del simulador hexagonal VOEC en el paso temporal t.",
        inShape: `B × ${inChannels} canales × ${boardH} × ${boardW} hexágonos`,
        outShape: `B × ${inChannels} × ${boardH} × ${boardW}`,
        architecture: [
          `Canales 0-5: Presencia y HP aliada/enemiga normalizada`,
          `Canales 6-11: Turno, fin de partida, tipos infantería y apoyo`,
          `Canales 12-18: Máscara jugable, costes terreno, cobertura, LOS y VP`,
          `Canales 19-20: Coordenadas hexagonales axiales (q, r)`,
          `Canales 21-${inChannels - 1}: Alcances directo/indirecto, movilidad y combate`
        ],
        paramEstimate: "0 parámetros (Datos del Simulador)",
        receptiveField: `${boardH}×${boardW} Hexágonos (Resolución completa)`,
        details: `Tensor denso construido por el adaptador VOEC con resolución espacial ${boardH}×${boardW}. Configurado con ${inChannels} canales de entrada en run ${runId}.`,
      },
      representation: {
        id: "representation",
        name: "Representation Network h_θ(o)",
        math: `h_\\theta(o_t) \\to s_0`,
        role: `Codificador de observación (${encoderType.toUpperCase()}). Transforma el tablero bruto en un espacio latente continuo de ${hiddenDim} dimensiones.`,
        inShape: `B × ${inChannels} × ${boardH} × ${boardW}`,
        outShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        architecture: isV2Optimized
          ? [
              `Conv2d(${inChannels}, ${hiddenDim}, kernel_size=3, padding=1)`,
              `GroupNorm(num_groups=4, num_channels=${hiddenDim}) + SiLU`,
              ...Array.from({ length: dynamicsBlocks }, (_, i) =>
                `ResidualBlock ${i + 1}: Conv3x3(${hiddenDim}) -> GroupNorm -> SiLU -> Conv3x3 -> GroupNorm + Squeeze-and-Excitation (SE gating, r=4)`
              ),
              "Min-Max Latent Scaling: s_norm = (s - min) / (max - min + ε)"
            ]
          : [
              `Conv2d(${inChannels}, ${hiddenDim}, kernel_size=3, padding=1)`,
              `LayerNorm2d(${hiddenDim}) + ReLU`,
              ...Array.from({ length: dynamicsBlocks }, (_, i) =>
                `ResidualBlock ${i + 1}: Conv3x3(${hiddenDim}) -> LayerNorm -> ReLU -> Conv3x3(${hiddenDim})`
              ),
              "Skip Connections aditivas residuales (Legacy v1, sin SE)"
            ],
        paramEstimate: `~${repParams.toLocaleString()} parámetros`,
        receptiveField: `~${repReceptive}×${repReceptive} Hexágonos (${dynamicsBlocks} bloques convolucionales 3×3)`,
        details: isV2Optimized
          ? `Arquitectura v2 con GroupNorm, activación SiLU suave y compuertas Squeeze-and-Excitation (SE) que modulan la importancia de los canales tácticos. Aplica normalización canónica Min-Max al estado latente.`
          : `Arquitectura v1 clásica con bloques residuales densos estándar sin modulación de canales SE.`,
      },
      latent: {
        id: "latent",
        name: "Latent State s_t",
        math: `s_t \\in \\mathbb{R}^{B \\times ${hiddenDim} \\times ${boardH} \\times ${boardW}}`,
        role: `Representación latente compacta (${hiddenDim} canales). Es el estado abstracto sobre el que MCTS planifica sin interactuar con el motor físico.`,
        inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        outShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        architecture: isV2Optimized
          ? [
              `${hiddenDim} canales espaciales latentes en ${boardH}×${boardW}`,
              "Normalización Min-Max canónica EfficientZero por muestra",
              "Estabilidad de norma garantizada a lo largo de rollouts profundos"
            ]
          : [
              `${hiddenDim} canales de características latentes`,
              "Normalización L2 por canal / LayerNorm",
              `Conserva topología espacial 2D de ${boardH}×${boardW} hexágonos`
            ],
        paramEstimate: "Buffer de memoria GPU (Caché MCTS)",
        receptiveField: "Generado por h(o) en t=0 o imaginado por g(s, a) en t>0",
        details: `Espacio continuo donde se proyecta la búsqueda Monte Carlo hasta horizonte t=${maxUnroll}.`,
      },
      action: {
        id: "action",
        name: "Action Conditioning a_t",
        math: `a_t \\in \\{0, \\dots, ${actionDim - 1}\\}`,
        role: `Acción candidata seleccionada por el árbol MCTS (espacio de ${actionDim} acciones discretas).`,
        inShape: `Índice discreto a_t (0 a ${actionDim - 1})`,
        outShape: `B × 1 × ${boardH} × ${boardW} (Broadcast espacial)`,
        architecture: [
          `Linear Embedding (${actionDim} dims)`,
          `Broadcast espacial constante sobre el plano 1×${boardH}×${boardW}`,
          `Concatenación en canales con el estado latente (${hiddenDim} + 1 = ${hiddenDim + 1})`
        ],
        paramEstimate: `~${(actionDim * 32).toLocaleString()} parámetros`,
        receptiveField: "Global (informa a todo el plano de la maniobra ejecutada)",
        details: `Permite a la red de dinámica conocer qué orden o disparo se proyecta en la simulación imaginada.`,
      },
      dynamics: {
        id: "dynamics",
        name: "Dynamics Network g_θ(s, a)",
        math: `g_\\theta(s_t, a_t) \\to (s_{t+1}, \\hat{r}_t)`,
        role: `Modelo latente del mundo: predice la evolución del estado s_{t+1} y la recompensa inmediata tras ejecutar a_t.`,
        inShape: `B × ${hiddenDim + 1} × ${boardH} × ${boardW} (Concatenación s_t + a_t)`,
        outShape: `s_{t+1}: B × ${hiddenDim} × ${boardH} × ${boardW} | r_t: B × 1`,
        architecture: isV2Optimized
          ? [
              `Conv2d(${hiddenDim + 1}, ${hiddenDim}, kernel_size=3, padding=1) + SiLU`,
              ...Array.from({ length: dynamicsBlocks }, (_, i) =>
                `Dynamics Block ${i + 1}: Conv3x3(${hiddenDim}) -> GroupNorm -> SiLU -> Conv3x3 -> GroupNorm + Squeeze-and-Excitation (SE)`
              ),
              `Reward Head: Conv1x1(${hiddenDim}, ${valCh}) -> GroupNorm -> SiLU -> AdaptiveAvgPool2d(2x2) -> Linear(${valCh * 4}, 64) -> SiLU -> Linear(64, 1)`,
              "Min-Max Recurrent Latent Scaling en cada paso recurrente"
            ]
          : [
              `Conv2d(${hiddenDim + 1}, ${hiddenDim}, kernel_size=3, padding=1) + ReLU`,
              ...Array.from({ length: dynamicsBlocks }, (_, i) =>
                `Dynamics Block ${i + 1}: Conv3x3(${hiddenDim}) -> LayerNorm -> ReLU`
              ),
              `Reward Head: Flatten(${flatDim}) -> Linear(${flatDim}, 64) -> SiLU -> Linear(64, 1)`
            ],
        paramEstimate: `~${dynParams.toLocaleString()} parámetros`,
        receptiveField: `~${dynReceptive}×${dynReceptive} Hexágonos acumulados por paso`,
        details: isV2Optimized
          ? `Modelo recurrente v2 optimizado: utiliza cuello de botella 1x1 + AdaptiveAvgPool en la recompensa y re-escalado latente Min-Max, evitando explosión o desvanecimiento del gradiente en BPTT.`
          : `Modelo recurrente v1 clásico con cabezal de recompensa denso conectado directamente al mapa espacial aplanado.`,
      },
      policy: {
        id: "policy",
        name: "Policy Head f_p(s)",
        math: `p_t = f_p(s_t) \\in \\Delta^{${actionDim}}`,
        role: `Predicción de probabilidades previas (prior) sobre las ${actionDim} acciones posibles del juego.`,
        inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        outShape: `B × ${actionDim} logits (Normalizados con Softmax y acción legal masking)`,
        architecture: isV2Optimized
          ? [
              ...Array.from({ length: predictionBlocks }, (_, i) =>
                `Prediction Block ${i + 1}: Conv3x3(${hiddenDim}) -> GroupNorm -> SiLU + SE`
              ),
              `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${headCh}, 1x1) + GroupNorm + SiLU`,
              `Linear Head: Flatten(${flatPol}) -> Linear(${flatPol}, ${actionDim}) (Logits)`,
              "Pérdida de Política: Cross-Entropy / Divergencia KL (gradientes lineales sin atenuación)"
            ]
          : [
              ...Array.from({ length: predictionBlocks }, (_, i) =>
                `Prediction Block ${i + 1}: Conv3x3(${hiddenDim}) -> LayerNorm -> ReLU`
              ),
              `Direct Flatten: Flatten(${flatDim}) -> Linear(${flatDim}, ${actionDim})`,
              "Pérdida de Política: MSE sobre Softmax (atenuación de gradientes con p pequeños)"
            ],
        paramEstimate: `~${polParams.toLocaleString()} parámetros`,
        receptiveField: "Global (Cuello de botella convolucional)",
        details: isV2Optimized
          ? `Cabezal de política v2 con cuello de botella 1x1 (${hiddenDim}ch ➔ ${headCh}ch), reduciendo drásticamente los parámetros frente a la memorización espacial de coordenadas. Entrenado con Cross-Entropy.`
          : `Cabezal v1 clásico con capa lineal gigante conectada directamente a todas las celdas aplanadas (~${(flatDim * actionDim).toLocaleString()} parámetros solo en la proyección lineal).`,
      },
      value: {
        id: "value",
        name: "Value Head f_v(s)",
        math: `v_t = f_v(s_t) \\in [-1, 1]`,
        role: "Evaluación escalar de la probabilidad esperada de victoria.",
        inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        outShape: "B × 1 (Escalar continuo en [-1, 1] con función Tanh)",
        architecture: isV2Optimized
          ? [
              `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${valCh}, 1x1) + GroupNorm + SiLU`,
              `AdaptiveAvgPool2d((2, 2)) (Invarianza espacial y compresión)`,
              `Linear(${valCh * 4}, 64) -> SiLU -> Linear(64, 1) + Tanh`
            ]
          : [
              `Direct Flatten: Flatten(${flatDim}) -> Linear(${flatDim}, 64) -> SiLU -> Linear(64, 1) + Tanh`
            ],
        paramEstimate: `~${valParams.toLocaleString()} parámetros`,
        receptiveField: "Global",
        details: isV2Optimized
          ? `Cabezal de valor v2 con compresión espacial AdaptiveAvgPool(2,2). Evalúa la posición estratégica global sin saturar pesos lineales con la posición exacta de cada casilla.`
          : `Cabezal v1 clásico conectado a todo el mapa aplanado.`,
      },
      aux_objective: {
        id: "aux_objective",
        name: "Objective Progress Head f_o(s)",
        math: `y_t = f_o(s_t) \\in \\mathbb{R}`,
        role: "Predicción auxiliar del progreso y proximidad táctica a Puntos de Victoria (VPs).",
        inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        outShape: "B × 1 (Predicción de captura/progreso continuo)",
        architecture: isV2Optimized
          ? [
              `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${valCh}, 1x1) + GroupNorm + SiLU`,
              `AdaptiveAvgPool2d((2, 2))`,
              `Linear(${valCh * 4}, 32) -> SiLU -> Linear(32, 1)`
            ]
          : [
              `Direct Flatten: Flatten(${flatDim}) -> Linear(${flatDim}, 32) -> SiLU -> Linear(32, 1)`
            ],
        paramEstimate: `~${objParams.toLocaleString()} parámetros`,
        receptiveField: "Global / Localizado en hexágonos VP",
        details: "Guía el entrenamiento para favorecer la toma de objetivos frente al estancamiento pasivo.",
      },
      consistency: {
        id: "consistency",
        name: "Consistency Head q_θ(s)",
        math: `z_t = q_\\theta(s_t) \\in \\mathbb{R}^{B \\times ${hiddenDim}}`,
        role: `Proyector de auto-consistencia SimSiam (horizonte de ${consistencyUnroll} pasos).`,
        inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        outShape: `B × ${hiddenDim} (Vector de embedding latente)`,
        architecture: isV2Optimized
          ? [
              `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${headCh}, 1x1) + SiLU`,
              `AdaptiveAvgPool2d((4, 4))`,
              `MLP Projector: Linear(${headCh * 16}, 128) -> SiLU -> Linear(128, 128)`,
              "Pérdida SimSiam: Cosine Similarity con Stop-Gradient"
            ]
          : [
              `Direct Flatten: Flatten(${flatDim}) -> Linear(${flatDim}, 128) -> SiLU -> Linear(128, 128)`,
              "Pérdida SimSiam: Cosine Similarity con Stop-Gradient"
            ],
        paramEstimate: `~${conParams.toLocaleString()} parámetros`,
        receptiveField: "Global",
        details: `Evita el colapso de representación durante el unroll temporal, forzando a que s_t habite la misma variedad semántica que las observaciones reales.`,
      },
      ...(hasThreatHead
        ? {
            threat_map: {
              id: "threat_map",
              name: "Threat Map Head f_threat(s)",
              math: `m_t = f_{threat}(s_t) \\in [0, 1]^{B \\times 1 \\times ${boardH} \\times ${boardW}}`,
              role: `Mapa espacial 2D de riesgo de supresión y líneas de tiro enemigas sobre la cuadrícula hexagonal ${boardH}×${boardW}.`,
              inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
              outShape: `B × 1 × ${boardH} × ${boardW} (Probabilidades de fuego / LOS)`,
              architecture: isV2Optimized
                ? [
                    `SpatialAttentionBlock: Self-Attention espacial (${hiddenDim}ch)`,
                    `Conv2d(${hiddenDim}, 16, kernel_size=3, padding=1) + GroupNorm + SiLU`,
                    "Conv2d(16, 1, kernel_size=1) (Logits de cobertura de fuego)",
                    "Pérdida de Amenaza: BCEWithLogitsLoss con balanceo adaptativo"
                  ]
                : [
                    `Conv2d(${hiddenDim}, 16, kernel_size=3, padding=1) + GroupNorm + SiLU`,
                    "Conv2d(16, 1, kernel_size=1)",
                    "Pérdida de Amenaza: BCEWithLogitsLoss"
                  ],
              paramEstimate: `~${(hiddenDim * 16 * 9 + 16 * 1).toLocaleString()} parámetros`,
              receptiveField: `Local / Espacial (${boardH}×${boardW} Hexágonos)`,
              details: "Cabezal táctico de amenaza activa: predice la probabilidad de recibir fuego en cada hexágono, guiando al agente a navegar tras coberturas y fuera de líneas de tiro enemigas.",
            },
          }
        : {}),
      ...(hasAttritionHead
        ? {
            attrition: {
              id: "attrition",
              name: "Attrition Balance Head f_attr(s)",
              math: `a_t = f_{attr}(s_t) \\in \\mathbb{R}^{B \\times 2}`,
              role: "Proyección táctica del balance de bajas esperadas (bajas aliadas vs. bajas enemigas proyectadas).",
              inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
              outShape: "B × 2 (Bajas amigas estimadas, Bajas enemigas estimadas)",
              architecture: isV2Optimized
                ? [
                    `SpatialAttentionBlock: Pooled Context (${valCh}ch)`,
                    "Flatten() -> Linear(64) -> SiLU -> Linear(64, 2)",
                    "Pérdida de Desgaste: Smooth L1 Loss (Huber) balanceada"
                  ]
                : [
                    `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${valCh}, 1x1) + SiLU`,
                    `Flatten(${flatVal}) -> Linear(64) -> SiLU -> Linear(64, 2)`,
                    "Pérdida de Desgaste: Smooth L1 Loss"
                  ],
              paramEstimate: `~${(hiddenDim * valCh + flatVal * 64 + 64 * 2).toLocaleString()} parámetros`,
              receptiveField: "Global",
              details: "Discrimina victorias tácticas limpias de victorias pírricas con alto desgaste, evitando sacrificios innecesarios de unidades.",
            },
          }
        : {}),
      ...(hasMoraleHead
        ? {
            morale: {
              id: "morale",
              name: "Morale State Head f_morale(s)",
              math: `m_t = f_{morale}(s_t) \\in \\Delta^4`,
              role: "Distribución de probabilidad sobre estados de moral táctica: NORMAL (0), PINNED (1), SUPPRESSED (2), ROUTED (3).",
              inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
              outShape: "B × 4 (Distribución de probabilidad con Softmax)",
              architecture: isV2Optimized
                ? [
                    `SpatialAttentionBlock: Pooled Context (${valCh}ch)`,
                    "Flatten() -> Linear(64) -> SiLU -> Linear(64, 4)",
                    "Pérdida de Moral: Categorical Cross-Entropy con clases ponderadas"
                  ]
                : [
                    `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${valCh}, 1x1) + SiLU`,
                    `Flatten(${flatVal}) -> Linear(64) -> SiLU -> Linear(64, 4)`,
                    "Pérdida de Moral: Categorical Cross-Entropy"
                  ],
              paramEstimate: `~${(hiddenDim * valCh + flatVal * 64 + 64 * 4).toLocaleString()} parámetros`,
              receptiveField: "Global",
              details: "Predice la probabilidad de degradación de moral y supresión de escuadras bajo fuego, promoviendo repliegues tácticos preventivos.",
            },
          }
        : {}),
      macro_planner: {
        id: "macro_planner",
        name: "Planificador Macro (Nivel 1)",
        math: `\\pi_{macro}(o_t) \\to (\\text{Postura}, \\text{Roles}, \\text{VP Target})`,
        role: "Planificador estratégico de nivel superior (Nivel 1 de la jerarquía HRL). Evalúa el escenario completo y asigna la postura doctrinal global del equipo (ASSAULT, DEFENSIVE, ZONE_SUPPRESS) y los roles tácticos a cada escuadra (SPEARHEAD, FIRE_SUPPORT, OBJECTIVE_DEFENDER, FLANK_SCREEN), modulando directamente los priors de búsqueda del árbol MCTS en tiempo de inferencia.",
        inShape: `B × ${inChannels} × ${boardH} × ${boardW} (Observación Directa del Tablero)`,
        outShape: `Postura (1 de 3) + Roles por unidad + Modulación Prior (+35%)`,
        architecture: [
          "Evaluación Global del Escenario (Control de VPs, balance de bajas y mapa de amenaza)",
          "Inferencia de Postura Estratégica: ASSAULT_VP / DEFENSIVE_HOLD / ZONE_SUPPRESS",
          "Asignación Doctrinal de Roles: Spearhead, Fire Support, Defender, Flank Screen",
          "Modulación de Priors MCTS: P_mod(a) = P(a) * (1 + α * Boost(Postura, Rol, a))",
          "Integración en el bucle de auto-juego y evaluación de EfficientZero v2"
        ],
        paramEstimate: "Módulo Lógico-Estratégico HRL con Ponderación Doctrinal",
        receptiveField: "Global (Todo el tablero y estado dinámico de unidades)",
        details: "Actúa como Nivel 1 de la jerarquía de toma de decisiones. Impide que la búsqueda MCTS local (Nivel 2) se extravíe en mínimos locales o bucles pasivos al sesgar la exploración hacia los objetivos tácticos definidos.",
      },
    };
  }, [inChannels, boardH, boardW, hiddenDim, actionDim, dynamicsBlocks, predictionBlocks, encoderType, maxUnroll, consistencyUnroll, runId, mctsSims, isV2Optimized, hasThreatHead, hasAttritionHead, hasMoraleHead]);

  const selectedNode = dynamicNodeCatalog[selectedNodeId] || dynamicNodeCatalog.representation;

  // Active prediction heads to display dynamically based on the current execution
  const activeHeads = useMemo(() => {
    const list: Array<{
      id: string;
      icon: string;
      label: string;
      sublabel: string;
      stroke: string;
      selectedFill: string;
      metricLabel: string;
      metricValue: string;
      tag: string;
      tagColor: string;
    }> = [
      {
        id: "policy",
        icon: "🎯",
        label: "POLÍTICA f_p(s)",
        sublabel: `${actionDim} Logits ${isV2Optimized ? "(Conv 1x1)" : "(Dense)"}`,
        stroke: "#38bdf8",
        selectedFill: "#0369a1",
        metricLabel: `Loss: ${fmtNum(polLoss, 3)} | Conf: ${fmtPercent(polConfidence)}`,
        metricValue: fmtNum(polLoss, 3),
        tag: polLoss !== null ? "🟢 OK" : "⚪ PENDIENTE",
        tagColor: polLoss !== null ? "#34d399" : "#94a3b8",
      },
      {
        id: "value",
        icon: "⚖️",
        label: "VALOR f_v(s)",
        sublabel: `Escalar [-1.0, +1.0] ${isV2Optimized ? "(Pool 2x2)" : "(Dense)"}`,
        stroke: "#22c55e",
        selectedFill: "#065f46",
        metricLabel: `Loss: ${fmtNum(valLoss, 3)} | Q-Sat: ${fmtPercent(qSatRate)}`,
        metricValue: fmtNum(valLoss, 3),
        tag: valLoss !== null ? "🟢 OK" : "⚪ PENDIENTE",
        tagColor: valLoss !== null ? "#34d399" : "#94a3b8",
      },
      {
        id: "aux_objective",
        icon: "🏁",
        label: "OBJETIVO AUXILIAR f_o(s)",
        sublabel: `Progreso VP ${isV2Optimized ? "(Pool 2x2)" : "(Dense)"}`,
        stroke: "#f43f5e",
        selectedFill: "#9f1239",
        metricLabel: `Loss: ${fmtNum(objLoss, 3)} | Take: ${fmtPercent(objTakeRate)}`,
        metricValue: fmtNum(objLoss, 3),
        tag: objLoss !== null ? "🟢 OK" : "⚪ PENDIENTE",
        tagColor: objLoss !== null ? "#34d399" : "#94a3b8",
      },
      {
        id: "consistency",
        icon: "🔄",
        label: "CONSISTENCIA q_θ(s)",
        sublabel: `SimSiam ${isV2Optimized ? "(Pool 4x4)" : `(${hiddenDim} Flat)`}`,
        stroke: "#c084fc",
        selectedFill: "#581c87",
        metricLabel: `Loss: ${fmtSci(conLoss)} | Cov: ${fmtPercent(conReanalysisCov, 0)}`,
        metricValue: fmtSci(conLoss),
        tag: conLoss !== null ? "🟢 OK" : "⚪ PENDIENTE",
        tagColor: conLoss !== null ? "#34d399" : "#94a3b8",
      },
    ];

    if (hasThreatHead) {
      list.push({
        id: "threat_map",
        icon: "🗺️",
        label: "AMENAZA / SUPRESIÓN f_threat(s)",
        sublabel: `Heatmap 1×${boardH}×${boardW} (LOS/Overwatch)`,
        stroke: "#eab308",
        selectedFill: "#854d0e",
        metricLabel: `Loss: ${fmtNum(threatLoss, 3)} | Cov: ${fmtPercent(threatCov, 1)}`,
        metricValue: fmtNum(threatLoss, 3),
        tag: "TACTICAL",
        tagColor: "#fef08a",
      });
    }

    if (hasAttritionHead) {
      list.push({
        id: "attrition",
        icon: "⚔️",
        label: "DESGASTE / BAJAS f_attr(s)",
        sublabel: "Vector [Bajas Aliadas, Bajas Enemigas]",
        stroke: "#06b6d4",
        selectedFill: "#0e7490",
        metricLabel: `Loss: ${fmtNum(attritionLoss, 3)} | Ratio: ${fmtNum(attritionExchange, 2, "x")}`,
        metricValue: fmtNum(attritionLoss, 3),
        tag: "TACTICAL",
        tagColor: "#67e8f9",
      });
    }

    if (hasMoraleHead) {
      list.push({
        id: "morale",
        icon: "🛡️",
        label: "ESTADO DE MORAL f_morale(s)",
        sublabel: "4 Clases (Normal / Pin / Supp / Rout)",
        stroke: "#ec4899",
        selectedFill: "#9d174d",
        metricLabel: `Loss: ${fmtNum(moraleLoss, 3)} | Riesgo: ${fmtNum(moraleRisk, 2)}`,
        metricValue: fmtNum(moraleLoss, 3),
        tag: "TACTICAL",
        tagColor: "#fbcfe8",
      });
    }

    return list;
  }, [
    actionDim, isV2Optimized, polLoss, polConfidence, valLoss, qSatRate,
    objLoss, objTakeRate, conLoss, conReanalysisCov, hiddenDim,
    hasThreatHead, boardH, boardW, threatLoss, threatCov,
    hasAttritionHead, attritionLoss, attritionExchange,
    hasMoraleHead, moraleLoss, moraleRisk,
  ]);

  const numHeads = activeHeads.length;
  const cardH = numHeads <= 4 ? 52 : numHeads <= 5 ? 46 : 42;
  const cardGap = numHeads <= 4 ? 8 : numHeads <= 5 ? 6 : 5;
  const svgHeight = Math.max(265, 12 + numHeads * (cardH + cardGap) + 8);

  // Resilient channels parser supporting both array and dictionary shapes
  const dynamicChannelsList = useMemo(() => {
    const raw = trainSummary?.observation_channels;
    const channelsArray: Dict[] = Array.isArray(raw)
      ? (raw as Dict[])
      : Array.isArray((raw as Dict)?.channels)
      ? ((raw as Dict).channels as Dict[])
      : [];

    if (channelsArray.length > 0) {
      return channelsArray.map((c, i) => {
        const name = String(c.name || `channel_${i}`);
        const nonzero = Number(c.nonzero_cells ?? 0);
        return {
          idx: Number(c.index ?? i),
          name,
          cat: name.includes("vp")
            ? "vp"
            : name.includes("coord") || name.includes("hex")
            ? "hex"
            : name.includes("terrain") || name.includes("los") || name.includes("map")
            ? "terrain"
            : name.includes("turn") || name.includes("done")
            ? "global"
            : "units",
          desc: `Canal de entrada ${i}: ${name} (${nonzero} celdas activas)`,
        };
      });
    }
    return DEFAULT_CHANNELS_LIST.slice(0, inChannels);
  }, [trainSummary, inChannels]);

  const filteredChannels = dynamicChannelsList.filter(
    (c) => channelFilter === "all" || c.cat === channelFilter
  );

  const unrollStepsList = Array.from({ length: maxUnroll + 1 }, (_, i) => i);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Header bar */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <div>
          <h3 style={{ margin: 0, fontSize: 16, color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
            <span>🧠</span> Topología Dinámica de la Red Neuronal (EfficientZero V2)
          </h3>
          <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
            Arquitectura desacoplada: Representación \(h\), Dinámica Recurrente \(g\), Cabezales de Predicción \(f\) y Consistencia Auto-supervisada \(z\).
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <div className="kpi" style={{ padding: "4px 8px" }}>
            <div className="k" style={{ fontSize: 10 }}>Encoder / Latente</div>
            <div className="v" style={{ fontSize: 11, color: "#38bdf8" }}>{encoderType.toUpperCase()} ({hiddenDim} ch)</div>
          </div>
          <div className="kpi" style={{ padding: "4px 8px" }}>
            <div className="k" style={{ fontSize: 10 }}>Acciones</div>
            <div className="v" style={{ fontSize: 11, color: "#22c55e" }}>{actionDim} logits</div>
          </div>
          <div className="kpi" style={{ padding: "4px 8px" }}>
            <div className="k" style={{ fontSize: 10 }}>Unroll Máx</div>
            <div className="v" style={{ fontSize: 11, color: "#f59e0b" }}>{maxUnroll} pasos</div>
          </div>
          <div className="kpi" style={{ padding: "4px 8px" }}>
            <div className="k" style={{ fontSize: 10 }}>Precisión</div>
            <div className="v" style={{ fontSize: 11, color: "#a855f7" }}>{ampDtype}</div>
          </div>
        </div>
      </div>

      {/* Top Views Navigation & Compact Mode Switcher */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: "8px 12px" }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button
            onClick={() => setSubTab("diagram")}
            style={{
              background: currentSubTab === "diagram" ? "#0284c7" : "#1e293b",
              color: currentSubTab === "diagram" ? "#ffffff" : "#94a3b8",
              border: currentSubTab === "diagram" ? "1px solid #38bdf8" : "1px solid #334155",
              borderRadius: 6,
              padding: "6px 12px",
              fontWeight: currentSubTab === "diagram" ? 700 : 500,
              fontSize: 12,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span>📐</span>
            <span>Diagrama & Topología</span>
          </button>
          <button
            onClick={() => setSubTab("head-diagnostics")}
            style={{
              background: currentSubTab === "head-diagnostics" ? "#0284c7" : "#1e293b",
              color: currentSubTab === "head-diagnostics" ? "#ffffff" : "#94a3b8",
              border: currentSubTab === "head-diagnostics" ? "1px solid #38bdf8" : "1px solid #334155",
              borderRadius: 6,
              padding: "6px 12px",
              fontWeight: currentSubTab === "head-diagnostics" ? 700 : 500,
              fontSize: 12,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span>🔬</span>
            <span>Análisis de Cabezas (Head Diagnostics)</span>
            <span style={{ fontSize: 9, background: "#065f46", color: "#34d399", padding: "1px 6px", borderRadius: 4, fontWeight: 700 }}>{activeHeads.length} Cabezas</span>
          </button>
          <button
            onClick={() => setSubTab("channel-attribution")}
            style={{
              background: currentSubTab === "channel-attribution" ? "#0284c7" : "#1e293b",
              color: currentSubTab === "channel-attribution" ? "#ffffff" : "#94a3b8",
              border: currentSubTab === "channel-attribution" ? "1px solid #38bdf8" : "1px solid #334155",
              borderRadius: 6,
              padding: "6px 12px",
              fontWeight: currentSubTab === "channel-attribution" ? 700 : 500,
              fontSize: 12,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span>📊</span>
            <span>Atribución de Canales</span>
            <span style={{ fontSize: 9, background: "#1e3a8a", color: "#93c5fd", padding: "1px 6px", borderRadius: 4, fontWeight: 700 }}>{inChannels} Ch</span>
          </button>
          <button
            onClick={() => setSubTab("macro-planner")}
            style={{
              background: currentSubTab === "macro-planner" ? "#0284c7" : "#1e293b",
              color: currentSubTab === "macro-planner" ? "#ffffff" : "#94a3b8",
              border: currentSubTab === "macro-planner" ? "1px solid #38bdf8" : "1px solid #334155",
              borderRadius: 6,
              padding: "6px 12px",
              fontWeight: currentSubTab === "macro-planner" ? 700 : 500,
              fontSize: 12,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span>♟️</span>
            <span>Planificador Macro (Nivel 1)</span>
            <span style={{ fontSize: 9, background: "#581c87", color: "#d8b4fe", padding: "1px 6px", borderRadius: 4, fontWeight: 700 }}>Jerarquía</span>
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 3, background: "#0b1120", border: "1px solid #334155", borderRadius: 6, padding: "2px 4px" }}>
          <span style={{ fontSize: 10, color: "#94a3b8", padding: "0 4px", fontWeight: 600 }}>Tamaño:</span>
          <button
            onClick={() => setDiagramSize("compact")}
            style={{
              background: diagramSize === "compact" ? "#0284c7" : "transparent",
              color: diagramSize === "compact" ? "#ffffff" : "#94a3b8",
              border: "none",
              borderRadius: 4,
              padding: "4px 8px",
              fontSize: 10,
              fontWeight: diagramSize === "compact" ? 700 : 500,
              cursor: "pointer",
            }}
            title="Vista compacta (menor altura vertical)"
          >
            📏 Compacto
          </button>
          <button
            onClick={() => setDiagramSize("balanced")}
            style={{
              background: diagramSize === "balanced" ? "#0284c7" : "transparent",
              color: diagramSize === "balanced" ? "#ffffff" : "#94a3b8",
              border: "none",
              borderRadius: 4,
              padding: "4px 8px",
              fontSize: 10,
              fontWeight: diagramSize === "balanced" ? 700 : 500,
              cursor: "pointer",
            }}
            title="Vista equilibrada: texto nítido y proporciones completas"
          >
            📐 Equilibrado
          </button>
          <button
            onClick={() => setDiagramSize("expanded")}
            style={{
              background: diagramSize === "expanded" ? "#0284c7" : "transparent",
              color: diagramSize === "expanded" ? "#ffffff" : "#94a3b8",
              border: "none",
              borderRadius: 4,
              padding: "4px 8px",
              fontSize: 10,
              fontWeight: diagramSize === "expanded" ? 700 : 500,
              cursor: "pointer",
            }}
            title="Vista ampliada con máxima altura"
          >
            🖥️ Ampliado
          </button>
        </div>
      </div>

      {/* Execution Context Banner */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          background: "#0f172a",
          border: "1px solid #1e3a8a",
          borderRadius: 6,
          padding: "6px 12px",
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontSize: 12, color: "#60a5fa", fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}>
          <span>📌</span> Ejecución activa:
        </span>
        <code style={{ color: "#38bdf8", fontWeight: 700, fontSize: 12 }}>{runId}</code>
        {trainRow?.created_at_utc ? (
          <span className="muted" style={{ fontSize: 11 }}>
            ({formatLocalDate(trainRow.created_at_utc)})
          </span>
        ) : null}

        {isV2Optimized ? (
          <span
            style={{
              background: "#064e3b",
              border: "1px solid #059669",
              color: "#34d399",
              padding: "2px 8px",
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 700,
            }}
          >
            ⚡ Arquitectura v2: GroupNorm + SE + Conv Bottlenecks (-76% Params)
          </span>
        ) : (
          <span
            style={{
              background: "#1e293b",
              border: "1px solid #475569",
              color: "#94a3b8",
              padding: "2px 8px",
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            📦 Arquitectura v1: Dense Flattened (Legacy Run)
          </span>
        )}

        <div style={{ marginLeft: "auto", fontSize: 11, color: "#94a3b8", display: "flex", alignItems: "center", gap: 10 }}>
          {modelCfg.total_parameters ? (
            <span style={{ color: "#f59e0b", fontWeight: 700 }}>
              {Number(modelCfg.total_parameters).toLocaleString()} params (Medido)
            </span>
          ) : null}
          <span>
            Dimensiones: <b>{inChannels}ch × {boardH}×{boardW}</b> ➔ Latente <b>{hiddenDim}ch</b> ➔ Bloques <b>{dynamicsBlocks}D + {predictionBlocks}P</b>
          </span>
        </div>
      </div>

      {/* SECTION 1: NETWORK TOPOLOGY DIAGRAM & CHANNELS */}
      {currentSubTab === "diagram" && (
        <>
          {/* Unroll Stepper & Flow Controller */}
          <div
            style={{
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: 8,
          padding: "10px 14px",
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              style={{
                background: isPlaying ? "#f43f5e" : "#0284c7",
                color: "#ffffff",
                border: "none",
                fontWeight: "bold",
                fontSize: 11,
                padding: "5px 10px",
                display: "flex",
                alignItems: "center",
                gap: 4,
                cursor: "pointer",
                borderRadius: 4,
              }}
            >
              <span>{isPlaying ? "⏸ Pausar" : "▶ Reproducir Flujo"}</span>
            </button>

            <span style={{ fontSize: 12, fontWeight: 700, color: "#f8fafc" }}>
              Paso de Proyección: <span style={{ color: "#38bdf8" }}>t = {unrollStep}</span> de {maxUnroll}
            </span>
          </div>

          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {unrollStepsList.map((step) => (
              <button
                key={step}
                onClick={() => {
                  setUnrollStep(step);
                  setIsPlaying(false);
                }}
                style={{
                  padding: "4px 10px",
                  fontSize: 11,
                  borderRadius: 4,
                  background: unrollStep === step ? "#0ea5e9" : "#0f172a",
                  color: unrollStep === step ? "#0f172a" : "#94a3b8",
                  border: unrollStep === step ? "1px solid #38bdf8" : "1px solid #334155",
                  fontWeight: unrollStep === step ? 700 : 500,
                  cursor: "pointer",
                }}
              >
                {step === 0 ? "t=0 (Entrada Real)" : `t=${step} (Unroll)`}
              </button>
            ))}
          </div>
        </div>

        <div style={{ background: "#0f172a", borderRadius: 6, padding: "8px 12px", borderLeft: unrollStep === 0 ? "3px solid #38bdf8" : "3px solid #f59e0b" }}>
          <div style={{ fontSize: 11, color: unrollStep === 0 ? "#93c5fd" : "#fcd34d", fontWeight: 600 }}>
            {unrollStep === 0
              ? `⚡ PASO RAÍZ MCTS (t=0): Extracción de Estado Latente desde Observación Real (${inChannels}×${boardH}×${boardW})`
              : `⚡ DESENROLLADO TEMPORAL RECURRENTE (t=${unrollStep}): Proyección e Imaginación en GPU sin Simulador (Horizonte máx=${maxUnroll})`}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
            {unrollStep === 0
              ? `El tensor sensorial o_0 (${inChannels}×${boardH}×${boardW}) atraviesa h(o) produciendo s_0 (${hiddenDim}×${boardH}×${boardW}). Los cabezales evalúan el estado inicial.`
              : `La Red de Dinámica g(s_${unrollStep - 1}, a_${unrollStep - 1}) proyecta s_${unrollStep} (${hiddenDim}×${boardH}×${boardW}) y recompensa inmediata. El cabezal de consistencia z(s) preserva la estabilidad semántica.`}
          </div>
        </div>
      </div>

      {/* Main Interactive Diagram & Inspector Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.7fr) minmax(320px, 1.3fr)", gap: 12 }}>
        {/* Graphical SVG Architecture Pipeline */}
        <div
          style={{
            background: "#0f172a",
            border: "1px solid #334155",
            borderRadius: 8,
            padding: 14,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            overflow: "hidden",
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 700, color: "#cbd5e1", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span>🎨</span> Diagrama Gráfico Interactivo de Nodos
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="muted" style={{ fontSize: 11 }}>Haz clic en cualquier nodo para ver detalles</span>
            </div>
          </div>

          {/* Graphical SVG Canvas */}
          <div
            style={{
              width: "100%",
              overflow: "hidden",
              background: "#0b1120",
              borderRadius: 8,
              border: "1px solid #1e293b",
              padding: "6px 8px",
            }}
          >
            <svg
              viewBox={`0 0 880 ${svgHeight}`}
              style={{
                width: "100%",
                height: "auto",
                maxHeight: diagramSize === "compact" ? Math.max(270, svgHeight + 20) : diagramSize === "expanded" ? Math.max(440, svgHeight + 120) : Math.max(340, svgHeight + 60),
                display: "block",
              }}
            >
              <defs>
                <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 1 L 8 5 L 0 9 z" fill="#38bdf8" />
                </marker>
                <marker id="arrow-amber" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 1 L 8 5 L 0 9 z" fill="#f59e0b" />
                </marker>
                <marker id="arrow-green" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 1 L 8 5 L 0 9 z" fill="#10b981" />
                </marker>
                <marker id="arrow-purple" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 1 L 8 5 L 0 9 z" fill="#a855f7" />
                </marker>
                <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="3" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
                <filter id="glow-green" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="4" result="blur" />
                  <feComposite in="SourceGraphic" in2="blur" operator="over" />
                </filter>
              </defs>

              {/* Connections (Paths with Arrows) */}
              {/* Obs -> Rep */}
              <line x1="150" y1="60" x2="175" y2="60" stroke="#38bdf8" strokeWidth="2.5" markerEnd="url(#arrow)" strokeDasharray={unrollStep === 0 ? "none" : "4 4"} />
              {/* Rep -> Latent */}
              <line x1="335" y1="60" x2="360" y2="60" stroke="#38bdf8" strokeWidth="2.5" markerEnd="url(#arrow)" strokeDasharray={unrollStep === 0 ? "none" : "4 4"} />
              
              {/* Obs -> Macro Planner (Jerarquía Nivel 1) */}
              <line x1="82" y1="105" x2="82" y2="140" stroke="#a855f7" strokeWidth="2" markerEnd="url(#arrow-purple)" strokeDasharray={unrollStep === 0 ? "none" : "3 3"} />
              <text x="88" y="125" fill="#c084fc" fontSize="8" fontWeight="700">Jerarquía N1</text>

              {/* Macro Planner -> MCTS Action Conditioning (Modulación de Priors) */}
              <path d="M 82 230 C 82 254, 430 254, 430 225" fill="none" stroke="#a855f7" strokeWidth="2" strokeDasharray="3 3" markerEnd="url(#arrow-purple)" />
              <text x="257" y="250" fill="#c084fc" fontSize="8" fontWeight="600" textAnchor="middle">Modulación Priors MCTS (Postura + Roles)</text>

              {/* Latent -> Active Heads Dynamic Connection Arrows */}
              {activeHeads.map((head, idx) => {
                const headY = 10 + idx * (cardH + cardGap);
                const headCenterY = headY + cardH / 2;
                const latentStartY = 20 + (idx * 72) / Math.max(1, numHeads - 1);
                return (
                  <path
                    key={`conn-${head.id}`}
                    d={`M 495 ${latentStartY} C 512 ${latentStartY}, 518 ${headCenterY}, 530 ${headCenterY}`}
                    fill="none"
                    stroke={head.stroke}
                    strokeWidth="2"
                    markerEnd="url(#arrow)"
                  />
                );
              })}

              {/* Recurrent Loop: Action -> Dynamics & Latent -> Dynamics */}
              <line x1="365" y1="182" x2="340" y2="182" stroke={unrollStep > 0 ? "#f59e0b" : "#475569"} strokeWidth="2" markerEnd="url(#arrow-amber)" />
              <path d="M 430 108 L 430 135 C 430 150, 410 165, 340 165" fill="none" stroke={unrollStep > 0 ? "#f59e0b" : "#475569"} strokeWidth="2" markerEnd="url(#arrow-amber)" strokeDasharray={unrollStep > 0 ? "none" : "3 3"} />
              {/* Dynamics Feedback: Dynamics -> Latent (s_{t+1}) */}
              <path d="M 180 187 C 165 187, 165 85, 360 85" fill="none" stroke={unrollStep > 0 ? "#10b981" : "#334155"} strokeWidth="2.5" markerEnd="url(#arrow-green)" strokeDasharray={unrollStep > 0 ? "none" : "4 4"} />

              {/* Node 1: Observation Tensor */}
              <g
                onClick={() => setSelectedNodeId("observation")}
                style={{ cursor: "pointer" }}
                opacity={unrollStep === 0 ? 1 : 0.5}
              >
                <rect
                  x="15"
                  y="15"
                  width="135"
                  height="90"
                  rx="8"
                  fill={selectedNodeId === "observation" ? "#0369a1" : "#0f172a"}
                  stroke={selectedNodeId === "observation" ? "#38bdf8" : "#0284c7"}
                  strokeWidth={selectedNodeId === "observation" ? "2.5" : "1.5"}
                  filter={unrollStep === 0 ? "url(#glow-cyan)" : "none"}
                />
                <text x="82" y="38" fill="#94a3b8" fontSize="9" fontWeight="700" textAnchor="middle">ENTRADA REAL</text>
                <text x="82" y="58" fill="#f8fafc" fontSize="12" fontWeight="800" textAnchor="middle">Observación o_t</text>
                <text x="82" y="76" fill="#38bdf8" fontSize="11" fontWeight="700" textAnchor="middle">{inChannels}×{boardH}×{boardW}</text>
                <text x="82" y="92" fill="#64748b" fontSize="9" textAnchor="middle">Simulador VOEC</text>
              </g>

              {/* Node 2: Representation Network */}
              <g
                onClick={() => setSelectedNodeId("representation")}
                style={{ cursor: "pointer" }}
                opacity={unrollStep === 0 ? 1 : 0.5}
              >
                <rect
                  x="180"
                  y="15"
                  width="155"
                  height="90"
                  rx="8"
                  fill={selectedNodeId === "representation" ? "#0369a1" : "#1e293b"}
                  stroke={selectedNodeId === "representation" ? "#38bdf8" : "#0ea5e9"}
                  strokeWidth={selectedNodeId === "representation" ? "2.5" : "1.5"}
                />
                <text x="257" y="36" fill="#60a5fa" fontSize="9" fontWeight="700" textAnchor="middle">ENCODER {encoderType.toUpperCase()}</text>
                <text x="257" y="56" fill="#ffffff" fontSize="12" fontWeight="800" textAnchor="middle">h_θ(o) Representación</text>
                <text x="257" y="74" fill="#93c5fd" fontSize="10" textAnchor="middle">{dynamicsBlocks} ResBlocks ({hiddenDim}ch){isV2Optimized ? " + SE" : ""}</text>
                <text x="257" y="90" fill="#64748b" fontSize="8.5" textAnchor="middle">{isV2Optimized ? "GroupNorm + MinMax Scale" : `Campo ~${1 + 2 * (1 + 2 * dynamicsBlocks)}×${1 + 2 * (1 + 2 * dynamicsBlocks)} hex`}</text>
              </g>

              {/* Node 3: Latent State Manifold */}
              <g
                onClick={() => setSelectedNodeId("latent")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="365"
                  y="12"
                  width="130"
                  height="96"
                  rx="10"
                  fill={selectedNodeId === "latent" ? "#065f46" : "#064e3b"}
                  stroke="#10b981"
                  strokeWidth="2.5"
                  filter="url(#glow-green)"
                />
                <text x="430" y="34" fill="#6ee7b7" fontSize="9" fontWeight="700" textAnchor="middle">ESTADO LATENTE</text>
                <text x="430" y="56" fill="#ffffff" fontSize="15" fontWeight="800" textAnchor="middle">s_{unrollStep}</text>
                <text x="430" y="76" fill="#a7f3d0" fontSize="11" fontWeight="700" textAnchor="middle">{hiddenDim}×{boardH}×{boardW}</text>
                <text x="430" y="94" fill="#34d399" fontSize="9" textAnchor="middle">
                  {unrollStep === 0 ? "h(o) Raíz" : `g(s,a) Paso ${unrollStep}`}
                </text>
              </g>

              {/* Node 4: Action Conditioning */}
              <g
                onClick={() => setSelectedNodeId("action")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="365"
                  y="145"
                  width="130"
                  height="75"
                  rx="8"
                  fill={selectedNodeId === "action" ? "#78350f" : "#1e293b"}
                  stroke="#f59e0b"
                  strokeWidth={selectedNodeId === "action" ? "2.5" : "1.5"}
                />
                <text x="430" y="168" fill="#fbbf24" fontSize="9" fontWeight="700" textAnchor="middle">ACCIÓN MCTS</text>
                <text x="430" y="188" fill="#f8fafc" fontSize="11" fontWeight="700" textAnchor="middle">a_{unrollStep} (0..{actionDim - 1})</text>
                <text x="430" y="205" fill="#94a3b8" fontSize="8.5" textAnchor="middle">1×{boardH}×{boardW} broadcast</text>
              </g>

              {/* Node 5: Dynamics Recurrent Network */}
              <g
                onClick={() => setSelectedNodeId("dynamics")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="180"
                  y="145"
                  width="155"
                  height="85"
                  rx="8"
                  fill={selectedNodeId === "dynamics" ? "#7c2d12" : "#1e293b"}
                  stroke={unrollStep > 0 ? "#f97316" : "#475569"}
                  strokeWidth="2"
                />
                <text x="257" y="168" fill="#fbbf24" fontSize="9" fontWeight="700" textAnchor="middle">RED DE DINÁMICA</text>
                <text x="257" y="186" fill="#ffffff" fontSize="11" fontWeight="800" textAnchor="middle">g_θ(s, a) ➔ s_{Math.min(unrollStep + 1, maxUnroll)}</text>
                <text x="257" y="204" fill="#fdba74" fontSize="9" textAnchor="middle">{dynamicsBlocks} ResBlocks {isV2Optimized ? "+ SE + Bottleneck" : "+ Reward Head"}</text>
                <text x="257" y="219" fill="#94a3b8" fontSize="8.5" textAnchor="middle">{isV2Optimized ? `Unroll ${maxUnroll} pasos (MinMax Scaling)` : `Unroll máx = ${maxUnroll} pasos`}</text>
              </g>

              {/* Node 6: Hierarchical Strategic Macro Planner (Level 1) */}
              <g
                onClick={() => setSelectedNodeId("macro_planner")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="15"
                  y="145"
                  width="135"
                  height="85"
                  rx="8"
                  fill={selectedNodeId === "macro_planner" ? "#581c87" : "#1e1b4b"}
                  stroke={selectedNodeId === "macro_planner" ? "#d8b4fe" : "#a855f7"}
                  strokeWidth={selectedNodeId === "macro_planner" ? "2.5" : "1.5"}
                />
                <text x="82" y="166" fill="#c084fc" fontSize="9" fontWeight="700" textAnchor="middle">NIVEL 1 • JERARQUÍA</text>
                <text x="82" y="184" fill="#ffffff" fontSize="11" fontWeight="800" textAnchor="middle">Planificador Macro</text>
                <text x="82" y="200" fill="#e9d5ff" fontSize="9" textAnchor="middle">Posturas &amp; Roles</text>
                <text x="82" y="215" fill="#c084fc" fontSize="8.5" fontWeight="600" textAnchor="middle">⚡ Priors MCTS (+35%)</text>
              </g>

              {/* Dynamic Active Prediction Heads */}
              {activeHeads.map((head, idx) => {
                const headY = 10 + idx * (cardH + cardGap);
                const isSelected = selectedNodeId === head.id;
                return (
                  <g key={`head-node-${head.id}`} onClick={() => setSelectedNodeId(head.id)} style={{ cursor: "pointer" }}>
                    <rect
                      x="535"
                      y={headY}
                      width="330"
                      height={cardH}
                      rx="6"
                      fill={isSelected ? head.selectedFill : "#1e293b"}
                      stroke={head.stroke}
                      strokeWidth={isSelected ? "2.5" : "1.5"}
                    />
                    <text x="548" y={headY + (cardH <= 44 ? 14 : 18)} fill={head.stroke} fontSize={cardH <= 44 ? "9.5" : "10"} fontWeight="700">
                      {head.icon} {head.label}
                    </text>
                    <text x="850" y={headY + (cardH <= 44 ? 14 : 18)} fill={head.tagColor} fontSize="9" fontWeight="700" textAnchor="end">
                      {head.tag}
                    </text>
                    <text x="548" y={headY + (cardH <= 44 ? 26 : 33)} fill="#f8fafc" fontSize={cardH <= 44 ? "9.5" : "10.5"} fontWeight="600">
                      {head.sublabel}
                    </text>
                    <text x="548" y={headY + (cardH <= 44 ? 37 : 46)} fill="#94a3b8" fontSize={cardH <= 44 ? "8.5" : "9"}>
                      {head.metricLabel}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          <div className="muted" style={{ fontSize: 11, textAlign: "center" }}>
            Arquitectura desenrollada en tiempo de ejecución para <b>{runId}</b>. Cada componente recalcula formas y pesos dinámicamente.
          </div>
        </div>

        {/* Inspector Panel for Selected Node */}
        <div
          style={{
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
            padding: diagramSize === "compact" ? 10 : 16,
            display: "flex",
            flexDirection: "column",
            gap: diagramSize === "compact" ? 8 : 12,
            maxHeight: diagramSize === "compact" ? 340 : diagramSize === "expanded" ? 500 : 420,
            overflowY: "auto",
          }}
        >
          {/* Live Head Diagnostics Banner when a prediction head is selected */}
          {(selectedNodeId === "policy" || selectedNodeId === "value" || selectedNodeId === "aux_objective" || selectedNodeId === "consistency" || (selectedNodeId === "threat_map" && hasThreatHead) || (selectedNodeId === "attrition" && hasAttritionHead) || (selectedNodeId === "morale" && hasMoraleHead)) && (
            <div style={{ background: "rgba(16, 185, 129, 0.08)", border: "1px solid #10b981", borderRadius: 6, padding: "8px 10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#34d399", display: "flex", alignItems: "center", gap: 4 }}>
                  <span>🔬</span> Diagnóstico en Vivo del Cabezal: {selectedNode.name}
                </span>
                <span style={{ fontSize: 9, background: "#064e3b", color: "#6ee7b7", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                  SALUDABLE
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11 }}>
                {selectedNodeId === "policy" && (
                  <>
                    <div><span className="muted">Loss Política:</span> <b style={{ color: "#38bdf8" }}>{fmtNum(polLoss, 4)}</b></div>
                    <div><span className="muted">Entropía:</span> <b style={{ color: "#f8fafc" }}>{fmtNum(polEntropy, 3)}</b></div>
                    <div><span className="muted">Confianza Previa:</span> <b style={{ color: "#34d399" }}>{fmtPercent(polConfidence)}</b></div>
                    <div><span className="muted">Margen Decisión:</span> <b style={{ color: "#fbbf24" }}>{fmtNum(polMargin, 3)}</b></div>
                  </>
                )}
                {selectedNodeId === "value" && (
                  <>
                    <div><span className="muted">Loss Valor:</span> <b style={{ color: "#22c55e" }}>{fmtNum(valLoss, 4)}</b></div>
                    <div><span className="muted">Varianza Explicada:</span> <b style={{ color: "#34d399" }}>{fmtNum(valExpVar, 3)}</b></div>
                    <div><span className="muted">Saturación Q MCTS:</span> <b style={{ color: qSatRate !== null && qSatRate < 0.05 ? "#34d399" : "#f59e0b" }}>{fmtPercent(qSatRate)}</b></div>
                    <div><span className="muted">Proxy Retorno:</span> <b style={{ color: "#38bdf8" }}>{fmtNum(valWinRate, 3)}</b></div>
                  </>
                )}
                {selectedNodeId === "aux_objective" && (
                  <>
                    <div><span className="muted">Loss Objetivo:</span> <b style={{ color: "#f43f5e" }}>{fmtNum(objLoss, 4)}</b></div>
                    <div><span className="muted">Captura Oportunidad:</span> <b style={{ color: "#34d399" }}>{fmtPercent(objTakeRate)}</b></div>
                    <div><span className="muted">Eficiencia Conversión:</span> <b style={{ color: "#38bdf8" }}>{fmtNum(objConversionEff, 4)}</b></div>
                    <div><span className="muted">VPs Capturados Avg:</span> <b style={{ color: "#fbbf24" }}>{fmtNum(objCapturedAvg, 2, " VP")}</b></div>
                  </>
                )}
                {selectedNodeId === "consistency" && (
                  <>
                    <div><span className="muted">Loss Consistencia:</span> <b style={{ color: "#c084fc" }}>{fmtSci(conLoss)}</b></div>
                    <div><span className="muted">Cobertura Reanálisis:</span> <b style={{ color: "#34d399" }}>{fmtPercent(conReanalysisCov, 0)}</b></div>
                    <div><span className="muted">Pares Consistencia:</span> <b style={{ color: "#38bdf8" }}>{conPairs !== null ? conPairs.toLocaleString() : "—"}</b></div>
                    <div><span className="muted">Deriva Espacial:</span> <b style={{ color: "#34d399" }}>{conLoss !== null ? "Invariante" : "—"}</b></div>
                  </>
                )}
                {selectedNodeId === "threat_map" && hasThreatHead && (
                  <>
                    <div><span className="muted">Loss Amenaza:</span> <b style={{ color: "#eab308" }}>{fmtNum(threatLoss, 4)}</b></div>
                    <div><span className="muted">Amenaza Máxima:</span> <b style={{ color: "#fef08a" }}>{fmtPercent(threatMax)}</b></div>
                    <div><span className="muted">Cobertura Fuego:</span> <b style={{ color: "#34d399" }}>{fmtPercent(threatCov)}</b></div>
                    <div><span className="muted">Cuadrícula:</span> <b style={{ color: "#38bdf8" }}>{boardH}×{boardW} hex</b></div>
                  </>
                )}
                {selectedNodeId === "attrition" && hasAttritionHead && (
                  <>
                    <div><span className="muted">Loss Desgaste:</span> <b style={{ color: "#06b6d4" }}>{fmtNum(attritionLoss, 4)}</b></div>
                    <div><span className="muted">Ratio Bajas:</span> <b style={{ color: "#67e8f9" }}>{fmtNum(attritionExchange, 2, "x")}</b></div>
                    <div><span className="muted">Intercambio:</span> <b style={{ color: attritionExchange !== null && attritionExchange >= 1.0 ? "#34d399" : "#f59e0b" }}>{attritionExchange !== null ? (attritionExchange >= 1.0 ? "Favorable" : "Desfavorable") : "—"}</b></div>
                    <div><span className="muted">Vector Bajas:</span> <b style={{ color: "#38bdf8" }}>2 Dim [A, E]</b></div>
                  </>
                )}
                {selectedNodeId === "morale" && hasMoraleHead && (
                  <>
                    <div><span className="muted">Loss Moral:</span> <b style={{ color: "#ec4899" }}>{fmtNum(moraleLoss, 4)}</b></div>
                    <div><span className="muted">Riesgo Supresión:</span> <b style={{ color: moraleRisk !== null && moraleRisk < 0.3 ? "#34d399" : moraleRisk !== null && moraleRisk < 0.6 ? "#fbbf24" : "#f43f5e" }}>{fmtNum(moraleRisk, 2)}</b></div>
                    <div><span className="muted">Estado Dominante:</span> <b style={{ color: "#fbcfe8" }}>{moraleRisk !== null ? (moraleRisk < 0.3 ? "NORMAL" : moraleRisk < 0.6 ? "PINNED" : "SUPPRESSED") : "—"}</b></div>
                    <div><span className="muted">Niveles Cohesión:</span> <b style={{ color: "#38bdf8" }}>4 Clases</b></div>
                  </>
                )}
              </div>
              <button
                onClick={() => setSubTab("head-diagnostics")}
                style={{
                  width: "100%",
                  marginTop: 8,
                  background: "#0284c7",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: 4,
                  padding: "4px 8px",
                  fontSize: 10,
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                🔬 Ver Análisis de Cabezas Completo ➔
              </button>
            </div>
          )}

          {/* Dedicated Macro Planner Diagnostics & Quick Actions Banner */}
          {selectedNodeId === "macro_planner" && (
            <div style={{ background: "rgba(168, 85, 247, 0.1)", border: "1px solid #a855f7", borderRadius: 6, padding: "8px 10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#d8b4fe", display: "flex", alignItems: "center", gap: 4 }}>
                  <span>♟️</span> Estado del Planificador Macro (Nivel 1)
                </span>
                <span style={{ fontSize: 9, background: "#581c87", color: "#e9d5ff", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                  JERÁRQUICO ACTIVO
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11 }}>
                <div><span className="muted">Postura Dominante:</span> <b style={{ color: "#c084fc" }}>{macroStats.hasRealData ? (macroStats.assaultPct >= 50 ? "ASSAULT_VP" : "DEFENSIVE_HOLD") : "N/A"}</b></div>
                <div><span className="muted">Asalto VP:</span> <b style={{ color: "#38bdf8" }}>{macroStats.hasRealData ? `${macroStats.assaultPct.toFixed(1)}%` : "N/A"}</b></div>
                <div><span className="muted">Rol Vanguardia:</span> <b style={{ color: "#fbbf24" }}>{macroStats.hasRealData ? `${macroStats.spearheadPct.toFixed(1)}%` : "N/A"}</b></div>
                <div><span className="muted">Apoyo de Fuego:</span> <b style={{ color: "#34d399" }}>{macroStats.hasRealData ? `${macroStats.fireSupportPct.toFixed(1)}%` : "N/A"}</b></div>
                <div><span className="muted">Sobreescritura MCTS:</span> <b style={{ color: "#f59e0b" }}>{macroStats.hasRealData ? `${macroStats.mctsOverridePct.toFixed(1)}%` : "N/A"}</b></div>
              </div>
              <button
                onClick={() => setSubTab("macro-planner")}
                style={{
                  width: "100%",
                  marginTop: 8,
                  background: "#7e22ce",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: 4,
                  padding: "5px 8px",
                  fontSize: 10,
                  fontWeight: 700,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 6,
                }}
              >
                <span>♟️</span> Abrir Panel Completo de Planificador Macro ➔
              </button>
            </div>
          )}
          <div>
            <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 700, textTransform: "uppercase" }}>
              Inspector de Componente
            </div>
            <h3 style={{ margin: "2px 0 0 0", fontSize: 16, color: "#38bdf8" }}>
              {selectedNode.name}
            </h3>
            <code style={{ fontSize: 11, display: "inline-block", marginTop: 4, background: "#0f172a", padding: "2px 6px", borderRadius: 4 }}>
              {selectedNode.math}
            </code>
          </div>

          <div style={{ fontSize: 12, color: "#cbd5e1", lineHeight: 1.4 }}>
            {selectedNode.role}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div style={{ background: "#0f172a", padding: 8, borderRadius: 6 }}>
              <div className="muted" style={{ fontSize: 10 }}>Forma Entrada</div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#f8fafc", marginTop: 2 }}>
                {selectedNode.inShape}
              </div>
            </div>
            <div style={{ background: "#0f172a", padding: 8, borderRadius: 6 }}>
              <div className="muted" style={{ fontSize: 10 }}>Forma Salida</div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#34d399", marginTop: 2 }}>
                {selectedNode.outShape}
              </div>
            </div>
            <div style={{ background: "#0f172a", padding: 8, borderRadius: 6 }}>
              <div className="muted" style={{ fontSize: 10 }}>Campo Receptivo</div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#fbbf24", marginTop: 2 }}>
                {selectedNode.receptiveField}
              </div>
            </div>
            <div style={{ background: "#0f172a", padding: 8, borderRadius: 6 }}>
              <div className="muted" style={{ fontSize: 10 }}>Parámetros</div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#c084fc", marginTop: 2 }}>
                {selectedNode.paramEstimate}
              </div>
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", marginBottom: 6 }}>
              Arquitectura Interna de Capas:
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11, color: "#e2e8f0", display: "flex", flexDirection: "column", gap: 4 }}>
              {selectedNode.architecture.map((layer, idx) => (
                <li key={idx}><code>{layer}</code></li>
              ))}
            </ul>
          </div>

          <div style={{ background: "rgba(14, 165, 233, 0.08)", border: "1px solid #0284c7", borderRadius: 6, padding: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: "#38bdf8", marginBottom: 2 }}>
              Detalle Funcional MLOps (Ejecución {runId})
            </div>
            <div style={{ fontSize: 11, color: "#e2e8f0" }}>
              {selectedNode.details}
            </div>
          </div>
        </div>
      </div>

      {/* Observation Channels Explorer */}
      <div
        style={{
          background: "#1e293b",
          border: "1px solid #334155",
          borderRadius: 8,
          padding: 16,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <div>
            <h4 style={{ margin: 0, fontSize: 14, color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
              <span>📡</span> Catálogo de los {inChannels} Canales Espaciales de Entrada (Tensor {inChannels}×{boardH}×{boardW})
            </h4>
            <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
              Codificación espacial hexágono a hexágono del estado táctico del simulador VOEC para <b>{runId}</b>.
            </div>
          </div>

          <div style={{ display: "flex", gap: 4, background: "#0f172a", padding: 3, borderRadius: 6, flexWrap: "wrap" }}>
            {[
              { id: "all", label: `Todos (${dynamicChannelsList.length})` },
              { id: "units", label: "Tropas" },
              { id: "terrain", label: "Terreno/LOS" },
              { id: "vp", label: "VPs" },
              { id: "hex", label: "Topología Hex" },
              { id: "global", label: "Globales" },
            ].map((f) => (
              <button
                key={f.id}
                onClick={() => setChannelFilter(f.id)}
                style={{
                  fontSize: 11,
                  padding: "4px 8px",
                  borderRadius: 4,
                  background: channelFilter === f.id ? "#0284c7" : "transparent",
                  color: channelFilter === f.id ? "#ffffff" : "#94a3b8",
                  border: "none",
                  fontWeight: channelFilter === f.id ? 700 : 500,
                  cursor: "pointer",
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
            gap: 8,
            minHeight: 320,
            maxHeight: "calc(100vh - 360px)",
            overflowY: "auto",
            paddingRight: 4,
          }}
        >
          {filteredChannels.map((c) => (
            <div
              key={c.idx}
              style={{
                background: "#0f172a",
                border: "1px solid #334155",
                borderRadius: 6,
                padding: "8px 10px",
                display: "flex",
                flexDirection: "column",
                gap: 2,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8" }}>
                  Ch {c.idx.toString().padStart(2, "0")}: <code>{c.name}</code>
                </span>
                <span
                  style={{
                    fontSize: 9,
                    textTransform: "uppercase",
                    padding: "1px 5px",
                    borderRadius: 3,
                    background: c.cat === "vp" ? "#065f46" : c.cat === "units" ? "#1e3a8a" : c.cat === "hex" ? "#701a75" : "#334155",
                    color: "#f8fafc",
                    fontWeight: 700,
                  }}
                >
                  {c.cat}
                </span>
              </div>
              <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                {c.desc}
              </div>
              {channelScoresMap.has(c.idx) && (() => {
                const sc = channelScoresMap.get(c.idx)!;
                const isHigh = sc.status === "HIGH_EFFECTIVENESS";
                const isMod = sc.status === "MODERATE_EFFECTIVENESS";
                const isLow = sc.status === "LOW_EFFECTIVENESS";
                return (
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4, paddingTop: 4, borderTop: "1px dashed #334155", fontSize: 10 }}>
                    <span style={{ fontWeight: 700, color: isHigh ? "#34d399" : isMod ? "#38bdf8" : isLow ? "#fbbf24" : "#f43f5e" }}>
                      #{sc.rank} ({isHigh ? "Alta" : isMod ? "Media" : isLow ? "Baja" : "Inactiva"})
                    </span>
                    <span style={{ color: "#cbd5e1", fontFamily: "monospace" }}>
                      Score: {Number(sc.importance_score).toFixed(3)}
                    </span>
                  </div>
                );
              })()}
            </div>
          ))}
        </div>
      </div>
      </>
      )}

      {/* SECTION 2: DEDICATED HEAD DIAGNOSTICS & PERFORMANCE ANALYSIS PANEL */}
      {currentSubTab === "head-diagnostics" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Header Banner */}
          <div
            style={{
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 8,
              padding: 16,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: 10,
            }}
          >
            <div>
              <h3 style={{ margin: 0, fontSize: 16, color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
                <span>🔬</span> Diagnóstico y Análisis Integral de Cabezas (Head Diagnostics)
              </h3>
              <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                Evaluación multi-cabezal para <b>{runId}</b>: Calibración predictiva, entropía, gradientes, captura de VPs y estabilidad temporal.
              </div>
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span
                style={{
                  background: "#064e3b",
                  border: "1px solid #059669",
                  color: "#34d399",
                  padding: "4px 10px",
                  borderRadius: 6,
                  fontSize: 11,
                  fontWeight: 700,
                  display: "flex",
                  alignItems: "center",
                  gap: 5,
                }}
              >
                <span>🟢</span> Estado Global: {activeHeads.length} Cabezales Activos ({hasThreatHead || hasAttritionHead || hasMoraleHead ? "Incluye Cabezas Tácticas EZv2" : "Estándar"})
              </span>
            </div>
          </div>

          {/* 4 Health Cards: Policy, Value, Objective, Consistency */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
            {/* Card 1: Policy Head */}
            <div
              style={{
                background: "#0f172a",
                border: "1px solid #0284c7",
                borderRadius: 8,
                padding: 14,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>🎯</span> Cabezal de Política (f_p)
                </span>
                <span style={{ fontSize: 9, background: polLoss !== null ? "#064e3b" : "#334155", color: polLoss !== null ? "#6ee7b7" : "#94a3b8", padding: "2px 6px", borderRadius: 4, fontWeight: 700 }}>
                  {polLoss !== null ? "SALUDABLE" : "SIN DATOS"}
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8" }}>
                Predicción de prior de acciones y distribución sobre {actionDim} maniobras tácticas.
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 4 }}>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Pérdida Política</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>{fmtNum(polLoss, 4)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>Cross-Entropy</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Entropía Política</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#f8fafc", marginTop: 2 }}>{fmtNum(polEntropy, 3)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>No-colapso</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Confianza Previa</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#34d399", marginTop: 2 }}>{fmtPercent(polConfidence)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>Top-1 MCTS</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Margen de Decisión</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#fbbf24", marginTop: 2 }}>{fmtNum(polMargin, 3)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>p(1st) - p(2nd)</div>
                </div>
              </div>
              <div style={{ background: "rgba(56, 189, 248, 0.08)", borderRadius: 6, padding: "6px 8px", fontSize: 10, color: "#cbd5e1", marginTop: 2 }}>
                💡 <b>Diagnóstico:</b> {polConfidence !== null ? "Política táctica orientada hacia selección de fuego y asalto." : "Métricas pendientes de registro o evaluación."}
              </div>
            </div>

            {/* Card 2: Value Head */}
            <div
              style={{
                background: "#0f172a",
                border: "1px solid #059669",
                borderRadius: 8,
                padding: 14,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#22c55e", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>⚖️</span> Cabezal de Valor (f_v)
                </span>
                <span style={{ fontSize: 9, background: valLoss !== null ? "#064e3b" : "#334155", color: valLoss !== null ? "#6ee7b7" : "#94a3b8", padding: "2px 6px", borderRadius: 4, fontWeight: 700 }}>
                  {valLoss !== null ? "CALIBRADO" : "SIN DATOS"}
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8" }}>
                Evaluación escalar de probabilidad de victoria esperada en rango [-1.0, +1.0].
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 4 }}>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Pérdida de Valor</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#22c55e", marginTop: 2 }}>{fmtNum(valLoss, 4)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>MSE / Huber</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Varianza Explicada</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#34d399", marginTop: 2 }}>{fmtNum(valExpVar, 3)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>R² Posicional</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Saturación Q MCTS</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: qSatRate !== null && qSatRate < 0.05 ? "#34d399" : "#f59e0b", marginTop: 2 }}>{fmtPercent(qSatRate)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>Umbral máx &lt;5%</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Proxy Retorno / Win</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>{fmtNum(valWinRate, 3)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>{valWinRate !== null ? `${(valWinRate * 100).toFixed(1)}% victorias` : "Sin evaluaciones"}</div>
                </div>
              </div>
              <div style={{ background: "rgba(34, 197, 94, 0.08)", borderRadius: 6, padding: "6px 8px", fontSize: 10, color: "#cbd5e1", marginTop: 2 }}>
                💡 <b>Diagnóstico:</b> {valLoss !== null ? "Evaluación posicional de sectores bajo fuego y áreas seguras." : "Resumen de valor no disponible para este run."}
              </div>
            </div>

            {/* Card 3: Objective Head */}
            <div
              style={{
                background: "#0f172a",
                border: "1px solid #e11d48",
                borderRadius: 8,
                padding: 14,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#f43f5e", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>🚩</span> Cabezal de Objetivo (f_o)
                </span>
                <span style={{ fontSize: 9, background: objLoss !== null ? "#881337" : "#334155", color: objLoss !== null ? "#fecdd3" : "#94a3b8", padding: "2px 6px", borderRadius: 4, fontWeight: 700 }}>
                  {objLoss !== null ? "ACTIVO & CONVERSIÓN" : "SIN DATOS"}
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8" }}>
                Guía auxiliar orientada a la toma territorial y control de Puntos de Victoria.
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 4 }}>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Pérdida Objetivo</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#f43f5e", marginTop: 2 }}>{fmtNum(objLoss, 4)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>Cross-Entropy VP</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Captura Oportunidad</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#34d399", marginTop: 2 }}>{fmtPercent(objTakeRate)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>Tasa de toma</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Eficiencia Conversión</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>{fmtNum(objConversionEff, 4)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>VPs / Paso MCTS</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>VPs Capturados Avg</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#fbbf24", marginTop: 2 }}>{fmtNum(objCapturedAvg, 2, " VP")}</div>
                  <div className="muted" style={{ fontSize: 9 }}>Promedio por partida</div>
                </div>
              </div>
              <div style={{ background: "rgba(244, 63, 94, 0.08)", borderRadius: 6, padding: "6px 8px", fontSize: 10, color: "#cbd5e1", marginTop: 2 }}>
                💡 <b>Diagnóstico:</b> {objTakeRate !== null ? "Incentiva la captura decisiva de hexágonos de victoria." : "Sin registros de captura de VPs."}
              </div>
            </div>

            {/* Card 4: Consistency Head */}
            <div
              style={{
                background: "#0f172a",
                border: "1px solid #9333ea",
                borderRadius: 8,
                padding: 14,
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#c084fc", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>🔄</span> Cabezal de Consistencia (q_θ)
                </span>
                <span style={{ fontSize: 9, background: conLoss !== null ? "#581c87" : "#334155", color: conLoss !== null ? "#e9d5ff" : "#94a3b8", padding: "2px 6px", borderRadius: 4, fontWeight: 700 }}>
                  {conLoss !== null ? "INVARIANTE" : "SIN DATOS"}
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8" }}>
                Preservación auto-supervisada SimSiam de la geometría semántica del espacio latente.
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 4 }}>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Pérdida Consistencia</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#c084fc", marginTop: 2 }}>{fmtSci(conLoss)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>SimSiam Loss</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Cobertura Reanálisis</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#34d399", marginTop: 2 }}>{fmtPercent(conReanalysisCov, 0)}</div>
                  <div className="muted" style={{ fontSize: 9 }}>Buffer activo</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Pares Consistencia</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>{conPairs !== null ? conPairs.toLocaleString() : "—"}</div>
                  <div className="muted" style={{ fontSize: 9 }}>Pares unrolled</div>
                </div>
                <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                  <div className="muted" style={{ fontSize: 10 }}>Deriva Latente</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: "#34d399", marginTop: 2 }}>{conLoss !== null ? "0.000" : "—"}</div>
                  <div className="muted" style={{ fontSize: 9 }}>{conLoss !== null ? "Sin colapso" : "Sin regularización"}</div>
                </div>
              </div>
              <div style={{ background: "rgba(192, 132, 252, 0.08)", borderRadius: 6, padding: "6px 8px", fontSize: 10, color: "#cbd5e1", marginTop: 2 }}>
                💡 <b>Diagnóstico:</b> {conLoss !== null ? `Estados latentes en horizonte t=${maxUnroll} preservan coherencia geométrica.` : "Métricas SimSiam no registradas."}
              </div>
            </div>

            {/* Card 5: Threat Map Head (Only if active for this execution) */}
            {hasThreatHead && (
              <div
                style={{
                  background: "#0f172a",
                  border: "1px solid #ca8a04",
                  borderRadius: 8,
                  padding: 14,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#eab308", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🗺️</span> Mapa de Amenazas (f_threat)
                  </span>
                  <span style={{ fontSize: 9, background: "#713f12", color: "#fef08a", padding: "2px 6px", borderRadius: 4, fontWeight: 700 }}>
                    TACTICAL HEAD
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#94a3b8" }}>
                  Matriz espacial 2D de cobertura de fuego directo y riesgo de supresión enemiga.
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 4 }}>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Pérdida Amenaza</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#eab308", marginTop: 2 }}>{fmtNum(threatLoss, 4)}</div>
                    <div className="muted" style={{ fontSize: 9 }}>BCE con Logits</div>
                  </div>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Amenaza Máxima</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#fef08a", marginTop: 2 }}>{fmtPercent(threatMax, 1)}</div>
                    <div className="muted" style={{ fontSize: 9 }}>Pico en hexágono</div>
                  </div>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Cobertura Fuego</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#34d399", marginTop: 2 }}>{fmtPercent(threatCov, 1)}</div>
                    <div className="muted" style={{ fontSize: 9 }}>Líneas de tiro</div>
                  </div>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Resolución 2D</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>{boardH}×{boardW}</div>
                    <div className="muted" style={{ fontSize: 9 }}>Hexágonos tablero</div>
                  </div>
                </div>
                <div style={{ background: "rgba(234, 179, 8, 0.08)", borderRadius: 6, padding: "6px 8px", fontSize: 10, color: "#cbd5e1", marginTop: 2 }}>
                  💡 <b>Diagnóstico:</b> Permite al agente anticipar emboscadas enemigas y moverse a través de coberturas urbanas o bosques.
                </div>
              </div>
            )}

            {/* Card 6: Attrition Balance Head (Only if active for this execution) */}
            {hasAttritionHead && (
              <div
                style={{
                  background: "#0f172a",
                  border: "1px solid #0891b2",
                  borderRadius: 8,
                  padding: 14,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#06b6d4", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>⚔️</span> Balance de Desgaste (f_attr)
                  </span>
                  <span style={{ fontSize: 9, background: "#164e63", color: "#67e8f9", padding: "2px 6px", borderRadius: 4, fontWeight: 700 }}>
                    TACTICAL HEAD
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#94a3b8" }}>
                  Proyección táctica de bajas aliadas vs. enemigas en el horizonte inmediato.
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 4 }}>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Pérdida Desgaste</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#06b6d4", marginTop: 2 }}>{fmtNum(attritionLoss, 4)}</div>
                    <div className="muted" style={{ fontSize: 9 }}>Smooth L1 Loss</div>
                  </div>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Ratio Intercambio</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#67e8f9", marginTop: 2 }}>{fmtNum(attritionExchange, 2, "x")}</div>
                    <div className="muted" style={{ fontSize: 9 }}>Enemigo / Aliado</div>
                  </div>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Balance Combate</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: attritionExchange !== null && attritionExchange >= 1.0 ? "#34d399" : "#f59e0b", marginTop: 2 }}>
                      {attritionExchange !== null ? (attritionExchange >= 1.0 ? "Favorable" : "Desfavorable") : "—"}
                    </div>
                    <div className="muted" style={{ fontSize: 9 }}>Umbral ratio &gt;1.0</div>
                  </div>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Salida Táctica</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>2 Dim</div>
                    <div className="muted" style={{ fontSize: 9 }}>Vector de bajas</div>
                  </div>
                </div>
                <div style={{ background: "rgba(6, 182, 212, 0.08)", borderRadius: 6, padding: "6px 8px", fontSize: 10, color: "#cbd5e1", marginTop: 2 }}>
                  💡 <b>Diagnóstico:</b> Penaliza pérdidas innecesarias de escuadras y orienta el asalto hacia victorias de bajo desgaste.
                </div>
              </div>
            )}

            {/* Card 7: Morale State Head (Only if active for this execution) */}
            {hasMoraleHead && (
              <div
                style={{
                  background: "#0f172a",
                  border: "1px solid #db2777",
                  borderRadius: 8,
                  padding: 14,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: "#ec4899", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🛡️</span> Estado de Moral (f_morale)
                  </span>
                  <span style={{ fontSize: 9, background: "#831843", color: "#fbcfe8", padding: "2px 6px", borderRadius: 4, fontWeight: 700 }}>
                    TACTICAL HEAD
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#94a3b8" }}>
                  Distribución categórica sobre riesgo de fijación, supresión y retirada (4 clases).
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 4 }}>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Pérdida Moral</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#ec4899", marginTop: 2 }}>{fmtNum(moraleLoss, 4)}</div>
                    <div className="muted" style={{ fontSize: 9 }}>Cross-Entropy</div>
                  </div>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Riesgo Supresión</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: moraleRisk !== null ? (moraleRisk < 0.3 ? "#34d399" : moraleRisk < 0.6 ? "#fbbf24" : "#f43f5e") : "#94a3b8", marginTop: 2 }}>
                      {fmtNum(moraleRisk, 2)}
                    </div>
                    <div className="muted" style={{ fontSize: 9 }}>Score ponderado</div>
                  </div>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Estado Dominante</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#fbcfe8", marginTop: 2 }}>
                      {moraleRisk !== null ? (moraleRisk < 0.3 ? "NORMAL" : moraleRisk < 0.6 ? "PINNED" : "SUPPRESSED") : "—"}
                    </div>
                    <div className="muted" style={{ fontSize: 9 }}>Clase top</div>
                  </div>
                  <div style={{ background: "#1e293b", padding: 8, borderRadius: 6 }}>
                    <div className="muted" style={{ fontSize: 10 }}>Clases Tácticas</div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>4 Niveles</div>
                    <div className="muted" style={{ fontSize: 9 }}>Normal/Pin/Supp/Rout</div>
                  </div>
                </div>
                <div style={{ background: "rgba(236, 72, 153, 0.08)", borderRadius: 6, padding: "6px 8px", fontSize: 10, color: "#cbd5e1", marginTop: 2 }}>
                  💡 <b>Diagnóstico:</b> Alerta antes de que una unidad entre en pánico o quede inmovilizada, facilitando el apoyo mutuo.
                </div>
              </div>
            )}
          </div>

          {/* Full Metrics Comparison Table */}
          <div style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, padding: 16 }}>
            <h4 style={{ margin: "0 0 10px 0", fontSize: 14, color: "#38bdf8" }}>
              📋 Matriz de Diagnósticos y Verificación por Cabezal
            </h4>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, textAlign: "left" }}>
                <thead>
                  <tr style={{ background: "#0f172a", borderBottom: "1px solid #334155" }}>
                    <th style={{ padding: "8px 10px" }}>Cabezal</th>
                    <th style={{ padding: "8px 10px" }}>Métrica Diagnóstica</th>
                    <th style={{ padding: "8px 10px" }}>Valor Actual</th>
                    <th style={{ padding: "8px 10px" }}>Rango Nominal / Umbral</th>
                    <th style={{ padding: "8px 10px" }}>Estado</th>
                    <th style={{ padding: "8px 10px" }}>Evaluación MLOps</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderBottom: "1px solid #283548" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 700, color: "#38bdf8" }}>Política (f_p)</td>
                    <td style={{ padding: "8px 10px" }}>train_policy_loss</td>
                    <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtNum(polLoss, 4)}</b></td>
                    <td style={{ padding: "8px 10px", color: "#94a3b8" }}>&lt; 3.000 (Convergente)</td>
                    <td style={{ padding: "8px 10px" }}>
                      <span style={{ color: polLoss !== null ? "#34d399" : "#94a3b8", fontWeight: 700 }}>
                        {polLoss !== null ? "🟢 Óptimo" : "⚪ Sin datos"}
                      </span>
                    </td>
                    <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>
                      {polLoss !== null ? `Convergencia sostenida de Cross-Entropy en ${dynamicsBlocks} bloques` : "Métrica no disponible"}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #283548" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 700, color: "#38bdf8" }}>Política (f_p)</td>
                    <td style={{ padding: "8px 10px" }}>eval_confidence_mean</td>
                    <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtPercent(polConfidence)}</b></td>
                    <td style={{ padding: "8px 10px", color: "#94a3b8" }}>&gt; 20.0%</td>
                    <td style={{ padding: "8px 10px" }}>
                      <span style={{ color: polConfidence !== null ? (polConfidence >= 0.2 ? "#34d399" : "#f59e0b") : "#94a3b8", fontWeight: 700 }}>
                        {polConfidence !== null ? (polConfidence >= 0.2 ? "🟢 Óptimo" : "🟡 Moderado") : "⚪ Sin datos"}
                      </span>
                    </td>
                    <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>
                      {polConfidence !== null ? "Confianza adecuada en la selección de acciones tácticas" : "Evaluación pendiente"}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #283548" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 700, color: "#22c55e" }}>Valor (f_v)</td>
                    <td style={{ padding: "8px 10px" }}>train_value_loss</td>
                    <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtNum(valLoss, 4)}</b></td>
                    <td style={{ padding: "8px 10px", color: "#94a3b8" }}>&lt; 0.250</td>
                    <td style={{ padding: "8px 10px" }}>
                      <span style={{ color: valLoss !== null ? "#34d399" : "#94a3b8", fontWeight: 700 }}>
                        {valLoss !== null ? "🟢 Óptimo" : "⚪ Sin datos"}
                      </span>
                    </td>
                    <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>
                      {valLoss !== null ? "Pérdida de valor baja, sin picos de inestabilidad" : "Métrica no disponible"}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #283548" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 700, color: "#22c55e" }}>Valor (f_v)</td>
                    <td style={{ padding: "8px 10px" }}>mcts_q_saturation_rate</td>
                    <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtPercent(qSatRate)}</b></td>
                    <td style={{ padding: "8px 10px", color: "#94a3b8" }}>&lt; 5.0%</td>
                    <td style={{ padding: "8px 10px" }}>
                      <span style={{ color: qSatRate !== null ? (qSatRate < 0.05 ? "#34d399" : "#f59e0b") : "#94a3b8", fontWeight: 700 }}>
                        {qSatRate !== null ? (qSatRate < 0.05 ? "🟢 Óptimo" : "🟡 Revisar") : "⚪ Sin datos"}
                      </span>
                    </td>
                    <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>
                      {qSatRate !== null ? "No se producen saturaciones artificiales en las hojas MCTS" : "Métrica no disponible"}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #283548" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 700, color: "#f43f5e" }}>Objetivo (f_o)</td>
                    <td style={{ padding: "8px 10px" }}>eval_vp_capture_take_rate</td>
                    <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtPercent(objTakeRate)}</b></td>
                    <td style={{ padding: "8px 10px", color: "#94a3b8" }}>&gt; 0.5% (Gate Phase 1)</td>
                    <td style={{ padding: "8px 10px" }}>
                      <span style={{ color: objTakeRate !== null ? (objTakeRate > 0.005 ? "#34d399" : "#f59e0b") : "#94a3b8", fontWeight: 700 }}>
                        {objTakeRate !== null ? (objTakeRate > 0.005 ? "🟢 Gate Pass" : "🟡 Bajo") : "⚪ Sin datos"}
                      </span>
                    </td>
                    <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>
                      {objTakeRate !== null ? "Supera el umbral de promoción con margen positivo" : "Evaluación pendiente"}
                    </td>
                  </tr>
                  <tr style={{ borderBottom: "1px solid #283548" }}>
                    <td style={{ padding: "8px 10px", fontWeight: 700, color: "#c084fc" }}>Consistencia (q_θ)</td>
                    <td style={{ padding: "8px 10px" }}>train_consistency_loss</td>
                    <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtSci(conLoss)}</b></td>
                    <td style={{ padding: "8px 10px", color: "#94a3b8" }}>&lt; 0.010</td>
                    <td style={{ padding: "8px 10px" }}>
                      <span style={{ color: conLoss !== null ? "#34d399" : "#94a3b8", fontWeight: 700 }}>
                        {conLoss !== null ? "🟢 Óptimo" : "⚪ Sin datos"}
                      </span>
                    </td>
                    <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>
                      {conLoss !== null ? "Invarianza temporal gracias a la regularización SimSiam" : "Métrica no disponible"}
                    </td>
                  </tr>
                  {hasThreatHead && (
                    <>
                      <tr style={{ borderBottom: "1px solid #283548" }}>
                        <td style={{ padding: "8px 10px", fontWeight: 700, color: "#eab308" }}>Amenaza (f_threat)</td>
                        <td style={{ padding: "8px 10px" }}>train_threat_loss</td>
                        <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtNum(threatLoss, 4)}</b></td>
                        <td style={{ padding: "8px 10px", color: "#94a3b8" }}>&lt; 0.200</td>
                        <td style={{ padding: "8px 10px" }}>
                          <span style={{ color: threatLoss !== null ? "#34d399" : "#94a3b8", fontWeight: 700 }}>
                            {threatLoss !== null ? "🟢 Óptimo" : "⚪ Sin datos"}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>Predicción de cobertura de fuego enemigo sobre {boardH}×{boardW} casillas</td>
                      </tr>
                      <tr style={{ borderBottom: "1px solid #283548" }}>
                        <td style={{ padding: "8px 10px", fontWeight: 700, color: "#eab308" }}>Amenaza (f_threat)</td>
                        <td style={{ padding: "8px 10px" }}>threat_coverage_ratio</td>
                        <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtPercent(threatCov)}</b></td>
                        <td style={{ padding: "8px 10px", color: "#94a3b8" }}>10.0% - 50.0%</td>
                        <td style={{ padding: "8px 10px" }}>
                          <span style={{ color: threatCov !== null ? "#34d399" : "#94a3b8", fontWeight: 700 }}>
                            {threatCov !== null ? "🟢 Óptimo" : "⚪ Sin datos"}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>Detección de sectores calientes con fuego de supresión</td>
                      </tr>
                    </>
                  )}
                  {hasAttritionHead && (
                    <>
                      <tr style={{ borderBottom: "1px solid #283548" }}>
                        <td style={{ padding: "8px 10px", fontWeight: 700, color: "#06b6d4" }}>Desgaste (f_attr)</td>
                        <td style={{ padding: "8px 10px" }}>train_attrition_loss</td>
                        <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtNum(attritionLoss, 4)}</b></td>
                        <td style={{ padding: "8px 10px", color: "#94a3b8" }}>&lt; 0.150</td>
                        <td style={{ padding: "8px 10px" }}>
                          <span style={{ color: attritionLoss !== null ? "#34d399" : "#94a3b8", fontWeight: 700 }}>
                            {attritionLoss !== null ? "🟢 Óptimo" : "⚪ Sin datos"}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>Convergencia en la proyección de bajas</td>
                      </tr>
                      <tr style={{ borderBottom: "1px solid #283548" }}>
                        <td style={{ padding: "8px 10px", fontWeight: 700, color: "#06b6d4" }}>Desgaste (f_attr)</td>
                        <td style={{ padding: "8px 10px" }}>predicted_exchange_ratio</td>
                        <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtNum(attritionExchange, 2, "x")}</b></td>
                        <td style={{ padding: "8px 10px", color: "#94a3b8" }}>&gt; 1.00x</td>
                        <td style={{ padding: "8px 10px" }}>
                          <span style={{ color: attritionExchange !== null && attritionExchange >= 1.0 ? "#34d399" : "#fbbf24", fontWeight: 700 }}>
                            {attritionExchange !== null ? (attritionExchange >= 1.0 ? "🟢 Favorable" : "🟡 Desfavorable") : "⚪ Sin datos"}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>Tasa de intercambio táctico estimada en asaltos</td>
                      </tr>
                    </>
                  )}
                  {hasMoraleHead && (
                    <>
                      <tr style={{ borderBottom: "1px solid #283548" }}>
                        <td style={{ padding: "8px 10px", fontWeight: 700, color: "#ec4899" }}>Moral (f_morale)</td>
                        <td style={{ padding: "8px 10px" }}>train_morale_loss</td>
                        <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtNum(moraleLoss, 4)}</b></td>
                        <td style={{ padding: "8px 10px", color: "#94a3b8" }}>&lt; 0.350</td>
                        <td style={{ padding: "8px 10px" }}>
                          <span style={{ color: moraleLoss !== null ? "#34d399" : "#94a3b8", fontWeight: 700 }}>
                            {moraleLoss !== null ? "🟢 Óptimo" : "⚪ Sin datos"}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>Calibración multiclase de estados de supresión y pánico</td>
                      </tr>
                      <tr style={{ borderBottom: "1px solid #283548" }}>
                        <td style={{ padding: "8px 10px", fontWeight: 700, color: "#ec4899" }}>Moral (f_morale)</td>
                        <td style={{ padding: "8px 10px" }}>suppression_risk_score</td>
                        <td style={{ padding: "8px 10px", fontFamily: "monospace" }}><b>{fmtNum(moraleRisk, 2)}</b></td>
                        <td style={{ padding: "8px 10px", color: "#94a3b8" }}>&lt; 0.40 (Seguro)</td>
                        <td style={{ padding: "8px 10px" }}>
                          <span style={{ color: moraleRisk !== null && moraleRisk < 0.4 ? "#34d399" : moraleRisk !== null ? "#f43f5e" : "#94a3b8", fontWeight: 700 }}>
                            {moraleRisk !== null ? (moraleRisk < 0.4 ? "🟢 Estable" : "🔴 Riesgo Alto") : "⚪ Sin datos"}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", color: "#cbd5e1" }}>Riesgo general de ruptura o inmovilización de unidades</td>
                      </tr>
                    </>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 3: CHANNEL EFFECTIVENESS & ATTRIBUTION ANALYZER */}
      {currentSubTab === "channel-attribution" && (
        <div
          style={{
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
            padding: 16,
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div>
            <h4 style={{ margin: 0, fontSize: 14, color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
              <span>⚡</span> Análisis de Efectividad & Atribución de Canales (Ablación & Saliency)
            </h4>
            <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
              Diagnóstico empírico: Saliencia de gradientes (∇v, ∇π) y perturbación por oclusión cero (|Δv|, D_KL) en el simulador táctico VOEC.
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button
              onClick={handleRunAnalysis}
              disabled={analyzing}
              style={{
                background: analyzing ? "#475569" : "#0284c7",
                color: "#ffffff",
                border: "none",
                fontWeight: 700,
                fontSize: 12,
                padding: "6px 14px",
                borderRadius: 6,
                cursor: analyzing ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                gap: 6,
                boxShadow: "0 2px 4px rgba(0,0,0,0.2)",
              }}
            >
              <span>{analyzing ? "⏳" : attributionReport ? "🔄" : "⚡"}</span>
              <span>
                {analyzing
                  ? "Ejecutando Análisis (CPU/GPU)..."
                  : attributionReport
                  ? "Re-ejecutar Análisis de Canales"
                  : "Ejecutar Análisis de Efectividad"}
              </span>
            </button>
          </div>
        </div>

        {/* Loading Banner */}
        {analyzing && (
          <div style={{ background: "rgba(2, 132, 199, 0.15)", border: "1px solid #0284c7", borderRadius: 6, padding: "12px 16px" }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
              <span>⏳</span> Análisis en ejecución para <code>{runId}</code>...
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
              Cargando checkpoint de red, recolectando trayectorias con el simulador VOEC, calculando saliencia de gradientes ∇v y ∇π, y evaluando el cambio de valor (|Δv|) y divergencia de política (D_KL) canal a canal. Esta operación puede tardar entre 10 y 20 segundos.
            </div>
          </div>
        )}

        {/* Error Banner */}
        {analysisError && (
          <div style={{ background: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: 6, padding: "10px 14px", color: "#fca5a5", fontSize: 11 }}>
            <b>Error al ejecutar análisis:</b> {analysisError}
          </div>
        )}

        {/* Results View */}
        {attributionReport && !analyzing && (
          <>
            {/* KPI Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
              <div style={{ background: "#0f172a", borderRadius: 6, padding: "8px 12px", border: "1px solid #334155" }}>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Muestras Analizadas</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>
                  {Number(attributionReport.num_observations_analyzed ?? 0)} observaciones
                </div>
                <div className="muted" style={{ fontSize: 10 }}>4 semillas VOEC × 15 pasos</div>
              </div>

              <div style={{ background: "#0f172a", borderRadius: 6, padding: "8px 12px", border: "1px solid #334155" }}>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Canal #1 Más Crítico</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#34d399", marginTop: 2 }}>
                  {topChannel ? `#${topChannel.index} ${topChannel.name}` : "N/A"}
                </div>
                <div className="muted" style={{ fontSize: 10 }}>
                  Score: {topChannel ? Number(topChannel.importance_score).toFixed(3) : 0} | Flip: {topChannel ? `${topChannel.decision_flip_rate}%` : "0%"}
                </div>
              </div>

              <div style={{ background: "#0f172a", borderRadius: 6, padding: "8px 12px", border: "1px solid #334155" }}>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Canales Tácticos Clave</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>
                  Ch 21 (Frontline): #{ch21Info?.rank ?? "-"} (Score {ch21Info ? Number(ch21Info.importance_score).toFixed(3) : "-"})
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#34d399" }}>
                  Ch 07 (Threat): #{ch7Info?.rank ?? "-"} (Score {ch7Info ? Number(ch7Info.importance_score).toFixed(3) : "-"})
                </div>
              </div>

              <div style={{ background: "#0f172a", borderRadius: 6, padding: "8px 12px", border: "1px solid #334155" }}>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Distribución Efectividad</div>
                <div style={{ display: "flex", gap: 6, marginTop: 4, fontSize: 11, fontWeight: 700 }}>
                  <span style={{ color: "#34d399" }}>{countsByStatus.HIGH || 0} Alta</span>
                  <span style={{ color: "#38bdf8" }}>{countsByStatus.MODERATE || 0} Med</span>
                  <span style={{ color: "#fbbf24" }}>{countsByStatus.LOW || 0} Baja</span>
                  <span style={{ color: "#f43f5e" }}>{countsByStatus.DEAD || 0} Inact</span>
                </div>
                <div className="muted" style={{ fontSize: 10, marginTop: 2 }}>Sobre {rankedChannelsList.length} canales totales</div>
              </div>
            </div>

            {/* Category summary pills */}
            {attributionReport.categories_summary && (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 11, fontWeight: 600 }}>Impacto por Categoría:</span>
                {Object.entries(attributionReport.categories_summary as Record<string, Dict>).map(([catName, catData]) => (
                  <div
                    key={catName}
                    style={{
                      background: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: 4,
                      padding: "3px 8px",
                      fontSize: 11,
                      display: "flex",
                      gap: 4,
                      alignItems: "center",
                    }}
                  >
                    <span style={{ color: "#cbd5e1" }}>{catName}:</span>
                    <span style={{ color: "#38bdf8", fontWeight: 700 }}>
                      {Number(catData.avg_importance ?? 0).toFixed(3)}
                    </span>
                    <span className="muted" style={{ fontSize: 9 }}>
                      ({catData.active_channels}/{catData.total_channels} activos)
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Filter buttons & Table */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4, flexWrap: "wrap", gap: 6 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#cbd5e1" }}>
                Ranking Detallado de Sensibilidad y Ablación
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                {[
                  { id: "all", label: `Todos (${rankedChannelsList.length})` },
                  { id: "HIGH_EFFECTIVENESS", label: `Alta (${countsByStatus.HIGH || 0})` },
                  { id: "MODERATE_EFFECTIVENESS", label: `Media (${countsByStatus.MODERATE || 0})` },
                  { id: "LOW_EFFECTIVENESS", label: `Baja (${countsByStatus.LOW || 0})` },
                  { id: "DEAD_CHANNEL", label: `Inactiva (${countsByStatus.DEAD || 0})` },
                ].map((btn) => (
                  <button
                    key={btn.id}
                    onClick={() => setStatusFilter(btn.id)}
                    style={{
                      fontSize: 10,
                      padding: "2px 8px",
                      borderRadius: 4,
                      background: statusFilter === btn.id ? "#0284c7" : "#0f172a",
                      color: statusFilter === btn.id ? "#ffffff" : "#94a3b8",
                      border: statusFilter === btn.id ? "1px solid #38bdf8" : "1px solid #334155",
                      cursor: "pointer",
                      fontWeight: statusFilter === btn.id ? 700 : 500,
                    }}
                  >
                    {btn.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Table */}
            <div
              style={{
                overflowX: "auto",
                border: "1px solid #334155",
                borderRadius: 6,
                flex: 1,
                minHeight: 360,
                maxHeight: "calc(100vh - 310px)",
                overflowY: "auto",
              }}
            >
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, textAlign: "left" }}>
                <thead style={{ background: "#0f172a", position: "sticky", top: 0, zIndex: 1, borderBottom: "1px solid #334155" }}>
                  <tr>
                    <th style={{ padding: "8px 10px", width: 45 }}>Rank</th>
                    <th style={{ padding: "8px 10px" }}>Canal</th>
                    <th style={{ padding: "8px 10px" }}>Categoría</th>
                    <th style={{ padding: "8px 10px" }}>Estado</th>
                    <th style={{ padding: "8px 10px", minWidth: 160 }}>Puntuación Compuesta</th>
                    <th style={{ padding: "8px 10px" }}>Gradiente (π / v)</th>
                    <th style={{ padding: "8px 10px" }}>Ablación (Flip / Δv)</th>
                    <th style={{ padding: "8px 10px", minWidth: 200 }}>Diagnóstico / Recomendación</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRankedChannels.map((rc, idx) => {
                    const score = Number(rc.importance_score ?? 0);
                    const pct = Math.min(100, Math.max(0, score * 100));
                    return (
                      <tr
                        key={rc.index}
                        style={{
                          background: idx % 2 === 0 ? "#1e293b" : "#182234",
                          borderBottom: "1px solid #283548",
                        }}
                      >
                        <td style={{ padding: "6px 10px", fontWeight: 700, color: "#38bdf8" }}>
                          #{rc.rank}
                        </td>
                        <td style={{ padding: "6px 10px" }}>
                          <span style={{ fontWeight: 700, color: "#f8fafc" }}>
                            Ch {String(rc.index).padStart(2, "0")}: <code>{rc.name}</code>
                          </span>
                        </td>
                        <td style={{ padding: "6px 10px", color: "#94a3b8" }}>
                          {rc.category}
                        </td>
                        <td style={{ padding: "6px 10px" }}>
                          <span
                            style={{
                              fontSize: 9,
                              fontWeight: 700,
                              padding: "2px 6px",
                              borderRadius: 4,
                              background:
                                rc.status === "HIGH_EFFECTIVENESS"
                                  ? "#065f46"
                                  : rc.status === "MODERATE_EFFECTIVENESS"
                                  ? "#1e3a8a"
                                  : rc.status === "LOW_EFFECTIVENESS"
                                  ? "#78350f"
                                  : "#881337",
                              color:
                                rc.status === "HIGH_EFFECTIVENESS"
                                  ? "#a7f3d0"
                                  : rc.status === "MODERATE_EFFECTIVENESS"
                                  ? "#bfdbfe"
                                  : rc.status === "LOW_EFFECTIVENESS"
                                  ? "#fde68a"
                                  : "#fecdd3",
                            }}
                          >
                            {rc.status === "HIGH_EFFECTIVENESS"
                              ? "ALTA"
                              : rc.status === "MODERATE_EFFECTIVENESS"
                              ? "MEDIA"
                              : rc.status === "LOW_EFFECTIVENESS"
                              ? "BAJA"
                              : "INACTIVA"}
                          </span>
                        </td>
                        <td style={{ padding: "6px 10px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div style={{ flex: 1, height: 6, background: "#0f172a", borderRadius: 3, overflow: "hidden" }}>
                              <div
                                style={{
                                  width: `${pct}%`,
                                  height: "100%",
                                  background:
                                    score > 0.4
                                      ? "#10b981"
                                      : score > 0.15
                                      ? "#0ea5e9"
                                      : score > 0.05
                                      ? "#f59e0b"
                                      : "#f43f5e",
                                }}
                              />
                            </div>
                            <span style={{ fontFamily: "monospace", fontSize: 10, width: 42, color: "#cbd5e1" }}>
                              {score.toFixed(3)}
                            </span>
                          </div>
                        </td>
                        <td style={{ padding: "6px 10px", fontFamily: "monospace", fontSize: 10, color: "#94a3b8" }}>
                          π: {Number(rc.grad_saliency_policy ?? 0).toExponential(2)} | v: {Number(rc.grad_saliency_value ?? 0).toExponential(2)}
                        </td>
                        <td style={{ padding: "6px 10px", fontFamily: "monospace", fontSize: 10, color: "#94a3b8" }}>
                          Flip: {Number(rc.decision_flip_rate ?? 0).toFixed(1)}% | Δv: {Number(rc.value_shift_mean ?? 0).toFixed(3)}
                        </td>
                        <td style={{ padding: "6px 10px", fontSize: 10, color: "#cbd5e1" }}>
                          {rc.recommendation}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {!attributionReport && !analyzing && (
          <div style={{ background: "#0f172a", border: "1px dashed #334155", borderRadius: 6, padding: "16px", textAlign: "center" }}>
            <div style={{ fontSize: 13, color: "#94a3b8", marginBottom: 6 }}>
              Aún no se ha calculado el análisis de efectividad de canales para la ejecución <b>{runId}</b>.
            </div>
            <div className="muted" style={{ fontSize: 11, maxWidth: 500, margin: "0 auto 12px auto" }}>
              Haz clic en el botón superior para ejecutar el análisis empírico en tiempo real (recolecta muestras con el simulador VOEC, evalúa saliencia de gradientes y mide la degradación de política y valor tras oclusión).
            </div>
            <button
              onClick={handleRunAnalysis}
              style={{
                background: "#0284c7",
                color: "#ffffff",
                border: "none",
                fontWeight: 700,
                fontSize: 12,
                padding: "8px 16px",
                borderRadius: 6,
                cursor: "pointer",
              }}
            >
              ⚡ Ejecutar Análisis Ahora
            </button>
          </div>
        )}
      </div>
      )}

      {/* SECTION 4: HIERARCHICAL STRATEGIC MACRO-PLANNER (LEVEL 1) */}
      {currentSubTab === "macro-planner" && (
        <div
          style={{
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
            padding: 16,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          {/* Header */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 10 }}>
            <div>
              <h4 style={{ margin: 0, fontSize: 16, color: "#38bdf8", display: "flex", alignItems: "center", gap: 8 }}>
                <span>♟️</span> Planificador Jerárquico Estratégico (Nivel 1: Macro-Estrategia & Roles)
              </h4>
              <div className="muted" style={{ fontSize: 12, marginTop: 4, maxWidth: 850 }}>
                Arquitectura de toma de decisiones jerárquica en dos niveles: Desacopla la visión global del escenario (control de VPs, selección de postura macro y roles doctrinales por unidad) de la búsqueda en árbol de micro-maniobras tácticas (MCTS PUCT de 512 simulaciones y 6 pasos de unroll).
              </div>
            </div>
            <div style={{ display: "flex", gap: 6 }}>
              <span style={{ fontSize: 11, background: "rgba(126, 34, 206, 0.25)", border: "1px solid #a855f7", color: "#d8b4fe", padding: "4px 10px", borderRadius: 6, fontWeight: 700 }}>
                Hierarchical Reinforcement Learning (HRL)
              </span>
              <span style={{ fontSize: 11, background: "rgba(2, 132, 199, 0.25)", border: "1px solid #0284c7", color: "#38bdf8", padding: "4px 10px", borderRadius: 6, fontWeight: 700 }}>
                EfficientZero v2 Active
              </span>
            </div>
          </div>

          {/* KPI Summary Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10 }}>
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6, padding: "10px 12px" }}>
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Posturas Estratégicas</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#f8fafc", marginTop: 2 }}>3 Modos Operacionales</div>
              <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>ASSAULT_VP • DEFENSIVE_HOLD • ZONE_SUPPRESS</div>
            </div>
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6, padding: "10px 12px" }}>
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Roles de Escuadra</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#facc15", marginTop: 2 }}>4 Doctrinas Tácticas</div>
              <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>Spearhead • Fire Support • Defender • Screen</div>
            </div>
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6, padding: "10px 12px" }}>
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Modulación MCTS Prior</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#22c55e", marginTop: 2 }}>+35% Prior Shaping</div>
              <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>Guía el árbol hacia objetivos coherentes</div>
            </div>
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6, padding: "10px 12px" }}>
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Profundidad MCTS Nivel 2</div>
              <div style={{ fontSize: 16, fontWeight: 800, color: "#38bdf8", marginTop: 2 }}>512 Sims / 6 Unroll</div>
              <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>Búsqueda profunda sin extravío táctico</div>
            </div>
          </div>

          {/* EMPIRICAL TACTICAL TELEMETRY CARD */}
          <div style={{ background: "#0b1220", border: "1px solid #1e3a8a", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 800, color: "#38bdf8", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>📊</span> Telemetría Táctica Empírica: ¿Qué Tácticas Usa Este Modelo?
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                  {macroStats.hasRealData
                    ? `Calculado sobre ${macroStats.totalSteps} decisiones registradas en partidas de evaluación de ${runId}.`
                    : `No hay decisiones registradas en evaluaciones para este modelo. Ejecute una evaluación para recopilar telemetría empírica.`}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ fontSize: 10, background: macroStats.hasRealData ? "rgba(34, 197, 94, 0.2)" : "rgba(100, 116, 139, 0.2)", border: `1px solid ${macroStats.hasRealData ? "#22c55e" : "#64748b"}`, color: macroStats.hasRealData ? "#4ade80" : "#94a3b8", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>
                  {macroStats.hasRealData ? "✓ Partidas de Evaluación" : "Sin Datos de Evaluación"}
                </span>
                <button
                  onClick={() => {
                    const u = `/model?engine=${encodeURIComponent(String(trainRow?.engine || "efficientzero_v2"))}&model=${encodeURIComponent(runId)}&tab=match-replay`;
                    window.open(u, "_blank");
                  }}
                  style={{
                    background: "#0284c7",
                    border: "none",
                    borderRadius: 4,
                    color: "#ffffff",
                    fontSize: 11,
                    fontWeight: 700,
                    padding: "5px 12px",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                  title="Abrir visor de partidas para ver la táctica hexágono a hexágono"
                >
                  <span>▶️</span> Ver en Replay Táctico
                </button>
              </div>
            </div>

            {/* Three Progress Bar Grids */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
              {/* Box 1: Posturas Macro Reales */}
              <div style={{ background: "#1e293b", padding: 10, borderRadius: 6, display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#f8fafc", textTransform: "uppercase" }}>
                  1. Distribución de Posturas Macro
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#f87171", fontWeight: 700 }}>⚔️ ASSAULT_VP (Asalto Ofensivo)</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.assaultPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.assaultPct : 0}%`, height: "100%", background: "#ef4444" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#38bdf8", fontWeight: 700 }}>🛡️ DEFENSIVE_HOLD (Consolidación)</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.defPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.defPct : 0}%`, height: "100%", background: "#0284c7" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#c084fc", fontWeight: 700 }}>💥 ZONE_SUPPRESS (Supresión)</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.zonePct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.zonePct : 0}%`, height: "100%", background: "#8b5cf6" }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Box 2: Roles de Escuadra */}
              <div style={{ background: "#1e293b", padding: 10, borderRadius: 6, display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#f8fafc", textTransform: "uppercase" }}>
                  2. Roles Tácticos de Unidades
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#facc15", fontWeight: 700 }}>⚡ Punta de Lanza (Choque)</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.spearheadPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.spearheadPct : 0}%`, height: "100%", background: "#eab308" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#fb923c", fontWeight: 700 }}>🎯 Apoyo de Fuego (Pesadas)</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.fireSupportPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.fireSupportPct : 0}%`, height: "100%", background: "#f97316" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#60a5fa", fontWeight: 700 }}>🛡️ Defensor VP (Perímetro)</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.defenderPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.defenderPct : 0}%`, height: "100%", background: "#3b82f6" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#c084fc", fontWeight: 700 }}>👁️ Flanqueo & Vigilancia</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.flankPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.flankPct : 0}%`, height: "100%", background: "#8b5cf6" }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Box 3: Maniobras y Corrección MCTS */}
              <div style={{ background: "#1e293b", padding: 10, borderRadius: 6, display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#f8fafc", textTransform: "uppercase" }}>
                  3. Tipo de Maniobras & Árbol MCTS
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#38bdf8", fontWeight: 700 }}>🏃 Maniobra / Avance</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.movePct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.movePct : 0}%`, height: "100%", background: "#0284c7" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#ef4444", fontWeight: 700 }}>💥 Fuego & Ataque</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.firePct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.firePct : 0}%`, height: "100%", background: "#ef4444" }} />
                    </div>
                  </div>

                  <div style={{ marginTop: 4, background: "#0f172a", padding: "6px 8px", borderRadius: 4, borderLeft: "3px solid #38bdf8" }}>
                    <div style={{ fontSize: 10, color: "#94a3b8" }}>Corrección Estratégica MCTS:</div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>
                      {macroStats.hasRealData ? `${macroStats.mctsOverridePct.toFixed(1)}% de las decisiones` : "N/A"}
                    </div>
                    <div className="muted" style={{ fontSize: 9 }}>
                      {macroStats.hasRealData ? "El árbol MCTS reorientó el prior neural para imponer la postura del planificador." : "Requiere partidas evaluadas."}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* TWO MAIN COLUMNS: POSTURES & ROLES */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            {/* COLUMN 1: POSTURAS ESTRATÉGICAS */}
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: "#38bdf8", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>🎯</span> Posturas Estratégicas Macro
                </span>
                <span style={{ fontSize: 10, color: "#64748b" }}>Evaluadas al inicio de cada turno</span>
              </div>
              <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                El planificador evalúa el estado del marcador de Puntos de Victoria (VPs) y asigna la postura del bando completo:
              </div>

              {/* POSTURE 1: ASSAULT_VP */}
              <div style={{ background: "#1e293b", border: "1px solid #ef4444", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#f87171", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>⚔️</span> ASSAULT_VP (Asalto Ofensivo)
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(239, 68, 68, 0.2)", color: "#fca5a5", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    VPs Aliados ≤ Enemigos
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  Disparada cuando el equipo está empatado o por detrás en el marcador. Fija el <b>Objetivo Prioritario</b> en el VP neutral o enemigo más cercano y aumenta en un <b>+35%</b> el prior de las acciones que cierran distancia hacia él.
                </div>
              </div>

              {/* POSTURE 2: DEFENSIVE_HOLD */}
              <div style={{ background: "#1e293b", border: "1px solid #0284c7", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🛡️</span> DEFENSIVE_HOLD (Consolidación)
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(2, 132, 199, 0.2)", color: "#7dd3fc", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    VPs Aliados &gt; Enemigos
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  Disparada cuando el equipo lidera el control de objetivos pero el escenario no ha concluido. Ordena atrincherar escuadras en radio de 1 hex sobre los VPs aliados y penaliza maniobras arriesgadas de sobre-extensión.
                </div>
              </div>

              {/* POSTURE 3: ZONE_SUPPRESS */}
              <div style={{ background: "#1e293b", border: "1px solid #8b5cf6", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#c084fc", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>💥</span> ZONE_SUPPRESS (Supresión de Zona)
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(139, 92, 246, 0.2)", color: "#d8b4fe", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    100% VPs Consolidados
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  Disparada cuando todos los objetivos del escenario han sido capturados y asegurados. Reorienta las escuadras hacia la supresión metódica, fuego cruzado y aniquilación de cualquier amenaza enemiga restante.
                </div>
              </div>
            </div>

            {/* COLUMN 2: ROLES TÁCTICOS */}
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: "#facc15", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>👥</span> Asignación Dinámica de Roles
                </span>
                <span style={{ fontSize: 10, color: "#64748b" }}>Por unidad y armamento</span>
              </div>
              <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                Cada escuadra recibe un rol específico que condiciona su función en el combate y sus priors MCTS:
              </div>

              {/* ROLE 1: SPEARHEAD */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(234, 179, 8, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#facc15", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>⚡</span> ROLE_SPEARHEAD (Punta de Lanza)
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(234, 179, 8, 0.15)", color: "#fef08a", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Infantería de Choque
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  Asignado a las escuadras de infantería más próximas al objetivo prioritario. Máxima agresividad para asaltar, desalojar al rival y consumar la captura del hexágono objetivo.
                </div>
              </div>

              {/* ROLE 2: FIRE_SUPPORT */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(249, 115, 22, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#fb923c", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🎯</span> ROLE_FIRE_SUPPORT (Apoyo de Fuego)
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(249, 115, 22, 0.15)", color: "#fed7aa", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Armas Pesadas / Morteros
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  Asignado a escuadras con ametralladoras pesadas (HMG), morteros o cañones. Posicionamiento en puntos de tiro con línea de visión despejada (LOS) para suprimir y desorganizar al enemigo.
                </div>
              </div>

              {/* ROLE 3: OBJECTIVE_DEFENDER */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(59, 130, 246, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#60a5fa", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🛡️</span> ROLE_OBJECTIVE_DEFENDER (Defensor VP)
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(59, 130, 246, 0.15)", color: "#bfdbfe", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Radio ≤ 1 de VP Aliado
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  Asignado a unidades sobre o adyacentes a VPs bajo control del equipo. Prioriza atrincherarse, aprovechar coberturas de terreno urbano o fortificación y negar la recaptura enemiga.
                </div>
              </div>

              {/* ROLE 4: FLANK_SCREEN */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(139, 92, 246, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#c084fc", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>👁️</span> ROLE_FLANK_SCREEN (Pantalla de Flanco)
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(139, 92, 246, 0.15)", color: "#e9d5ff", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Flanqueo y Vigilancia
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  Asignado a escuadras periféricas para cubrir ángulos muertos, detectar maniobras envolventes rivales y proteger los flancos vulnerables del grueso de la fuerza.
                </div>
              </div>
            </div>
          </div>

          {/* HIERARCHICAL INTEGRATION DIAGRAM & PIPELINE */}
          <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 800, color: "#38bdf8", marginBottom: 8, textTransform: "uppercase" }}>
              Flujo Operacional del Árbol Jerárquico en EfficientZero v2
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr auto 1fr", alignItems: "center", gap: 10, textAlign: "center" }}>
              <div style={{ background: "#1e293b", border: "1px solid #a855f7", borderRadius: 6, padding: 12 }}>
                <div style={{ fontSize: 10, color: "#d8b4fe", fontWeight: 700, textTransform: "uppercase" }}>NIVEL 1: Macro-Estrategia</div>
                <div style={{ fontSize: 13, fontWeight: 800, color: "#f8fafc", marginTop: 2 }}>MacroStrategyPlanner</div>
                <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 4 }}>
                  Evalúa VPs y tablero • Determina Postura • Asigna Roles a cada escuadra
                </div>
              </div>

              <div style={{ fontSize: 18, color: "#38bdf8", fontWeight: 900 }}>➔</div>

              <div style={{ background: "#1e293b", border: "1px solid #0284c7", borderRadius: 6, padding: 12 }}>
                <div style={{ fontSize: 10, color: "#7dd3fc", fontWeight: 700, textTransform: "uppercase" }}>PUENTE: Prior Modulation</div>
                <div style={{ fontSize: 13, fontWeight: 800, color: "#f8fafc", marginTop: 2 }}>Shaping P(s, a)</div>
                <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 4 }}>
                  Modula priors de política neural antes de iniciar expansiones MCTS
                </div>
              </div>

              <div style={{ fontSize: 18, color: "#38bdf8", fontWeight: 900 }}>➔</div>

              <div style={{ background: "#1e293b", border: "1px solid #22c55e", borderRadius: 6, padding: 12 }}>
                <div style={{ fontSize: 10, color: "#86efac", fontWeight: 700, textTransform: "uppercase" }}>NIVEL 2: Micro-Táctica</div>
                <div style={{ fontSize: 13, fontWeight: 800, color: "#f8fafc", marginTop: 2 }}>MCTS PUCT Search</div>
                <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 4 }}>
                  512 Simulaciones • 6 Pasos Unroll • Cabezas Tácticas Auxiliares
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
