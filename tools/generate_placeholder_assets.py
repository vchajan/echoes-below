from __future__ import annotations

from pathlib import Path

import pygame


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = PROJECT_ROOT / "assets"

TILE = 48
CYAN = (71, 226, 240, 255)
CYAN_DIM = (25, 105, 122, 255)
ORANGE = (231, 126, 45, 255)
RED = (224, 64, 68, 255)
BLACK = (5, 7, 11, 255)
CHARCOAL = (18, 24, 30, 255)
METAL = (76, 86, 92, 255)
METAL_DARK = (42, 50, 57, 255)
METAL_LIGHT = (115, 126, 130, 255)


def ensure_dirs() -> None:
    for name in ("tiles", "sprites", "objects", "ui", "effects", "audio"):
        (ASSET_ROOT / name).mkdir(parents=True, exist_ok=True)


def save(surface: pygame.Surface, relative_path: str) -> None:
    pygame.image.save(surface, str(PROJECT_ROOT / relative_path))


def cell_rect(index: int, columns: int, width: int, height: int) -> pygame.Rect:
    return pygame.Rect((index % columns) * width, (index // columns) * height, width, height)


def draw_panel(surface: pygame.Surface, rect: pygame.Rect, base: tuple[int, int, int, int]) -> None:
    pygame.draw.rect(surface, base, rect)
    pygame.draw.rect(surface, (8, 11, 16, 255), rect, 2)
    inset = rect.inflate(-10, -10)
    pygame.draw.rect(surface, tuple(min(c + 14, 255) for c in base[:3]) + (255,), inset, 1)
    pygame.draw.line(surface, METAL_DARK, rect.midleft, rect.midright, 2)
    pygame.draw.line(surface, METAL_DARK, rect.midtop, rect.midbottom, 2)


def generate_tileset() -> None:
    sheet = pygame.Surface((TILE * 6, TILE * 2), pygame.SRCALPHA)
    for index in range(12):
        rect = cell_rect(index, 6, TILE, TILE)
        draw_panel(sheet, rect, (22, 29, 34, 255))

    draw_panel(sheet, cell_rect(1, 6, TILE, TILE), (28, 36, 42, 255))

    damaged = cell_rect(2, 6, TILE, TILE)
    pygame.draw.line(sheet, (9, 12, 16, 255), damaged.topleft, damaged.bottomright, 4)
    pygame.draw.line(sheet, CYAN_DIM, (damaged.left + 9, damaged.bottom - 10), (damaged.right - 8, damaged.top + 13), 1)

    wall = cell_rect(3, 6, TILE, TILE)
    pygame.draw.rect(sheet, (60, 68, 73, 255), wall)
    for y in (8, 24, 40):
        pygame.draw.line(sheet, METAL_LIGHT, (wall.left + 4, wall.top + y), (wall.right - 4, wall.top + y), 2)
    pygame.draw.rect(sheet, BLACK, wall, 2)

    broken_wall = cell_rect(4, 6, TILE, TILE)
    pygame.draw.rect(sheet, (54, 61, 66, 255), broken_wall)
    pygame.draw.polygon(
        sheet,
        (20, 22, 25, 255),
        [
            (broken_wall.left + 8, broken_wall.top + 8),
            (broken_wall.left + 30, broken_wall.top + 15),
            (broken_wall.left + 21, broken_wall.top + 36),
            (broken_wall.left + 5, broken_wall.top + 32),
        ],
    )
    pygame.draw.line(sheet, ORANGE, (broken_wall.left + 28, broken_wall.top + 7), (broken_wall.left + 40, broken_wall.top + 38), 2)
    pygame.draw.rect(sheet, BLACK, broken_wall, 2)

    machine = cell_rect(5, 6, TILE, TILE)
    pygame.draw.rect(sheet, (36, 43, 46, 255), machine)
    pygame.draw.rect(sheet, (77, 86, 87, 255), machine.inflate(-10, -8), border_radius=3)
    pygame.draw.circle(sheet, CYAN_DIM, machine.center, 9, 2)
    pygame.draw.rect(sheet, BLACK, machine, 2)

    pillar = cell_rect(6, 6, TILE, TILE)
    draw_panel(sheet, pillar, (18, 22, 27, 255))
    pygame.draw.circle(sheet, (82, 91, 94, 255), pillar.center, 17)
    pygame.draw.circle(sheet, (38, 45, 50, 255), pillar.center, 11)
    pygame.draw.circle(sheet, BLACK, pillar.center, 18, 2)

    doorway = cell_rect(7, 6, TILE, TILE)
    draw_panel(sheet, doorway, (25, 33, 36, 255))
    pygame.draw.rect(sheet, CYAN_DIM, doorway.inflate(-18, -8), 2)

    elevator = cell_rect(8, 6, TILE, TILE)
    draw_panel(sheet, elevator, (31, 40, 42, 255))
    pygame.draw.circle(sheet, CYAN, elevator.center, 13, 2)
    pygame.draw.line(sheet, CYAN_DIM, (elevator.centerx - 16, elevator.centery), (elevator.centerx + 16, elevator.centery), 2)

    containment = cell_rect(9, 6, TILE, TILE)
    draw_panel(sheet, containment, (28, 31, 38, 255))
    pygame.draw.rect(sheet, (23, 92, 105, 255), containment.inflate(-12, -12), 2)
    pygame.draw.circle(sheet, CYAN, containment.center, 5)

    cable = cell_rect(10, 6, TILE, TILE)
    draw_panel(sheet, cable, (20, 27, 31, 255))
    pygame.draw.arc(sheet, CYAN_DIM, cable.inflate(-8, -18), 0.1, 3.1, 3)
    pygame.draw.arc(sheet, ORANGE, cable.inflate(-12, -26), 3.2, 6.1, 2)

    void = cell_rect(11, 6, TILE, TILE)
    pygame.draw.rect(sheet, (2, 3, 6, 255), void)
    pygame.draw.rect(sheet, (8, 10, 15, 255), void.inflate(-8, -8), 1)

    save(sheet, "assets/tiles/industrial_tileset.png")


def draw_player(surface: pygame.Surface, rect: pygame.Rect, direction: str, step: int) -> None:
    foot_shift = [0, -3, 2, -2, 3][step]
    body_color = (42, 115, 128, 255)
    suit_dark = (21, 37, 45, 255)
    visor = CYAN

    center = rect.centerx
    body = pygame.Rect(0, 0, 25, 31)
    body.center = (center, rect.top + 34)
    head = pygame.Rect(0, 0, 22, 18)
    head.center = (center, rect.top + 17)

    if direction == "left":
        head.centerx -= 3
        body.centerx -= 2
        visor_rect = pygame.Rect(head.left + 2, head.top + 6, 9, 5)
    elif direction == "right":
        head.centerx += 3
        body.centerx += 2
        visor_rect = pygame.Rect(head.right - 11, head.top + 6, 9, 5)
    elif direction == "up":
        visor_rect = pygame.Rect(head.left + 5, head.top + 3, 12, 4)
    else:
        visor_rect = pygame.Rect(head.left + 4, head.top + 10, 14, 5)

    pygame.draw.ellipse(surface, (8, 9, 11, 120), (center - 16, rect.bottom - 13, 32, 8))
    pygame.draw.rect(surface, suit_dark, body, border_radius=6)
    pygame.draw.rect(surface, body_color, body.inflate(-8, -6), border_radius=5)
    pygame.draw.rect(surface, suit_dark, head, border_radius=6)
    pygame.draw.rect(surface, visor, visor_rect, border_radius=2)

    left_leg = pygame.Rect(center - 12, rect.top + 48 + foot_shift, 8, 10)
    right_leg = pygame.Rect(center + 4, rect.top + 48 - foot_shift, 8, 10)
    pygame.draw.rect(surface, suit_dark, left_leg, border_radius=2)
    pygame.draw.rect(surface, suit_dark, right_leg, border_radius=2)

    tool = pygame.Rect(center + (12 if direction != "left" else -18), rect.top + 31, 7, 16)
    pygame.draw.rect(surface, (97, 107, 110, 255), tool, border_radius=2)
    pygame.draw.circle(surface, CYAN_DIM, tool.center, 3)


def generate_player_sheet() -> None:
    frame_w, frame_h = 48, 64
    sheet = pygame.Surface((frame_w * 5, frame_h * 4), pygame.SRCALPHA)
    directions = ["down", "left", "right", "up"]
    for row, direction in enumerate(directions):
        for column in range(5):
            draw_player(sheet, cell_rect(row * 5 + column, 5, frame_w, frame_h), direction, column)
    save(sheet, "assets/sprites/player_sheet.png")


def generate_creature_sheet() -> None:
    frame = 64
    sheet = pygame.Surface((frame * 4, frame), pygame.SRCALPHA)
    for i in range(4):
        rect = cell_rect(i, 4, frame, frame)
        cx, cy = rect.center
        pulse = [0, 3, -1, 2][i]
        pygame.draw.ellipse(sheet, (6, 6, 9, 120), (rect.left + 12, rect.top + 46, 40, 9))
        pygame.draw.ellipse(sheet, (63, 36, 48, 255), (cx - 18 - pulse, cy - 15, 36 + pulse * 2, 28))
        pygame.draw.ellipse(sheet, (21, 18, 24, 255), (cx - 11, cy - 9, 22, 16))
        for t in range(5):
            x = cx - 20 + t * 10
            pygame.draw.line(sheet, (91, 63, 77, 255), (x, cy + 2), (x - 8 + pulse, cy + 19 + (t % 2) * 3), 3)
        pygame.draw.circle(sheet, CYAN_DIM, (cx - 6, cy - 4), 3)
        pygame.draw.circle(sheet, CYAN_DIM, (cx + 7, cy - 3), 2)
        pygame.draw.arc(sheet, RED, (cx - 18, cy - 14, 36, 25), 0.2, 2.9, 2)
    save(sheet, "assets/sprites/creature_sheet.png")


def generate_door_sheet(relative_path: str, accent: tuple[int, int, int, int], labels: list[str]) -> None:
    frame_w, frame_h = 96, 96
    sheet = pygame.Surface((frame_w * 4, frame_h), pygame.SRCALPHA)
    openings = [0, 18, 34, 48]
    for i, gap in enumerate(openings):
        rect = cell_rect(i, 4, frame_w, frame_h)
        pygame.draw.rect(sheet, (8, 9, 11, 90), (rect.left + 10, rect.top + 72, 76, 11))
        frame_rect = rect.inflate(-10, -14)
        pygame.draw.rect(sheet, METAL_DARK, frame_rect, border_radius=4)
        pygame.draw.rect(sheet, BLACK, frame_rect, 2, border_radius=4)
        left = pygame.Rect(frame_rect.left + 5, frame_rect.top + 8, max(0, 36 - gap), frame_rect.height - 16)
        right = pygame.Rect(frame_rect.right - 5 - max(0, 36 - gap), frame_rect.top + 8, max(0, 36 - gap), frame_rect.height - 16)
        pygame.draw.rect(sheet, METAL, left, border_radius=3)
        pygame.draw.rect(sheet, METAL, right, border_radius=3)
        pygame.draw.line(sheet, accent, (frame_rect.centerx, frame_rect.top + 12), (frame_rect.centerx, frame_rect.bottom - 12), 3)
        if i == 0 and labels[0] == "locked":
            pygame.draw.circle(sheet, RED, frame_rect.center, 7)
        elif i <= 1:
            pygame.draw.circle(sheet, accent, frame_rect.center, 5)
    save(sheet, relative_path)


def draw_machine_base(surface: pygame.Surface, rect: pygame.Rect, accent: tuple[int, int, int, int]) -> None:
    pygame.draw.ellipse(surface, (5, 6, 8, 110), (rect.left + 10, rect.bottom - 14, rect.width - 20, 8))
    body = rect.inflate(-14, -14)
    pygame.draw.rect(surface, METAL_DARK, body, border_radius=7)
    pygame.draw.rect(surface, METAL, body.inflate(-10, -12), border_radius=5)
    pygame.draw.rect(surface, BLACK, body, 2, border_radius=7)
    pygame.draw.circle(surface, accent, body.center, min(body.width, body.height) // 8)


def generate_object_sheets() -> None:
    component = pygame.Surface((64 * 2, 64), pygame.SRCALPHA)
    for i in range(2):
        rect = cell_rect(i, 2, 64, 64)
        draw_machine_base(component, rect, CYAN if i else CYAN_DIM)
        pygame.draw.line(component, ORANGE, (rect.left + 20, rect.top + 22), (rect.left + 44, rect.top + 42), 3)
    save(component, "assets/objects/generator_component_sheet.png")

    generator = pygame.Surface((96 * 5, 96), pygame.SRCALPHA)
    for i in range(5):
        rect = cell_rect(i, 5, 96, 96)
        accent = RED if i == 0 else ORANGE if i == 1 else CYAN
        draw_machine_base(generator, rect, accent)
        pygame.draw.rect(generator, (25, 29, 31, 255), (rect.left + 25, rect.top + 22, 46, 16), border_radius=3)
        for n in range(3):
            color = accent if i >= 2 and n <= i - 2 else CYAN_DIM
            pygame.draw.circle(generator, color, (rect.left + 34 + n * 14, rect.top + 30), 3)
    save(generator, "assets/objects/generator_sheet.png")

    keycard = pygame.Surface((48 * 2, 48), pygame.SRCALPHA)
    for i in range(2):
        rect = cell_rect(i, 2, 48, 48)
        card = pygame.Rect(rect.left + 8, rect.top + 14, 32, 20)
        pygame.draw.rect(keycard, (29, 39, 42, 255), card, border_radius=4)
        pygame.draw.rect(keycard, CYAN if i else CYAN_DIM, card, 2, border_radius=4)
        pygame.draw.rect(keycard, METAL_LIGHT, (card.left + 6, card.top + 6, 9, 5))
        pygame.draw.line(keycard, CYAN, (card.left + 18, card.top + 14), (card.right - 5, card.top + 14), 1)
    save(keycard, "assets/objects/keycard_sheet.png")

    relay = pygame.Surface((72 * 5, 72), pygame.SRCALPHA)
    for i in range(5):
        rect = cell_rect(i, 5, 72, 72)
        draw_machine_base(relay, rect, CYAN if i == 4 else ORANGE if i > 0 else CYAN_DIM)
        bar_h = 8 + i * 5
        pygame.draw.rect(relay, CYAN if i == 4 else ORANGE, (rect.centerx - 4, rect.bottom - 20 - bar_h, 8, bar_h))
    save(relay, "assets/objects/relay_sheet.png")

    containment_component = pygame.Surface((64 * 2, 64), pygame.SRCALPHA)
    for i in range(2):
        rect = cell_rect(i, 2, 64, 64)
        pygame.draw.polygon(
            containment_component,
            METAL,
            [(rect.centerx, rect.top + 9), (rect.right - 14, rect.centery), (rect.centerx, rect.bottom - 9), (rect.left + 14, rect.centery)],
        )
        pygame.draw.polygon(
            containment_component,
            CYAN if i else CYAN_DIM,
            [(rect.centerx, rect.top + 17), (rect.right - 23, rect.centery), (rect.centerx, rect.bottom - 17), (rect.left + 23, rect.centery)],
            2,
        )
    save(containment_component, "assets/objects/containment_component_sheet.png")

    control = pygame.Surface((72 * 3, 72), pygame.SRCALPHA)
    for i in range(3):
        rect = cell_rect(i, 3, 72, 72)
        draw_machine_base(control, rect, [CYAN_DIM, ORANGE, CYAN][i])
        pygame.draw.rect(control, [CYAN_DIM, ORANGE, CYAN][i], (rect.left + 21, rect.top + 19, 30, 12), 2)
    save(control, "assets/objects/containment_control_sheet.png")

    core = pygame.Surface((72 * 4, 72), pygame.SRCALPHA)
    for i in range(4):
        rect = cell_rect(i, 4, 72, 72)
        radius = 15 + i % 2 * 3
        pygame.draw.circle(core, (18, 44, 52, 150), rect.center, radius + 10)
        pygame.draw.circle(core, CYAN_DIM, rect.center, radius + 5, 2)
        pygame.draw.polygon(
            core,
            CYAN,
            [
                (rect.centerx, rect.centery - radius),
                (rect.centerx + radius, rect.centery),
                (rect.centerx, rect.centery + radius),
                (rect.centerx - radius, rect.centery),
            ],
        )
        pygame.draw.circle(core, (230, 255, 255, 255), rect.center, 5)
    save(core, "assets/objects/echo_core_sheet.png")

    elevator = pygame.Surface((96 * 3, 96), pygame.SRCALPHA)
    for i in range(3):
        rect = cell_rect(i, 3, 96, 96)
        pygame.draw.ellipse(elevator, (4, 5, 7, 120), (rect.left + 14, rect.top + 74, 68, 10))
        pygame.draw.rect(elevator, METAL_DARK, (rect.left + 14, rect.top + 18, 68, 58), border_radius=5)
        pygame.draw.rect(elevator, METAL, (rect.left + 23, rect.top + 26, 50, 42), border_radius=4)
        color = RED if i == 0 else CYAN_DIM if i == 1 else CYAN
        pygame.draw.circle(elevator, color, (rect.centerx, rect.top + 47), 14, 2)
        pygame.draw.line(elevator, color, (rect.centerx - 18, rect.top + 47), (rect.centerx + 18, rect.top + 47), 2)
    save(elevator, "assets/objects/elevator_sheet.png")


def generate_materials() -> None:
    sheet = pygame.Surface((48 * 2, 48 * 3), pygame.SRCALPHA)
    for row, name in enumerate(("scrap", "circuit", "power_cell")):
        for frame in range(2):
            rect = cell_rect(row * 2 + frame, 2, 48, 48)
            if name == "scrap":
                pygame.draw.polygon(sheet, METAL, [(rect.left + 12, rect.top + 17), (rect.left + 31, rect.top + 11), (rect.left + 38, rect.top + 30), (rect.left + 18, rect.top + 36)])
                pygame.draw.line(sheet, METAL_LIGHT, (rect.left + 17, rect.top + 23), (rect.left + 34, rect.top + 18), 2)
            elif name == "circuit":
                pygame.draw.rect(sheet, (30, 88, 75, 255), (rect.left + 11, rect.top + 13, 26, 22), border_radius=3)
                for x in range(15, 36, 8):
                    pygame.draw.line(sheet, CYAN, (rect.left + x, rect.top + 15), (rect.left + x, rect.top + 33), 1)
                pygame.draw.circle(sheet, CYAN if frame else CYAN_DIM, (rect.left + 24, rect.top + 24), 4)
            else:
                pygame.draw.rect(sheet, METAL_DARK, (rect.left + 16, rect.top + 9, 16, 31), border_radius=5)
                pygame.draw.rect(sheet, CYAN if frame else CYAN_DIM, (rect.left + 19, rect.top + 15, 10, 18), border_radius=3)
                pygame.draw.rect(sheet, METAL_LIGHT, (rect.left + 18, rect.top + 6, 12, 5), border_radius=2)
    save(sheet, "assets/objects/materials_sheet.png")


def draw_icon_base(surface: pygame.Surface, disabled: bool = False) -> None:
    rect = surface.get_rect()
    pygame.draw.rect(surface, (16, 24, 31, 255), rect, border_radius=6)
    pygame.draw.rect(surface, CYAN_DIM if not disabled else METAL, rect.inflate(-3, -3), 2, border_radius=5)
    if disabled:
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill((5, 5, 8, 135))
        surface.blit(overlay, (0, 0))


def save_icon(name: str, drawer, disabled: bool = False) -> None:
    surface = pygame.Surface((48, 48), pygame.SRCALPHA)
    draw_icon_base(surface, disabled)
    drawer(surface, disabled)
    save(surface, f"assets/ui/{name}.png")


def generate_icons() -> None:
    def shock(s: pygame.Surface, disabled: bool) -> None:
        color = METAL_LIGHT if disabled else CYAN
        pygame.draw.circle(s, color, (24, 24), 13, 3)
        pygame.draw.line(s, color, (16, 25), (24, 10), 3)
        pygame.draw.line(s, color, (24, 10), (31, 25), 3)

    def beacon(s: pygame.Surface, disabled: bool) -> None:
        color = METAL_LIGHT if disabled else CYAN
        pygame.draw.rect(s, color, (19, 20, 10, 17), border_radius=3)
        pygame.draw.arc(s, color, (12, 9, 24, 25), 3.7, 5.7, 2)
        pygame.draw.arc(s, color, (7, 5, 34, 34), 3.7, 5.7, 2)

    def wedge(s: pygame.Surface, disabled: bool) -> None:
        color = METAL_LIGHT if disabled else ORANGE
        pygame.draw.polygon(s, color, [(13, 33), (36, 18), (36, 35)])
        pygame.draw.rect(s, METAL, (11, 14, 8, 24), border_radius=2)

    def projector(s: pygame.Surface, disabled: bool) -> None:
        color = METAL_LIGHT if disabled else CYAN
        pygame.draw.rect(s, METAL, (12, 23, 18, 12), border_radius=3)
        pygame.draw.polygon(s, color, [(29, 18), (42, 13), (42, 40), (29, 35)], 2)

    for base, drawer in (
        ("shock_pulse", shock),
        ("decoy_beacon", beacon),
        ("door_wedge", wedge),
        ("scan_projector", projector),
    ):
        save_icon(f"{base}_ready", drawer, False)
        save_icon(f"{base}_cooldown", drawer, True)

    save_icon("scan_ready", lambda s, d: pygame.draw.circle(s, CYAN, (24, 24), 14, 2), False)
    save_icon("scan_cooldown", lambda s, d: pygame.draw.circle(s, METAL_LIGHT, (24, 24), 14, 2), True)
    save_icon("scrap", lambda s, d: pygame.draw.polygon(s, METAL_LIGHT, [(14, 18), (34, 12), (38, 31), (18, 36)]), False)
    save_icon("circuit", lambda s, d: pygame.draw.rect(s, CYAN_DIM, (14, 15, 20, 18), border_radius=3), False)
    save_icon("power_cell", lambda s, d: pygame.draw.rect(s, CYAN, (19, 11, 10, 27), border_radius=3), False)
    save_icon("score", lambda s, d: pygame.draw.circle(s, ORANGE, (24, 24), 12, 3), False)
    save_icon("floor", lambda s, d: pygame.draw.rect(s, METAL_LIGHT, (14, 13, 20, 23), 3), False)


def generate_effects() -> None:
    pulse = pygame.Surface((64 * 4, 64), pygame.SRCALPHA)
    for i in range(4):
        rect = cell_rect(i, 4, 64, 64)
        pygame.draw.circle(pulse, (71, 226, 240, max(60, 220 - i * 45)), rect.center, 10 + i * 7, 2)
    save(pulse, "assets/effects/scan_origin_pulse_sheet.png")

    effects = {
        "scan_point": lambda s: pygame.draw.circle(s, CYAN, (16, 16), 3),
        "shock_pulse_ring": lambda s: pygame.draw.circle(s, CYAN, (32, 32), 25, 3),
        "beacon_pulse": lambda s: pygame.draw.arc(s, CYAN, (10, 8, 44, 44), 3.8, 5.7, 3),
        "projector_activation": lambda s: pygame.draw.polygon(s, CYAN, [(12, 20), (54, 8), (54, 56), (12, 44)], 2),
        "material_pickup": lambda s: pygame.draw.circle(s, ORANGE, (24, 24), 13, 2),
        "objective_activation": lambda s: pygame.draw.rect(s, CYAN, (12, 12, 40, 40), 3, border_radius=4),
        "creature_warning": lambda s: pygame.draw.polygon(s, RED, [(32, 8), (56, 52), (8, 52)], 3),
    }
    for name, drawer in effects.items():
        size = (32, 32) if name == "scan_point" else (64, 64)
        surface = pygame.Surface(size, pygame.SRCALPHA)
        drawer(surface)
        if name == "creature_warning":
            pygame.draw.line(surface, RED, (32, 22), (32, 37), 3)
            pygame.draw.circle(surface, RED, (32, 45), 2)
        save(surface, f"assets/effects/{name}.png")


def main() -> int:
    pygame.init()
    ensure_dirs()
    generate_tileset()
    generate_player_sheet()
    generate_creature_sheet()
    generate_door_sheet("assets/objects/powered_door_sheet.png", CYAN, ["closed", "opening", "opening", "open"])
    generate_door_sheet("assets/objects/security_door_sheet.png", ORANGE, ["locked", "unlocked", "opening", "open"])
    generate_door_sheet("assets/objects/containment_door_sheet.png", CYAN, ["locked", "powered", "opening", "open"])
    generate_object_sheets()
    generate_materials()
    generate_icons()
    generate_effects()
    pygame.quit()
    print("Generated placeholder assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
