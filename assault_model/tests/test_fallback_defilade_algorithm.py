"""
Unit and integration tests for Roadmap Task 3.1:
Algoritmo de Retirada a Borde Amigo en Desenfilada (Regla 13.3 / Sección 6.4).

Verifica:
1. Priorización de desenfilada (LOS BLOCKED vs CLEAR) respecto al atacante.
2. Selección de la mayor cobertura de terreno entre hexágonos en desenfilada.
3. Vector dirigido al borde amigo (Friendly Edge: NORTH / SOUTH).
4. Aumento o conservación de distancia respecto a la dirección de ataque.
5. Eliminación inmediata de artillería o unidades inmovilizadas en fallback (Regla 13.3).
6. Penalización de 1 punto de daño si la unidad está completamente bloqueada/rodeada (Regla 13.3).
7. Integración end-to-end con resolución de combate a distancia y GameState.
"""

import pytest

from assault_model.combat.line_of_sight import LineOfSight
from assault_model.combat.morale import resolve_fallback, apply_suppression_hits
from assault_model.map.hex import Hex
from assault_model.map.hex_coord import HexCoord
from assault_model.map.map import Map
from assault_model.map.terrain import Terrain
from assault_model.rules.movement_rules import MovementRules
from assault_model.state.game_state import GameState
from assault_model.units.unit_instance import UnitInstance
from assault_model.units.unit_type import UnitCategory, UnitSide, UnitType


def _make_test_unit_type(
    code: str = "INF",
    side: UnitSide = UnitSide.IT,
    category: UnitCategory = UnitCategory.INFANTRY,
    movement: int = 2,
    max_strength: int = 4,
) -> UnitType:
    return UnitType(
        code=code,
        side=side,
        category=category,
        movement=movement,
        movement_type="foot",
        max_strength=max_strength,
    )


def _make_simple_map(width: int = 10, height: int = 10, default_terrain: Terrain = Terrain.CLEAR) -> Map:
    hexes = []
    for q in range(width):
        for r in range(height):
            hexes.append(Hex(q, r, default_terrain))
    return Map(hexes=hexes)


# =============================================================================
# TEST CASES
# =============================================================================

def test_fallback_selects_defilade_over_exposed():
    """
    Given a defender targeted by an attacker from the South,
    when one retreat hex has LOS BLOCKED (defilade behind building)
    and another has LOS CLEAR, the algorithm must choose the defilade hex.
    """
    gmap = _make_simple_map(10, 10, Terrain.CLEAR)
    # Put a heavy building at (4, 4) to block LOS from (5, 6) to (4, 3)
    gmap.get_hex(4, 4).terrain = Terrain.BUILDING_MULTI

    u_type = _make_test_unit_type(side=UnitSide.IT)
    defender = UnitInstance(unit_id="IT_DEF", unit_type=u_type, side="IT", position=HexCoord(5, 4))
    attacker = UnitInstance(unit_id="US_ATK", unit_type=u_type, side="US", position=HexCoord(5, 6))

    game_state = GameState(game_map=gmap, units=[defender, attacker])

    best_hex, scored = MovementRules.calculate_fallback_destination(
        game_state=game_state,
        unit=defender,
        attacker=attacker,
        friendly_edge="NORTH",
    )

    assert best_hex is not None
    # Best hex must increase distance to attacker and be in defilade
    best_cand = scored[0]
    assert best_cand["defilade_status"] == LineOfSight.BLOCKED
    assert best_cand["cand_dist"] >= 2


def test_fallback_selects_highest_cover_among_defilade_options():
    """
    Given multiple retreat options in defilade (LOS BLOCKED),
    the algorithm must select the one providing the highest terrain/fortification cover.
    """
    gmap = _make_simple_map(10, 10, Terrain.CLEAR)
    # (5, 3) is Heavy Forest
    gmap.get_hex(5, 3).terrain = Terrain.HEAVY_FOREST
    # (4, 3) is Clear
    gmap.get_hex(4, 3).terrain = Terrain.CLEAR

    # Put a building at (5, 5) to block direct LOS from South
    gmap.get_hex(5, 5).terrain = Terrain.BUILDING_MULTI

    u_type = _make_test_unit_type(side=UnitSide.IT)
    defender = UnitInstance(unit_id="IT_DEF", unit_type=u_type, side="IT", position=HexCoord(5, 4))
    attacker = UnitInstance(unit_id="US_ATK", unit_type=u_type, side="US", position=HexCoord(5, 6))

    game_state = GameState(game_map=gmap, units=[defender, attacker])

    best_hex, scored = MovementRules.calculate_fallback_destination(
        game_state=game_state,
        unit=defender,
        attacker=attacker,
        friendly_edge="NORTH",
    )

    assert best_hex == HexCoord(5, 3)
    # Verify that heavy forest cover score is higher than clear
    cand_5_3 = next(c for c in scored if (c["q"], c["r"]) == (5, 3))
    cand_4_3 = next(c for c in scored if (c["q"], c["r"]) == (4, 3))
    assert cand_5_3["cover_score"] > cand_4_3["cover_score"]


def test_fallback_aligns_with_friendly_edge():
    """
    When enemy attacks from the East, friendly edge (NORTH vs SOUTH)
    guides the retreat vector towards friendly territory.
    """
    gmap = _make_simple_map(10, 10, Terrain.CLEAR)

    u_type = _make_test_unit_type(side=UnitSide.IT)
    defender = UnitInstance(unit_id="IT_DEF", unit_type=u_type, side="IT", position=HexCoord(5, 5))
    attacker = UnitInstance(unit_id="US_ATK", unit_type=u_type, side="US", position=HexCoord(7, 5))

    game_state = GameState(game_map=gmap, units=[defender, attacker])

    # Defender with NORTH friendly edge
    best_north, _ = MovementRules.calculate_fallback_destination(
        game_state=game_state,
        unit=defender,
        attacker=attacker,
        friendly_edge="NORTH",
    )
    assert best_north.r < defender.position.r  # Retreated towards lower r (North)

    # Defender with SOUTH friendly edge
    best_south, _ = MovementRules.calculate_fallback_destination(
        game_state=game_state,
        unit=defender,
        attacker=attacker,
        friendly_edge="SOUTH",
    )
    assert best_south.r > defender.position.r  # Retreated towards higher r (South)


def test_fallback_penalizes_moving_towards_attacker():
    """
    Candidate hexes that decrease the distance to the attacker must be heavily penalized.
    """
    gmap = _make_simple_map(10, 10, Terrain.CLEAR)
    u_type = _make_test_unit_type(side=UnitSide.IT)

    defender = UnitInstance(unit_id="IT_DEF", unit_type=u_type, side="IT", position=HexCoord(5, 5))
    attacker = UnitInstance(unit_id="US_ATK", unit_type=u_type, side="US", position=HexCoord(5, 7))
    game_state = GameState(game_map=gmap, units=[defender, attacker])

    _, scored = MovementRules.calculate_fallback_destination(
        game_state=game_state,
        unit=defender,
        attacker=attacker,
    )

    # Any candidate with distance < current_dist (2) must have a negative dist_score
    for cand in scored:
        if cand["cand_dist"] < 2:
            assert cand["dist_score"] < 0


def test_resolve_fallback_destroys_artillery_or_immobile():
    """
    Rule 13.3: Artillery or immobilised units are eliminated if they are ever in fallback.
    """
    u_type_art = _make_test_unit_type(code="ART", category=UnitCategory.INFANTRY)
    # Force category ARTILLERY
    object.__setattr__(u_type_art, "category", type("DummyCat", (), {"name": "ARTILLERY"})())

    artillery_unit = UnitInstance(
        unit_id="IT_ART_1",
        unit_type=u_type_art,
        side="IT",
        position=HexCoord(3, 3),
    )
    artillery_unit.fallback = True

    resolve_fallback(artillery_unit)
    assert not artillery_unit.alive
    assert artillery_unit.strength == 0

    # Immobile vehicle unit
    u_type_veh = _make_test_unit_type(code="VEH", category=UnitCategory.VEHICLE)
    vehicle_unit = UnitInstance(
        unit_id="GE_PANZER",
        unit_type=u_type_veh,
        side="GE",
        position=HexCoord(4, 4),
    )
    vehicle_unit.immobile = True
    vehicle_unit.fallback = True

    resolve_fallback(vehicle_unit)
    assert not vehicle_unit.alive
    assert vehicle_unit.strength == 0


def test_resolve_fallback_takes_damage_when_trapped():
    """
    Rule 13.3: If no legal retreat hex exists (unit surrounded or trapped by impassable terrain),
    it takes a damage point and remains in its current hex.
    """
    gmap = _make_simple_map(10, 10, Terrain.CLEAR)
    u_type = _make_test_unit_type(side=UnitSide.IT, max_strength=4)

    defender = UnitInstance(unit_id="IT_TRAPPED", unit_type=u_type, side="IT", position=HexCoord(5, 5))
    defender.strength = 3
    defender.fallback = True

    # Surround defender completely with enemies in all 6 neighbors
    from assault_model.map.hex_utils import neighbors as hex_neighbors
    surrounding_enemies = []
    for i, (nq, nr) in enumerate(hex_neighbors((5, 5))):
        enemy = UnitInstance(
            unit_id=f"US_SURROUND_{i}",
            unit_type=u_type,
            side="US",
            position=HexCoord(nq, nr),
        )
        surrounding_enemies.append(enemy)

    game_state = GameState(game_map=gmap, units=[defender] + surrounding_enemies)

    resolve_fallback(defender, game_state=game_state)

    # Unit must have stayed in (5, 5) and suffered 1 damage point
    assert defender.position == HexCoord(5, 5)
    assert defender.strength == 2  # 3 - 1
    assert defender.alive


def test_resolve_fallback_integrates_with_game_state_spatial_control():
    """
    Verify that resolve_fallback executes correctly with a GameState,
    updating position, fallback status, and triggering hex control recalculation.
    """
    gmap = _make_simple_map(10, 10, Terrain.CLEAR)
    gmap.get_hex(5, 3).terrain = Terrain.HEAVY_FOREST
    gmap.add_hex_fortification(5, 3, "trench")

    u_type = _make_test_unit_type(side=UnitSide.IT)
    defender = UnitInstance(unit_id="IT_DEF", unit_type=u_type, side="IT", position=HexCoord(5, 4))
    attacker = UnitInstance(unit_id="US_ATK", unit_type=u_type, side="US", position=HexCoord(5, 6))

    game_state = GameState(game_map=gmap, units=[defender, attacker])

    # Trigger fallback on defender
    defender.fallback = True
    resolve_fallback(defender, game_state=game_state, attacker=attacker, friendly_edge="NORTH")

    assert defender.position == HexCoord(5, 3)
    assert defender.fallback is True
    assert defender.alive is True
