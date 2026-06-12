from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview a generated Echoes Below floor.")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--floor", type=int, default=1)
    parser.add_argument("--headless", action="store_true")
    return parser.parse_args()


args = parse_args()
if args.headless:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pygame

from game.assets import AssetManager
from game.world.generator import FloorGenerator
from game.world.rendering import draw_debug_overlay, render_floor_surface, scale_floor_surface


def build_preview(seed: int, floor_number: int) -> tuple[pygame.Surface, object, pygame.Rect]:
    generator = FloorGenerator()
    generated_floor = generator.generate(seed=seed, floor_number=floor_number)
    config = generator.config_for_floor(floor_number)
    assets = AssetManager()
    world_surface = render_floor_surface(generated_floor, assets, config.tile_size)
    overview, _ = scale_floor_surface(world_surface, (1120, 800))

    preview = pygame.Surface((1180, 900)).convert()
    preview.fill((8, 11, 18))
    rect = overview.get_rect(center=(590, 470))
    preview.blit(overview, rect)

    font = pygame.font.SysFont("consolas", 20, bold=True)
    title = font.render(
        f"Seed {seed} | Floor {floor_number} | {generated_floor.width}x{generated_floor.height} | "
        f"Rooms {len(generated_floor.rooms)} | Edges {len(generated_floor.graph_edges)}",
        True,
        (225, 236, 232),
    )
    preview.blit(title, (24, 24))
    draw_debug_overlay(preview, generated_floor, rect, font)
    return preview, generated_floor, rect


def main() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1) if args.headless else (1180, 900))
    pygame.display.set_caption("Echoes Below Generation Preview")

    preview, generated_floor, _ = build_preview(args.seed, args.floor)
    artifacts = PROJECT_ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    output_path = artifacts / f"generation_preview_{args.seed}_floor{args.floor}.png"
    pygame.image.save(preview, str(output_path))

    print(f"seed: {generated_floor.seed}")
    print(f"floor: {generated_floor.floor_number}")
    print(f"dimensions: {generated_floor.width}x{generated_floor.height}")
    print(f"rooms: {len(generated_floor.rooms)}")
    print(f"graph_edges: {len(generated_floor.graph_edges)}")
    print(f"player_spawn: {generated_floor.player_spawn}")
    print(f"elevator: {generated_floor.elevator_tile}")
    print(f"preview: {output_path}")

    if not args.headless:
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
