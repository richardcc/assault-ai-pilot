import sys
import math
import pygame
from pathlib import Path

from assault_runner.runner import Runner

# ============================================================
# TABLERO
# ============================================================

COLS = 9
TOTAL_ROWS = 16
LETTERS = "ABCDEFGHI"

HEX_R = 52
HEX_W = math.sqrt(3) * HEX_R
HEX_ROW_STEP = 1.5 * HEX_R

GRID_COLOR = (200, 200, 200)
TEXT_COLOR = (80, 120, 200)
FONT_SIZE = 14

# ============================================================
# CÁMARA (ratón + zoom)
# ============================================================

camera_x = 0.0
camera_y = 0.0
zoom = 1.0

dragging = False
last_mouse = (0, 0)

def world_to_screen(x, y):
    return int((x - camera_x) * zoom), int((y - camera_y) * zoom)

# ============================================================
# ASSETS
# ============================================================

def load_counters():
    base = Path(__file__).resolve().parent / "assets" / "counters"
    return {
        "US_RIFLES_43": pygame.image.load(base / "US Rifles 43.png").convert_alpha(),
        "US_RANGERS_43": pygame.image.load(base / "US Rangers 43.png").convert_alpha(),
        "GE_RIFLES_43": pygame.image.load(base / "GE Rifles 43.png").convert_alpha(),
        "GE_FJ_RIFLES_43": pygame.image.load(base / "GE FJ Rifles 43.png").convert_alpha(),
        "US_RIFLES_43b": pygame.image.load(base / "US Rifles 43b.png").convert_alpha(),
        "GE_RIFLES_43b": pygame.image.load(base / "GE Rifles 43b.png").convert_alpha(),
    }

def load_maps():
    base = Path(__file__).resolve().parent / "assets" / "maps"
    # IMPORTANTE: resolución nativa, sin escalar aquí
    s2 = pygame.image.load(base / "Map_S2.png").convert()
    s3 = pygame.image.load(base / "Map_S3.png").convert_alpha()
    return s2, s3

# ============================================================
# GEOMETRÍA HEX
# ============================================================

def hex_vertices(cx, cy, r):
    angles = [30, 90, 150, 210, 270, 330]
    return [
        (
            cx + r * math.cos(math.radians(a)),
            cy + r * math.sin(math.radians(a)),
        )
        for a in angles
    ]

def draw_hex(surface, cx, cy, r):
    pygame.draw.polygon(surface, GRID_COLOR, hex_vertices(cx, cy, r), 1)

def parse_hex_id(hex_id):
    return LETTERS.index(hex_id[0]), int(hex_id[1:]) - 1

def hex_to_world(col, row):
    x = col * HEX_W + (row % 2) * (HEX_W / 2)
    y = row * HEX_ROW_STEP
    return x, y

# ============================================================
# DIBUJO
# ============================================================

def draw_maps(surface, map_s2, map_s3):
    # El mapa vive en WORLD (0,0)
    sx, sy = world_to_screen(0, 0)

    # HACER ZOOM DEL MAPA (CLAVE QUE FALTABA)
    scaled_w = int(map_s2.get_width() * zoom)
    scaled_h = int(map_s2.get_height() * zoom)

    map2 = pygame.transform.smoothscale(map_s2, (scaled_w, scaled_h))
    map3 = pygame.transform.smoothscale(map_s3, (scaled_w, scaled_h))

    surface.blit(map2, (sx, sy))
    surface.blit(map3, (sx, sy))

def draw_grid(surface, font):
    r = HEX_R * zoom

    for row in range(TOTAL_ROWS):
        for col in range(COLS):
            wx, wy = hex_to_world(col, row)
            sx, sy = world_to_screen(wx, wy)

            draw_hex(surface, sx, sy, r)

            label = f"{LETTERS[col]}{row + 1}"
            txt = font.render(label, True, TEXT_COLOR)
            surface.blit(txt, (sx + r * 0.25, sy - r * 0.6))

def draw_counter(surface, unit, counters, stack_index=0):
    col, row = parse_hex_id(unit.hex)
    wx, wy = hex_to_world(col, row)
    sx, sy = world_to_screen(wx, wy)

    size = int(HEX_R * 1.3 * zoom)
    img = pygame.transform.smoothscale(
        counters[unit.counter_id], (size, size)
    )

    offset = stack_index * int(size * 0.12)
    surface.blit(
        img,
        (
            sx - size // 2 + offset,
            sy - size // 2 - offset,
        ),
    )

def draw_game_state(surface, state, counters):
    stacks = {}
    for u in state.units:
        stacks.setdefault(u.hex, []).append(u)

    for units in stacks.values():
        for i, u in enumerate(units):
            draw_counter(surface, u, counters, i)

# ============================================================
# MAIN
# ============================================================

def main():
    global camera_x, camera_y, zoom, dragging, last_mouse

    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("Assault Replay Viewer")

    font = pygame.font.SysFont("arial", FONT_SIZE)

    counters = load_counters()
    map_s2, map_s3 = load_maps()

    runner = Runner()
    replay = runner.run(["B10", "C10", "C11", "D11", "D10"])

    step = 0
    auto_play = False

    clock = pygame.time.Clock()

    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                elif e.key == pygame.K_d:
                    step = min(step + 1, len(replay.states) - 1)
                elif e.key == pygame.K_a:
                    step = max(step - 1, 0)
                elif e.key == pygame.K_SPACE:
                    auto_play = not auto_play

            elif e.type == pygame.MOUSEBUTTONDOWN:
                if e.button == 1:
                    dragging = True
                    last_mouse = e.pos
                elif e.button == 4:
                    zoom *= 1.1
                elif e.button == 5:
                    zoom /= 1.1

            elif e.type == pygame.MOUSEBUTTONUP:
                if e.button == 1:
                    dragging = False

            elif e.type == pygame.MOUSEMOTION and dragging:
                mx, my = e.pos
                dx = mx - last_mouse[0]
                dy = my - last_mouse[1]
                camera_x -= dx / zoom
                camera_y -= dy / zoom
                last_mouse = e.pos

        if auto_play:
            step = min(step + 1, len(replay.states) - 1)

        screen.fill((0, 0, 0))

        # ORDEN CORRECTO
        draw_maps(screen, map_s2, map_s3)
        draw_grid(screen, font)
        draw_game_state(screen, replay.states[step], counters)

        pygame.display.flip()
        clock.tick(60)

if __name__ == "__main__":
    main()
