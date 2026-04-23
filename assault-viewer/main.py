import sys
import math
import pygame
from pathlib import Path

# =========================
# BOARD CONSTANTS
# =========================

COLS = 9
ROWS_PER_MAP = 8
TOTAL_ROWS = 16

LETTERS = "ABCDEFGHI"

HEX_R = 52
HEX_W = math.sqrt(3) * HEX_R
HEX_ROW_STEP = 1.5 * HEX_R

GRID_COLOR = (255, 0, 0)          # red dashed grid
TEXT_COLOR = (30, 60, 140)        # azul marino
GRID_WIDTH = 1
DASH_LEN = 8
FONT_SIZE = 11
BG_COLOR = (18, 18, 18)

# =========================
# HEX GEOMETRY
# =========================

def hex_vertices(cx, cy, r):
    angles = [30, 90, 150, 210, 270, 330]  # pointy-top
    return [
        (
            cx + r * math.cos(math.radians(a)),
            cy + r * math.sin(math.radians(a)),
        )
        for a in angles
    ]


def draw_dashed_line(surface, p1, p2, color, dash=DASH_LEN, width=GRID_WIDTH):
    x1, y1 = p1
    x2, y2 = p2
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        return

    dx = (x2 - x1) / length
    dy = (y2 - y1) / length
    step = dash * 2

    for i in range(0, int(length), step):
        start = (x1 + dx * i, y1 + dy * i)
        end = (
            x1 + dx * min(i + dash, length),
            y1 + dy * min(i + dash, length),
        )
        pygame.draw.line(surface, color, start, end, width)


def draw_hex_dashed(surface, cx, cy, r):
    verts = hex_vertices(cx, cy, r)
    for i in range(6):
        draw_dashed_line(
            surface,
            verts[i],
            verts[(i + 1) % 6],
            GRID_COLOR,
        )


def fit_zoom(vw, vh, mw, mh):
    return min(vw / mw, vh / mh)

# =========================
# MAIN
# =========================

def main():
    pygame.init()

    # Window
    screen = pygame.display.set_mode((0, 0), pygame.RESIZABLE)
    pygame.display.set_caption("Assault AI Viewer – Final Grid")
    view_w, view_h = screen.get_size()

    font = pygame.font.SysFont("arial", FONT_SIZE)

    # Load maps
    base = Path(__file__).resolve().parent
    maps = base / "assets" / "maps"
    s3 = pygame.image.load(maps / "Map_S3.png").convert_alpha()
    s2 = pygame.image.load(maps / "Map_S2.png").convert_alpha()

    # Logical board size (grid truth)
    BOARD_W = COLS * HEX_W + (HEX_W / 2)
    BOARD_H = (TOTAL_ROWS - 1) * HEX_ROW_STEP + 2 * HEX_R

    # Correct texture height
    MAP_W = BOARD_W
    MAP_H = (ROWS_PER_MAP - 1) * HEX_ROW_STEP + 2 * HEX_R

    s3_scaled = pygame.transform.scale(s3, (int(MAP_W), int(MAP_H)))
    s2_scaled = pygame.transform.scale(s2, (int(MAP_W), int(MAP_H)))

    # Final, correct artistic offset
    MAP_OFFSET_X = -HEX_W / 2
    MAP_OFFSET_Y = -HEX_R

    zoom = fit_zoom(view_w, view_h, BOARD_W, BOARD_H)
    cam_x = 0.0
    cam_y = 0.0
    cam_speed = 40

    clock = pygame.time.Clock()
    running = True

    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False

            elif e.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((e.w, e.h), pygame.RESIZABLE)
                view_w, view_h = e.w, e.h
                zoom = fit_zoom(view_w, view_h, BOARD_W, BOARD_H)

            elif e.type == pygame.MOUSEWHEEL:
                zoom = zoom * 1.1 if e.y > 0 else zoom * 0.9

            elif e.type == pygame.KEYDOWN and e.key == pygame.K_r:
                zoom = fit_zoom(view_w, view_h, BOARD_W, BOARD_H)
                cam_x = cam_y = 0.0

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:  cam_x += cam_speed
        if keys[pygame.K_RIGHT]: cam_x -= cam_speed
        if keys[pygame.K_UP]:    cam_y += cam_speed
        if keys[pygame.K_DOWN]:  cam_y -= cam_speed

        screen.fill(BG_COLOR)

        # ---- MAPS ----
        screen.blit(
            pygame.transform.scale(
                s3_scaled,
                (int(MAP_W * zoom), int(MAP_H * zoom)),
            ),
            ((MAP_OFFSET_X + cam_x) * zoom,
             (MAP_OFFSET_Y + cam_y) * zoom),
        )

        screen.blit(
            pygame.transform.scale(
                s2_scaled,
                (int(MAP_W * zoom), int(MAP_H * zoom)),
            ),
            ((MAP_OFFSET_X + cam_x) * zoom,
             (MAP_OFFSET_Y + cam_y + ROWS_PER_MAP * HEX_ROW_STEP) * zoom),
        )

        # ---- GRID + LABELS ----
        overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        r_scaled = HEX_R * zoom

        for row in range(TOTAL_ROWS):
            y = row * HEX_ROW_STEP
            row_offset = (row % 2) * (HEX_W / 2)

            for col in range(COLS):
                x = col * HEX_W + row_offset

                sx = (x + cam_x) * zoom
                sy = (y + cam_y) * zoom

                # dashed hex
                draw_hex_dashed(overlay, sx, sy, r_scaled)

                # label (top-right)
                label = f"{LETTERS[col]}{row + 1}"
                text = font.render(label, True, TEXT_COLOR)
                overlay.blit(
                    text,
                    (
                        sx + r_scaled * 0.35,
                        sy - r_scaled * 0.55,
                    ),
                )

        screen.blit(overlay, (0, 0))
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
