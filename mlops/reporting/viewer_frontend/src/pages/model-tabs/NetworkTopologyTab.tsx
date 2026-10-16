import { useState, useEffect, useMemo } from "react";
import type { Dict, TrainRow } from "../../types";
import { formatLocalDate } from "../../dateUtils";
import { fetchChannelAttribution, runChannelAttribution } from "../../api";

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
  { idx: 2, name: "ally_hp_norm", cat: "units", desc: "Puntos de vida normalizados [0-1] de las escuadras aliadas." },
  { idx: 3, name: "enemy_hp_norm", cat: "units", desc: "Puntos de vida normalizados [0-1] de las escuadras enemigas." },
  { idx: 4, name: "ally_alive", cat: "units", desc: "Máscara booleana de unidades aliadas operativas (no eliminadas)." },
  { idx: 5, name: "enemy_alive", cat: "units", desc: "Máscara booleana de unidades enemigas operativas." },
  { idx: 6, name: "turn_norm", cat: "global", desc: "Progreso temporal del escenario normalizado (turno_actual / turnos_max)." },
  { idx: 7, name: "reaction_fire_threat", cat: "units", desc: "Mapa de calor continuo de amenaza y fuego de reacción enemigo (overwatch)." },
  { idx: 8, name: "ally_infantry", cat: "units", desc: "1.0 si la unidad aliada es infantería / zapadores." },
  { idx: 9, name: "enemy_infantry", cat: "units", desc: "1.0 si la unidad enemiga es infantería." },
  { idx: 10, name: "ally_support", cat: "units", desc: "1.0 para armas de apoyo aliadas (ametralladoras pesadas, morteros)." },
  { idx: 11, name: "enemy_support", cat: "units", desc: "1.0 para armas de apoyo enemigas." },
  { idx: 12, name: "map_playable", cat: "terrain", desc: "1.0 en hexágonos válidos del mapa; 0.0 en los bordes fuera de tablero." },
  { idx: 13, name: "vp_mask", cat: "vp", desc: "1.0 en hexágonos que son Puntos de Victoria (VPs)." },
  { idx: 14, name: "vp_owner_relative", cat: "vp", desc: "+1.0 controlado por aliado, -1.0 por enemigo, 0.0 disputado/neutral." },
  { idx: 15, name: "terrain_move_cost_norm", cat: "terrain", desc: "Coste en puntos de movimiento (carretera = bajo, bosque/colina = alto)." },
  { idx: 16, name: "terrain_cover_norm", cat: "terrain", desc: "Bonificación defensiva de cobertura (edificios urbanos = 0.5+)." },
  { idx: 17, name: "terrain_los_block", cat: "terrain", desc: "Bloqueo de línea de visión por elevación o construcciones densas." },
  { idx: 18, name: "vp_distance_inv", cat: "vp", desc: "Inverso de la distancia axial mínima a un VP (1 / (1 + dist))." },
  { idx: 19, name: "q_coord_norm", cat: "hex", desc: "Coordenada axial Q del hexágono normalizada [-1, 1]." },
  { idx: 20, name: "r_coord_norm", cat: "hex", desc: "Coordenada axial R del hexágono normalizada [-1, 1]." },
  { idx: 21, name: "frontline_control", cat: "hex", desc: "Campo de potencial territorial [-1, +1] (difusión y control de línea de frente)." },
  { idx: 22, name: "ally_mobility_norm", cat: "units", desc: "Puntos de movimiento disponibles restantes de la escuadra activa." },
  { idx: 23, name: "enemy_mobility_norm", cat: "units", desc: "Capacidad de movimiento estimada de unidades enemigas visibles." },
  { idx: 24, name: "ally_direct_range_norm", cat: "units", desc: "Alcance máximo de fuego directo de las armas aliadas." },
  { idx: 25, name: "enemy_direct_range_norm", cat: "units", desc: "Alcance máximo de fuego directo enemigo." },
  { idx: 26, name: "ally_indirect_range_norm", cat: "units", desc: "Alcance de armas indirectas (morteros/artillería)." },
  { idx: 27, name: "enemy_indirect_range_norm", cat: "units", desc: "Alcance de armas indirectas enemigas." },
  { idx: 28, name: "ally_attack_power_norm", cat: "units", desc: "Poder de fuego ofensivo (dados de combate normalizados)." },
  { idx: 29, name: "enemy_attack_power_norm", cat: "units", desc: "Poder de fuego ofensivo enemigo estimado." },
  { idx: 30, name: "ally_defense_power_norm", cat: "units", desc: "Capacidad defensiva y moral de las escuadras aliadas." },
  { idx: 31, name: "enemy_defense_power_norm", cat: "units", desc: "Capacidad defensiva y moral de las escuadras enemigas." },
];

export function NetworkTopologyTab({
  trainRow,
  trainSummary,
}: {
  trainRow: TrainRow | null;
  trainSummary: Dict | null;
}) {
  const [unrollStep, setUnrollStep] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string>("representation");
  const [channelFilter, setChannelFilter] = useState<string>("all");

  // Dynamic parameters extracted from the selected train execution
  const runId = String(trainRow?.run_id || "execution");
  const cfg = useMemo(() => (trainRow?.config || {}) as Dict, [trainRow]);
  const modelCfg = useMemo(() => ((cfg.model || {}) as Dict), [cfg]);
  const selfplayCfg = useMemo(() => ((cfg.selfplay || {}) as Dict), [cfg]);

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
  const isV2Optimized = useMemo(() => {
    return (
      modelCfg.architecture_version === "ezv2_compact_bottleneck_v2" ||
      (Array.isArray(modelCfg.features) && modelCfg.features.includes("conv1x1_bottlenecks")) ||
      Boolean(modelCfg.total_parameters && Number(modelCfg.total_parameters) < 1_500_000)
    );
  }, [modelCfg]);

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
    };
  }, [inChannels, boardH, boardW, hiddenDim, actionDim, dynamicsBlocks, predictionBlocks, encoderType, maxUnroll, consistencyUnroll, runId, mctsSims, isV2Optimized]);

  const selectedNode = dynamicNodeCatalog[selectedNodeId] || dynamicNodeCatalog.representation;

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
          <div style={{ fontSize: 12, fontWeight: 700, color: "#cbd5e1", display: "flex", justifyContent: "space-between" }}>
            <span>🎨 Diagrama Gráfico Interactivo de Nodos</span>
            <span className="muted" style={{ fontSize: 11 }}>Haz clic en cualquier nodo para inspeccionar capas</span>
          </div>

          {/* Graphical SVG Canvas */}
          <div style={{ width: "100%", overflowX: "auto", background: "#0b1120", borderRadius: 8, border: "1px solid #1e293b", padding: "10px 4px" }}>
            <svg
              viewBox="0 0 760 360"
              style={{ width: "100%", height: "auto", minWidth: 640, display: "block" }}
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
              <line x1="130" y1="75" x2="165" y2="75" stroke="#38bdf8" strokeWidth="2.5" markerEnd="url(#arrow)" strokeDasharray={unrollStep === 0 ? "none" : "4 4"} />
              {/* Rep -> Latent */}
              <line x1="315" y1="75" x2="350" y2="75" stroke="#38bdf8" strokeWidth="2.5" markerEnd="url(#arrow)" strokeDasharray={unrollStep === 0 ? "none" : "4 4"} />
              {/* Latent -> Heads */}
              <path d="M 470 60 C 510 60, 520 40, 555 40" fill="none" stroke="#38bdf8" strokeWidth="2" markerEnd="url(#arrow)" />
              <path d="M 470 70 C 510 70, 520 100, 555 100" fill="none" stroke="#22c55e" strokeWidth="2" markerEnd="url(#arrow-green)" />
              <path d="M 470 80 C 510 80, 520 160, 555 160" fill="none" stroke="#f43f5e" strokeWidth="2" markerEnd="url(#arrow)" />
              <path d="M 470 90 C 510 90, 520 220, 555 220" fill="none" stroke="#c084fc" strokeWidth="2" markerEnd="url(#arrow)" />

              {/* Recurrent Loop: Latent -> Dynamics & Action -> Dynamics */}
              <path d="M 410 115 L 410 180 C 410 200, 390 220, 360 220 L 320 220" fill="none" stroke={unrollStep > 0 ? "#f59e0b" : "#475569"} strokeWidth="2" markerEnd="url(#arrow-amber)" strokeDasharray={unrollStep > 0 ? "none" : "3 3"} />
              <path d="M 410 290 L 350 290 C 330 290, 320 280, 320 265" fill="none" stroke={unrollStep > 0 ? "#f59e0b" : "#475569"} strokeWidth="2" markerEnd="url(#arrow-amber)" />
              {/* Dynamics Loop Feedback: Dynamics -> Latent (s_{t+1}) */}
              <path d="M 170 240 C 130 240, 130 140, 350 100" fill="none" stroke={unrollStep > 0 ? "#10b981" : "#334155"} strokeWidth="2.5" markerEnd="url(#arrow-green)" strokeDasharray={unrollStep > 0 ? "none" : "4 4"} />

              {/* Node 1: Observation Tensor */}
              <g
                onClick={() => setSelectedNodeId("observation")}
                style={{ cursor: "pointer" }}
                opacity={unrollStep === 0 ? 1 : 0.5}
              >
                <rect
                  x="15"
                  y="35"
                  width="115"
                  height="80"
                  rx="8"
                  fill={selectedNodeId === "observation" ? "#0369a1" : "#0f172a"}
                  stroke={selectedNodeId === "observation" ? "#38bdf8" : "#0284c7"}
                  strokeWidth={selectedNodeId === "observation" ? "2.5" : "1.5"}
                  filter={unrollStep === 0 ? "url(#glow-cyan)" : "none"}
                />
                <text x="72" y="58" fill="#94a3b8" fontSize="9" fontWeight="700" textAnchor="middle">ENTRADA REAL</text>
                <text x="72" y="76" fill="#f8fafc" fontSize="11" fontWeight="800" textAnchor="middle">Observación o_t</text>
                <text x="72" y="93" fill="#38bdf8" fontSize="10" textAnchor="middle">{inChannels}×{boardH}×{boardW}</text>
                <text x="72" y="106" fill="#64748b" fontSize="8" textAnchor="middle">Simulador VOEC</text>
              </g>

              {/* Node 2: Representation Network */}
              <g
                onClick={() => setSelectedNodeId("representation")}
                style={{ cursor: "pointer" }}
                opacity={unrollStep === 0 ? 1 : 0.5}
              >
                <rect
                  x="170"
                  y="35"
                  width="145"
                  height="80"
                  rx="8"
                  fill={selectedNodeId === "representation" ? "#0369a1" : "#1e293b"}
                  stroke={selectedNodeId === "representation" ? "#38bdf8" : "#0ea5e9"}
                  strokeWidth={selectedNodeId === "representation" ? "2.5" : "1.5"}
                />
                <text x="242" y="56" fill="#60a5fa" fontSize="9" fontWeight="700" textAnchor="middle">ENCODER {encoderType.toUpperCase()}</text>
                <text x="242" y="74" fill="#ffffff" fontSize="11" fontWeight="800" textAnchor="middle">h_θ(o) Representación</text>
                <text x="242" y="92" fill="#93c5fd" fontSize="9" textAnchor="middle">{dynamicsBlocks} ResBlocks ({hiddenDim}ch){isV2Optimized ? " + SE" : ""}</text>
                <text x="242" y="105" fill="#64748b" fontSize="8" textAnchor="middle">{isV2Optimized ? "GroupNorm + MinMax Scale" : `Campo ~${1 + 2 * (1 + 2 * dynamicsBlocks)}×${1 + 2 * (1 + 2 * dynamicsBlocks)} hex`}</text>
              </g>

              {/* Node 3: Latent State Manifold */}
              <g
                onClick={() => setSelectedNodeId("latent")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="355"
                  y="30"
                  width="115"
                  height="90"
                  rx="10"
                  fill={selectedNodeId === "latent" ? "#065f46" : "#064e3b"}
                  stroke="#10b981"
                  strokeWidth="2.5"
                  filter="url(#glow-green)"
                />
                <text x="412" y="52" fill="#6ee7b7" fontSize="9" fontWeight="700" textAnchor="middle">ESTADO LATENTE</text>
                <text x="412" y="72" fill="#ffffff" fontSize="13" fontWeight="800" textAnchor="middle">s_{unrollStep}</text>
                <text x="412" y="90" fill="#a7f3d0" fontSize="10" fontWeight="600" textAnchor="middle">{hiddenDim}×{boardH}×{boardW}</text>
                <text x="412" y="106" fill="#34d399" fontSize="8" textAnchor="middle">
                  {unrollStep === 0 ? "h(o) Raíz" : `g(s,a) Paso ${unrollStep}`}
                </text>
              </g>

              {/* Node 4: Action Conditioning */}
              <g
                onClick={() => setSelectedNodeId("action")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="370"
                  y="260"
                  width="120"
                  height="60"
                  rx="8"
                  fill={selectedNodeId === "action" ? "#78350f" : "#1e293b"}
                  stroke="#f59e0b"
                  strokeWidth={selectedNodeId === "action" ? "2.5" : "1.5"}
                />
                <text x="430" y="278" fill="#fbbf24" fontSize="9" fontWeight="700" textAnchor="middle">ACCIÓN MCTS</text>
                <text x="430" y="295" fill="#f8fafc" fontSize="11" fontWeight="700" textAnchor="middle">a_{unrollStep} (0..{actionDim - 1})</text>
                <text x="430" y="310" fill="#94a3b8" fontSize="8" textAnchor="middle">1×{boardH}×{boardW} broadcast</text>
              </g>

              {/* Node 5: Dynamics Recurrent Network */}
              <g
                onClick={() => setSelectedNodeId("dynamics")}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x="170"
                  y="195"
                  width="145"
                  height="85"
                  rx="8"
                  fill={selectedNodeId === "dynamics" ? "#7c2d12" : "#1e293b"}
                  stroke={unrollStep > 0 ? "#f97316" : "#475569"}
                  strokeWidth="2"
                />
                <text x="242" y="216" fill="#fbbf24" fontSize="9" fontWeight="700" textAnchor="middle">RED DE DINÁMICA</text>
                <text x="242" y="234" fill="#ffffff" fontSize="11" fontWeight="800" textAnchor="middle">g_θ(s, a) ➔ s_{Math.min(unrollStep + 1, maxUnroll)}</text>
                <text x="242" y="251" fill="#fdba74" fontSize="9" textAnchor="middle">{dynamicsBlocks} ResBlocks {isV2Optimized ? "+ SE + Cuello Botella" : "+ Reward Head"}</text>
                <text x="242" y="266" fill="#94a3b8" fontSize="8" textAnchor="middle">{isV2Optimized ? `Unroll ${maxUnroll} pasos (MinMax Scaling)` : `Unroll máx = ${maxUnroll} pasos`}</text>
              </g>

              {/* Node 6: Policy Head */}
              <g onClick={() => setSelectedNodeId("policy")} style={{ cursor: "pointer" }}>
                <rect x="560" y="15" width="180" height="50" rx="6" fill={selectedNodeId === "policy" ? "#0369a1" : "#1e293b"} stroke="#38bdf8" strokeWidth="1.5" />
                <text x="572" y="33" fill="#38bdf8" fontSize="9" fontWeight="700">POLÍTICA f_p(s)</text>
                <text x="572" y="48" fill="#f8fafc" fontSize="10" fontWeight="600">{actionDim} Logits {isV2Optimized ? "(Conv 1x1 Bottleneck)" : "(Dense Flatten)"}</text>
              </g>

              {/* Node 7: Value Head */}
              <g onClick={() => setSelectedNodeId("value")} style={{ cursor: "pointer" }}>
                <rect x="560" y="75" width="180" height="50" rx="6" fill={selectedNodeId === "value" ? "#065f46" : "#1e293b"} stroke="#22c55e" strokeWidth="1.5" />
                <text x="572" y="93" fill="#22c55e" fontSize="9" fontWeight="700">VALOR f_v(s)</text>
                <text x="572" y="108" fill="#f8fafc" fontSize="10" fontWeight="600">Escalar [-1.0, +1.0] {isV2Optimized ? "(Pool 2x2)" : "(Dense)"}</text>
              </g>

              {/* Node 8: Auxiliary Objective Head */}
              <g onClick={() => setSelectedNodeId("aux_objective")} style={{ cursor: "pointer" }}>
                <rect x="560" y="135" width="180" height="50" rx="6" fill={selectedNodeId === "aux_objective" ? "#9f1239" : "#1e293b"} stroke="#f43f5e" strokeWidth="1.5" />
                <text x="572" y="153" fill="#f43f5e" fontSize="9" fontWeight="700">OBJETIVO AUXILIAR f_o(s)</text>
                <text x="572" y="168" fill="#f8fafc" fontSize="10" fontWeight="600">Progreso VP {isV2Optimized ? "(Pool 2x2)" : "(Dense)"}</text>
              </g>

              {/* Node 9: Consistency Head */}
              <g onClick={() => setSelectedNodeId("consistency")} style={{ cursor: "pointer" }}>
                <rect x="560" y="195" width="180" height="50" rx="6" fill={selectedNodeId === "consistency" ? "#581c87" : "#1e293b"} stroke="#c084fc" strokeWidth="1.5" />
                <text x="572" y="213" fill="#c084fc" fontSize="9" fontWeight="700">CONSISTENCIA q_θ(s)</text>
                <text x="572" y="228" fill="#f8fafc" fontSize="10" fontWeight="600">SimSiam {isV2Optimized ? "(Pool 4x4)" : `(${hiddenDim} Flat)`}</text>
              </g>
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
            padding: 16,
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
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

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 8, maxHeight: 320, overflowY: "auto", paddingRight: 4 }}>
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

      {/* Channel Effectiveness & Attribution Analyzer Section */}
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
                <div className="muted" style={{ fontSize: 10, textTransform: "uppercase" }}>Nuevos Canales (Opción C)</div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#fbbf24", marginTop: 2 }}>
                  Ch 21: #{ch21Info?.rank ?? "-"} (Score {ch21Info ? Number(ch21Info.importance_score).toFixed(3) : "-"})
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#fbbf24" }}>
                  Ch 07: #{ch7Info?.rank ?? "-"} (Score {ch7Info ? Number(ch7Info.importance_score).toFixed(3) : "-"})
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
            <div style={{ overflowX: "auto", border: "1px solid #334155", borderRadius: 6, maxHeight: 360, overflowY: "auto" }}>
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
                    const isNewOptC = rc.index === 7 || rc.index === 21;
                    return (
                      <tr
                        key={rc.index}
                        style={{
                          background: isNewOptC ? "rgba(245, 158, 11, 0.08)" : idx % 2 === 0 ? "#1e293b" : "#182234",
                          borderBottom: "1px solid #283548",
                        }}
                      >
                        <td style={{ padding: "6px 10px", fontWeight: 700, color: "#38bdf8" }}>
                          #{rc.rank}
                        </td>
                        <td style={{ padding: "6px 10px" }}>
                          <span style={{ fontWeight: 700, color: isNewOptC ? "#fbbf24" : "#f8fafc" }}>
                            Ch {String(rc.index).padStart(2, "0")}: <code>{rc.name}</code>
                          </span>
                          {isNewOptC && (
                            <span style={{ marginLeft: 6, fontSize: 9, background: "#78350f", color: "#fef3c7", padding: "1px 4px", borderRadius: 3, fontWeight: 700 }}>
                              OPCIÓN C
                            </span>
                          )}
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
    </div>
  );
}
