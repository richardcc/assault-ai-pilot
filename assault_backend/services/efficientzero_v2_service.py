from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import torch

from agents.efficientzero_v2.core.adapter_voec import EZV2Observation
from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.efficientzero_v2.core.observation import observation_to_tensor
from assault_bench.episode_action_planner import choose_action_with_mcts
from assault_bench.runner import (
    ezv2_unit_prefilter_ranking,
    priors_and_values_from_model,
    run_mcts_puct_ezv2,
    value_signs_from_to_play,
)
from voec_sim.core.simulator import VOECSimulator


class EfficientZeroV2Service:
    """
    Live AI service powered by EfficientZeroV2 with MCTS search,
    spatial observation encoding, tactical heads, and live telemetry.
    """

    def __init__(self, repo_root: Path | None = None):
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]
        self.runs_root = self.repo_root / "runs_curriculum"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model: Optional[EfficientZeroV2Network] = None
        self.active_checkpoint_path: Optional[str] = None
        self.active_run_id: Optional[str] = None
        self.model_config: Dict[str, Any] = {}

        # MCTS live interactive parameters
        self.mcts_simulations = 80
        self.mcts_c_puct = 2.3
        self.mcts_temperature = 0.6
        self.unit_prefilter_enabled = True
        self.unit_prefilter_replan_enabled = True
        self.unit_prefilter_top_k = 2

        # Auto-load latest valid checkpoint
        self.auto_load_latest_checkpoint()

    def list_available_checkpoints(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        if not self.runs_root.exists():
            return results

        for run_dir in sorted(self.runs_root.iterdir(), reverse=True):
            if not run_dir.is_dir() or not run_dir.name.startswith("efficientzero_v2_"):
                continue
            ckpt_path = run_dir / "checkpoints" / "final.pt"
            if not ckpt_path.exists():
                # Check for any .pt
                pts = list((run_dir / "checkpoints").glob("*.pt")) if (run_dir / "checkpoints").exists() else []
                if not pts:
                    continue
                ckpt_path = sorted(pts, key=lambda p: p.stat().st_mtime, reverse=True)[0]

            manifest_path = run_dir / "run_manifest.json"
            manifest: Dict[str, Any] = {}
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    pass

            cfg = manifest.get("config", {})
            m_cfg = cfg.get("model", {})
            mtime = ckpt_path.stat().st_mtime
            results.append(
                {
                    "run_id": str(manifest.get("run_id", run_dir.name)),
                    "checkpoint_name": ckpt_path.name,
                    "checkpoint_path": str(ckpt_path),
                    "scenario_id": str(manifest.get("scenario_id", "") or "multi"),
                    "iterations": int(cfg.get("iterations", 0) or 0),
                    "hidden_dim": int(m_cfg.get("hidden_dim", 48) or 48),
                    "action_dim": int(m_cfg.get("action_dim", 32) or 32),
                    "total_parameters": int(m_cfg.get("total_parameters", 0) or 0),
                    "last_modified": float(mtime),
                    "is_active": (str(ckpt_path) == str(self.active_checkpoint_path)),
                }
            )

        results.sort(key=lambda r: float(r["last_modified"]), reverse=True)
        return results

    def auto_load_latest_checkpoint(self) -> bool:
        ckpts = self.list_available_checkpoints()
        if not ckpts:
            return False
        return self.load_checkpoint(ckpts[0]["checkpoint_path"])

    def load_checkpoint(self, checkpoint_path_str: str | Path | None) -> bool:
        if not checkpoint_path_str:
            return False
        ckpt_path = Path(checkpoint_path_str).resolve()
        if not ckpt_path.exists():
            return False

        run_dir = ckpt_path.parent.parent
        manifest_path = run_dir / "run_manifest.json"
        manifest: Dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        cfg = manifest.get("config", {})
        m_cfg = cfg.get("model", {})

        # Default fallback architecture params matching EZv2 contract
        obs_channels = int(m_cfg.get("observation_channels", 32) or 32)
        obs_height = int(m_cfg.get("observation_height", 16) or 16)
        obs_width = int(m_cfg.get("observation_width", 16) or 16)
        hidden_dim = int(m_cfg.get("hidden_dim", 48) or 48)
        action_dim = int(m_cfg.get("action_dim", 32) or 32)
        encoder_type = str(m_cfg.get("encoder_type", "cnn") or "cnn")
        dynamics_blocks = int(m_cfg.get("dynamics_blocks", 3) or 3)
        prediction_blocks = int(m_cfg.get("prediction_blocks", 2) or 2)
        aux_intent_classes = int(cfg.get("aux_intent_classes", 8) or 8)
        aux_multi_vp_feature_dim = int(cfg.get("aux_multi_vp_feature_dim", 4) or 4)
        support_size = int(m_cfg.get("support_size", 0) or 0)
        use_spatial_attention = bool(m_cfg.get("use_spatial_attention", False))
        enable_threat_head = bool(m_cfg.get("enable_threat_head", True))
        enable_attrition_head = bool(m_cfg.get("enable_attrition_head", True))
        enable_morale_head = bool(m_cfg.get("enable_morale_head", True))
        morale_classes = int(m_cfg.get("morale_classes", 4) or 4)

        try:
            model = EfficientZeroV2Network(
                observation_dim=obs_channels * obs_height * obs_width,
                hidden_dim=hidden_dim,
                action_dim=action_dim,
                encoder_type=encoder_type,
                observation_channels=obs_channels,
                observation_height=obs_height,
                observation_width=obs_width,
                dynamics_blocks=dynamics_blocks,
                prediction_blocks=prediction_blocks,
                objective_intent_classes=aux_intent_classes,
                multi_vp_feature_dim=aux_multi_vp_feature_dim,
                support_size=support_size,
                use_spatial_attention=use_spatial_attention,
                enable_threat_head=enable_threat_head,
                enable_attrition_head=enable_attrition_head,
                enable_morale_head=enable_morale_head,
                morale_classes=morale_classes,
            )
            device = self.device
            state_dict = torch.load(ckpt_path, map_location="cpu", weights_only=False)
            model.load_state_dict(state_dict, strict=True)
            model.to(device)
            model.eval()

            self.model = model
            self.active_checkpoint_path = str(ckpt_path)
            self.active_run_id = str(manifest.get("run_id", run_dir.name))
            self.model_config = {
                "obs_channels": obs_channels,
                "obs_height": obs_height,
                "obs_width": obs_width,
                "hidden_dim": hidden_dim,
                "action_dim": action_dim,
                "dynamics_blocks": dynamics_blocks,
                "prediction_blocks": prediction_blocks,
                "device": device,
            }
            print(f"[EZV2Service] Loaded checkpoint successfully: {ckpt_path.name} from {self.active_run_id} on {device}")
            return True
        except Exception as e:
            print(f"[EZV2Service][ERROR] Failed loading {ckpt_path}: {e}")
            return False

    def build_ezv2_observation(self, env: Any, scenario_id: str = "") -> EZV2Observation:
        sim = VOECSimulator()
        sim._state = env.game_state
        sim._runtime = env.runtime
        sim._scenario_id = scenario_id or getattr(env, "scenario_id", "") or "live"

        snap = sim.snapshot()
        spatial = sim.spatial_features()
        return EZV2Observation(
            turn=snap.turn,
            to_play=snap.to_play,
            done=snap.done,
            units=[
                {
                    "unit_id": u.unit_id,
                    "unit_key": u.unit_key,
                    "unit_label": u.unit_label,
                    "art_ref": u.art_ref,
                    "side": u.side,
                    "q": u.q,
                    "r": u.r,
                    "hp": u.hp,
                    "alive": u.alive,
                }
                for u in snap.units
            ],
            playable_hexes=list(spatial.get("playable_hexes", [])),
            vp_hexes=list(spatial.get("vp_hexes", [])),
            vp_owner_by_hex=dict(spatial.get("vp_owner_by_hex", {})),
            terrain_move_cost_by_hex=dict(spatial.get("terrain_move_cost_by_hex", {})),
            terrain_cover_by_hex=dict(spatial.get("terrain_cover_by_hex", {})),
            terrain_los_block_by_hex=dict(spatial.get("terrain_los_block_by_hex", {})),
            terrain_type_by_hex=dict(spatial.get("terrain_type_by_hex", {})),
            fortification_type_by_hex=dict(spatial.get("fortification_type_by_hex", {})),
            fortification_edge_by_hex=dict(spatial.get("fortification_edge_by_hex", {})),
        )

    def choose_action(
        self,
        env: Any,
        active_side: str,
        scenario_id: str = "",
    ) -> Dict[str, Any]:
        """
        Executes an MCTS-driven AI turn on the live game state.
        Returns the chosen action, target unit, and comprehensive telemetry.
        """
        if self.model is None:
            self.auto_load_latest_checkpoint()

        sim = VOECSimulator()
        sim._state = env.game_state
        sim._runtime = env.runtime
        sim._scenario_id = scenario_id or getattr(env, "scenario_id", "") or "live"
        legal_actions = sim.legal_actions()

        if not legal_actions:
            return {
                "action": None,
                "unit_id": None,
                "source": "no_legal_actions",
                "telemetry": {},
            }

        obs = self.build_ezv2_observation(env, scenario_id=scenario_id)
        obs_tensor = observation_to_tensor(obs)

        # Fallback if model could not be initialized
        if self.model is None:
            action = legal_actions[0]
            unit_id = action.split(":")[1] if ":" in action else None
            return {
                "action": action,
                "unit_id": unit_id,
                "source": "fallback_no_model",
                "telemetry": {
                    "root_value": 0.0,
                    "win_prob": 0.5,
                    "legal_count": len(legal_actions),
                },
            }

        device = self.device
        model = self.model
        action_dim = int(self.model_config.get("action_dim", 32) or 32)

        # 1. Network direct priors and values
        priors, values = priors_and_values_from_model(
            model,
            obs_tensor,
            legal_actions,
            action_dim=action_dim,
        )
        signs = value_signs_from_to_play(obs, legal_actions)

        # 2. Extract tactical heads diagnostics directly from root inference
        tactical_heads: Dict[str, Any] = {}
        root_value = 0.0
        try:
            with torch.no_grad():
                inp = obs_tensor.unsqueeze(0).to(device)
                hidden, policy_logits, value, reward, aux = model.initial_inference(inp, return_aux=True)
                root_value = float(value.squeeze().cpu().item()) if value is not None else 0.0
                if aux and "threat_map_pred" in aux and aux["threat_map_pred"] is not None:
                    t_map = aux["threat_map_pred"].squeeze(0).cpu().numpy()
                    tactical_heads["threat_map_max"] = round(float(t_map.max()), 4)
                    tactical_heads["threat_map_mean"] = round(float(t_map.mean()), 4)
                    grid = t_map[0] if t_map.ndim > 2 else t_map
                    tactical_heads["threat_grid"] = [[round(float(v), 3) for v in row] for row in grid]
                if aux and "morale_pred" in aux and aux["morale_pred"] is not None:
                    mor = aux["morale_pred"].squeeze(0).cpu()
                    mor_probs = torch.softmax(mor, dim=-1).tolist()
                    tactical_heads["morale_distribution"] = [round(float(p), 4) for p in mor_probs]
        except Exception as e:
            tactical_heads["error"] = str(e)

        # 3. MCTS Search
        planner = choose_action_with_mcts(
            legal_for_step=legal_actions,
            obs_units=obs.units,
            obs_vp_hexes=obs.vp_hexes,
            active_side=active_side,
            obs_vp_owner_by_hex=obs.vp_owner_by_hex,
            unit_prefilter_enabled=self.unit_prefilter_enabled,
            unit_prefilter_replan_enabled=self.unit_prefilter_replan_enabled,
            unit_prefilter_top_k=self.unit_prefilter_top_k,
            unit_prefilter_vp_progress_weight=1.0,
            unit_prefilter_capture_opportunity_weight=2.0,
            unit_prefilter_threat_weight=0.25,
            terrain_cover_by_hex=obs.terrain_cover_by_hex,
            terrain_los_block_by_hex=obs.terrain_los_block_by_hex,
            priors=priors,
            values=values,
            signs=signs,
            mcts_simulations=self.mcts_simulations,
            mcts_c_puct=self.mcts_c_puct,
            mcts_temperature=self.mcts_temperature,
            mcts_dirichlet_alpha=0.3,
            mcts_dirichlet_epsilon=0.0,
            mcts_q_clip_abs=100.0,
            mcts_q_root_normalization_mode="adaptive_minmax",
            mcts_q_root_normalization_strength=0.9,
            mcts_value_rescale_mode="tanh",
            mcts_value_rescale_temperature=1.5,
            mcts_success_prob_enabled=True,
            mcts_success_prob_alpha=0.25,
            mcts_success_prob_center=0.45,
            mcts_success_prob_scale=0.35,
            mcts_success_prob_centered_clip_abs=1.0,
            mcts_min_root_visits_per_action=1,
            mcts_min_root_visits_top_n=4,
            run_policy_mcts_fn=run_mcts_puct_ezv2,
            unit_prefilter_ranking_fn=ezv2_unit_prefilter_ranking,
        )

        chosen_action = str(planner.get("action", "") or legal_actions[0])
        unit_id = chosen_action.split(":")[1] if ":" in chosen_action else None
        mcts_out = planner.get("mcts_out")

        # Top 5 actions by visits/prior for telemetry
        top_candidates: List[Dict[str, Any]] = []
        if mcts_out and hasattr(mcts_out, "root_candidate_breakdown"):
            sorted_candidates = sorted(
                list(mcts_out.root_candidate_breakdown or []),
                key=lambda c: int(c.get("visit_count", 0)),
                reverse=True,
            )
            for c in sorted_candidates[:6]:
                top_candidates.append(
                    {
                        "action_id": str(c.get("action_id", "")),
                        "visit_count": int(c.get("visit_count", 0)),
                        "q_value": float(c.get("q_value", 0.0) or 0.0),
                        "prior": float(c.get("prior", 0.0) or 0.0),
                        "value": float(c.get("value", 0.0) or 0.0),
                    }
                )

        # Win probability mapped from root value ([-1, 1] -> [0, 1])
        win_prob = max(0.01, min(0.99, (root_value + 1.0) / 2.0))

        telemetry = {
            "engine": "EfficientZeroV2",
            "source": "efficientzero_v2_mcts",
            "run_id": self.active_run_id,
            "checkpoint": Path(self.active_checkpoint_path).name if self.active_checkpoint_path else None,
            "checkpoint_name": Path(self.active_checkpoint_path).name if self.active_checkpoint_path else None,
            "root_value": round(root_value, 4),
            "win_prob": round(win_prob, 3),
            "active_side": active_side,
            "simulations": self.mcts_simulations,
            "legal_count": len(legal_actions),
            "top_candidates": top_candidates,
            "top_actions": top_candidates,
            "tactical_heads": tactical_heads,
            "replan_units": [
                {
                    "unit_id": str(u.get("unit_id", "")),
                    "score": round(float(u.get("score", 0.0) or 0.0), 3),
                }
                for u in list(planner.get("replan_evaluated_units", []) or [])[:4]
            ],
        }

        return {
            "action": chosen_action,
            "unit_id": unit_id,
            "source": "efficientzero_v2_mcts",
            "telemetry": telemetry,
        }
