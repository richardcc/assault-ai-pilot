import sys
import math
import pygame
from pathlib import Path

from assault.replay.loader import load_replay_from_json

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

ROWS_S3 = TOTAL_ROWS // 2
ROWS_S2 = TOTAL_ROWS - ROWS_S3

HEIGHT_S3 = (ROWS_S3 - 1) * HEX_ROW_STEP + 2 * HEX_R
HEIGHT_S2 = (ROWS_S2 - 1) * HEX_ROW_STEP + 2 * HEX_R

# ------------------------------------------------------------
# WORLD WIDTH
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
    base = Path(__file__).resolve().parents[1] / "assets" / "maps"
    s2 = pygame.image.load(base / "Map_S2.png").convert_alpha()
    s3 = pygame.image.load(base / "Map_S3.png").convert_alpha()
    return s2, s3

def load_counters():
    base = Path(__file__).resolve().parents[1] / "assets" / "counters"

    us = pygame.image.load(base / "US Rifles 43.png").convert_alpha()
    ge = pygame.image.load(base / "GE Rifles 43.png").convert_alpha()

    return {
        "A": us,   # Aliados
        "B": ge,   # Enemigos (alias del replay RL)
        "D": ge,   # Enemigos (nombre histórico del viewer)
    }

# ============================================================
# HEX GEOMETRY
# ============================================================

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
# MAP DRAWING
# ============================================================

def draw_maps(surface, map_s2, map_s3):
    scaled_w = int(WORLD_WIDTH * zoom)
    scaled_h_s3 = int(HEIGHT_S3 * zoom)
    scaled_h_s2 = int(HEIGHT_S2 * zoom)

    s3_scaled = pygame.transform.smoothscale(map_s3, (scaled_w, scaled_h_s3))
    s2_scaled = pygame.transform.smoothscale(map_s2, (scaled_w, scaled_h_s2))

    sx = int((WORLD_MIN_X - camera_x) * zoom)
    sy = int((-HEX_R - camera_y) * zoom)

    surface.blit(s3_scaled, (sx, sy))

    _, a9_y = hex_to_world(0, 8)
    s2_y = int((a9_y - HEX_R - camera_y) * zoom)
    surface.blit(s2_scaled, (sx, s2_y))

# ============================================================
# GRID
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
            surface.blit(txt, (sx + r * 0.25, sy - r * 0.6))

# ============================================================
# UNITS  ✅ CORRECCIÓN AQUÍ (SOLO AQUÍ)
# ============================================================

def draw_counter(surface, unit, counters):
    # unit.hex is like "B10"
    col = LETTERS.index(unit.hex[0])
    row = int(unit.hex[1:]) - 1

    wx, wy = hex_to_world(col, row)
    sx, sy = world_to_screen(wx, wy)

    size = int(HEX_R * 1.3 * zoom)
    img = pygame.transform.smoothscale(
        counters[unit.side], (size, size)
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

    if len(sys.argv) < 2:
        print("Usage: replay_viewer.py <replay.json>")
        sys.exit(1)

    replay = load_replay_from_json(sys.argv[1])

    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    pygame.display.set_caption("Assault Replay Viewer")

    font = pygame.font.SysFont("arial", FONT_SIZE)

    map_s2, map_s3 = load_maps()
    counters = load_counters()

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

        state = replay.states[step]

        turn_text = font.render(
            f"Turn {state.turn} / {len(replay.states) - 1}",
            True,
            (255, 255, 255),
        )
        index_text = font.render(
            f"Replay state index: {step}",
            True,
            (200, 200, 200),
        )

        screen.blit(turn_text, (20, 20))
        screen.blit(index_text, (20, 45))

        draw_maps(screen, map_s2, map_s3)
        draw_grid(screen, font)
        draw_game_state(screen, state, counters)

        pygame.display.flip()
        clock.tick(60)

if __name__ == "__main__":
    main()