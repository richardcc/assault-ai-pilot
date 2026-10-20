# agents/efficientzero_v2/tests/test_vp_acceleration_curriculum.py
"""
Test Suite for Roadmap Task 2.5:
Currículum Progresivo Acelerado de Captura de VPs (Paridad Humana).
Verifies:
1. Master curriculum specification (curriculum.yaml) with 4 progressive phases and gates.
2. Progressive scenario loading and structural invariants in VOECSimulator:
   - Phase 1: VPs desocupados a 3 hexágonos (sprint puro).
   - Phase 2: VPs defendidos por unidad estática suprimida (base de fuego + asalto).
   - Phase 3: Carrera frontal simultánea de VPs (2 vs 2 unidades).
   - Phase 4: Escenario táctico completo (Gela - Battaglia Cittadina: >=75% victoria vs bot en <15 turnos).
3. Root trainer.py delegation contracts (pure EfficientZero V2).
4. Cycle JSON definitions and CLI training/eval commands.
"""

from pathlib import Path
import json
import yaml
import pytest

from voec_sim.core.simulator import VOECSimulator
from assault_model.map.hex_utils import safe_hex_distance
import trainer


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_vp_acceleration_curriculum_yaml_validity():
    curriculum_path = REPO_ROOT / "curriculums" / "vp_acceleration" / "curriculum.yaml"
    assert curriculum_path.exists(), f"Missing curriculum file: {curriculum_path}"

    data = yaml.safe_load(curriculum_path.read_text(encoding="utf-8"))
    assert data["name"] == "vp_acceleration_v1"
    assert data["engine"] == "efficientzero_v2"
    assert "phases" in data
    phases = data["phases"]
    assert len(phases) == 4

    expected_phases = [
        "phase1_vp_sprint_unoccupied",
        "phase2_vp_assault_suppressed",
        "phase3_vp_race_2v2",
        "phase4_tactical_gela_mastery",
    ]
    actual_phases = [p["name"] for p in phases]
    assert actual_phases == expected_phases

    # Verify quantitative acceptance criteria in Phase 4 gate
    phase4_gate = phases[3]["gate"]
    assert phase4_gate.get("min_win_rate_vs_heuristic") == 0.75  # >= 75% vs heuristic bot
    assert phase4_gate.get("max_avg_turns") == 15.0             # < 15 turnos

    # Verify all referenced training and eval configs exist
    for p in phases:
        t_cfg = REPO_ROOT / p["train_config"]
        e_cfg = REPO_ROOT / p["eval_config"]
        assert t_cfg.exists(), f"Missing train config: {t_cfg}"
        assert e_cfg.exists(), f"Missing eval config: {e_cfg}"


def test_progressive_scenarios_contracts_in_voec():
    sim = VOECSimulator()

    # Phase 1: Unoccupied VP at 3 hexes
    ep1 = sim.new_episode("vp_phase1_unoccupied_3hex")
    assert ep1.scenario_id == "vp_phase1_unoccupied_3hex"
    snap1 = sim.snapshot()
    assert len(snap1.units) == 1
    assert snap1.units[0].side == "US"
    spatial1 = sim.spatial_features()
    vp_hexes1 = spatial1.get("vp_hexes", [])
    assert len(vp_hexes1) == 1
    u_pos1 = (snap1.units[0].q, snap1.units[0].r)
    vp_pos1 = (vp_hexes1[0]["q"], vp_hexes1[0]["r"])
    # Distance from unit to VP must be exactly 3 hexes
    assert safe_hex_distance(u_pos1, vp_pos1) == 3

    # Phase 2: Defended VP by static suppressed defender
    ep2 = sim.new_episode("vp_phase2_defended_suppressed")
    assert ep2.scenario_id == "vp_phase2_defended_suppressed"
    snap2 = sim.snapshot()
    us_units = [u for u in snap2.units if u.side == "US"]
    it_units = [u for u in snap2.units if u.side == "IT"]
    assert len(us_units) == 2  # Spearhead + Fire Support
    assert len(it_units) == 1  # Defender on VP
    raw_it = [u for u in sim._state.units if u.side == "IT"]
    assert bool(raw_it[0].suppressed) is True  # Defending unit begins suppressed

    # Phase 3: Simultaneous 2v2 VP race
    ep3 = sim.new_episode("vp_phase3_race_2v2")
    assert ep3.scenario_id == "vp_phase3_race_2v2"
    snap3 = sim.snapshot()
    us_units3 = [u for u in snap3.units if u.side == "US"]
    it_units3 = [u for u in snap3.units if u.side == "IT"]
    assert len(us_units3) == 2
    assert len(it_units3) == 2
    spatial3 = sim.spatial_features()
    assert len(spatial3.get("vp_hexes", [])) == 2

    # Phase 4: Full tactical scenario (Gela / Battaglia Cittadina)
    ep4 = sim.new_episode("battaglia_cittadina_2_1")
    assert ep4.scenario_id == "battaglia_cittadina_2_1"
    snap4 = sim.snapshot()
    assert len(snap4.units) >= 10


def test_root_trainer_delegates_to_efficientzero_v2():
    # Verify root trainer imports and exposes canonical EZv2 trainer
    assert trainer.EfficientZeroV2Trainer is not None
    assert callable(trainer.run_training)
    assert hasattr(trainer, "main")


def test_vp_acceleration_cycles_json():
    cycles_dir = REPO_ROOT / "curriculums" / "vp_acceleration" / "cycles"
    assert cycles_dir.exists()

    cycle_files = list(cycles_dir.glob("*.cycle.json"))
    assert len(cycle_files) == 4

    for cf in cycle_files:
        payload = json.loads(cf.read_text(encoding="utf-8"))
        assert "train_command" in payload
        assert "eval_command" in payload
        # Zero tolerance to Muzero: must use train_efficientzero_v2
        assert "train_efficientzero_v2" in payload["train_command"]
        assert "muzero" not in payload["train_command"].lower()
        assert "assault_bench.runner" in payload["eval_command"]
