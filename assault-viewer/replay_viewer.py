import sys
import math
import pygame
from pathlib import Path

from assault_runner.runner import Runner

# ============================================================
# GRID (THE GRID DEFINES THE WORLD)
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

# ------------------------------------------------------------
# MAP SPLIT BY GRID ROWS
# ------------------------------------------------------------

ROWS_S3 = TOTAL_ROWS // 2           # top half
ROWS_S2 = TOTAL_ROWS - ROWS_S3     # bottom half

HEIGHT_S3 = (ROWS_S3 - 1) * HEX_ROW_STEP + 2 * HEX_R
HEIGHT_S2 = (ROWS_S2 - 1) * HEX_ROW_STEP + 2 * HEX_R

# ------------------------------------------------------------
# WORLD WIDTH (pointy-top grid)
# ------------------------------------------------------------

WORLD_MIN_X = -HEX_W / 2
WORLD_MAX_X = (COLS - 1) * HEX_W + HEX_W
WORLD_WIDTH = WORLD_MAX_X - WORLD_MIN_X

# ============================================================
# CAMERA
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

def load_maps():
    base = Path(__file__).resolve().parent / "assets" / "maps"

    # IMPORTANT:
    # Both maps MUST use convert_alpha()
    # because both PNGs contain transparency
    s2 = pygame.image.load(base / "Map_S2.png").convert_alpha()
    s3 = pygame.image.load(base / "Map_S3.png").convert_alpha()

    return s2, s3

def load_counters():
    base = Path(__file__).resolve().parent / "assets" / "counters"
    return {
        "US_RIFLES_43": pygame.image.load(base / "US Rifles 43.png").convert_alpha(),
        "US_RANGERS_43": pygame.image.load(base / "US Rangers 43.png").convert_alpha(),
        "GE_RIFLES_43": pygame.image.load(base / "GE Rifles 43.png").convert_alpha(),
        "GE_FJ_RIFLES_43": pygame.image.load(base / "GE FJ Rifles 43.png").convert_alpha(),
    }

# ============================================================
# HEX GEOMETRY
# ============================================================

def parse_hex_id(hex_id):
    return LETTERS.index(hex_id[0]), int(hex_id[1:]) - 1

def hex_to_world(col, row):
    x = col * HEX_W + (row % 2) * (HEX_W / 2)
    y = row * HEX_ROW_STEP
    return x, y

def draw_hex(surface, cx, cy, r):
    angles = [30, 90, 150, 210, 270, 330]
    pts = [
        (cx + r * math.cos(math.radians(a)),
         cy + r * math.sin(math.radians(a)))
        for a in angles
    ]
    pygame.draw.polygon(surface, GRID_COLOR, pts, 1)

# ============================================================
# MAP DRAWING (ONLY OFFSET Y FOR S2)
# ============================================================

def draw_maps(surface, map_s2, map_s3):
    # Resize based on grid (unchanged)
    scaled_w = int(WORLD_WIDTH * zoom)
    scaled_h_s3 = int(HEIGHT_S3 * zoom)
    scaled_h_s2 = int(HEIGHT_S2 * zoom)

    s3_scaled = pygame.transform.smoothscale(
        map_s3, (scaled_w, scaled_h_s3)
    )
    s2_scaled = pygame.transform.smoothscale(
        map_s2, (scaled_w, scaled_h_s2)
    )

    # World origin at row 0 (top of A1)
    sx = int((WORLD_MIN_X - camera_x) * zoom)
    sy = int((-HEX_R - camera_y) * zoom)

    # S3 starts at A1 (unchanged)
    surface.blit(s3_scaled, (sx, sy))

    # S2 starts at A9 (row 8), top edge of the hex
    _, a9_y = hex_to_world(0, 8)
    s2_y = int((a9_y - HEX_R - camera_y) * zoom)

    surface.blit(s2_scaled, (sx, s2_y))

# ============================================================
# GRID DRAWING
# ============================================================

def draw_grid(surface, font):
    r = HEX_R * zoom

    for row in range(TOTAL_ROWS):
        for col in range(COLS):
            wx, wy = hex_to_world(col, row)
            sx, sy = world_to_screen(wx, wy)

            draw_hex(surface, sx, sy, r)

            label = f"{LETTERS[col]}{row + 1}"
            txt = font.render(label, True, TEXT_COLOR)
            surface.blit(txt, (sx + r * 0.28, sy - r * 0.6))

# ============================================================
# UNITS
# ============================================================

def draw_counter(surface, unit, counters):
    col, row = parse_hex_id(unit.hex)
    wx, wy = hex_to_world(col, row)
    sx, sy = world_to_screen(wx, wy)

    size = int(HEX_R * 1.3 * zoom)
    img = pygame.transform.smoothscale(
        counters[unit.counter_id], (size, size)
    )

    surface.blit(img, (sx - size // 2, sy - size // 2))

def draw_game_state(surface, state, counters):
    for u in state.units:
        draw_counter(surface, u, counters)

# ============================================================
# MAIN
# ============================================================

def main():
    global camera_x, camera_y, zoom, dragging, last_mouse

    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("Assault Replay Viewer")

    font = pygame.font.SysFont("arial", FONT_SIZE)

    map_s2, map_s3 = load_maps()
    counters = load_counters()

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
                dragging = False

            elif e.type == pygame.MOUSEMOTION and dragging:
                dx = e.pos[0] - last_mouse[0]
                dy = e.pos[1] - last_mouse[1]
                camera_x -= dx / zoom
                camera_y -= dy / zoom
                last_mouse = e.pos

        if auto_play:
            step = min(step + 1, len(replay.states) - 1)

        screen.fill((0, 0, 0))
        draw_maps(screen, map_s2, map_s3)
        draw_grid(screen, font)
        draw_game_state(screen, replay.states[step], counters)

        pygame.display.flip()
        clock.tick(60)

if __name__ == "__main__":
    main()
