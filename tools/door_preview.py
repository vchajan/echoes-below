from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview Echoes Below dynamic doors and blockers.")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--floor", type=int, default=2)
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
from game.entities.door import DoorState, DoorType, DynamicDoor
from game.entities.player import Player, movement_direction_from_bools
from game.world import collision
from game.world.blockers import BlockerPurpose
from game.world.door_generation import create_doors_for_floor
from game.world.generator import FloorGenerator
from game.world.rendering import (
    StaticWorldRenderer,
    apply_darkness,
    build_local_glow_surface,
    draw_camera_debug_overlay,
    draw_door_debug_overlay,
    draw_doors,
)


def create_session(seed: int, floor_number: int):
    assets = AssetManager(audio_available=False)
    generated_floor = FloorGenerator().generate(seed=seed, floor_number=floor_number)
    player = Player(generated_floor.player_spawn, assets, settings.TILE_SIZE)
    camera = Camera(settings.WINDOW_SIZE, generated_floor.world_size_pixels(settings.TILE_SIZE))
    camera.update(player.world_position)
    renderer = StaticWorldRenderer(assets, settings.TILE_SIZE)
    renderer.build_for_floor(generated_floor)
    door_result = create_doors_for_floor(generated_floor, assets, settings.TILE_SIZE)
    return {
        "assets": assets,
        "floor": generated_floor,
        "player": player,
        "camera": camera,
        "renderer": renderer,
        "doors": door_result.doors,
        "blockers": door_result.blockers,
        "power": True,
    }


def nearest_door(session: dict[str, object], door_type: DoorType | None = None) -> DynamicDoor | None:
    player: Player = session["player"]  # type: ignore[assignment]
    doors: list[DynamicDoor] = session["doors"]  # type: ignore[assignment]
    candidates = [door for door in doors if door_type is None or door.door_type is door_type]
    if not candidates:
        return None
    return min(candidates, key=lambda door: door.world_center.distance_squared_to(player.world_position))


def tile_rect(tile: tuple[int, int]) -> pygame.Rect:
    return collision.tile_to_world_rect(tile[0], tile[1], settings.TILE_SIZE)


def approach_tile_for_door(session: dict[str, object], door: DynamicDoor) -> tuple[int, int]:
    generated_floor = session["floor"]
    candidates = (
        [(door.tile[0] - 1, door.tile[1]), (door.tile[0] + 1, door.tile[1])]
        if door.orientation == "vertical_door_plane"
        else [(door.tile[0], door.tile[1] - 1), (door.tile[0], door.tile[1] + 1)]
    )
    for tile in candidates:
        if generated_floor.is_walkable(*tile) and door.approach_rect.colliderect(tile_rect(tile)):
            return tile
    for tile in generated_floor.walkable_tiles():
        if tile != door.tile and door.approach_rect.colliderect(tile_rect(tile)):
            return tile
    return generated_floor.player_spawn


def place_player_at(session: dict[str, object], tile: tuple[int, int]) -> None:
    player: Player = session["player"]  # type: ignore[assignment]
    camera: Camera = session["camera"]  # type: ignore[assignment]
    player.place_at_tile(tile)
    camera.update(player.world_position)


def update_session(session: dict[str, object], dt: float, direction: pygame.Vector2) -> None:
    generated_floor = session["floor"]
    player: Player = session["player"]  # type: ignore[assignment]
    camera: Camera = session["camera"]  # type: ignore[assignment]
    doors: list[DynamicDoor] = session["doors"]  # type: ignore[assignment]
    blockers = session["blockers"]
    power: bool = session["power"]  # type: ignore[assignment]

    for door in doors:
        door.update(dt, player.collision_rect, floor_powered=power)
    player.update(direction, dt, generated_floor, blockers)
    camera.update(player.world_position, dt)


def draw_scene(
    surface: pygame.Surface,
    session: dict[str, object],
    darkness_surface: pygame.Surface,
    glow_surface: pygame.Surface,
    font: pygame.font.Font,
    debug: bool,
) -> None:
    generated_floor = session["floor"]
    player: Player = session["player"]  # type: ignore[assignment]
    camera: Camera = session["camera"]  # type: ignore[assignment]
    renderer: StaticWorldRenderer = session["renderer"]  # type: ignore[assignment]
    doors: list[DynamicDoor] = session["doors"]  # type: ignore[assignment]
    power: bool = session["power"]  # type: ignore[assignment]

    renderer.render_view(surface, generated_floor, camera)
    draw_doors(surface, doors, camera)
    player_screen_rect = camera.world_rect_to_screen(player.visual_rect)

    if debug:
        surface.blit(player.image, player_screen_rect)
        draw_camera_debug_overlay(surface, generated_floor, camera, settings.TILE_SIZE, font, player)
        draw_door_debug_overlay(surface, doors, camera, font)
    else:
        apply_darkness(surface, darkness_surface, glow_surface, player_screen_rect.center)
        surface.blit(player.image, player_screen_rect)

    lines = [
        f"Seed {generated_floor.seed} | Floor {generated_floor.floor_number}",
        f"Doors {len(doors)} | Power {'ON' if power else 'OFF'} | F2 {'ON' if debug else 'OFF'}",
        "F6 nearest door | F7 nearest locked door | F8 power",
    ]
    for index, line in enumerate(lines):
        color = settings.COLOR_TEXT if index == 0 else settings.COLOR_TEXT_MUTED
        surface.blit(font.render(line, True, color), (16, 16 + index * 24))


def run_headless() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1))
    session = create_session(args.seed, args.floor)
    surface = pygame.Surface(settings.WINDOW_SIZE).convert()
    darkness = pygame.Surface(settings.WINDOW_SIZE, pygame.SRCALPHA)
    glow = build_local_glow_surface(settings.LOCAL_VISIBILITY_RADIUS)
    font = pygame.font.SysFont("consolas", settings.FONT_SMALL_SIZE)

    doors: list[DynamicDoor] = session["doors"]  # type: ignore[assignment]
    powered_door = next(door for door in doors if door.door_type is DoorType.POWERED)
    place_player_at(session, approach_tile_for_door(session, powered_door))

    artifacts = PROJECT_ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    closed_path = artifacts / f"door_preview_{args.seed}_floor{args.floor}_closed.png"
    open_path = artifacts / f"door_preview_{args.seed}_floor{args.floor}_open.png"

    draw_scene(surface, session, darkness, glow, font, debug=True)
    pygame.image.save(surface, str(closed_path))
    assert session["blockers"].blocks_tile(*powered_door.tile, BlockerPurpose.MOVEMENT)

    for _ in range(90):
        update_session(session, 1.0 / settings.FPS, pygame.Vector2(0, 0))
        if powered_door.state is DoorState.OPEN:
            break
    assert powered_door.state is DoorState.OPEN
    assert not session["blockers"].blocks_tile(*powered_door.tile, BlockerPurpose.MOVEMENT)

    draw_scene(surface, session, darkness, glow, font, debug=True)
    pygame.image.save(surface, str(open_path))

    print(f"door_closed_preview: {closed_path}")
    print(f"door_open_preview: {open_path}")
    print(f"doors: {[(door.door_id, door.door_type.value, door.state.value) for door in doors]}")
    pygame.quit()
    return 0


def run_interactive() -> int:
    pygame.init()
    screen = pygame.display.set_mode(settings.WINDOW_SIZE)
    pygame.display.set_caption("Echoes Below Door Preview")
    clock = pygame.time.Clock()
    session = create_session(args.seed, args.floor)
    darkness = pygame.Surface(settings.WINDOW_SIZE, pygame.SRCALPHA)
    glow = build_local_glow_surface(settings.LOCAL_VISIBILITY_RADIUS)
    font = pygame.font.SysFont("consolas", settings.FONT_SMALL_SIZE)
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
                elif debug and event.key == pygame.K_F6:
                    door = nearest_door(session)
                    if door is not None:
                        door.debug_toggle_open_closed()
                elif debug and event.key == pygame.K_F7:
                    door = nearest_door(session, DoorType.SECURITY) or nearest_door(session, DoorType.CONTAINMENT)
                    if door is not None:
                        if door.is_locked:
                            door.unlock()
                        else:
                            door.lock()
                elif debug and event.key == pygame.K_F8:
                    session["power"] = not session["power"]
                    for door in session["doors"]:
                        door.set_powered(session["power"])

        keys = pygame.key.get_pressed()
        direction = movement_direction_from_bools(
            keys[pygame.K_w] or keys[pygame.K_UP],
            keys[pygame.K_s] or keys[pygame.K_DOWN],
            keys[pygame.K_a] or keys[pygame.K_LEFT],
            keys[pygame.K_d] or keys[pygame.K_RIGHT],
        )
        update_session(session, dt, direction)
        draw_scene(screen, session, darkness, glow, font, debug)
        pygame.display.flip()

    pygame.quit()
    return 0


def main() -> int:
    if args.headless:
        return run_headless()
    return run_interactive()


if __name__ == "__main__":
    raise SystemExit(main())
