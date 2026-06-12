from __future__ import annotations

import os
import sys
from pathlib import Path

if "--headless" in sys.argv:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pygame

from game.assets import EFFECT_IMAGE_PATHS, MODULE_ICON_PATHS, AssetManager


def draw_label(surface: pygame.Surface, font: pygame.font.Font, text: str, pos: tuple[int, int]) -> None:
    image = font.render(text, True, (225, 236, 232))
    surface.blit(image, pos)


def blit_row(
    surface: pygame.Surface,
    frames: list[pygame.Surface],
    start: tuple[int, int],
    max_count: int | None = None,
    gap: int = 8,
) -> int:
    x, y = start
    count = max_count or len(frames)
    for frame in frames[:count]:
        surface.blit(frame, (x, y))
        x += frame.get_width() + gap
    return x


def build_preview(manager: AssetManager) -> pygame.Surface:
    preview = pygame.Surface((1180, 980), pygame.SRCALPHA)
    preview.fill((8, 11, 18, 255))
    font = pygame.font.SysFont("consolas", 22, bold=True)

    y = 24
    draw_label(preview, font, "Tiles", (24, y))
    blit_row(preview, manager.get_sheet_frames("industrial_tiles"), (24, y + 34), max_count=12)

    y += 110
    draw_label(preview, font, "Player frames and outlines", (24, y))
    player_frames = manager.get_frames("player", "walk_down") + manager.get_frames("player", "walk_right")
    player_outlines = manager.get_outline_frames("player", "walk_down") + manager.get_outline_frames("player", "walk_right")
    blit_row(preview, player_frames, (24, y + 34))
    blit_row(preview, player_outlines, (24, y + 105))

    y += 185
    draw_label(preview, font, "Creature frames and outlines", (24, y))
    blit_row(preview, manager.get_frames("creature", "move"), (24, y + 34))
    blit_row(preview, manager.get_outline_frames("creature", "move"), (320, y + 34))

    y += 120
    draw_label(preview, font, "Doors and objectives", (24, y))
    x = blit_row(
        preview,
        [
            manager.get_frames("powered_door", "closed")[0],
            manager.get_frames("security_door", "locked")[0],
            manager.get_frames("containment_door", "powered")[0],
        ],
        (24, y + 34),
    )
    x += 18
    objective_samples = []
    for sheet_name, animation_name in (
        ("generator_component", "pulse"),
        ("generator", "powered"),
        ("keycard", "glow"),
        ("relay", "active"),
        ("containment_component", "pulse"),
        ("containment_control", "active"),
        ("echo_core", "pulse"),
        ("elevator", "unlocked"),
    ):
        objective_samples.append(manager.get_frames(sheet_name, animation_name)[0])
    blit_row(preview, objective_samples, (x, y + 34), gap=10)

    y += 140
    draw_label(preview, font, "Object outlines", (24, y))
    outline_samples = []
    for sheet_name in (
        "powered_door",
        "generator",
        "relay",
        "echo_core",
        "elevator",
    ):
        outline_samples.append(manager.get_outline_frames(sheet_name)[0])
    blit_row(preview, outline_samples, (24, y + 34), gap=12)

    y += 140
    draw_label(preview, font, "Materials and module icons", (24, y))
    blit_row(preview, manager.get_sheet_frames("materials"), (24, y + 34))
    x = 370
    for icon_name in (
        "shock_pulse_ready",
        "decoy_beacon_ready",
        "door_wedge_ready",
        "scan_projector_ready",
        "scan_ready",
        "scrap",
        "circuit",
        "power_cell",
        "score",
        "floor",
    ):
        icon = manager.load_image(MODULE_ICON_PATHS[icon_name], (48, 48))
        preview.blit(icon, (x, y + 34))
        preview.blit(manager.get_outline_image(MODULE_ICON_PATHS[icon_name], (48, 48)), (x, y + 88))
        x += 56

    y += 170
    draw_label(preview, font, "Effects", (24, y))
    x = blit_row(preview, manager.get_sheet_frames("scan_origin_pulse"), (24, y + 34))
    for effect_name, path in EFFECT_IMAGE_PATHS.items():
        size = (32, 32) if effect_name == "scan_point" else (64, 64)
        effect = manager.load_image(path, size)
        preview.blit(effect, (x, y + 34))
        x += effect.get_width() + 10

    return preview


def main() -> int:
    headless = "--headless" in sys.argv
    pygame.init()
    if headless:
        pygame.display.set_mode((1, 1))
    else:
        pygame.display.set_mode((1180, 980))
        pygame.display.set_caption("Echoes Below Asset Preview")

    manager = AssetManager()
    preview = build_preview(manager)

    artifacts = PROJECT_ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    output_path = artifacts / "asset_preview.png"
    pygame.image.save(preview, str(output_path))
    print(f"Saved asset preview to {output_path}")

    if not headless:
        screen = pygame.display.get_surface()
        assert screen is not None
        clock = pygame.time.Clock()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                    running = False
            screen.blit(preview, (0, 0))
            pygame.display.flip()
            clock.tick(30)

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
