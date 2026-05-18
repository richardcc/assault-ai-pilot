from assault_model.combat.dice_color import DiceColor

TERRAIN_DEFENSE = {
    "clear": [],

    # woods (tu mapa)
    "woods": [DiceColor.BLUE],

    # buildings (tu mapa)
    "building": [DiceColor.GREEN, DiceColor.YELLOW],

    # agua (normalmente sin bonus, pero depende del chart real)
    "water": [],
}