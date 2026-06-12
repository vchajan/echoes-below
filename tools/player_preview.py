from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview Echoes Below player movement and camera.")
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

from game import settings
from game.assets import AssetManager
from game.camera import Camera
from game.entities.player import Player, movement_direction_from_bools
from game.world.generator import FloorGenerator
from game.world.rendering import (
    StaticWorldRenderer,
    apply_darkness,
    build_local_glow_surface,
    draw_camera_debug_overlay,
)


def create_session(seed: int, floor_number: int) -> tuple[object, Player, Camera, StaticWorldRenderer, AssetManager]:
    assets = AssetManager(audio_available=False)
    generator = FloorGenerator()
    generated_floor = generator.generate(seed=seed, floor_number=floor_number)
    player = Player(generated_floor.player_spawn, assets, settings.TILE_SIZE)
    camera = Camera(settings.WINDOW_SIZE, generated_floor.world_size_pixels(settings.TILE_SIZE))
    camera.update(player.world_position)
    renderer = StaticWorldRenderer(assets, settings.TILE_SIZE)
    renderer.build_for_floor(generated_floor)
    return generated_floor, player, camera, renderer, assets


def draw_scene(
    surface: pygame.Surface,
    generated_floor,
    player: Player,
    camera: Camera,
    renderer: StaticWorldRenderer,
    darkness_surface: pygame.Surface,
    glow_surface: pygame.Surface,
    font: pygame.font.Font,
    debug: bool,
) -> None:
    renderer.render_view(surface, generated_floor, camera)
    player_screen_rect = camera.world_rect_to_screen(player.visual_rect)

    if debug:
        surface.blit(player.image, player_screen_rect)
        draw_camera_debug_overlay(surface, generated_floor, camera, settings.TILE_SIZE, font, player)
    else:
        apply_darkness(surface, darkness_surface, glow_surface, player_screen_rect.center)
        surface.blit(player.image, player_screen_rect)

    lines = [
        f"Seed {generated_floor.seed} | Floor {generated_floor.floor_number}",
        f"Position ({player.world_position.x:0.1f}, {player.world_position.y:0.1f})",
        f"Tile {player.current_tile} | F2 Debug {'ON' if debug else 'OFF'}",
    ]
    for index, line in enumerate(lines):
        image = font.render(line, True, settings.COLOR_TEXT if index == 0 else settings.COLOR_TEXT_MUTED)
        surface.blit(image, (16, 16 + index * 24))


def movement_options(generated_floor, tile: tuple[int, int]) -> list[pygame.Vector2]:
    options: list[pygame.Vector2] = []
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        if generated_floor.is_walkable(tile[0] + dx, tile[1] + dy):
            options.append(pygame.Vector2(dx, dy))
    return options or [pygame.Vector2(1, 0)]


def simulate_sequence(generated_floor, player: Player, camera: Camera) -> None:
    sequence = movement_options(generated_floor, player.current_tile)[:2]
    if len(sequence) == 1:
        sequence.append(sequence[0].rotate(90))

    for direction in sequence:
        for _ in range(36):
            player.update(direction, 1.0 / settings.FPS, generated_floor)
            camera.update(player.world_position)


def run_headless() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1))
    generated_floor, player, camera, renderer, _ = create_session(args.seed, args.floor)
    font = pygame.font.SysFont("consolas", settings.FONT_SMALL_SIZE)
    surface = pygame.Surface(settings.WINDOW_SIZE).convert()
    darkness = pygame.Surface(settings.WINDOW_SIZE, pygame.SRCALPHA)
    glow = build_local_glow_surface(settings.LOCAL_VISIBILITY_RADIUS)

    artifacts = PROJECT_ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    start_path = artifacts / f"player_preview_{args.seed}_start.png"
    moved_path = artifacts / f"player_preview_{args.seed}_moved.png"

    draw_scene(surface, generated_floor, player, camera, renderer, darkness, glow, font, debug=True)
    pygame.image.save(surface, str(start_path))
    simulate_sequence(generated_floor, player, camera)
    draw_scene(surface, generated_floor, player, camera, renderer, darkness, glow, font, debug=True)
    pygame.image.save(surface, str(moved_path))

    print(f"player_start_preview: {start_path}")
    print(f"player_moved_preview: {moved_path}")
    print(f"final_position: ({player.world_position.x:0.2f}, {player.world_position.y:0.2f})")
    print(f"final_tile: {player.current_tile}")
    pygame.quit()
    return 0


def run_interactive() -> int:
    pygame.init()
    screen = pygame.display.set_mode(settings.WINDOW_SIZE)
    pygame.display.set_caption("Echoes Below Player Preview")
    clock = pygame.time.Clock()
    generated_floor, player, camera, renderer, _ = create_session(args.seed, args.floor)
    font = pygame.font.SysFont("consolas", settings.FONT_SMALL_SIZE)
    darkness = pygame.Surface(settings.WINDOW_SIZE, pygame.SRCALPHA)
    glow = build_local_glow_surface(settings.LOCAL_VISIBILITY_RADIUS)
    debug = False
    running = True

    while running:
        dt = min(clock.tick(settings.FPS) / 1000.0, settings.MAX_DELTA_TIME)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_F2:
                    debug = not debug

        keys = pygame.key.get_pressed()
        direction = movement_direction_from_bools(
            keys[pygame.K_w] or keys[pygame.K_UP],
            keys[pygame.K_s] or keys[pygame.K_DOWN],
            keys[pygame.K_a] or keys[pygame.K_LEFT],
            keys[pygame.K_d] or keys[pygame.K_RIGHT],
        )
        player.update(direction, dt, generated_floor)
        camera.update(player.world_position, dt)
        draw_scene(screen, generated_floor, player, camera, renderer, darkness, glow, font, debug)
        pygame.display.flip()

    pygame.quit()
    return 0


def main() -> int:
    if args.headless:
        return run_headless()
    return run_interactive()


if __name__ == "__main__":
    raise SystemExit(main())
