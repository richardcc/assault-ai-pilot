import torch
from pathlib import Path

from assault_sim.decision.decision_engine import DecisionEngine

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.state_encoder import encode_state

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.rl.tactical_options import TacticalOption

from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

from assault_sim.engine.match_runner import MatchRunner

from assault_sim.debug.console_observer import ConsoleObserver
from assault_sim.debug.debug_config import DebugConfig

from assault_sim.debug.replay_observer import ReplayObserver
from assault_sim.debug.replay_writer import ReplayWriter
from assault_sim.debug.replay_utils import extract_initial_state


RL_SIDE = "US"
CHECKPOINT = Path("models/latest.pt")


# -------------------------------------------------
# ✅ CONTROLLER TOTALMENTE ARREGLADO (NO SECUENCIAL)
# -------------------------------------------------
class DecisionEngineController:
    def __init__(self, rl_side, decision_engine, option_policy, heuristic, sim_env):
        self.rl_side = rl_side
        self.engine = decision_engine
        self.option_policy = option_policy
        self.heuristic = heuristic
        self.sim_env = sim_env

    def select_best_unit(self, side, state, blocked_units):
        """
        🎯 INTELIGENTE: Usa el DecisionEngine para elegir la MEJOR unidad disponible.
        Llamado por ActivationManager para reemplazar la selección secuencial.
        
        Returns the best unit for the given side, or None.
        """
        if side != self.rl_side:
            # No intelligent selection for enemy side
            return None
        
        # Candidatos: unidades vivas, del bando correcto, no bloqueadas
        candidates = [
            u for u in state.units
            if u.alive
            and u.side == side
            and u.unit_id not in blocked_units
            and self._can_act(u)
        ]
        
        print(f"[DEBUG] select_best_unit({side}): blocked={sorted(blocked_units)}, candidates={[u.unit_id for u in candidates]}")
        
        if not candidates:
            return None
        
        # Si solo hay una, retornarla directamente
        if len(candidates) == 1:
            return candidates[0]
        
        # ✅ IMPORTANTE: Guardar estado inicial para restaurar después de cada evaluación
        import copy as copy_module
        initial_state = copy_module.deepcopy(self.sim_env)
        
        # ✅ Evaluar cada candidato con su mejor acción
        best_unit = None
        best_score = -999999
        scores = {}
        
        for unit in candidates:
            try:
                # Restaurar estado antes de evaluar esta unidad
                self.sim_env = copy_module.deepcopy(initial_state)
                
                actions = self.engine._get_unit_actions(self.sim_env, unit)
                
                if not actions:
                    scores[unit.unit_id] = -999999
                    continue
                
                # Mejor acción para esta unidad
                best_action_score = max(
                    (self.engine.evaluate_action(self.sim_env, action, side) for action in actions),
                    default=-999999
                )
                                
                scores[unit.unit_id] = best_action_score
                
                if best_action_score > best_score:
                    best_score = best_action_score
                    best_unit = unit
                    
            except Exception as e:
                print(f"[WARN] Error evaluating {unit.unit_id}: {e}")
                scores[unit.unit_id] = -999999
        
        # Restaurar estado final
        self.sim_env = copy_module.deepcopy(initial_state)
        
        print(f"[DEBUG]   Scores: {sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]}")
        print(f"[DEBUG]   SELECTED: {best_unit.unit_id if best_unit else None}")
        
        return best_unit

    def _can_act(self, unit):
        """Helper to check if unit can act."""
        if hasattr(unit, "is_suppressed") and unit.is_suppressed():
            return False
        if hasattr(unit, "is_in_fallback") and unit.is_in_fallback():
            return False
        return True

    def act(self, state, side, unit, obs):
        """
        Determina la acción a ejecutar. Si es el bando de RL, consulta al DecisionEngine
        para evaluar dinámicamente cuál es la unidad óptima para actuar en este paso.
        """
        # -------------------------------------------------
        # ✅ RL SIDE
        # -------------------------------------------------
        if side == self.rl_side:
            if unit.side != self.rl_side:
                return None

            # 🎯 RECALCULO EN CADA PASO: Evaluamos el mapa de forma abierta y dinámica
            intent = self.engine.compute_intent(self.sim_env)

            # Validamos que el intent sea una tupla correcta (best_unit, best_action)
            if intent is not None and isinstance(intent, tuple) and len(intent) == 2:
                chosen_unit, action_to_execute = intent

                # Si la unidad evaluada como óptima por el cerebro coincide con la que el MatchRunner 
                # nos ofrece en el micro-paso actual, la ejecutamos.
                if chosen_unit and chosen_unit.unit_id == unit.unit_id and action_to_execute is not None:
                    
                    # Aseguramos el mapeo correcto del ID y sincronizamos en el runtime
                    action_to_execute.unit_id = unit.unit_id
                    self.sim_env.runtime.activated_units.add(unit.unit_id)
                    
                    return action_to_execute

            # 🛡️ FALLBACK DE EMERGENCIA: Si el engine no elige esta unidad, usamos la heurística basada en PPO
            # para evitar atascar el entorno o caer en un bucle infinito.
            option, _ = self.option_policy.choose_option(obs)
            action_fallback = self.heuristic.choose_action(state, unit, option)
            if action_fallback:
                action_fallback.unit_id = unit.unit_id
            
            self.sim_env.runtime.activated_units.add(unit.unit_id)
            return action_fallback

        # -------------------------------------------------
        # ✅ ENEMY SIDE (MÁQUINA / SCRIPTED)
        # -------------------------------------------------
        option, _ = self.option_policy.choose_option(obs)
        action_enemy = self.heuristic.choose_action(state, unit, option)
        if action_enemy:
            action_enemy.unit_id = unit.unit_id
            
        self.sim_env.runtime.activated_units.add(unit.unit_id)
        return action_enemy


def main():

    rl_side = RL_SIDE
    enemy_side = "GE" if rl_side == "US" else "US"

    print(f">>> Replaying: RL ({rl_side}) vs Heuristic ({enemy_side})")

    # -------------------------------------------------
    # ENV
    # -------------------------------------------------
    sim_config = load_sim_config(
        Path("C:/repos/python/assault/assault_sim/config/sim_config.yaml")
    )

    sim_config.scenario_name = "phase01_seq001_initial_contact"
    sim_config.seed = 42

    sim_env = SimEnv(
        sim_config,
        controller=None,
        debug_config=DebugConfig(enabled=True),
    )

    env = TrainingEnv(
        sim_env,
        env_config_path=Path("C:/repos/python/assault/assault_sim/config/env_config.json"),
        rl_side=rl_side,
    )

    obs = env.reset()
    input_dim = obs.shape[0]

    # -------------------------------------------------
    # MODEL
    # -------------------------------------------------
    print(f">>> Loading checkpoint: {CHECKPOINT}")

    policy = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption),
    )

    checkpoint = torch.load(CHECKPOINT, map_location="cpu")
    policy.load_state_dict(checkpoint)
    policy.eval()

    print(">>> PPO model loaded [OK]")

    # -------------------------------------------------
    # ✅ DecisionEngine (Cerebro Lookahead)
    # -------------------------------------------------
    def build_obs(sim_env):
        # Sincronizamos con el encoder para que coincida exactamente con las dimensiones del modelo
        return encode_state(
            sim_env.game_state,
            unit=None,
            rl_side=RL_SIDE,
            max_turns=sim_env.scenario.max_turns
        )

    decision_engine = DecisionEngine()

    # -------------------------------------------------
    # ✅ COMPONENTES CORRECTOS
    # -------------------------------------------------
    option_policy = OptionPolicy(policy)
    heuristic = TacticalPathHeuristic()

    # -------------------------------------------------
    # ✅ CONTROLLER
    # -------------------------------------------------
    controller = DecisionEngineController(
        rl_side=rl_side,
        decision_engine=decision_engine,
        option_policy=option_policy,
        heuristic=heuristic,
        sim_env=sim_env,
    )

    # -------------------------------------------------
    # OBSERVERS
    # -------------------------------------------------
    observer = ConsoleObserver(rl_side=rl_side)
    replay_observer = ReplayObserver()

    if sim_env.event_bus:
        sim_env.event_bus.subscribe(observer)
        sim_env.event_bus.subscribe(replay_observer)

    replay_observer.replay.initial_state = extract_initial_state(
        sim_env.game_state
    )

    replay_observer.replay.meta = {
        "scenario_id": sim_config.scenario_name,
        "sides": {
            rl_side: "RL",
            enemy_side: "HEURISTIC",
        },
    }

    # -------------------------------------------------
    # MATCH RUN
    # -------------------------------------------------
    runner = MatchRunner(env, controller=controller)

    done = False
    step = 0

    while not done:
        result = runner.step(controller, obs)
        obs = result["obs"]
        done = result["done"]
        step += 1

    # -------------------------------------------------
    # RESULT
    # -------------------------------------------------
    final_state = sim_env.game_state

    vp = final_state.vp_tracker.total_points if final_state.vp_tracker else 0

    print("\n=== MATCH FINISHED ===")
    print(f"Total steps: {step}")
    print(f"Winner:      {final_state.winner}")
    print(f"Reason:      {final_state.end_reason}")
    print(f"Final VP:    {vp}")

    replay_observer.replay.meta["result"] = {
        "winner": final_state.winner,
        "reason": final_state.end_reason,
        "vp": vp,
        "steps": step,
    }

    # -------------------------------------------------
    # SAVE REPLAY
    # -------------------------------------------------
    replay_dir = Path("C:/repos/python/assault/assault_sim/session/replays")
    replay_dir.mkdir(parents=True, exist_ok=True)

    replay_path = replay_dir / (
        f"{sim_config.scenario_name}__"
        f"{rl_side}_RL_vs_{enemy_side}_HEURISTIC.json"
    )

    ReplayWriter.write(replay_observer.replay, replay_path)

    print(f"[OK] Replay saved to: {replay_path}")


if __name__ == "__main__":
    main()