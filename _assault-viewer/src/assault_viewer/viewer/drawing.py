import pygame

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED   = (200, 50, 50)
BLUE  = (50, 50, 200)


def draw_frame(screen, state):
    screen.fill(WHITE)

    font = pygame.font.SysFont("arial", 18)

    # Debug header (neutral replay, no active player)
    header = font.render(
        f"Turn {state.turn}",
        True,
        BLACK,
    )
    screen.blit(header, (20, 10))

    # Draw units
    for unit in state.units:
        draw_unit(screen, unit)


def draw_unit(screen, unit):
    color = BLUE if unit.side == "A" else RED

    x, y = hex_to_screen(unit.hex)

    pygame.draw.circle(screen, color, (x, y), 18, 2)

    font = pygame.font.SysFont("arial", 14)
    label = font.render(
        f"{unit.unit_id} ({unit.strength})",
        True,
        BLACK,
    )
    screen.blit(label, (x - 20, y + 20))


def hex_to_screen(hex_id):
    """
    VERY SIMPLE mapping for debug only.
    """

    col = ord(hex_id[0]) - ord("A")
    row = int(hex_id[1:]) - 1

    HEX_W = 90
    HEX_ROW_STEP = 78

    x = 200 + col * HEX_W + (row % 2) * (HEX_W // 2)
    y = 100 + row * HEX_ROW_STEP

    return x, y