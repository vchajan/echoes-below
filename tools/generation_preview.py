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
    report = generated_floor.validation_report
    title = font.render(
        f"Seed {seed} | Floor {floor_number} | Attempt {generated_floor.generation_attempt} | "
        f"Rooms {len(generated_floor.rooms)} | Edges {len(generated_floor.graph_edges)} | "
        f"Cycle {report.graph_cycle_rank if report else '?'}",
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

    report = generated_floor.validation_report
    print(f"base_seed: {generated_floor.seed}")
    print(f"attempt_index: {generated_floor.generation_attempt}")
    print(f"attempt_seed: {generated_floor.attempt_seed}")
    print(f"floor: {generated_floor.floor_number}")
    print(f"dimensions: {generated_floor.width}x{generated_floor.height}")
    print(f"rooms: {len(generated_floor.rooms)}")
    print(f"graph_edges: {len(generated_floor.graph_edges)}")
    if report is not None:
        print(f"cycle_rank: {report.graph_cycle_rank}")
        print(f"walkable_tiles: {report.total_walkable_tiles}")
        print(f"reachable_walkable_tiles: {report.reachable_walkable_tiles}")
        print(f"connectivity_ratio: {report.connectivity_ratio:0.3f}")
        print(f"minimum_spawn_distance: {report.minimum_spawn_distance}")
        print(f"validation_warnings: {report.warnings}")
    print(f"player_spawn: {generated_floor.player_spawn}")
    print(f"elevator: {generated_floor.elevator_tile}")
    print(f"elevator_approach_tiles: {generated_floor.elevator_approach_tiles}")
    print(f"creature_spawn_candidates: {generated_floor.candidate_creature_spawns}")
    print(f"objective_room_groups: {generated_floor.objective_room_groups}")
    print(f"material_room_candidates: {generated_floor.candidate_material_rooms}")
    print(f"gate_edge_candidates: {[gate.edge for gate in generated_floor.gate_candidates]}")
    print(f"containment_room_candidates: {generated_floor.containment_room_candidates}")
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
