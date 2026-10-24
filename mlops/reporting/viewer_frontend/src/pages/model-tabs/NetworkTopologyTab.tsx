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
  { idx: 0, name: "ally_presence", cat: "units", desc: "1.0 in hexes occupied by active friendly units." },
  { idx: 1, name: "enemy_presence", cat: "units", desc: "1.0 in hexes with detected enemy units." },
  { idx: 2, name: "ally_hp_norm", cat: "units", desc: "Normalized HP [0-1] of friendly squads based on max_strength." },
  { idx: 3, name: "enemy_hp_norm", cat: "units", desc: "Normalized HP [0-1] of enemy squads based on max_strength." },
  { idx: 4, name: "ally_crossfire_risk", cat: "units", desc: "Enemy crossfire risk on friendly units / friendly suppression state." },
  { idx: 5, name: "enemy_target_engagement", cat: "units", desc: "Enemy hexes with friendly targets in weapon range / enemy suppression state." },
  { idx: 6, name: "vp_contest_race", cat: "vp", desc: "Differential advantage in VP race: >0 if friendly arrives first, <0 if enemy leads." },
  { idx: 7, name: "reaction_fire_threat", cat: "units", desc: "Continuous heatmap of enemy threat and reaction fire (overwatch/opportunity fire)." },
  { idx: 8, name: "ally_heavy_mg_support", cat: "units", desc: "1.0 for friendly heavy and medium machine guns (HMG, MMG, MG42)." },
  { idx: 9, name: "enemy_heavy_mg_support", cat: "units", desc: "1.0 for enemy heavy and medium machine guns (HMG, MMG, MG42)." },
  { idx: 10, name: "ally_indirect_mortar", cat: "units", desc: "1.0 for friendly indirect fire weapons / mortars (50mm, 60mm, 81mm)." },
  { idx: 11, name: "local_firepower_balance", cat: "units", desc: "Local firepower balance [+1 friendly dominant, 0 contested, -1 enemy dominant]." },
  { idx: 12, name: "map_playable", cat: "terrain", desc: "1.0 in playable map hexes; 0.0 on out-of-bounds map borders." },
  { idx: 13, name: "vp_mask", cat: "vp", desc: "1.0 in hexes designated as Victory Points (VPs)." },
  { idx: 14, name: "vp_owner_relative", cat: "vp", desc: "+1.0 friendly controlled, -1.0 enemy controlled, 0.0 contested/neutral." },
  { idx: 15, name: "terrain_move_cost_norm", cat: "terrain", desc: "Movement point cost (road = low, forest/hill = high)." },
  { idx: 16, name: "terrain_cover_norm", cat: "terrain", desc: "Defensive cover bonus (urban stone buildings = 0.5+)." },
  { idx: 17, name: "terrain_los_block", cat: "terrain", desc: "Line of sight block due to elevation or dense terrain/structures." },
  { idx: 18, name: "vp_distance_field", cat: "vp", desc: "Continuous radial proximity field to nearest VP (1 / (1 + dist))." },
  { idx: 19, name: "q_coord_norm", cat: "hex", desc: "Normalized axial Q coordinate [-1, 1]." },
  { idx: 20, name: "r_coord_norm", cat: "hex", desc: "Normalized axial R coordinate [-1, 1]." },
  { idx: 21, name: "frontline_control", cat: "hex", desc: "Territorial potential field [-1, +1] (frontline diffusion and area control)." },
  { idx: 22, name: "ally_mobility_norm", cat: "units", desc: "Remaining available movement points of the active squad." },
  { idx: 23, name: "enemy_indirect_mortar", cat: "units", desc: "1.0 for enemy indirect fire weapons / mortars (50mm, 8cm)." },
  { idx: 24, name: "ally_direct_range_norm", cat: "units", desc: "Direct fire range and projected 2D optimal combat footprint for friendly squad." },
  { idx: 25, name: "enemy_direct_range_norm", cat: "units", desc: "Direct fire range and projected 2D optimal combat footprint for enemy squad." },
  { idx: 26, name: "ally_fire_coverage", cat: "units", desc: "Heatmap of friendly direct fire coverage over each board hex." },
  { idx: 27, name: "heavy_fortifications", cat: "terrain", desc: "Heavy fortifications: +1.0 bunker/pillbox, +0.70 trench/gun pit, +0.40 sandbag/defensive stone urban." },
  { idx: 28, name: "ally_attack_power_norm", cat: "units", desc: "Friendly offensive combat firepower (normalized combat dice weight)." },
  { idx: 29, name: "hazard_mines_and_wire", cat: "terrain", desc: "Terrain hazards and obstacles: +1.0 minefields, +0.60 barbed wire entanglements." },
  { idx: 30, name: "ally_defense_power_norm", cat: "units", desc: "Defensive capability of friendly squads (normalized defense dice weight)." },
  { idx: 31, name: "enemy_defense_power_norm", cat: "units", desc: "Defensive capability of enemy squads (normalized defense dice weight)." },
  { idx: 32, name: "ally_doctrine_role", cat: "units", desc: "Continuous encoding of friendly doctrinal role (Spearhead=1.0, Fire Support=0.75, Recon=0.50, Screen=0.25, Command=0.10)." },
  { idx: 33, name: "enemy_doctrine_role", cat: "units", desc: "Continuous encoding of projected enemy doctrinal role (Spearhead=1.0, Fire Support=0.75, Recon=0.50, Screen=0.25)." },
  { idx: 34, name: "ally_optimal_footprint", cat: "units", desc: "Projected 2D optimal combat range footprint for friendly forces across the board." },
  { idx: 35, name: "enemy_optimal_footprint", cat: "units", desc: "Projected 2D optimal combat range footprint for enemy forces across the board." },
  { idx: 36, name: "turn_urgency_pressure", cat: "global", desc: "Continuous temporal pressure (t/T) and radial urgency field amplified towards unconquered VPs." },
  { idx: 37, name: "paralysis_exposure_risk", cat: "units", desc: "Paralysis exposure risk heatmap: friendly squads exposed in open terrain without cover, maneuver, or fire." },
];

export function NetworkTopologyTab({
  trainRow,
  trainSummary,
  evalRows = [],
  activeSubTab,
  onSubTabChange,
  onNavigateToHeadDiagnostics,
}: {
  trainRow: TrainRow | null;
  trainSummary: Dict | null;
  evalRows?: EvalRow[];
  activeSubTab?: "diagram" | "channel-attribution" | "macro-planner";
  onSubTabChange?: (tab: "diagram" | "channel-attribution" | "macro-planner") => void;
  onNavigateToHeadDiagnostics?: () => void;
}) {
  const [internalSubTab, setInternalSubTab] = useState<"diagram" | "channel-attribution" | "macro-planner">("diagram");
  const currentSubTab = activeSubTab ?? internalSubTab;
  const setSubTab = (tab: "diagram" | "channel-attribution" | "macro-planner") => {
    setInternalSubTab(tab);
    onSubTabChange?.(tab);
  };
  const [diagramSize, setDiagramSize] = useState<"compact" | "balanced" | "expanded">("balanced");
  const isCompact = diagramSize === "compact";
  const [unrollStep, setUnrollStep] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string>("representation");
  const [channelFilter, setChannelFilter] = useState<string>("all");
  const [isExportingOnnx, setIsExportingOnnx] = useState(false);
  const [onnxExportResult, setOnnxExportResult] = useState<any | null>(null);
  const [onnxError, setOnnxError] = useState<string | null>(null);
  const [copiedFolder, setCopiedFolder] = useState(false);

  const handleOpenFolder = async () => {
    if (!onnxExportResult?.run_id) return;
    try {
      await fetch(`/api/model/open-folder?run_id=${encodeURIComponent(onnxExportResult.run_id)}`);
    } catch (err) {
      console.warn('Failed to trigger open folder:', err);
    }
  };

  const handleCopyFolder = () => {
    if (!onnxExportResult?.export_dir) return;
    navigator.clipboard?.writeText(onnxExportResult.export_dir);
    setCopiedFolder(true);
    setTimeout(() => setCopiedFolder(false), 2000);
  };

  const handleSaveFileWithPicker = async (downloadUrl: string, fileName: string) => {
    if (typeof (window as any).showSaveFilePicker === 'function') {
      try {
        const handle = await (window as any).showSaveFilePicker({
          suggestedName: fileName,
          types: [
            {
              description: 'ONNX Neural Network Model (*.onnx)',
              accept: { 'application/octet-stream': ['.onnx'] },
            },
          ],
        });
        const res = await fetch(downloadUrl);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        return;
      } catch (err: any) {
        if (err.name === 'AbortError') {
          return;
        }
        console.warn('showSaveFilePicker failed, using fallback:', err);
      }
    }
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  // Dynamic parameters extracted from the selected train execution
  const runId = String(trainRow?.run_id || "execution");

  const handleExportOnnx = async () => {
    setIsExportingOnnx(true);
    setOnnxError(null);
    try {
      const res = await fetch(`/api/model/export-onnx?run_id=${encodeURIComponent(runId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: runId }),
      });
      const data = await res.json();
      if (data.ok) {
        setOnnxExportResult(data);
      } else {
        setOnnxError(data.error || data.message || "Failed to export ONNX model.");
      }
    } catch (err: any) {
      setOnnxError(err?.message || "Network error while exporting ONNX.");
    } finally {
      setIsExportingOnnx(false);
    }
  };
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

  const inChannels = Number(modelCfg.observation_channels || cfg.observation_channels || 38) || 38;
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
  const enableMultitask = Boolean(modelCfg.enable_multitask ?? cfg.enable_multitask ?? true);
  const numTasks = Number(modelCfg.num_tasks ?? cfg.num_tasks ?? 16) || 16;
  const taskEmbedDim = Number(modelCfg.task_embedding_dim ?? cfg.task_embedding_dim ?? 32) || 32;
  const enableHierarchicalGoals = Boolean(modelCfg.enable_hierarchical_goals ?? cfg.enable_hierarchical_goals ?? true);
  const numGoalModes = Number(modelCfg.num_goal_modes ?? cfg.num_goal_modes ?? 4) || 4;

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
        throw new Error(String(res?.error || "Failed to process channel effectiveness analysis"));
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
    let reconCount = 0;
    let closeDefCount = 0;
    let reserveCount = 0;
    let recoverCount = 0;
    let mutatedCount = 0;
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
          const role = String(s.unit_macro_role || s.role_assigned || s.unit_doctrine_role || "").toUpperCase();
          const action = String(s.action_id || s.action || "").toUpperCase();

          if (s.policy_overridden_by_mcts) mctsOverrideCount += 1;

          if (
            Boolean(s.is_mutated) ||
            Boolean(s.role_is_mutated) ||
            Boolean(s.doctrine_mutation) ||
            (s.role_mutation_reason && s.role_mutation_reason !== "DEFAULT_PROFILE") ||
            (s.mutation_trigger && s.mutation_trigger !== "DEFAULT_PROFILE")
          ) {
            mutatedCount += 1;
          }

          if (action.startsWith("FIRE") || action.startsWith("ATTACK")) fireCount += 1;
          else if (action.startsWith("MOVE")) moveCount += 1;
          else if (action.startsWith("OPPORTUNITY")) oppCount += 1;

          if (posture === "DEFENSIVE_HOLD") defCount += 1;
          else if (posture === "ZONE_SUPPRESS") zoneCount += 1;
          else if (posture === "ASSAULT_VP" || posture === "ASSAULT") assaultCount += 1;

          if (role.includes("FIRE_SUPPORT")) fireSupportCount += 1;
          else if (role.includes("CLOSE_DEFENSE")) closeDefCount += 1;
          else if (role.includes("DEFENDER") || role.includes("OBJECTIVE_DEFENDER")) defenderCount += 1;
          else if (role.includes("RECON")) reconCount += 1;
          else if (role.includes("RESERVE") || role.includes("TACTICAL_RESERVE")) reserveCount += 1;
          else if (role.includes("RECOVER")) recoverCount += 1;
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
      reconPct: totalSteps > 0 ? (reconCount / totalSteps) * 100 : 0.0,
      closeDefPct: totalSteps > 0 ? (closeDefCount / totalSteps) * 100 : 0.0,
      reservePct: totalSteps > 0 ? (reserveCount / totalSteps) * 100 : 0.0,
      recoverPct: totalSteps > 0 ? (recoverCount / totalSteps) * 100 : 0.0,
      mutatedPct: totalSteps > 0 ? (mutatedCount / totalSteps) * 100 : 0.0,
      mutatedCount,
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
        role: "Sensory input tensor extracted from the VOEC hexagonal tactical simulator at timestep t.",
        inShape: `B × ${inChannels} channels × ${boardH} × ${boardW} hexes`,
        outShape: `B × ${inChannels} × ${boardH} × ${boardW}`,
        architecture: [
          `Channels 0-5: Friendly/Enemy presence, normalized HP, crossfire risk, and suppression state`,
          `Channels 6-11: VP contest race, reaction threat, HMG support, indirect mortars, and firepower balance`,
          `Channels 12-18: Playable hex mask, terrain movement costs, cover bonuses, LOS blocking, and radial VP field`,
          `Channels 19-20: Normalized axial coordinates (q, r)`,
          `Channels 21-25: Frontline potential, remaining mobility, and 2D optimal direct combat range footprint`,
          `Channels 26-31: Friendly fire coverage heatmap, heavy fortifications, and offensive/defensive combat dice weights`,
          `Channels 32-35: Continuous friendly/enemy doctrinal roles and projected optimal engagement footprints`,
          `Channels 36-37: Temporal turn urgency pressure (t/T) and paralysis exposure risk in open terrain`
        ],
        paramEstimate: "0 parameters (Environment Sensory Feed)",
        receptiveField: `${boardH}×${boardW} Hexes (Full Board Resolution)`,
        details: `Dense feature tensor constructed by VOEC adapter with ${boardH}×${boardW} spatial resolution. Dynamically configured with ${inChannels} input channels for run ${runId}.`,
      },
      representation: {
        id: "representation",
        name: "Representation Network h_θ(o)",
        math: `h_\\theta(o_t) \\to s_0`,
        role: `Observation encoder (${encoderType.toUpperCase()}). Projects the raw 38-channel tactical board into a continuous ${hiddenDim}-dimensional latent state.`,
        inShape: `B × ${inChannels} × ${boardH} × ${boardW}`,
        outShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        architecture: isV2Optimized
          ? [
              `Conv2d(${inChannels}, ${hiddenDim}, kernel_size=3, padding=1)`,
              `GroupNorm(num_groups=4, num_channels=${hiddenDim}) + SiLU`,
              ...Array.from({ length: dynamicsBlocks }, (_, i) =>
                `ResidualBlock ${i + 1}: Conv3x3(${hiddenDim}) -> GroupNorm -> SiLU -> Conv3x3 -> GroupNorm + Squeeze-and-Excitation (SE gating, r=4)`
              ),
              "Min-Max Latent Scaling: s_norm = (s - min) / (max - min + ε)",
              enableMultitask ? "FiLMLayer Hook: Ready for Multi-Task scenario modulation" : "Monotask Representation Backbone"
            ]
          : [
              `Conv2d(${inChannels}, ${hiddenDim}, kernel_size=3, padding=1)`,
              `LayerNorm2d(${hiddenDim}) + ReLU`,
              ...Array.from({ length: dynamicsBlocks }, (_, i) =>
                `ResidualBlock ${i + 1}: Conv3x3(${hiddenDim}) -> LayerNorm -> ReLU -> Conv3x3(${hiddenDim})`
              ),
              "Additive Residual Skip Connections (Legacy v1, without SE)"
            ],
        paramEstimate: `~${repParams.toLocaleString()} parameters`,
        receptiveField: `~${repReceptive}×${repReceptive} Hexes (${dynamicsBlocks} convolutional 3×3 blocks)`,
        details: isV2Optimized
          ? `V2 architecture with GroupNorm, smooth SiLU activation, and Squeeze-and-Excitation (SE) channel gating to weight critical tactical features. Normalizes latent manifold with canonical Min-Max scaling.`
          : `Classic V1 architecture with dense residual blocks without SE channel modulation.`,
      },
      task_conditioning: {
        id: "task_conditioning",
        name: "Task Conditioning & FiLM Module (EZ-M)",
        math: `e_\\tau = \\text{TaskEmbed}(\\tau, c_\\tau) \\implies \\text{FiLM}(x, e_\\tau) = (1 + \\gamma(e_\\tau)) \\odot x + \\beta(e_\\tau)`,
        role: "Multi-Task Model-Based RL (EZ-M): Decouples universal combat physics from scenario-specific goals via Feature-wise Linear Modulation with zero-init identity preservation.",
        inShape: `Task ID \\tau \\in \\{0..${numTasks - 1}\\} + Topography Context c_\\tau \\in \\mathbb{R}^5`,
        outShape: `Embedding e_\\tau \\in \\mathbb{R}^{${taskEmbedDim}} \\to \\text{Modulation } (\\gamma, \\beta)`,
        architecture: [
          `Task Embedding: Embedding(${numTasks}, ${taskEmbedDim})`,
          `Context Projection: Linear(5 + ${taskEmbedDim}, ${taskEmbedDim}) -> SiLU`,
          `Zero-Init FiLM Projections: Linear(${taskEmbedDim}, ${hiddenDim}) [Weights & Biases = 0]`,
          "Identity Preservation: FiLM(x, 0) = x (Zero distortion on single-task/unconditioned inference)",
          "Stratified Multi-Task Replay Buffer (Balanced sampling across all 38 scenarios)"
        ],
        paramEstimate: `~${((numTasks * taskEmbedDim) + (5 + taskEmbedDim) * taskEmbedDim + taskEmbedDim * hiddenDim * 2).toLocaleString()} parameters`,
        receptiveField: "Global / Cross-Scenario Conditioned",
        details: "Prevents catastrophic forgetting when transitioning between open terrain and dense urban assault. The world model learns universal combat physics while FiLM modulates value and policy objectives per scenario.",
      },
      latent: {
        id: "latent",
        name: "Latent State s_t",
        math: `s_t \\in \\mathbb{R}^{B \\times ${hiddenDim} \\times ${boardH} \\times ${boardW}}`,
        role: `Compact latent spatial state (${hiddenDim} channels). Abstract state representation upon which MCTS plans without interacting with the physical game engine.`,
        inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        outShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        architecture: isV2Optimized
          ? [
              `${hiddenDim} spatial latent feature channels on ${boardH}×${boardW}`,
              "Canonical EfficientZero Min-Max normalization per sample",
              "Guaranteed norm stability across deep temporal rollouts"
            ]
          : [
              `${hiddenDim} latent feature channels`,
              "L2 normalization per channel / LayerNorm",
              `Preserves 2D spatial topology on ${boardH}×${boardW} hex grid`
            ],
        paramEstimate: "GPU Memory Buffer (MCTS Search Tree Cache)",
        receptiveField: "Generated by h(o) at t=0 or imagined by g(s, a) at t>0",
        details: `Continuous latent space where Monte Carlo Tree Search projects candidate futures up to horizon t=${maxUnroll}.`,
      },
      action: {
        id: "action",
        name: "Action Conditioning a_t",
        math: `a_t \\in \\{0, \\dots, ${actionDim - 1}\\}`,
        role: `Candidate discrete tactical action selected during MCTS simulation (${actionDim} action space).`,
        inShape: `Discrete action index a_t (0 to ${actionDim - 1})`,
        outShape: `B × 1 × ${boardH} × ${boardW} (Spatial broadcast plane)`,
        architecture: [
          `Linear Action Embedding (${actionDim} dimensions)`,
          `Constant spatial broadcast across 1×${boardH}×${boardW} grid`,
          `Channel-wise concatenation with latent state (${hiddenDim} + 1 = ${hiddenDim + 1})`
        ],
        paramEstimate: `~${(actionDim * 32).toLocaleString()} parameters`,
        receptiveField: "Global (informs entire spatial board of candidate order)",
        details: `Enables the recurrent dynamics model to predict combat outcome, movement transitions, and reaction fire for the executed action.`,
      },
      dynamics: {
        id: "dynamics",
        name: "Dynamics Network g_θ(s, a)",
        math: `g_\\theta(s_t, a_t) \\to (s_{t+1}, \\hat{r}_t)`,
        role: "Recurrent latent world model: predicts the next latent state s_{t+1} and immediate reward r_t after executing action a_t.",
        inShape: `B × ${hiddenDim + 1} × ${boardH} × ${boardW} (s_t + a_t concatenation)`,
        outShape: `s_{t+1}: B × ${hiddenDim} × ${boardH} × ${boardW} | r_t: B × 1 (Two-Hot Support)`,
        architecture: isV2Optimized
          ? [
              `Conv2d(${hiddenDim + 1}, ${hiddenDim}, kernel_size=3, padding=1) + SiLU`,
              ...Array.from({ length: dynamicsBlocks }, (_, i) =>
                `Dynamics Block ${i + 1}: Conv3x3(${hiddenDim}) -> GroupNorm -> SiLU -> Conv3x3 -> GroupNorm + Squeeze-and-Excitation (SE)`
              ),
              `Reward Head: Conv1x1(${hiddenDim}, ${valCh}) -> GroupNorm -> SiLU -> AdaptiveAvgPool2d(2x2) -> Linear(${valCh * 4}, 64) -> SiLU -> Linear(64, 601)`,
              "Two-Hot Categorical Reward Distribution ([-300, 300] support bounds)",
              "Min-Max Recurrent Latent Scaling per imagination step"
            ]
          : [
              `Conv2d(${hiddenDim + 1}, ${hiddenDim}, kernel_size=3, padding=1) + ReLU`,
              ...Array.from({ length: dynamicsBlocks }, (_, i) =>
                `Dynamics Block ${i + 1}: Conv3x3(${hiddenDim}) -> LayerNorm -> ReLU`
              ),
              `Reward Head: Flatten(${flatDim}) -> Linear(${flatDim}, 64) -> SiLU -> Linear(64, 1)`
            ],
        paramEstimate: `~${dynParams.toLocaleString()} parameters`,
        receptiveField: `~${dynReceptive}×${dynReceptive} Hexes accumulated per step`,
        details: isV2Optimized
          ? `Optimized V2 recurrent model: utilizes 1x1 bottlenecks + AdaptiveAvgPool in reward prediction and Min-Max latent re-scaling, preventing gradient vanishing or explosion during deep BPTT.`
          : `Classic V1 recurrent model with dense reward head connected directly to flattened spatial map.`,
      },
      manager_network: {
        id: "manager_network",
        name: "Strategic Manager Network (H-EZ-M v3.0)",
        math: `\\pi_{manager}(o_t, c_{topo}) \\to (g_T^{\\text{spatial}} \\in [0, 1]^{16 \\times 16}, m_T \\in \\{1..4\\})`,
        role: "High-level strategic commander operating at macro-cycles (T <= 8 turns). Evaluates global battlefield topography (IPB) and generates macro-goals that condition tactical MCTS workers.",
        inShape: `B × (38 + 5) × ${boardH} × ${boardW} (Sensory Observation + 5D Topography IPB)`,
        outShape: `Spatial Goal Heatmap: B × 1 × ${boardH} × ${boardW} + Tactical Mode: B × 4`,
        architecture: [
          `Global Topography Encoder: Conv3x3 -> GroupNorm -> SiLU`,
          `Residual Macro Blocks: 4 ResidualBlocks with Spatial Squeeze-and-Excitation`,
          `Spatial Goal Head: Conv1x1 -> Sigmoid (16x16 Heatmap)`,
          `Tactical Mode Head: AdaptiveAvgPool -> Linear -> Softmax (Assault, Defend, Suppress, Screen)`,
          `SpatialGoalFiLMBridge: Multi-modal modulation coupling Manager goals into Worker MCTS`
        ],
        paramEstimate: "~850,000 parameters",
        receptiveField: "Global Map Resolution (Full Board View)",
        details: "Resolves temporal and spatial scale mismatch by decoupling macro objective planning from local hex movement, guiding tactical workers to execute coordinated assaults.",
      },
      loss_balancer: {
        id: "loss_balancer",
        name: "Adaptive Loss Balancer & Multi-Task PCGrad",
        math: `g_i \\leftarrow g_i - \\frac{g_i \\cdot g_j}{\\|g_j\\|^2} g_j \\quad (\\text{if } g_i \\cdot g_j < 0)`,
        role: "Dynamic gradient surgery and multi-head loss balancing. Projects conflicting gradients onto orthogonal planes to prevent negative transfer between disparate scenarios.",
        inShape: "Per-task Gradients g_i, g_j + Head Losses (Policy, Value, Consistency, Aux)",
        outShape: "Conflict-Free Combined Gradient Vector \\nabla_\\theta \\mathcal{L}",
        architecture: [
          "Gradient Surgery (PCGrad): Orthogonal projection for pairs with negative inner product",
          "Cosine Similarity Telemetry: CosSim(i, j) exported to MLOps for cross-scenario transfer forensics",
          "GradNorm Adaptive Weighting: Balances gradient norms across auxiliary heads dynamically",
          "Two-Hot Categorical Value Support: 601 bins ([-300, 300]) with smooth label distribution"
        ],
        paramEstimate: "Dynamic Optimizer Operator (Zero Inference Overhead)",
        receptiveField: "Global Gradient Parameter Space",
        details: "Prevents urban assault gradients from overriding open terrain maneuvers, ensuring continuous Pareto improvements across all curriculum phases simultaneously.",
      },
      policy: {
        id: "policy",
        name: "Policy Head f_p(s)",
        math: `p_t = f_p(s_t) \\in \\Delta^{${actionDim}}`,
        role: `Prior probability distribution over the ${actionDim} available discrete game actions.`,
        inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        outShape: `B × ${actionDim} logits (Normalized with Softmax and legal action masking)`,
        architecture: isV2Optimized
          ? [
              ...Array.from({ length: predictionBlocks }, (_, i) =>
                `Prediction Block ${i + 1}: Conv3x3(${hiddenDim}) -> GroupNorm -> SiLU + SE`
              ),
              `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${headCh}, 1x1) + GroupNorm + SiLU`,
              `Linear Head: Flatten(${flatPol}) -> Linear(${flatPol}, ${actionDim}) (Logits)`,
              "Policy Loss: Cross-Entropy / KL-Divergence with non-attenuated linear gradients"
            ]
          : [
              ...Array.from({ length: predictionBlocks }, (_, i) =>
                `Prediction Block ${i + 1}: Conv3x3(${hiddenDim}) -> LayerNorm -> ReLU`
              ),
              `Direct Flatten: Flatten(${flatDim}) -> Linear(${flatDim}, ${actionDim})`,
              "Policy Loss: MSE over Softmax (gradient attenuation on small p)"
            ],
        paramEstimate: `~${polParams.toLocaleString()} parameters`,
        receptiveField: "Global (Convolutional Bottleneck)",
        details: isV2Optimized
          ? `V2 policy head with 1x1 bottleneck (${hiddenDim}ch ➔ ${headCh}ch), drastically reducing parameter count and preventing coordinate memorization. Trained with Cross-Entropy.`
          : `Classic V1 head with dense linear layer connecting to all flattened cells (~${(flatDim * actionDim).toLocaleString()} parameters in linear projection alone).`,
      },
      value: {
        id: "value",
        name: "Value Head f_v(s) (Two-Hot Support)",
        math: `v_t = f_v(s_t) \\in [-300, 300] \\implies \\text{Two-Hot Categorical Support (601 bins)}`,
        role: "Scalar state value evaluation representing expected discounted game outcome and victory margin.",
        inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        outShape: "B × 601 Logits (Two-hot categorical distribution over scalar support)",
        architecture: isV2Optimized
          ? [
              `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${valCh}, 1x1) + GroupNorm + SiLU`,
              `AdaptiveAvgPool2d((2, 2)) (Spatial invariance and compression)`,
              `Linear(${valCh * 4}, 64) -> SiLU -> Linear(64, 601) (Categorical Support Bins)`,
              "Two-Hot Cross-Entropy Loss: Invertible scalar mapping with bounded gradient variance"
            ]
          : [
              `Direct Flatten: Flatten(${flatDim}) -> Linear(${flatDim}, 64) -> SiLU -> Linear(64, 1) + Tanh`
            ],
        paramEstimate: `~${valParams.toLocaleString()} parameters`,
        receptiveField: "Global",
        details: isV2Optimized
          ? `V2 value head utilizing two-hot categorical representation over 601 support bins ([-300, 300]). Eliminates regression scale instability and prevents value collapse during sudden game reversals.`
          : `Classic V1 head connected to raw flattened board.`,
      },
      aux_objective: {
        id: "aux_objective",
        name: "Objective Progress Head f_o(s)",
        math: `y_t = f_o(s_t) \\in \\mathbb{R}`,
        role: "Auxiliary prediction head estimating progress and proximity to Victory Points (VPs).",
        inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        outShape: "B × 1 (Continuous capture progress & proximity estimation)",
        architecture: isV2Optimized
          ? [
              `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${valCh}, 1x1) + GroupNorm + SiLU`,
              `AdaptiveAvgPool2d((2, 2))`,
              `Linear(${valCh * 4}, 32) -> SiLU -> Linear(32, 1)`
            ]
          : [
              `Direct Flatten: Flatten(${flatDim}) -> Linear(${flatDim}, 32) -> SiLU -> Linear(32, 1)`
            ],
        paramEstimate: `~${objParams.toLocaleString()} parameters`,
        receptiveField: "Global / Localized to VP hexes",
        details: "Guides reinforcement learning to prioritize objective capture over passive camping.",
      },
      consistency: {
        id: "consistency",
        name: "Consistency Head q_θ(s) (Fast Vectorized)",
        math: `z_t = q_\\theta(s_t) \\in \\mathbb{R}^{B \\times ${hiddenDim}}`,
        role: `SimSiam self-supervised consistency projector (${consistencyUnroll}-step unroll horizon) with batched single-pass reanalysis.`,
        inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
        outShape: `B × ${hiddenDim} (Latent embedding vector)`,
        architecture: isV2Optimized
          ? [
              `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${headCh}, 1x1) + SiLU`,
              `AdaptiveAvgPool2d((4, 4))`,
              `MLP Projector: Linear(${headCh * 16}, 128) -> SiLU -> Linear(128, 128)`,
              "Single-Pass Vectorized Target Batching: Zero redundant forward passes in replay buffer",
              "SimSiam Loss: Negative Cosine Similarity with Stop-Gradient on target representations"
            ]
          : [
              `Direct Flatten: Flatten(${flatDim}) -> Linear(${flatDim}, 128) -> SiLU -> Linear(128, 128)`,
              "SimSiam Loss: Cosine Similarity with Stop-Gradient"
            ],
        paramEstimate: `~${conParams.toLocaleString()} parameters`,
        receptiveField: "Global",
        details: `Prevents latent representation collapse during temporal unrolling, forcing s_t to inhabit the same semantic manifold as physical observations.`,
      },
      ...(hasThreatHead
        ? {
            threat_map: {
              id: "threat_map",
              name: "Threat Map Head f_threat(s)",
              math: `m_t = f_{threat}(s_t) \\in [0, 1]^{B \\times 1 \\times ${boardH} \\times ${boardW}}`,
              role: `2D spatial heatmap predicting suppression risk and enemy lines of fire across the ${boardH}×${boardW} hexagonal board.`,
              inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
              outShape: `B × 1 × ${boardH} × ${boardW} (Fire / LOS risk probabilities)`,
              architecture: isV2Optimized
                ? [
                    `SpatialAttentionBlock: Self-Attention across ${hiddenDim} spatial channels`,
                    `Conv2d(${hiddenDim}, 16, kernel_size=3, padding=1) + GroupNorm + SiLU`,
                    "Conv2d(16, 1, kernel_size=1) (Fire coverage logits)",
                    "Threat Loss: BCEWithLogitsLoss with adaptive loss balancing"
                  ]
                : [
                    `Conv2d(${hiddenDim}, 16, kernel_size=3, padding=1) + GroupNorm + SiLU`,
                    "Conv2d(16, 1, kernel_size=1)",
                    "Threat Loss: BCEWithLogitsLoss"
                  ],
              paramEstimate: `~${(hiddenDim * 16 * 9 + 16 * 1).toLocaleString()} parameters`,
              receptiveField: `Local / Spatial (${boardH}×${boardW} Hexes)`,
              details: "Active threat auxiliary head: estimates probability of taking incoming fire in each hex, incentivizing tactical navigation through defilade and cover.",
            },
          }
        : {}),
      ...(hasAttritionHead
        ? {
            attrition: {
              id: "attrition",
              name: "Attrition Balance Head f_attr(s)",
              math: `a_t = f_{attr}(s_t) \\in \\mathbb{R}^{B \\times 2}`,
              role: "Tactical casualty projection predicting expected friendly vs enemy losses.",
              inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
              outShape: "B × 2 (Estimated friendly casualties, Estimated enemy casualties)",
              architecture: isV2Optimized
                ? [
                    `SpatialAttentionBlock: Pooled Context (${valCh}ch)`,
                    "Flatten() -> Linear(64) -> SiLU -> Linear(64, 2)",
                    "Attrition Loss: Smooth L1 Loss (Huber) with adaptive gradient balancing"
                  ]
                : [
                    `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${valCh}, 1x1) + SiLU`,
                    `Flatten(${flatVal}) -> Linear(64) -> SiLU -> Linear(64, 2)`,
                    "Attrition Loss: Smooth L1 Loss"
                  ],
              paramEstimate: `~${(hiddenDim * valCh + flatVal * 64 + 64 * 2).toLocaleString()} parameters`,
              receptiveField: "Global",
              details: "Discriminates clean tactical victories from pyrrhic victories with catastrophic squad losses.",
            },
          }
        : {}),
      ...(hasMoraleHead
        ? {
            morale: {
              id: "morale",
              name: "Morale State Head f_morale(s)",
              math: `m_t = f_{morale}(s_t) \\in \\Delta^4`,
              role: "Probability distribution over tactical cohesion states: NORMAL (0), PINNED (1), SUPPRESSED (2), ROUTED (3).",
              inShape: `B × ${hiddenDim} × ${boardH} × ${boardW}`,
              outShape: "B × 4 (Categorical distribution with Softmax)",
              architecture: isV2Optimized
                ? [
                    `SpatialAttentionBlock: Pooled Context (${valCh}ch)`,
                    "Flatten() -> Linear(64) -> SiLU -> Linear(64, 4)",
                    "Morale Loss: Categorical Cross-Entropy with class-weighted penalties"
                  ]
                : [
                    `Conv1x1 Bottleneck: Conv2d(${hiddenDim}, ${valCh}, 1x1) + SiLU`,
                    `Flatten(${flatVal}) -> Linear(64) -> SiLU -> Linear(64, 4)`,
                    "Morale Loss: Categorical Cross-Entropy"
                  ],
              paramEstimate: `~${(hiddenDim * valCh + flatVal * 64 + 64 * 4).toLocaleString()} parameters`,
              receptiveField: "Global",
              details: "Predicts suppression degradation and squad rout probability under fire, encouraging proactive tactical withdrawals.",
            },
          }
        : {}),
      macro_planner: {
        id: "macro_planner",
        name: "Macro Planner & Doctrinal Profiling (H-EZ-M 4-Tier Hierarchy)",
        math: `\\pi_{macro}(o_t) \\to (\\text{Posture}, \\text{Roles}_{[1..8]}, \\text{Mutations}) \\implies P_{mod}(a)`,
        role: "Strategic tactical planner operating as Level 1 of H-EZ-M. Evaluates the full board, assigns global team posture (ASSAULT_VP, DEFENSIVE_HOLD, ZONE_SUPPRESS), distributes 8 canonical roles per squad, and injects +35% π prior shaping at the root of the MCTS worker tree.",
        inShape: `B × ${inChannels} × ${boardH} × ${boardW} (Board Observation Tensor)`,
        outShape: "3 Postures + 8 Canonical Roles + 3 Contextual Mutation Rules + Prior Shaping (+35%)",
        architecture: [
          "Tier 1: VOEC Physical & Ballistic Invariants (Strict LOS, ranges, movement costs, and dice resolution)",
          "Tier 2: H-EZ-M Strategic Manager Network (Macro-goals g_T, 16x16 spatial heatmap, tactical modes)",
          "Tier 3: Inductive Doctrinal Profiler (8 Canonical Roles, Dunnigan Tactical Reserve, Hyde Cohesion, +35% prior shaping)",
          "Tier 4: Autonomous Tactical Operator (512 MCTS sims, 6-step unroll, off-policy reanalysis, Q(s,a) override)",
          "Prospective: TemplateRL Hybrid LLM+RL Strategic Macro-Planner (Line 4 / v2.6.0 roadmap alignment)"
        ],
        paramEstimate: "Hierarchical Decoupled Architecture (Manager + Doctrinal Profiler + MCTS Worker)",
        receptiveField: "Global (Full board topography, 2D weapon footprints, dynamic squad state)",
        details: "Prevents local MCTS search from falling into passive deadlocks by biasing exploration towards designated strategic objectives, while maintaining full flexibility for Q(s,a) to override when a superior move is found.",
      },
    };
  }, [inChannels, boardH, boardW, hiddenDim, actionDim, dynamicsBlocks, predictionBlocks, encoderType, maxUnroll, consistencyUnroll, runId, mctsSims, isV2Optimized, hasThreatHead, hasAttritionHead, hasMoraleHead, enableMultitask, numTasks, taskEmbedDim]);

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
        label: "POLICY f_p(s)",
        sublabel: `${actionDim} Logits ${isV2Optimized ? "(Conv 1x1)" : "(Dense)"}`,
        stroke: "#38bdf8",
        selectedFill: "#0369a1",
        metricLabel: `Loss: ${fmtNum(polLoss, 3)} | Conf: ${fmtPercent(polConfidence)}`,
        metricValue: fmtNum(polLoss, 3),
        tag: polLoss !== null ? "🟢 OK" : "⚪ PENDING",
        tagColor: polLoss !== null ? "#34d399" : "#94a3b8",
      },
      {
        id: "value",
        icon: "⚖️",
        label: "VALUE f_v(s) (Two-Hot)",
        sublabel: `Two-Hot [-300, 300] (601 bins) ${isV2Optimized ? "(Pool 2x2)" : "(Dense)"}`,
        stroke: "#22c55e",
        selectedFill: "#065f46",
        metricLabel: `Loss: ${fmtNum(valLoss, 3)} | Q-Sat: ${fmtPercent(qSatRate)}`,
        metricValue: fmtNum(valLoss, 3),
        tag: valLoss !== null ? "🟢 OK" : "⚪ PENDING",
        tagColor: valLoss !== null ? "#34d399" : "#94a3b8",
      },
      {
        id: "aux_objective",
        icon: "🏁",
        label: "AUX OBJECTIVE f_o(s)",
        sublabel: `VP Proximity ${isV2Optimized ? "(Pool 2x2)" : "(Dense)"}`,
        stroke: "#f43f5e",
        selectedFill: "#9f1239",
        metricLabel: `Loss: ${fmtNum(objLoss, 3)} | Take: ${fmtPercent(objTakeRate)}`,
        metricValue: fmtNum(objLoss, 3),
        tag: objLoss !== null ? "🟢 OK" : "⚪ PENDING",
        tagColor: objLoss !== null ? "#34d399" : "#94a3b8",
      },
      {
        id: "consistency",
        icon: "🔄",
        label: "CONSISTENCY q_θ(s) (Fast)",
        sublabel: `SimSiam Vectorized ${isV2Optimized ? "(Pool 4x4)" : `(${hiddenDim} Flat)`}`,
        stroke: "#c084fc",
        selectedFill: "#581c87",
        metricLabel: `Loss: ${fmtSci(conLoss)} | Cov: ${fmtPercent(conReanalysisCov, 0)}`,
        metricValue: fmtSci(conLoss),
        tag: conLoss !== null ? "🟢 OK" : "⚪ PENDING",
        tagColor: conLoss !== null ? "#34d399" : "#94a3b8",
      },
    ];

    if (hasThreatHead) {
      list.push({
        id: "threat_map",
        icon: "🗺️",
        label: "THREAT MAP f_threat(s)",
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
        label: "ATTRITION BALANCE f_attr(s)",
        sublabel: "2D Vector [Friendly Casualties, Enemy Casualties]",
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
        label: "MORALE COHESION f_morale(s)",
        sublabel: "4 Classes (Normal / Pinned / Suppressed / Routed)",
        stroke: "#ec4899",
        selectedFill: "#9d174d",
        metricLabel: `Loss: ${fmtNum(moraleLoss, 3)} | Risk: ${fmtNum(moraleRisk, 2)}`,
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
  const svgHeight = Math.max(340, 12 + numHeads * (cardH + cardGap) + 8);

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
          desc: `Input Channel ${i}: ${name} (${nonzero} active cells)`,
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
            <span>🧠</span> Dynamic Neural Network Topology (EfficientZero V2 / EZ-M)
          </h3>
          <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
            Decoupled architecture: Representation (h), Recurrent Dynamics (g), Prediction Heads (f), Self-Supervised Consistency (z), and Multi-Task FiLM Conditioning.
          </div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <div className="kpi" style={{ padding: "4px 8px" }}>
            <div className="k" style={{ fontSize: 10 }}>Encoder / Latent</div>
            <div className="v" style={{ fontSize: 11, color: "#38bdf8" }}>{encoderType.toUpperCase()} ({hiddenDim} ch)</div>
          </div>
          <div className="kpi" style={{ padding: "4px 8px" }}>
            <div className="k" style={{ fontSize: 10 }}>Action Space</div>
            <div className="v" style={{ fontSize: 11, color: "#22c55e" }}>{actionDim} logits</div>
          </div>
          <div className="kpi" style={{ padding: "4px 8px" }}>
            <div className="k" style={{ fontSize: 10 }}>Max Unroll</div>
            <div className="v" style={{ fontSize: 11, color: "#f59e0b" }}>{maxUnroll} steps</div>
          </div>
          <div className="kpi" style={{ padding: "4px 8px" }}>
            <div className="k" style={{ fontSize: 10 }}>Precision</div>
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
            <span>Diagram &amp; Topology</span>
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
            <span>Channel Attribution</span>
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
            <span>Macro Planner &amp; Doctrine</span>
            <span style={{ fontSize: 9, background: "#581c87", color: "#d8b4fe", padding: "1px 6px", borderRadius: 4, fontWeight: 700 }}>H-EZ-M v3.0 • 8 Roles</span>
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 3, background: "#0b1120", border: "1px solid #334155", borderRadius: 6, padding: "2px 4px" }}>
          <span style={{ fontSize: 10, color: "#94a3b8", padding: "0 4px", fontWeight: 600 }}>Size:</span>
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
            title="Compact view (reduced vertical height)"
          >
            📏 Compact
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
            title="Balanced view: crisp text and full proportions"
          >
            📐 Balanced
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
            title="Expanded view with maximum height"
          >
            🖥️ Expanded
          </button>
        </div>

        {/* ONNX Export Button */}
        <button
          onClick={handleExportOnnx}
          disabled={isExportingOnnx}
          style={{
            background: isExportingOnnx ? "#334155" : "linear-gradient(135deg, #059669, #047857)",
            color: "#ffffff",
            border: "1px solid #10b981",
            borderRadius: 6,
            padding: "5px 12px",
            fontSize: 11,
            fontWeight: 700,
            cursor: isExportingOnnx ? "wait" : "pointer",
            display: "flex",
            alignItems: "center",
            gap: 6,
            boxShadow: "0 2px 8px rgba(16, 185, 129, 0.25)",
            transition: "all 0.15s ease-in-out",
          }}
          title="Export model components to ONNX format for visual inspection in Netron"
        >
          <span>{isExportingOnnx ? "⏳" : "📦"}</span>
          <span>{isExportingOnnx ? "Exporting ONNX..." : "Export to ONNX (Netron)"}</span>
        </button>
      </div>

      {/* ONNX Export Result Card */}
      {onnxExportResult && (
        <div
          style={{
            background: "linear-gradient(145deg, #062419, #091a13)",
            border: "1px solid #059669",
            borderRadius: 8,
            padding: "14px 18px",
            marginBottom: 16,
            boxShadow: "0 4px 20px rgba(5, 150, 105, 0.25)",
            position: "relative",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 700, color: "#34d399" }}>
                <span>✅</span>
                <span>ONNX Models Successfully Generated</span>
                <span style={{ fontSize: 10, background: "#065f46", color: "#a7f3d0", padding: "1px 6px", borderRadius: 4 }}>
                  {onnxExportResult.files?.length || 0} Models Ready
                </span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginTop: 4 }}>
                <div style={{ fontSize: 11, color: "#94a3b8" }}>
                  Export directory: <code style={{ color: "#a7f3d0", background: "#0b1612", padding: "2px 6px", borderRadius: 4 }}>{onnxExportResult.export_dir}</code>
                </div>
                <button
                  onClick={handleOpenFolder}
                  style={{
                    background: "#1e293b",
                    color: "#38bdf8",
                    border: "1px solid #0284c7",
                    borderRadius: 4,
                    padding: "2px 8px",
                    fontSize: 10,
                    fontWeight: 600,
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                  title="Open folder in Windows File Explorer"
                >
                  <span>📂</span> Open Folder in Explorer
                </button>
                <button
                  onClick={handleCopyFolder}
                  style={{
                    background: "#1e293b",
                    color: copiedFolder ? "#34d399" : "#cbd5e1",
                    border: "1px solid #475569",
                    borderRadius: 4,
                    padding: "2px 8px",
                    fontSize: 10,
                    fontWeight: 600,
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                  }}
                  title="Copy directory path to clipboard"
                >
                  <span>{copiedFolder ? "✓" : "📋"}</span> {copiedFolder ? "Copied!" : "Copy Path"}
                </button>
              </div>
            </div>
            <button
              onClick={() => setOnnxExportResult(null)}
              style={{
                background: "transparent",
                border: "none",
                color: "#94a3b8",
                cursor: "pointer",
                fontSize: 16,
                padding: "2px 6px",
              }}
              title="Close notification"
            >
              ✕
            </button>
          </div>

          {/* Files List */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 10 }}>
            {onnxExportResult.files?.map((f: any) => (
              <div
                key={f.name}
                style={{
                  background: "#0b1612",
                  border: "1px solid #047857",
                  borderRadius: 6,
                  padding: "8px 12px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 12,
                  minWidth: 260,
                  flex: "1 1 280px",
                }}
              >
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#f8fafc" }}>{f.name}</div>
                  <div style={{ fontSize: 10, color: "#6ee7b7" }}>{f.label}</div>
                  <div style={{ fontSize: 9, color: "#64748b" }}>{(f.size_bytes / 1024 / 1024).toFixed(2)} MB</div>
                </div>
                <button
                  onClick={() => handleSaveFileWithPicker(f.download_url, f.name)}
                  style={{
                    background: "#059669",
                    color: "#ffffff",
                    border: "none",
                    borderRadius: 4,
                    padding: "6px 12px",
                    fontSize: 11,
                    fontWeight: 700,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 5,
                    boxShadow: "0 2px 6px rgba(5, 150, 105, 0.4)",
                    transition: "background 0.15s ease",
                  }}
                  title="Open 'Save As' window to choose destination folder"
                >
                  <span>💾</span> Save As...
                </button>
              </div>
            ))}
          </div>

          {/* Netron Action Footer */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12, paddingTop: 10, borderTop: "1px solid #04785750", flexWrap: "wrap", gap: 8 }}>
            <span style={{ fontSize: 11, color: "#cbd5e1" }}>
              💡 <strong>How to view:</strong> Download any file above and drag it into <a href="https://netron.app" target="_blank" rel="noopener noreferrer" style={{ color: "#38bdf8", textDecoration: "underline" }}>netron.app</a> or open in your Netron desktop app.
            </span>
            <a
              href="https://netron.app"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                background: "#0284c7",
                color: "#ffffff",
                borderRadius: 5,
                padding: "5px 12px",
                fontSize: 11,
                fontWeight: 700,
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
              }}
            >
              <span>🌐</span> Open Netron (netron.app) ↗
            </a>
          </div>
        </div>
      )}

      {onnxError && (
        <div
          style={{
            background: "#450a0a",
            border: "1px solid #b91c1c",
            borderRadius: 6,
            padding: "8px 12px",
            marginBottom: 16,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            fontSize: 11,
            color: "#fca5a5",
          }}
        >
          <span>⚠️ {onnxError}</span>
          <button
            onClick={() => setOnnxError(null)}
            style={{ background: "transparent", border: "none", color: "#fca5a5", cursor: "pointer" }}
          >
            ✕
          </button>
        </div>
      )}

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
          <span>📌</span> Active Run:
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
            ⚡ Architecture v2: GroupNorm + SE + Conv Bottlenecks + EZ-M Multi-Task
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
            📦 Architecture v1: Dense Flattened (Legacy Run)
          </span>
        )}

        <div style={{ marginLeft: "auto", fontSize: 11, color: "#94a3b8", display: "flex", alignItems: "center", gap: 10 }}>
          {modelCfg.total_parameters ? (
            <span style={{ color: "#f59e0b", fontWeight: 700 }}>
              {Number(modelCfg.total_parameters).toLocaleString()} params (Measured)
            </span>
          ) : null}
          <span>
            Dimensions: <b>{inChannels}ch × {boardH}×{boardW}</b> ➔ Latent <b>{hiddenDim}ch</b> ➔ Blocks <b>{dynamicsBlocks}D + {predictionBlocks}P</b>
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
              <span>{isPlaying ? "⏸ Pause Flow" : "▶ Play Unroll Flow"}</span>
            </button>

            <span style={{ fontSize: 12, fontWeight: 700, color: "#f8fafc" }}>
              Projection Step: <span style={{ color: "#38bdf8" }}>t = {unrollStep}</span> of {maxUnroll}
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
                {step === 0 ? "t=0 (Root Input)" : `t=${step} (Unroll)`}
              </button>
            ))}
          </div>
        </div>

        <div style={{ background: "#0f172a", borderRadius: 6, padding: "8px 12px", borderLeft: unrollStep === 0 ? "3px solid #38bdf8" : "3px solid #f59e0b" }}>
          <div style={{ fontSize: 11, color: unrollStep === 0 ? "#93c5fd" : "#fcd34d", fontWeight: 600 }}>
            {unrollStep === 0
              ? `⚡ MCTS ROOT STEP (t=0): Extracting Latent State from Real Board Observation (${inChannels}×${boardH}×${boardW})`
              : `⚡ RECURRENT IMAGINATION UNROLL (t=${unrollStep}): Latent Simulation on GPU without Physical Simulator (Horizon max=${maxUnroll})`}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
            {unrollStep === 0
              ? `The sensory tensor o_0 (${inChannels}×${boardH}×${boardW}) passes through h(o) to produce s_0 (${hiddenDim}×${boardH}×${boardW}). Multi-task FiLM layers condition evaluation per scenario.`
              : `Dynamics network g(s_${unrollStep - 1}, a_${unrollStep - 1}) projects next state s_${unrollStep} (${hiddenDim}×${boardH}×${boardW}) and two-hot reward. Consistency projector z(s) maintains latent invariance.`}
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
              <span>🎨</span> Interactive Neural Network Topology &amp; Flow Diagram
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span className="muted" style={{ fontSize: 11 }}>Click any node or pill to inspect architecture</span>
            </div>
          </div>

          {/* Quick Component Selection Pills */}
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
            {[
              { id: "observation", label: `Obs (${inChannels}ch)` },
              { id: "representation", label: "Rep h_θ" },
              { id: "task_conditioning", label: "Task FiLM (EZ-M)" },
              { id: "latent", label: "Latent s_t" },
              { id: "action", label: "Action a_t" },
              { id: "dynamics", label: "Dynamics g_θ" },
              { id: "manager_network", label: "Manager (H-EZ-M)" },
              { id: "loss_balancer", label: "PCGrad Balancer" },
              { id: "macro_planner", label: "Doctrine Profiler" },
              { id: "policy", label: "Policy f_p" },
              { id: "value", label: "Value (Two-Hot)" },
              { id: "aux_objective", label: "Objective f_o" },
              { id: "consistency", label: "Consistency q_θ" },
              ...(hasThreatHead ? [{ id: "threat_map", label: "Threat Map" }] : []),
              ...(hasAttritionHead ? [{ id: "attrition", label: "Attrition" }] : []),
              ...(hasMoraleHead ? [{ id: "morale", label: "Morale" }] : []),
            ].map((btn) => (
              <button
                key={btn.id}
                onClick={() => setSelectedNodeId(btn.id)}
                style={{
                  background: selectedNodeId === btn.id ? "#0284c7" : "#1e293b",
                  color: selectedNodeId === btn.id ? "#ffffff" : "#94a3b8",
                  border: selectedNodeId === btn.id ? "1px solid #38bdf8" : "1px solid #334155",
                  borderRadius: 4,
                  padding: "2px 7px",
                  fontSize: 10,
                  fontWeight: selectedNodeId === btn.id ? 700 : 500,
                  cursor: "pointer",
                  transition: "all 0.1s ease",
                }}
              >
                {btn.label}
              </button>
            ))}
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
                maxHeight: diagramSize === "compact" ? Math.max(290, svgHeight + 20) : diagramSize === "expanded" ? Math.max(460, svgHeight + 120) : Math.max(360, svgHeight + 60),
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
              <line x1="150" y1="55" x2="175" y2="55" stroke="#38bdf8" strokeWidth="2.5" markerEnd="url(#arrow)" strokeDasharray={unrollStep === 0 ? "none" : "4 4"} />
              {/* Rep -> Latent */}
              <line x1="335" y1="55" x2="360" y2="55" stroke="#38bdf8" strokeWidth="2.5" markerEnd="url(#arrow)" strokeDasharray={unrollStep === 0 ? "none" : "4 4"} />
              
              {/* Obs -> Manager Network (Level 1) */}
              <line x1="82" y1="95" x2="82" y2="125" stroke="#a855f7" strokeWidth="2" markerEnd="url(#arrow-purple)" strokeDasharray={unrollStep === 0 ? "none" : "3 3"} />
              <text x="88" y="112" fill="#c084fc" fontSize="8" fontWeight="700">H-EZ-M Level 1</text>

              {/* Manager Net -> Action / Priors */}
              <path d="M 150 157 C 240 157, 300 157, 360 157" fill="none" stroke="#a855f7" strokeWidth="2" strokeDasharray="3 3" markerEnd="url(#arrow-purple)" />
              <text x="257" y="148" fill="#c084fc" fontSize="8" fontWeight="600" textAnchor="middle">SpatialGoalFiLM Bridge (+35% π)</text>

              {/* Task Conditioning -> Rep & Dynamics */}
              <path d="M 257 235 L 257 198" fill="none" stroke="#f59e0b" strokeWidth="1.5" strokeDasharray="3 3" markerEnd="url(#arrow-amber)" />
              <text x="265" y="215" fill="#fbbf24" fontSize="7.5" fontWeight="600">FiLM (1+γ)z+β</text>

              {/* Loss Balancer -> Active Heads */}
              <path d="M 150 255 C 330 255, 450 255, 530 255" fill="none" stroke="#10b981" strokeWidth="1.5" strokeDasharray="4 4" markerEnd="url(#arrow-green)" />
              <text x="340" y="248" fill="#34d399" fontSize="7.5" fontWeight="600">PCGrad Orthogonal Surgery (g_i · g_j ≥ 0)</text>

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
              <line x1="365" y1="165" x2="340" y2="165" stroke={unrollStep > 0 ? "#f59e0b" : "#475569"} strokeWidth="2" markerEnd="url(#arrow-amber)" />
              <path d="M 430 98 L 430 115 C 430 135, 410 145, 340 145" fill="none" stroke={unrollStep > 0 ? "#f59e0b" : "#475569"} strokeWidth="2" markerEnd="url(#arrow-amber)" strokeDasharray={unrollStep > 0 ? "none" : "3 3"} />
              {/* Dynamics Feedback: Dynamics -> Latent (s_{t+1}) */}
              <path d="M 180 160 C 165 160, 165 80, 360 80" fill="none" stroke={unrollStep > 0 ? "#10b981" : "#334155"} strokeWidth="2.5" markerEnd="url(#arrow-green)" strokeDasharray={unrollStep > 0 ? "none" : "4 4"} />

              {/* Node 1: Observation Tensor */}
              <g
                onClick={() => setSelectedNodeId("observation")}
                style={{ cursor: "pointer" }}
                opacity={unrollStep === 0 ? 1 : 0.5}
              >
                <rect
                  x="15"
                  y="12"
                  width="135"
                  height="82"
                  rx="8"
                  fill={selectedNodeId === "observation" ? "#0369a1" : "#0f172a"}
                  stroke={selectedNodeId === "observation" ? "#38bdf8" : "#0284c7"}
                  strokeWidth={selectedNodeId === "observation" ? "2.5" : "1.5"}
                  filter={unrollStep === 0 ? "url(#glow-cyan)" : "none"}
                />
                <text x="82" y="32" fill="#94a3b8" fontSize="9" fontWeight="700" textAnchor="middle">SENSORY INPUT</text>
                <text x="82" y="50" fill="#f8fafc" fontSize="12" fontWeight="800" textAnchor="middle">Observation o_t</text>
                <text x="82" y="68" fill="#38bdf8" fontSize="11" fontWeight="700" textAnchor="middle">{inChannels}×{boardH}×{boardW}</text>
                <text x="82" y="83" fill="#64748b" fontSize="8.5" textAnchor="middle">VOEC Simulator Feed</text>
              </g>

              {/* Node 2: Representation Network */}
              <g
                onClick={() => setSelectedNodeId("representation")}
                style={{ cursor: "pointer" }}
                opacity={unrollStep === 0 ? 1 : 0.5}
              >
                <rect
                  x="180"
                  y="12"
                  width="155"
                  height="82"
                  rx="8"
                  fill={selectedNodeId === "representation" ? "#0369a1" : "#1e293b"}
                  stroke={selectedNodeId === "representation" ? "#38bdf8" : "#0ea5e9"}
                  strokeWidth={selectedNodeId === "representation" ? "2.5" : "1.5"}
                />
                <text x="257" y="32" fill="#60a5fa" fontSize="9" fontWeight="700" textAnchor="middle">ENCODER {encoderType.toUpperCase()}</text>
                <text x="257" y="50" fill="#ffffff" fontSize="11.5" fontWeight="800" textAnchor="middle">h_θ(o) Representation</text>
                <text x="257" y="67" fill="#93c5fd" fontSize="9.5" textAnchor="middle">{dynamicsBlocks} ResBlocks ({hiddenDim}ch){isV2Optimized ? " + SE" : ""}</text>
                <text x="257" y="82" fill="#64748b" fontSize="8" textAnchor="middle">{isV2Optimized ? "GroupNorm + MinMax Scaling" : `Field ~${1 + 2 * (1 + 2 * dynamicsBlocks)}×${1 + 2 * (1 + 2 * dynamicsBlocks)} hex`}</text>
              </g>

              {/* Node 3: Latent State Manifold */}
              <g
                onClick={() => setSelectedNodeId("latent")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="365"
                  y="10"
                  width="130"
                  height="86"
                  rx="10"
                  fill={selectedNodeId === "latent" ? "#065f46" : "#064e3b"}
                  stroke="#10b981"
                  strokeWidth="2.5"
                  filter="url(#glow-green)"
                />
                <text x="430" y="30" fill="#6ee7b7" fontSize="9" fontWeight="700" textAnchor="middle">LATENT MANIFOLD</text>
                <text x="430" y="50" fill="#ffffff" fontSize="15" fontWeight="800" textAnchor="middle">s_{unrollStep}</text>
                <text x="430" y="68" fill="#a7f3d0" fontSize="11" fontWeight="700" textAnchor="middle">{hiddenDim}×{boardH}×{boardW}</text>
                <text x="430" y="84" fill="#34d399" fontSize="8.5" textAnchor="middle">
                  {unrollStep === 0 ? "h(o) Root" : `g(s,a) Step ${unrollStep}`}
                </text>
              </g>

              {/* Node 4: Action Conditioning */}
              <g
                onClick={() => setSelectedNodeId("action")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="365"
                  y="125"
                  width="130"
                  height="72"
                  rx="8"
                  fill={selectedNodeId === "action" ? "#78350f" : "#1e293b"}
                  stroke="#f59e0b"
                  strokeWidth={selectedNodeId === "action" ? "2.5" : "1.5"}
                />
                <text x="430" y="145" fill="#fbbf24" fontSize="9" fontWeight="700" textAnchor="middle">MCTS ACTION</text>
                <text x="430" y="165" fill="#f8fafc" fontSize="11" fontWeight="700" textAnchor="middle">a_{unrollStep} (0..{actionDim - 1})</text>
                <text x="430" y="182" fill="#94a3b8" fontSize="8" textAnchor="middle">1×{boardH}×{boardW} broadcast</text>
              </g>

              {/* Node 5: Dynamics Recurrent Network */}
              <g
                onClick={() => setSelectedNodeId("dynamics")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="180"
                  y="125"
                  width="155"
                  height="72"
                  rx="8"
                  fill={selectedNodeId === "dynamics" ? "#7c2d12" : "#1e293b"}
                  stroke={unrollStep > 0 ? "#f97316" : "#475569"}
                  strokeWidth="2"
                />
                <text x="257" y="145" fill="#fbbf24" fontSize="9" fontWeight="700" textAnchor="middle">RECURRENT DYNAMICS</text>
                <text x="257" y="163" fill="#ffffff" fontSize="10.5" fontWeight="800" textAnchor="middle">g_θ(s, a) ➔ s_{Math.min(unrollStep + 1, maxUnroll)}</text>
                <text x="257" y="179" fill="#fdba74" fontSize="8.5" textAnchor="middle">{dynamicsBlocks} ResBlocks {isV2Optimized ? "+ SE + Two-Hot" : "+ Reward"}</text>
              </g>

              {/* Node 6: Strategic Manager Network (H-EZ-M Level 1) */}
              <g
                onClick={() => setSelectedNodeId("manager_network")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="15"
                  y="125"
                  width="135"
                  height="72"
                  rx="8"
                  fill={selectedNodeId === "manager_network" ? "#581c87" : "#1e1b4b"}
                  stroke={selectedNodeId === "manager_network" ? "#d8b4fe" : "#a855f7"}
                  strokeWidth={selectedNodeId === "manager_network" ? "2.5" : "1.5"}
                />
                <text x="82" y="145" fill="#c084fc" fontSize="8.5" fontWeight="700" textAnchor="middle">LEVEL 1 • STRATEGIC</text>
                <text x="82" y="163" fill="#ffffff" fontSize="10.5" fontWeight="800" textAnchor="middle">Manager Network</text>
                <text x="82" y="179" fill="#e9d5ff" fontSize="8" textAnchor="middle">Macro Goal g_T (16×16 Heatmap)</text>
              </g>

              {/* Node 7: Task Conditioning & FiLM (EZ-M) */}
              <g
                onClick={() => setSelectedNodeId("task_conditioning")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="180"
                  y="225"
                  width="155"
                  height="75"
                  rx="8"
                  fill={selectedNodeId === "task_conditioning" ? "#78350f" : "#1c1917"}
                  stroke={selectedNodeId === "task_conditioning" ? "#fcd34d" : "#d97706"}
                  strokeWidth={selectedNodeId === "task_conditioning" ? "2.5" : "1.5"}
                />
                <text x="257" y="244" fill="#fbbf24" fontSize="8.5" fontWeight="700" textAnchor="middle">EZ-M MULTI-TASK</text>
                <text x="257" y="262" fill="#ffffff" fontSize="10.5" fontWeight="800" textAnchor="middle">Task FiLM Layer</text>
                <text x="257" y="278" fill="#fde68a" fontSize="8" textAnchor="middle">e_τ ({taskEmbedDim}d) ➔ (1+γ)z+β Zero-Init</text>
              </g>

              {/* Node 8: Loss Balancer & Multi-Task PCGrad */}
              <g
                onClick={() => setSelectedNodeId("loss_balancer")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="15"
                  y="225"
                  width="135"
                  height="75"
                  rx="8"
                  fill={selectedNodeId === "loss_balancer" ? "#064e3b" : "#022c22"}
                  stroke={selectedNodeId === "loss_balancer" ? "#6ee7b7" : "#059669"}
                  strokeWidth={selectedNodeId === "loss_balancer" ? "2.5" : "1.5"}
                />
                <text x="82" y="244" fill="#34d399" fontSize="8.5" fontWeight="700" textAnchor="middle">GRADIENT SURGERY</text>
                <text x="82" y="262" fill="#ffffff" fontSize="10.5" fontWeight="800" textAnchor="middle">PCGrad Balancer</text>
                <text x="82" y="278" fill="#a7f3d0" fontSize="8" textAnchor="middle">Orthogonal Projection (g_i·g_j ≥ 0)</text>
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
            Runtime unrolled architecture for <b>{runId}</b>. All components recalculate tensor shapes, receptive fields, and parameter counts dynamically.
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
                  <span>🔬</span> Live Head Diagnostics: {selectedNode.name}
                </span>
                <span style={{ fontSize: 9, background: "#064e3b", color: "#6ee7b7", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                  HEALTHY
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11 }}>
                {selectedNodeId === "policy" && (
                  <>
                    <div><span className="muted">Policy Loss:</span> <b style={{ color: "#38bdf8" }}>{fmtNum(polLoss, 4)}</b></div>
                    <div><span className="muted">Entropy:</span> <b style={{ color: "#f8fafc" }}>{fmtNum(polEntropy, 3)}</b></div>
                    <div><span className="muted">Prior Confidence:</span> <b style={{ color: "#34d399" }}>{fmtPercent(polConfidence)}</b></div>
                    <div><span className="muted">Decision Margin:</span> <b style={{ color: "#fbbf24" }}>{fmtNum(polMargin, 3)}</b></div>
                  </>
                )}
                {selectedNodeId === "value" && (
                  <>
                    <div><span className="muted">Value Loss:</span> <b style={{ color: "#22c55e" }}>{fmtNum(valLoss, 4)}</b></div>
                    <div><span className="muted">Explained Variance:</span> <b style={{ color: "#34d399" }}>{fmtNum(valExpVar, 3)}</b></div>
                    <div><span className="muted">MCTS Q-Sat:</span> <b style={{ color: qSatRate !== null && qSatRate < 0.05 ? "#34d399" : "#f59e0b" }}>{fmtPercent(qSatRate)}</b></div>
                    <div><span className="muted">Return Proxy:</span> <b style={{ color: "#38bdf8" }}>{fmtNum(valWinRate, 3)}</b></div>
                  </>
                )}
                {selectedNodeId === "aux_objective" && (
                  <>
                    <div><span className="muted">Objective Loss:</span> <b style={{ color: "#f43f5e" }}>{fmtNum(objLoss, 4)}</b></div>
                    <div><span className="muted">Opportunity Take:</span> <b style={{ color: "#34d399" }}>{fmtPercent(objTakeRate)}</b></div>
                    <div><span className="muted">Conversion Efficiency:</span> <b style={{ color: "#38bdf8" }}>{fmtNum(objConversionEff, 4)}</b></div>
                    <div><span className="muted">Captured VPs Avg:</span> <b style={{ color: "#fbbf24" }}>{fmtNum(objCapturedAvg, 2, " VP")}</b></div>
                  </>
                )}
                {selectedNodeId === "consistency" && (
                  <>
                    <div><span className="muted">Consistency Loss:</span> <b style={{ color: "#c084fc" }}>{fmtSci(conLoss)}</b></div>
                    <div><span className="muted">Reanalysis Coverage:</span> <b style={{ color: "#34d399" }}>{fmtPercent(conReanalysisCov, 0)}</b></div>
                    <div><span className="muted">Consistency Pairs:</span> <b style={{ color: "#38bdf8" }}>{conPairs !== null ? conPairs.toLocaleString() : "—"}</b></div>
                    <div><span className="muted">Spatial Invariance:</span> <b style={{ color: "#34d399" }}>{conLoss !== null ? "Invariant" : "—"}</b></div>
                  </>
                )}
                {selectedNodeId === "threat_map" && hasThreatHead && (
                  <>
                    <div><span className="muted">Threat Loss:</span> <b style={{ color: "#eab308" }}>{fmtNum(threatLoss, 4)}</b></div>
                    <div><span className="muted">Max Threat:</span> <b style={{ color: "#fef08a" }}>{fmtPercent(threatMax)}</b></div>
                    <div><span className="muted">Fire Coverage:</span> <b style={{ color: "#34d399" }}>{fmtPercent(threatCov)}</b></div>
                    <div><span className="muted">Grid:</span> <b style={{ color: "#38bdf8" }}>{boardH}×{boardW} hex</b></div>
                  </>
                )}
                {selectedNodeId === "attrition" && hasAttritionHead && (
                  <>
                    <div><span className="muted">Attrition Loss:</span> <b style={{ color: "#06b6d4" }}>{fmtNum(attritionLoss, 4)}</b></div>
                    <div><span className="muted">Casualty Ratio:</span> <b style={{ color: "#67e8f9" }}>{fmtNum(attritionExchange, 2, "x")}</b></div>
                    <div><span className="muted">Exchange:</span> <b style={{ color: attritionExchange !== null && attritionExchange >= 1.0 ? "#34d399" : "#f59e0b" }}>{attritionExchange !== null ? (attritionExchange >= 1.0 ? "Favorable" : "Unfavorable") : "—"}</b></div>
                    <div><span className="muted">Loss Vector:</span> <b style={{ color: "#38bdf8" }}>2 Dim [A, E]</b></div>
                  </>
                )}
                {selectedNodeId === "morale" && hasMoraleHead && (
                  <>
                    <div><span className="muted">Morale Loss:</span> <b style={{ color: "#ec4899" }}>{fmtNum(moraleLoss, 4)}</b></div>
                    <div><span className="muted">Suppression Risk:</span> <b style={{ color: moraleRisk !== null && moraleRisk < 0.3 ? "#34d399" : moraleRisk !== null && moraleRisk < 0.6 ? "#fbbf24" : "#f43f5e" }}>{fmtNum(moraleRisk, 2)}</b></div>
                    <div><span className="muted">Dominant State:</span> <b style={{ color: "#fbcfe8" }}>{moraleRisk !== null ? (moraleRisk < 0.3 ? "NORMAL" : moraleRisk < 0.6 ? "PINNED" : "SUPPRESSED") : "—"}</b></div>
                    <div><span className="muted">Cohesion Levels:</span> <b style={{ color: "#38bdf8" }}>4 Classes</b></div>
                  </>
                )}
              </div>
              {onNavigateToHeadDiagnostics && (
                <button
                  onClick={onNavigateToHeadDiagnostics}
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
                  🔬 View Full Head Diagnostics (XAI) ➔
                </button>
              )}
            </div>
          )}

          {/* Dedicated Task Conditioning (EZ-M) Diagnostics Banner */}
          {selectedNodeId === "task_conditioning" && (
            <div style={{ background: "rgba(217, 119, 6, 0.1)", border: "1px solid #d97706", borderRadius: 6, padding: "8px 10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#fbbf24", display: "flex", alignItems: "center", gap: 4 }}>
                  <span>🧩</span> Multi-Task Conditioning (EZ-M) Status
                </span>
                <span style={{ fontSize: 9, background: "#78350f", color: "#fef3c7", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                  FiLM ACTIVE
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11 }}>
                <div><span className="muted">Multi-Task Mode:</span> <b style={{ color: "#34d399" }}>{enableMultitask ? "Enabled" : "Single-Task"}</b></div>
                <div><span className="muted">Total Tasks:</span> <b style={{ color: "#38bdf8" }}>{numTasks} scenarios</b></div>
                <div><span className="muted">Embedding Dim:</span> <b style={{ color: "#fbbf24" }}>{taskEmbedDim} dims</b></div>
                <div><span className="muted">FiLM Modulation:</span> <b style={{ color: "#34d399" }}>Zero-Init Identity</b></div>
                <div><span className="muted">Replay Stratification:</span> <b style={{ color: "#c084fc" }}>Uniform Multi-Queue</b></div>
                <div><span className="muted">Negative Transfer:</span> <b style={{ color: "#34d399" }}>Mitigated (PCGrad)</b></div>
              </div>
            </div>
          )}

          {/* Dedicated Manager Network (H-EZ-M Level 1) Diagnostics Banner */}
          {selectedNodeId === "manager_network" && (
            <div style={{ background: "rgba(168, 85, 247, 0.1)", border: "1px solid #a855f7", borderRadius: 6, padding: "8px 10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#d8b4fe", display: "flex", alignItems: "center", gap: 4 }}>
                  <span>🎖️</span> Strategic Manager Network (H-EZ-M v3.0)
                </span>
                <span style={{ fontSize: 9, background: "#581c87", color: "#e9d5ff", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                  LEVEL 1 COMMANDER
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11 }}>
                <div><span className="muted">Macro Cycle Horizon:</span> <b style={{ color: "#c084fc" }}>T ≤ 8 turns</b></div>
                <div><span className="muted">Tactical Modes:</span> <b style={{ color: "#38bdf8" }}>{numGoalModes} Modes (Assault, Hold...)</b></div>
                <div><span className="muted">Spatial Goal Map:</span> <b style={{ color: "#fbbf24" }}>16×16 Heatmap</b></div>
                <div><span className="muted">Topography IPB:</span> <b style={{ color: "#34d399" }}>5D Context Tensor</b></div>
                <div><span className="muted">Worker Modulation:</span> <b style={{ color: "#a855f7" }}>SpatialGoalFiLM Bridge</b></div>
                <div><span className="muted">Prior Shaping:</span> <b style={{ color: "#34d399" }}>+35% π Root Boost</b></div>
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
                <span>♟️</span> Open Strategic Macro Planner &amp; Doctrine View ➔
              </button>
            </div>
          )}

          {/* Dedicated Loss Balancer & PCGrad Diagnostics Banner */}
          {selectedNodeId === "loss_balancer" && (
            <div style={{ background: "rgba(5, 150, 105, 0.1)", border: "1px solid #059669", borderRadius: 6, padding: "8px 10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#34d399", display: "flex", alignItems: "center", gap: 4 }}>
                  <span>⚖️</span> Adaptive Loss Balancer &amp; PCGrad Surgery
                </span>
                <span style={{ fontSize: 9, background: "#064e3b", color: "#a7f3d0", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                  GRADIENT SURGERY
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11 }}>
                <div><span className="muted">Conflict Resolution:</span> <b style={{ color: "#34d399" }}>PCGrad (Orthogonal Projection)</b></div>
                <div><span className="muted">Cosine Telemetry:</span> <b style={{ color: "#38bdf8" }}>CosSim(i, j) Tracked</b></div>
                <div><span className="muted">Value / Reward Target:</span> <b style={{ color: "#fbbf24" }}>Two-Hot (601 bins)</b></div>
                <div><span className="muted">Reanalysis Target:</span> <b style={{ color: "#34d399" }}>Fast Vectorized Slice</b></div>
                <div><span className="muted">GradNorm Balancing:</span> <b style={{ color: "#a855f7" }}>Dynamic Weights</b></div>
                <div><span className="muted">Pareto Guarantee:</span> <b style={{ color: "#34d399" }}>Zero Destructive Drift</b></div>
              </div>
            </div>
          )}

          {/* Dedicated Macro Planner Diagnostics & Quick Actions Banner */}
          {selectedNodeId === "macro_planner" && (
            <div style={{ background: "rgba(168, 85, 247, 0.1)", border: "1px solid #a855f7", borderRadius: 6, padding: "8px 10px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#d8b4fe", display: "flex", alignItems: "center", gap: 4 }}>
                  <span>♟️</span> Macro Doctrinal Status (H-EZ-M 4-Tier Hierarchy)
                </span>
                <span style={{ fontSize: 9, background: "#581c87", color: "#e9d5ff", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                  8 CANONICAL ROLES
                </span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11 }}>
                <div><span className="muted">Dominant Posture:</span> <b style={{ color: "#c084fc" }}>{macroStats.hasRealData ? (macroStats.assaultPct >= 50 ? "ASSAULT_VP" : "DEFENSIVE_HOLD") : "N/A"}</b></div>
                <div><span className="muted">VP Assault:</span> <b style={{ color: "#38bdf8" }}>{macroStats.hasRealData ? `${macroStats.assaultPct.toFixed(1)}%` : "N/A"}</b></div>
                <div><span className="muted">Spearhead:</span> <b style={{ color: "#fbbf24" }}>{macroStats.hasRealData ? `${macroStats.spearheadPct.toFixed(1)}%` : "N/A"}</b></div>
                <div><span className="muted">Fire Support:</span> <b style={{ color: "#fb923c" }}>{macroStats.hasRealData ? `${macroStats.fireSupportPct.toFixed(1)}%` : "N/A"}</b></div>
                <div><span className="muted">Context Mutations:</span> <b style={{ color: "#f43f5e" }}>{macroStats.hasRealData ? `${macroStats.mutatedPct.toFixed(1)}%` : "N/A"}</b></div>
                <div><span className="muted">MCTS Overrides:</span> <b style={{ color: "#f59e0b" }}>{macroStats.hasRealData ? `${macroStats.mctsOverridePct.toFixed(1)}%` : "N/A"}</b></div>
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
                <span>♟️</span> Open Macro Planner &amp; Doctrine View ➔
              </button>
            </div>
          )}
          <div>
            <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 700, textTransform: "uppercase" }}>
              Component Inspector
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
              <div className="muted" style={{ fontSize: 10 }}>Input Shape</div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#f8fafc", marginTop: 2 }}>
                {selectedNode.inShape}
              </div>
            </div>
            <div style={{ background: "#0f172a", padding: 8, borderRadius: 6 }}>
              <div className="muted" style={{ fontSize: 10 }}>Output Shape</div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#34d399", marginTop: 2 }}>
                {selectedNode.outShape}
              </div>
            </div>
            <div style={{ background: "#0f172a", padding: 8, borderRadius: 6 }}>
              <div className="muted" style={{ fontSize: 10 }}>Receptive Field</div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#fbbf24", marginTop: 2 }}>
                {selectedNode.receptiveField}
              </div>
            </div>
            <div style={{ background: "#0f172a", padding: 8, borderRadius: 6 }}>
              <div className="muted" style={{ fontSize: 10 }}>Parameters</div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#c084fc", marginTop: 2 }}>
                {selectedNode.paramEstimate}
              </div>
            </div>
          </div>

          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", marginBottom: 6 }}>
              Internal Layer Architecture:
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 11, color: "#e2e8f0", display: "flex", flexDirection: "column", gap: 4 }}>
              {selectedNode.architecture.map((layer, idx) => (
                <li key={idx}><code>{layer}</code></li>
              ))}
            </ul>
          </div>

          <div style={{ background: "rgba(14, 165, 233, 0.08)", border: "1px solid #0284c7", borderRadius: 6, padding: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: "#38bdf8", marginBottom: 2 }}>
              MLOps Functional Details (Run {runId})
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
              <span>📡</span> Catalog of {inChannels} Spatial Input Channels (Tensor {inChannels}×{boardH}×{boardW})
            </h4>
            <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
              Hex-by-hex spatial encoding of the VOEC tactical simulation state for <b>{runId}</b>.
            </div>
          </div>

          <div style={{ display: "flex", gap: 4, background: "#0f172a", padding: 3, borderRadius: 6, flexWrap: "wrap" }}>
            {[
              { id: "all", label: `All (${dynamicChannelsList.length})` },
              { id: "units", label: "Units" },
              { id: "terrain", label: "Terrain/LOS" },
              { id: "vp", label: "VPs" },
              { id: "hex", label: "Hex Topology" },
              { id: "global", label: "Globals" },
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
                      #{sc.rank} ({isHigh ? "High" : isMod ? "Moderate" : isLow ? "Low" : "Inactive"})
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
              <span>⚡</span> Channel Effectiveness &amp; Saliency Attribution Analyzer (Ablation &amp; Saliency)
            </h4>
            <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
              Empirical diagnostics: Gradient saliency (∇v, ∇π) and zero-occlusion perturbation (|Δv|, D_KL) in VOEC tactical simulator.
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
                  ? "Running Analysis (CPU/GPU)..."
                  : attributionReport
                  ? "Re-run Channel Analysis"
                  : "Run Effectiveness Analysis"}
              </span>
            </button>
          </div>
        </div>

        {/* Loading Banner */}
        {analyzing && (
          <div style={{ background: "rgba(2, 132, 199, 0.15)", border: "1px solid #0284c7", borderRadius: 6, padding: "12px 16px" }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
              <span>⏳</span> Analysis running for <code>{runId}</code>...
            </div>
            <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
              Loading network checkpoint, sampling rollouts with VOEC simulator, computing gradient saliency ∇v and ∇π, and evaluating value shift (|Δv|) and policy divergence (D_KL) channel by channel. This operation may take 10 to 20 seconds.
            </div>
          </div>
        )}

        {/* Error Banner */}
        {analysisError && (
          <div style={{ background: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: 6, padding: "10px 14px", color: "#fca5a5", fontSize: 11 }}>
            <b>Error running analysis:</b> {analysisError}
          </div>
        )}

        {/* Results View */}
        {attributionReport && !analyzing && (
          <>
            {/* KPI Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>
              <div style={{ background: "#0f172a", borderRadius: 6, padding: "8px 12px", border: "1px solid #334155" }}>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Analyzed Samples</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>
                  {Number(attributionReport.num_observations_analyzed ?? 0)} observations
                </div>
                <div className="muted" style={{ fontSize: 10 }}>4 VOEC seeds × 15 steps</div>
              </div>

              <div style={{ background: "#0f172a", borderRadius: 6, padding: "8px 12px", border: "1px solid #334155" }}>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>#1 Most Critical Channel</div>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#34d399", marginTop: 2 }}>
                  {topChannel ? `#${topChannel.index} ${topChannel.name}` : "N/A"}
                </div>
                <div className="muted" style={{ fontSize: 10 }}>
                  Score: {topChannel ? Number(topChannel.importance_score).toFixed(3) : 0} | Flip: {topChannel ? `${topChannel.decision_flip_rate}%` : "0%"}
                </div>
              </div>

              <div style={{ background: "#0f172a", borderRadius: 6, padding: "8px 12px", border: "1px solid #334155" }}>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Key Tactical Channels</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#38bdf8", marginTop: 2 }}>
                  Ch 21 (Frontline): #{ch21Info?.rank ?? "-"} (Score {ch21Info ? Number(ch21Info.importance_score).toFixed(3) : "-"})
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#34d399" }}>
                  Ch 07 (Threat): #{ch7Info?.rank ?? "-"} (Score {ch7Info ? Number(ch7Info.importance_score).toFixed(3) : "-"})
                </div>
              </div>

              <div style={{ background: "#0f172a", borderRadius: 6, padding: "8px 12px", border: "1px solid #334155" }}>
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Effectiveness Distribution</div>
                <div style={{ display: "flex", gap: 6, marginTop: 4, fontSize: 11, fontWeight: 700 }}>
                  <span style={{ color: "#34d399" }}>{countsByStatus.HIGH || 0} High</span>
                  <span style={{ color: "#38bdf8" }}>{countsByStatus.MODERATE || 0} Med</span>
                  <span style={{ color: "#fbbf24" }}>{countsByStatus.LOW || 0} Low</span>
                  <span style={{ color: "#f43f5e" }}>{countsByStatus.DEAD || 0} Inact</span>
                </div>
                <div className="muted" style={{ fontSize: 10, marginTop: 2 }}>Across {rankedChannelsList.length} total channels</div>
              </div>
            </div>

            {/* Category summary pills */}
            {attributionReport.categories_summary && (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                <span className="muted" style={{ fontSize: 11, fontWeight: 600 }}>Impact by Category:</span>
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
                      ({catData.active_channels}/{catData.total_channels} active)
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Filter buttons & Table */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4, flexWrap: "wrap", gap: 6 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#cbd5e1" }}>
                Detailed Sensitivity &amp; Ablation Ranking
              </div>
              <div style={{ display: "flex", gap: 4 }}>
                {[
                  { id: "all", label: `All (${rankedChannelsList.length})` },
                  { id: "HIGH_EFFECTIVENESS", label: `High (${countsByStatus.HIGH || 0})` },
                  { id: "MODERATE_EFFECTIVENESS", label: `Moderate (${countsByStatus.MODERATE || 0})` },
                  { id: "LOW_EFFECTIVENESS", label: `Low (${countsByStatus.LOW || 0})` },
                  { id: "DEAD_CHANNEL", label: `Inactive (${countsByStatus.DEAD || 0})` },
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
                    <th style={{ padding: "8px 10px" }}>Channel</th>
                    <th style={{ padding: "8px 10px" }}>Category</th>
                    <th style={{ padding: "8px 10px" }}>Status</th>
                    <th style={{ padding: "8px 10px", minWidth: 160 }}>Composite Score</th>
                    <th style={{ padding: "8px 10px" }}>Gradient (π / v)</th>
                    <th style={{ padding: "8px 10px" }}>Ablation (Flip / Δv)</th>
                    <th style={{ padding: "8px 10px", minWidth: 200 }}>Diagnostic / Recommendation</th>
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
                              ? "HIGH"
                              : rc.status === "MODERATE_EFFECTIVENESS"
                              ? "MODERATE"
                              : rc.status === "LOW_EFFECTIVENESS"
                              ? "LOW"
                              : "INACTIVE"}
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
              Channel effectiveness analysis has not yet been computed for run <b>{runId}</b>.
            </div>
            <div className="muted" style={{ fontSize: 11, maxWidth: 500, margin: "0 auto 12px auto" }}>
              Click the button above to run real-time empirical analysis (samples rollouts with VOEC simulator, evaluates gradient saliency, and measures policy/value degradation under occlusion).
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
              ⚡ Run Analysis Now
            </button>
          </div>
        )}
      </div>
      )}
    

      {/* SECTION 4: HIERARCHICAL STRATEGIC MACRO-PLANNER (H-EZ-M v3.0) */}
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
                <span>♟️</span> H-EZ-M v3.0 Hierarchical Strategic Commander &amp; Doctrinal Profiling
              </h4>
              <div className="muted" style={{ fontSize: 12, marginTop: 4, maxWidth: 900 }}>
                Decoupled four-tier decision architecture: <b>Tier 1 Physical &amp; Ballistic Invariants (VOEC)</b>, <b>Tier 2 Strategic Goal Heatmap (Manager Network Level 1)</b>, <b>Tier 3 Inductive Doctrinal Bias (8 canonical roles, 2D footprints &amp; contextual mutation rules)</b>, and <b>Tier 4 Autonomous Tactical Operator (Worker MCTS PUCT with 512 simulations and 6 unroll steps)</b>.
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, background: "rgba(126, 34, 206, 0.25)", border: "1px solid #a855f7", color: "#d8b4fe", padding: "4px 10px", borderRadius: 6, fontWeight: 700 }}>
                4 Ontological Tiers
              </span>
              <span style={{ fontSize: 11, background: "rgba(14, 165, 233, 0.25)", border: "1px solid #0ea5e9", color: "#7dd3fc", padding: "4px 10px", borderRadius: 6, fontWeight: 700 }}>
                Manager Network (H-EZ-M)
              </span>
              <span style={{ fontSize: 11, background: "rgba(234, 179, 8, 0.25)", border: "1px solid #eab308", color: "#fef08a", padding: "4px 10px", borderRadius: 6, fontWeight: 700 }}>
                8 Canonical Roles
              </span>
              <span style={{ fontSize: 11, background: "rgba(34, 197, 94, 0.25)", border: "1px solid #22c55e", color: "#86efac", padding: "4px 10px", borderRadius: 6, fontWeight: 700 }}>
                Prior Shaping (+35% π)
              </span>
              <span style={{ fontSize: 11, background: "rgba(244, 63, 94, 0.25)", border: "1px solid #f43f5e", color: "#fda4af", padding: "4px 10px", borderRadius: 6, fontWeight: 700 }}>
                PCGrad Balancer
              </span>
              <span style={{ fontSize: 11, background: "rgba(2, 132, 199, 0.25)", border: "1px solid #0284c7", color: "#38bdf8", padding: "4px 10px", borderRadius: 6, fontWeight: 700 }}>
                H-EZ-M v3.0 Active
              </span>
            </div>
          </div>

          {/* TOP ARCHITECTURAL BREAKDOWN: THE 4 ONTOLOGICAL TIERS */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
            {/* Tier 1 */}
            <div style={{ background: "#0b1329", border: "1px solid #1e3a8a", borderRadius: 8, padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 12, fontWeight: 800, color: "#38bdf8", textTransform: "uppercase" }}>
                  1. Physical &amp; Ballistic Tier
                </span>
                <span style={{ fontSize: 9, background: "#1e3a8a", color: "#bfdbfe", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                  VOEC Hard Rules
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#cbd5e1", lineHeight: 1.4 }}>
                Mechanical and inviolable simulator invariants: hexagon-to-hexagon line of sight (LOS), strict weapon firing ranges, terrain movement costs, armor protection tables, and dice combat resolution. Latent dynamics g<sub>θ</sub> learns this invariant physics across all scenarios.
              </div>
            </div>

            {/* Tier 2 */}
            <div style={{ background: "#0b2027", border: "1px solid #0e7490", borderRadius: 8, padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 12, fontWeight: 800, color: "#22d3ee", textTransform: "uppercase" }}>
                  2. Strategic Goal Heatmap
                </span>
                <span style={{ fontSize: 9, background: "#155e75", color: "#cffafe", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                  Manager Network
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#cbd5e1", lineHeight: 1.4 }}>
                Macro-strategy neural module operating on a multi-turn cycle (T ≤ 8). Generates spatial macro-goal tensors (16×16 heatmaps) and operational modes (Assault VP, Defensive Hold, Zone Suppress) conditioned via FiLM bridge into worker latent space.
              </div>
            </div>

            {/* Tier 3 */}
            <div style={{ background: "#1a1329", border: "1px solid #7e22ce", borderRadius: 8, padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 12, fontWeight: 800, color: "#d8b4fe", textTransform: "uppercase" }}>
                  3. Inductive Doctrinal Bias
                </span>
                <span style={{ fontSize: 9, background: "#581c87", color: "#f3e8ff", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                  Soft Prior Shaping
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#cbd5e1", lineHeight: 1.4 }}>
                Catalog of 8 canonical roles, 2D optimal engagement footprints (channels 24/25), 3 cascading contextual mutation rules, Dunnigan Tactical Reserve, and Henry Hyde tactical cohesion. Injects soft +35% π prior shaping at the MCTS root.
              </div>
            </div>

            {/* Tier 4 */}
            <div style={{ background: "#062318", border: "1px solid #047857", borderRadius: 8, padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 12, fontWeight: 800, color: "#4ade80", textTransform: "uppercase" }}>
                  4. Tactical Operator MCTS
                </span>
                <span style={{ fontSize: 9, background: "#065f46", color: "#a7f3d0", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                  Worker RL Search
                </span>
              </div>
              <div style={{ fontSize: 11, color: "#cbd5e1", lineHeight: 1.4 }}>
                Deep Monte Carlo Tree Search (512 simulations, 6 unroll steps) with Two-Hot categorical value/reward representation, batched temporal consistency loss, and autonomous Q(s, a) override if search proves a superior tactical payoff.
              </div>
            </div>
          </div>

          {/* KPI Summary Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10 }}>
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6, padding: "10px 12px" }}>
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Macro Strategic Postures (Level 1)</div>
              <div style={{ fontSize: 15, fontWeight: 800, color: "#f8fafc", marginTop: 2 }}>3 Operational Modes</div>
              <div style={{ fontSize: 10.5, color: "#94a3b8", marginTop: 2 }}>ASSAULT_VP • DEFENSIVE_HOLD • ZONE_SUPPRESS</div>
            </div>
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6, padding: "10px 12px" }}>
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Squad Doctrinal Roles</div>
              <div style={{ fontSize: 15, fontWeight: 800, color: "#facc15", marginTop: 2 }}>8 Canonical Roles</div>
              <div style={{ fontSize: 10.5, color: "#94a3b8", marginTop: 2 }}>Spearhead • Fire Support • Close Def • Recon...</div>
            </div>
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6, padding: "10px 12px" }}>
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Contextual Mutation Rules</div>
              <div style={{ fontSize: 15, fontWeight: 800, color: "#f43f5e", marginTop: 2 }}>3 Priority Rules</div>
              <div style={{ fontSize: 10.5, color: "#94a3b8", marginTop: 2 }}>VP Pressure • Morale/Health • Flank Isolation</div>
            </div>
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 6, padding: "10px 12px" }}>
              <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Root Prior Modulation</div>
              <div style={{ fontSize: 15, fontWeight: 800, color: "#22c55e", marginTop: 2 }}>+35% Prior Shaping</div>
              <div style={{ fontSize: 10.5, color: "#94a3b8", marginTop: 2 }}>P_mod(a) = P(a) * (1 + 0.35) at root</div>
            </div>
          </div>

          {/* EMPIRICAL TACTICAL TELEMETRY CARD */}
          <div style={{ background: "#0b1220", border: "1px solid #1e3a8a", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 800, color: "#38bdf8", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>📊</span> Empirical Tactical Telemetry: Observed In-Game Model Behaviors
                </div>
                <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                  {macroStats.hasRealData
                    ? `Calculated over ${macroStats.totalSteps} recorded decisions in evaluation matches for ${runId}.`
                    : `No evaluation match decisions recorded for this model. Run an evaluation to collect empirical telemetry.`}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ fontSize: 10, background: macroStats.hasRealData ? "rgba(34, 197, 94, 0.2)" : "rgba(100, 116, 139, 0.2)", border: `1px solid ${macroStats.hasRealData ? "#22c55e" : "#64748b"}`, color: macroStats.hasRealData ? "#4ade80" : "#94a3b8", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>
                  {macroStats.hasRealData ? "✓ Evaluation Matches" : "No Evaluation Data"}
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
                  title="Open match replay viewer to inspect hex-by-hex tactics"
                >
                  <span>▶️</span> View in Tactical Replay
                </button>
              </div>
            </div>

            {/* Three Progress Bar Grids */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
              {/* Box 1: Macro Posture Distribution */}
              <div style={{ background: "#1e293b", padding: 10, borderRadius: 6, display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#f8fafc", textTransform: "uppercase" }}>
                  1. Macro Posture Distribution
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#f87171", fontWeight: 700 }}>⚔️ ASSAULT_VP (Offensive Assault)</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.assaultPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.assaultPct : 0}%`, height: "100%", background: "#ef4444" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#38bdf8", fontWeight: 700 }}>🛡️ DEFENSIVE_HOLD (Consolidation)</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.defPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.defPct : 0}%`, height: "100%", background: "#0284c7" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#c084fc", fontWeight: 700 }}>💥 ZONE_SUPPRESS (Zone Suppression)</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.zonePct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 6, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.zonePct : 0}%`, height: "100%", background: "#8b5cf6" }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Box 2: The 8 Doctrinal Roles in Battle */}
              <div style={{ background: "#1e293b", padding: 10, borderRadius: 6, display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#f8fafc", textTransform: "uppercase" }}>
                    2. The 8 Doctrinal Roles in Battle
                  </div>
                  <span style={{ fontSize: 9, color: "#94a3b8" }}>Canonical</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 12px" }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, marginBottom: 2 }}>
                      <span style={{ color: "#facc15", fontWeight: 700 }}>⚡ Spearhead</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.spearheadPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 5, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.spearheadPct : 0}%`, height: "100%", background: "#eab308" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, marginBottom: 2 }}>
                      <span style={{ color: "#fb923c", fontWeight: 700 }}>🎯 Fire Support</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.fireSupportPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 5, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.fireSupportPct : 0}%`, height: "100%", background: "#f97316" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, marginBottom: 2 }}>
                      <span style={{ color: "#ef4444", fontWeight: 700 }}>⚔️ Close Defense</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.closeDefPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 5, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.closeDefPct : 0}%`, height: "100%", background: "#ef4444" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, marginBottom: 2 }}>
                      <span style={{ color: "#38bdf8", fontWeight: 700 }}>🔭 Recon</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.reconPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 5, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.reconPct : 0}%`, height: "100%", background: "#38bdf8" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, marginBottom: 2 }}>
                      <span style={{ color: "#60a5fa", fontWeight: 700 }}>🛡️ VP Defender</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.defenderPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 5, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.defenderPct : 0}%`, height: "100%", background: "#3b82f6" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, marginBottom: 2 }}>
                      <span style={{ color: "#c084fc", fontWeight: 700 }}>👁️ Flank Screen</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.flankPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 5, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.flankPct : 0}%`, height: "100%", background: "#8b5cf6" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, marginBottom: 2 }}>
                      <span style={{ color: "#a855f7", fontWeight: 700 }}>🏛️ Tactical Reserve</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.reservePct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 5, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.reservePct : 0}%`, height: "100%", background: "#a855f7" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, marginBottom: 2 }}>
                      <span style={{ color: "#f43f5e", fontWeight: 700 }}>🩹 Recovery</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.recoverPct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 5, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.recoverPct : 0}%`, height: "100%", background: "#f43f5e" }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Box 3: Combat Dynamics, Mutations & MCTS */}
              <div style={{ background: "#1e293b", padding: 10, borderRadius: 6, display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#f8fafc", textTransform: "uppercase" }}>
                  3. Combat Dynamics, Mutations &amp; MCTS
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#38bdf8", fontWeight: 700 }}>🏃 Maneuver / Advance</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.movePct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 5, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.movePct : 0}%`, height: "100%", background: "#0284c7" }} />
                    </div>
                  </div>

                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 2 }}>
                      <span style={{ color: "#ef4444", fontWeight: 700 }}>💥 Fire &amp; Attack</span>
                      <span style={{ color: "#cbd5e1" }}>{macroStats.hasRealData ? `${macroStats.firePct.toFixed(1)}%` : "N/A"}</span>
                    </div>
                    <div style={{ background: "#0f172a", height: 5, borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ width: `${macroStats.hasRealData ? macroStats.firePct : 0}%`, height: "100%", background: "#ef4444" }} />
                    </div>
                  </div>

                  <div style={{ marginTop: 2, background: "#0f172a", padding: "5px 8px", borderRadius: 4, borderLeft: "3px solid #f43f5e" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 9.5, color: "#f43f5e", fontWeight: 700 }}>⚡ Contextual Mutations:</span>
                      <span style={{ fontSize: 10.5, fontWeight: 800, color: "#f43f5e" }}>
                        {macroStats.hasRealData ? `${macroStats.mutatedPct.toFixed(1)}%` : "N/A"}
                      </span>
                    </div>
                    <div className="muted" style={{ fontSize: 9 }}>
                      {macroStats.hasRealData ? `${macroStats.mutatedCount} decisions with dynamic role mutation.` : "Evaluation required."}
                    </div>
                  </div>

                  <div style={{ background: "#0f172a", padding: "5px 8px", borderRadius: 4, borderLeft: "3px solid #38bdf8" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 9.5, color: "#38bdf8", fontWeight: 700 }}>🧠 MCTS Override:</span>
                      <span style={{ fontSize: 10.5, fontWeight: 800, color: "#38bdf8" }}>
                        {macroStats.hasRealData ? `${macroStats.mctsOverridePct.toFixed(1)}%` : "N/A"}
                      </span>
                    </div>
                    <div className="muted" style={{ fontSize: 9 }}>
                      {macroStats.hasRealData ? "MCTS tree search corrected neural prior to enforce tactical posture." : "Evaluation required."}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* TWO MAIN COLUMNS: POSTURES & COMPLETE 8 ROLES CATALOG */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            {/* COLUMN 1: STRATEGIC POSTURES */}
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: "#38bdf8", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>🎯</span> Macro Strategic Postures
                </span>
                <span style={{ fontSize: 10, color: "#64748b" }}>Evaluated at start of each turn cycle</span>
              </div>
              <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                The macro planner evaluates Victory Point (VP) dynamics and issues team-wide strategic directives:
              </div>

              {/* POSTURE 1: ASSAULT_VP */}
              <div style={{ background: "#1e293b", border: "1px solid #ef4444", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#f87171", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>⚔️</span> ASSAULT_VP (Offensive Assault)
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(239, 68, 68, 0.2)", color: "#fca5a5", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Allied VPs ≤ Enemy VPs
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  Triggered when tied or trailing in victory points. Sets the <b>Priority Objective</b> to the nearest neutral or enemy VP and boosts actions closing distance toward it by <b>+35%</b>.
                </div>
              </div>

              {/* POSTURE 2: DEFENSIVE_HOLD */}
              <div style={{ background: "#1e293b", border: "1px solid #0284c7", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🛡️</span> DEFENSIVE_HOLD (Consolidation)
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(2, 132, 199, 0.2)", color: "#7dd3fc", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Allied VPs &gt; Enemy VPs
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  Triggered when leading in VPs while the match is underway. Orders squads to entrench within a 1-hex radius of allied VPs and penalizes reckless over-extension.
                </div>
              </div>

              {/* POSTURE 3: ZONE_SUPPRESS */}
              <div style={{ background: "#1e293b", border: "1px solid #8b5cf6", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#c084fc", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>💥</span> ZONE_SUPPRESS (Zone Suppression)
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(139, 92, 246, 0.2)", color: "#d8b4fe", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    100% VPs Consolidated
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  Triggered when all scenario victory objectives are captured. Reorients squads toward methodical suppression, crossfire traps, and eliminating lingering hostiles.
                </div>
              </div>
            </div>

            {/* COLUMN 2: HIERARCHICAL CONTEXTUAL MUTATION RULES */}
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: "#f43f5e", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>⚡</span> 3 Hierarchical Contextual Mutation Rules
                </span>
                <span style={{ fontSize: 10, color: "#64748b" }}>Strict Cascading Priority</span>
              </div>
              <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                At each inference step, squads evaluate these rules in strict priority order to dynamically adapt their doctrinal role:
              </div>

              {/* RULE 1: MORALE & CRITICAL HEALTH */}
              <div style={{ background: "#1e293b", border: "1px solid #f43f5e", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#fda4af", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🚨</span> Priority 1: Morale &amp; Critical Health
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(244, 63, 94, 0.2)", color: "#fecdd3", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    ➔ ROLE_RECOVER
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  <b>Trigger:</b> Unit in <code>PINNED</code>, <code>SUPPRESSED</code>, <code>FALLBACK</code>, or health &le; retreat threshold (Hyde 50% rule outside BUA/VPs). <b>Effect:</b> Instantly mutates to <code>ROLE_RECOVER</code> to seek defilade cover and rally.
                </div>
              </div>

              {/* RULE 2: FLANKED HEAVY SUPPORT */}
              <div style={{ background: "#1e293b", border: "1px solid #ef4444", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#f87171", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>⚠️</span> Priority 2: Isolation / Immediate Flank Threat
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(239, 68, 68, 0.2)", color: "#fca5a5", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    ➔ ROLE_CLOSE_DEFENSE
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  <b>Trigger:</b> Heavy support squad (<code>FIRE_SUPPORT</code>) with enemy adjacent (distance &le; 1 hex) without friendly infantry escort. <b>Effect:</b> Mutates to <code>ROLE_CLOSE_DEFENSE</code>, prioritizing survival and point-blank fire.
                </div>
              </div>

              {/* RULE 3: VP DEFICIT PRESSURE */}
              <div style={{ background: "#1e293b", border: "1px solid #eab308", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#fde047", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>⚔️</span> Priority 3: Decisive VP Pressure
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(234, 179, 8, 0.2)", color: "#fef08a", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    ➔ ROLE_SPEARHEAD
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  <b>Trigger:</b> VP deficit or late match phase (t &ge; 2/3 T_max) with unconquered VPs. <b>Effect:</b> Qualified support or screening units mutate to <code>ROLE_SPEARHEAD</code> for a coordinated breakthrough assault.
                </div>
              </div>

              {/* DUNNIGAN RESERVE */}
              <div style={{ background: "#1e293b", border: "1px solid #a855f7", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#d8b4fe", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🏛️</span> Dunnigan Tactical Reserve
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(168, 85, 247, 0.2)", color: "#e9d5ff", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    ➔ ROLE_TACTICAL_RESERVE
                  </span>
                </div>
                <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                  <b>Trigger:</b> Total force &ge; 4 squads and units located &gt; 5 hexes behind the active front line. <b>Effect:</b> Mobile reaction reserve held to plug enemy penetrations or exploit breakouts.
                </div>
              </div>
            </div>
          </div>

          {/* COMPLETE 8 ROLES CANONICAL CATALOG (GRID 4x2) */}
          <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <div>
                <span style={{ fontSize: 13, fontWeight: 800, color: "#facc15", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
                  <span>👥</span> Canonical Catalog of the 8 Doctrinal Roles (Profile Hierarchy)
                </span>
                <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                  Defined in <code>assets/catalogs/unit_catalog.json</code> and strictly typed in <code>DoctrineProfile</code>.
                </div>
              </div>
              <span style={{ fontSize: 10, background: "rgba(234, 179, 8, 0.2)", color: "#fef08a", border: "1px solid #eab308", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>
                100% of 19 Units Covered
              </span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 10 }}>
              {/* Role 1: SPEARHEAD */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(234, 179, 8, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#facc15", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>⚡</span> ROLE_SPEARHEAD
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(234, 179, 8, 0.15)", color: "#fef08a", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Spearhead / Assault Shock
                  </span>
                </div>
                <div style={{ fontSize: 10.5, color: "#cbd5e1" }}>
                  <b>Units:</b> Assault infantry, Fallschirmjäger, Medium Armor. <b>Range:</b> 0-2 hexes. <b>Mission:</b> Frontline breakthrough and direct assault on priority VPs.
                </div>
              </div>

              {/* Role 2: FIRE_SUPPORT */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(249, 115, 22, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#fb923c", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🎯</span> ROLE_FIRE_SUPPORT
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(249, 115, 22, 0.15)", color: "#fed7aa", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Heavy Fire Support
                  </span>
                </div>
                <div style={{ fontSize: 10.5, color: "#cbd5e1" }}>
                  <b>Units:</b> .50 M2HB HMG, M1919A4 MMG, MG42, 60mm/81mm Mortars, AT Guns. <b>Range:</b> 3-8 hexes. <b>Mission:</b> Continuous suppression, pinning enemy units, and area interdiction.
                </div>
              </div>

              {/* Role 3: CLOSE_DEFENSE */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(239, 68, 68, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#f87171", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>⚔️</span> ROLE_CLOSE_DEFENSE
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(239, 68, 68, 0.15)", color: "#fca5a5", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Close Defense / Point-Blank
                  </span>
                </div>
                <div style={{ fontSize: 10.5, color: "#cbd5e1" }}>
                  <b>Units:</b> Flanked heavy weapons or threatened squads at distance &le; 1 hex. <b>Range:</b> 0-1 hex. <b>Mission:</b> Immediate point-blank reactive fire and defensive survival.
                </div>
              </div>

              {/* Role 4: RECON */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(56, 189, 248, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#38bdf8", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🔭</span> ROLE_RECON
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(56, 189, 248, 0.15)", color: "#bae6fd", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Recon &amp; Tactical Spotting
                  </span>
                </div>
                <div style={{ fontSize: 10.5, color: "#cbd5e1" }}>
                  <b>Units:</b> Scout jeeps, Rangers, Snipers, light patrols. <b>Range:</b> 4-10 hexes. <b>Mission:</b> Fog-of-war clearing, early enemy detection, and target spotting.
                </div>
              </div>

              {/* Role 5: OBJECTIVE_DEFENDER */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(96, 165, 250, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#60a5fa", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🛡️</span> ROLE_OBJECTIVE_DEFENDER
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(96, 165, 250, 0.15)", color: "#bfdbfe", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    VP Objective Defender
                  </span>
                </div>
                <div style={{ fontSize: 10.5, color: "#cbd5e1" }}>
                  <b>Units:</b> Squads on or within 1 hex of allied VPs. <b>Terrain:</b> Bunkers, trenches, stone buildings. <b>Mission:</b> Entrenchment and denial of enemy recaptures.
                </div>
              </div>

              {/* Role 6: FLANK_SCREEN */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(192, 132, 252, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#c084fc", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>👁️</span> ROLE_FLANK_SCREEN
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(192, 132, 252, 0.15)", color: "#e9d5ff", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Flank Screen &amp; Security
                  </span>
                </div>
                <div style={{ fontSize: 10.5, color: "#cbd5e1" }}>
                  <b>Units:</b> Light infantry, secondary squads. <b>Range:</b> 2-4 hexes. <b>Mission:</b> Blind spot coverage, early warning, and containing enemy flanking attempts.
                </div>
              </div>

              {/* Role 7: TACTICAL_RESERVE */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(168, 85, 247, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#d8b4fe", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🏛️</span> ROLE_TACTICAL_RESERVE
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(168, 85, 247, 0.15)", color: "#f3e8ff", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Dunnigan Tactical Reserve
                  </span>
                </div>
                <div style={{ fontSize: 10.5, color: "#cbd5e1" }}>
                  <b>Units:</b> Rearguard squads (distance &gt; 5 hexes from active objective). <b>Mission:</b> Mobile reaction force to plug breaches or exploit breakthrough opportunities.
                </div>
              </div>

              {/* Role 8: RECOVER */}
              <div style={{ background: "#1e293b", border: "1px solid rgba(244, 63, 94, 0.4)", borderRadius: 6, padding: 10 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                  <span style={{ fontSize: 12, fontWeight: 800, color: "#fda4af", display: "flex", alignItems: "center", gap: 6 }}>
                    <span>🩹</span> ROLE_RECOVER
                  </span>
                  <span style={{ fontSize: 9, background: "rgba(244, 63, 94, 0.15)", color: "#fecdd3", padding: "1px 6px", borderRadius: 3, fontWeight: 700 }}>
                    Recovery / Tactical Withdrawal
                  </span>
                </div>
                <div style={{ fontSize: 10.5, color: "#cbd5e1" }}>
                  <b>Units:</b> Disorganized, suppressed, or heavily damaged squads (&lt;50% HP). <b>Mission:</b> Tactical withdrawal to cover/defilade, rally, and morale stabilization.
                </div>
              </div>
            </div>
          </div>

          {/* HYDE COHESION, PRIOR SHAPING & PCGRAD SURGERY */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
            {/* Box A: Henry Hyde Cohesion (2015) */}
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: "#38bdf8", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
                <span>🛡️</span> Tactical Cohesion Levels (Henry Hyde, 2015)
              </div>
              <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                Proximity between friendly squads in good order modulates tactical stability and resilience against panic:
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 11 }}>
                <div style={{ background: "#1e293b", padding: "6px 10px", borderRadius: 4, borderLeft: "3px solid #22c55e" }}>
                  <span style={{ color: "#4ade80", fontWeight: 700 }}>SUPPORTED (&le; 3 hexes):</span> Friendly squad in immediate mutual support. Optimal morale, rally bonus, no panic penalty.
                </div>
                <div style={{ background: "#1e293b", padding: "6px 10px", borderRadius: 4, borderLeft: "3px solid #facc15" }}>
                  <span style={{ color: "#facc15", fontWeight: 700 }}>FRIENDS_CLOSE (&le; 6 hexes):</span> Standard operational battle line cohesion. Support within heavy weapon range.
                </div>
                <div style={{ background: "#1e293b", padding: "6px 10px", borderRadius: 4, borderLeft: "3px solid #ef4444" }}>
                  <span style={{ color: "#f87171", fontWeight: 700 }}>ISOLATED (&gt; 6 hexes):</span> Squad isolated in hostile territory. High vulnerability to suppression and morale collapse.
                </div>
              </div>
            </div>

            {/* Box B: Prior Shaping Mathematics */}
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: "#22c55e", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
                <span>📐</span> Root Prior Shaping Formulation in MCTS
              </div>
              <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                At the root of the MCTS tree, neural policy logits P(s, a) are modulated by doctrinal posture and role:
              </div>
              <div style={{ background: "#1e293b", padding: 10, borderRadius: 6 }}>
                <code style={{ fontSize: 11.5, color: "#86efac", display: "block" }}>
                  P_{`{mod}`}(s, a) = P(s, a) \cdot \left(1 + \alpha_{`{boost}`} \cdot \mathbf{`{1}`}_{`{a \\in \\mathcal{A}_{role}}`}\right), \quad \alpha_{`{boost}`} = 0.35
                </code>
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.4 }}>
                <b>Autonomous Override by Q(s, a):</b> Latent-space MCTS rollouts (512 simulations) retain full authority to override this inductive bias whenever accumulated expected value proves an alternative maneuver yields higher terminal payoff.
              </div>
            </div>

            {/* Box C: Multi-Task PCGrad Conflict Surgery */}
            <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: "#f43f5e", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 6 }}>
                <span>⚡</span> Multi-Task PCGrad Conflict Surgery
              </div>
              <div style={{ fontSize: 11, color: "#cbd5e1" }}>
                Projecting conflicting gradients orthogonally during multi-scenario training across all 38 scenarios:
              </div>
              <div style={{ background: "#1e293b", padding: 10, borderRadius: 6 }}>
                <code style={{ fontSize: 11, color: "#fda4af", display: "block" }}>
                  {`\\text{if } g_i \\cdot g_j < 0: \\quad g_i \\leftarrow g_i - \\frac{g_i \\cdot g_j}{\\|g_j\\|^2} g_j`}
                </code>
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.4 }}>
                <b>Negative Cosine Elimination:</b> Prevents destructive gradient interference between tactical defense, offensive assault, and auxiliary predictions (threat, attrition, morale) without task interference.
              </div>
            </div>
          </div>

          {/* HIERARCHICAL INTEGRATION DIAGRAM & PIPELINE */}
          <div style={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, padding: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 800, color: "#38bdf8", marginBottom: 8, textTransform: "uppercase" }}>
              Operational Flow of the Hierarchical Architecture in EfficientZero v2 (H-EZ-M v3.0)
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto 1fr auto 1fr auto 1fr", alignItems: "center", gap: 8, textAlign: "center" }}>
              <div style={{ background: "#1e293b", border: "1px solid #0ea5e9", borderRadius: 6, padding: 10 }}>
                <div style={{ fontSize: 10, color: "#7dd3fc", fontWeight: 700, textTransform: "uppercase" }}>TIER 2: Macro-Strategy</div>
                <div style={{ fontSize: 12, fontWeight: 800, color: "#f8fafc", marginTop: 2 }}>Manager Network (H-EZ-M)</div>
                <div style={{ fontSize: 9.5, color: "#94a3b8", marginTop: 4 }}>
                  Macro-Goal g_T • 16×16 Heatmap • Multi-Turn Cadence
                </div>
              </div>

              <div style={{ fontSize: 16, color: "#38bdf8", fontWeight: 900 }}>➔</div>

              <div style={{ background: "#1e293b", border: "1px solid #a855f7", borderRadius: 6, padding: 10 }}>
                <div style={{ fontSize: 10, color: "#d8b4fe", fontWeight: 700, textTransform: "uppercase" }}>TIER 3: Doctrinal Bias</div>
                <div style={{ fontSize: 12, fontWeight: 800, color: "#f8fafc", marginTop: 2 }}>Prior Shaping (+35% π)</div>
                <div style={{ fontSize: 9.5, color: "#94a3b8", marginTop: 4 }}>
                  8 Canonical Roles • Contextual Mutations • Hyde Cohesion
                </div>
              </div>

              <div style={{ fontSize: 16, color: "#38bdf8", fontWeight: 900 }}>➔</div>

              <div style={{ background: "#1e293b", border: "1px solid #22c55e", borderRadius: 6, padding: 10 }}>
                <div style={{ fontSize: 10, color: "#86efac", fontWeight: 700, textTransform: "uppercase" }}>TIER 4: Micro-Tactics</div>
                <div style={{ fontSize: 12, fontWeight: 800, color: "#f8fafc", marginTop: 2 }}>Worker MCTS Search</div>
                <div style={{ fontSize: 9.5, color: "#94a3b8", marginTop: 4 }}>
                  512 Sims • Invariant Physics g_θ • Two-Hot Value
                </div>
              </div>

              <div style={{ fontSize: 16, color: "#f43f5e", fontWeight: 900 }}>➔</div>

              <div style={{ background: "#1e293b", border: "1px solid #f43f5e", borderRadius: 6, padding: 10 }}>
                <div style={{ fontSize: 10, color: "#fda4af", fontWeight: 700, textTransform: "uppercase" }}>OPTIMIZER: Surgery</div>
                <div style={{ fontSize: 12, fontWeight: 800, color: "#f8fafc", marginTop: 2 }}>PCGrad Balancer</div>
                <div style={{ fontSize: 9.5, color: "#94a3b8", marginTop: 4 }}>
                  Projects Conflicting Gradients Orthogonally
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
