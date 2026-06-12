import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pygame

from game import settings
from game.app import Game
from game.entities.door import DoorState, DoorType, DynamicDoor
from game.states import GameState
from game.systems.raycasting import has_line_of_sight
from game.world import collision
from game.world.blockers import BlockerPurpose


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def step_gameplay(game: Game, direction: pygame.Vector2, frames: int = 20) -> None:
    for _ in range(frames):
        game.update_gameplay(1.0 / settings.FPS, direction)


def movement_directions_from_spawn(game: Game) -> list[pygame.Vector2]:
    require(game.placeholder_run is not None, "Run was not created.")
    floor = game.placeholder_run.generated_floor
    require(floor is not None, "Floor was not generated.")
    require(game.player is not None, "Player was not created.")

    tile_x, tile_y = game.player.current_tile
    directions: list[pygame.Vector2] = []
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        if floor.is_walkable(tile_x + dx, tile_y + dy):
            directions.append(pygame.Vector2(dx, dy))
    return directions


def find_walkable_tile_next_to_blocker(game: Game) -> tuple[tuple[int, int], pygame.Vector2, pygame.Rect]:
    require(game.placeholder_run is not None, "Run was not created.")
    floor = game.placeholder_run.generated_floor
    require(floor is not None, "Floor was not generated.")

    for y in range(floor.height):
        for x in range(floor.width):
            if not floor.is_walkable(x, y):
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                blocker_x = x + dx
                blocker_y = y + dy
                if collision.is_blocking_tile(floor, blocker_x, blocker_y):
                    return (
                        (x, y),
                        pygame.Vector2(dx, dy),
                        collision.tile_to_world_rect(blocker_x, blocker_y, settings.TILE_SIZE),
                    )
    raise AssertionError("Could not find a walkable tile next to a blocker.")




def find_scan_tile_for_creature(game: Game, creature) -> tuple[int, int]:
    require(game.placeholder_run is not None, "Run was not created.")
    floor = game.placeholder_run.generated_floor
    require(floor is not None, "Floor was not generated.")
    for tile in floor.walkable_tiles():
        if tile == creature.current_tile:
            continue
        origin = pygame.Vector2(
            (tile[0] + 0.5) * settings.TILE_SIZE,
            (tile[1] + 0.5) * settings.TILE_SIZE,
        )
        distance = origin.distance_to(creature.scan_position)
        if not (settings.TILE_SIZE * 1.5 <= distance <= settings.SCAN_MAX_RADIUS * 0.6):
            continue
        if has_line_of_sight(
            origin,
            creature.scan_position,
            floor,
            game.dynamic_blockers,
            settings.TILE_SIZE,
        ):
            return tile
    raise AssertionError("Could not find a visible scan tile for the creature.")


def find_powered_door(game: Game) -> DynamicDoor:
    for door in game.doors:
        if door.door_type is DoorType.POWERED:
            return door
    raise AssertionError("No powered door exists in the generated session.")


def tile_rect(tile: tuple[int, int]) -> pygame.Rect:
    return collision.tile_to_world_rect(tile[0], tile[1], settings.TILE_SIZE)


def approach_tile_for_door(game: Game, door: DynamicDoor) -> tuple[int, int]:
    require(game.placeholder_run is not None, "Run was not created.")
    floor = game.placeholder_run.generated_floor
    require(floor is not None, "Floor was not generated.")

    candidates = (
        [(door.tile[0] - 1, door.tile[1]), (door.tile[0] + 1, door.tile[1])]
        if door.orientation == "vertical_door_plane"
        else [(door.tile[0], door.tile[1] - 1), (door.tile[0], door.tile[1] + 1)]
    )
    for tile in candidates:
        if floor.is_walkable(*tile) and door.approach_rect.colliderect(tile_rect(tile)):
            return tile
    for tile in floor.walkable_tiles():
        if tile != door.tile and door.approach_rect.colliderect(tile_rect(tile)):
            return tile
    raise AssertionError("Could not find a walkable approach tile for the door.")


def clear_tile_for_door(game: Game, door: DynamicDoor) -> tuple[int, int]:
    require(game.placeholder_run is not None, "Run was not created.")
    floor = game.placeholder_run.generated_floor
    require(floor is not None, "Floor was not generated.")
    for tile in floor.walkable_tiles():
        rect = tile_rect(tile)
        if tile != door.tile and not door.approach_rect.colliderect(rect) and not door.collision_rect.colliderect(rect):
            return tile
    raise AssertionError("Could not find a clear tile away from the door.")


def place_player_at(game: Game, tile: tuple[int, int]) -> None:
    require(game.player is not None, "Player was not created.")
    require(game.camera is not None, "Camera was not created.")
    game.player.place_at_tile(tile)
    game.camera.update(game.player.world_position)


def advance_until(game: Game, predicate, frames: int = 120) -> None:
    for _ in range(frames):
        game.update_gameplay(1.0 / settings.FPS, pygame.Vector2(0, 0))
        if predicate():
            return
    raise AssertionError("Timed out waiting for expected gameplay condition.")


def main() -> int:
    game = Game()
    try:
        require(game.state == GameState.SPLASH, "Application did not start on splash.")

        frames = int(settings.SPLASH_DURATION * settings.FPS) + 5
        for _ in range(frames):
            game.run_one_frame(1.0 / settings.FPS)
        require(game.state == GameState.MAIN_MENU, "Splash did not transition to main menu.")

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        game.run_one_frame(1.0 / settings.FPS)
        require(game.state == GameState.PLAYING, "New Run did not enter PLAYING.")
        require(game.placeholder_run is not None, "Run data was not created.")
        require(game.placeholder_run.generated_floor is not None, "Generated floor missing in PLAYING.")
        require(game.player is not None, "Player missing in PLAYING.")
        require(game.camera is not None, "Camera missing in PLAYING.")
        require(game.doors, "Dynamic doors were not created.")
        require(game.material_pickups, "Material pickups were not created.")
        require(game.elevator_entity is not None, "Elevator entity was not created.")

        directions = movement_directions_from_spawn(game)
        require(len(directions) >= 2, "Spawn did not expose two test movement directions.")

        scan_origin = game.player.world_position.copy()
        require(game.trigger_scan(), "Space-equivalent scan trigger failed.")
        require(game.scan_system.active_wave is not None, "Active scan wave was not created.")
        game.update_gameplay(1.0 / settings.FPS, pygame.Vector2(0, 0))
        require(game.scan_system.active_wave.current_radius > 0, "Scan radius did not advance.")
        step_gameplay(game, directions[0], frames=5)
        require(game.scan_system.active_wave.origin == scan_origin, "Scan origin followed the moving player.")
        paused_radius = game.scan_system.active_wave.current_radius
        paused_cooldown = game.scan_system.cooldown_remaining
        game.transition_to(GameState.PAUSED)
        game.update(0.5)
        require(game.scan_system.active_wave.current_radius == paused_radius, "Scan radius advanced while paused.")
        require(game.scan_system.cooldown_remaining == paused_cooldown, "Scan cooldown advanced while paused.")
        game.transition_to(GameState.PLAYING)
        for _ in range(80):
            game.update_gameplay(1.0 / settings.FPS, pygame.Vector2(0, 0))
        require(game.scan_system.traces, "Scan did not reveal static traces.")

        first_position = game.player.world_position.copy()
        step_gameplay(game, directions[0])
        require(
            game.player.world_position.distance_to(first_position) > 5,
            "Player did not move in the first simulated direction.",
        )
        second_position = game.player.world_position.copy()
        step_gameplay(game, directions[1])
        require(
            game.player.world_position.distance_to(second_position) > 5,
            "Player did not move in the second simulated direction.",
        )

        blocker_start, blocker_direction, blocker_rect = find_walkable_tile_next_to_blocker(game)
        game.player.place_at_tile(blocker_start)
        game.camera.update(game.player.world_position)
        step_gameplay(game, blocker_direction, frames=60)
        if blocker_direction.x > 0:
            require(game.player.collision_rect.right <= blocker_rect.left, "Player passed through a right-side blocker.")
        elif blocker_direction.x < 0:
            require(game.player.collision_rect.left >= blocker_rect.right, "Player passed through a left-side blocker.")
        elif blocker_direction.y > 0:
            require(game.player.collision_rect.bottom <= blocker_rect.top, "Player passed through a lower blocker.")
        elif blocker_direction.y < 0:
            require(game.player.collision_rect.top >= blocker_rect.bottom, "Player passed through an upper blocker.")

        game.handle_keydown(pygame.K_F2)
        require(game.debug_world_view, "F2 did not enable debug mode.")
        game.handle_keydown(pygame.K_F2)
        require(not game.debug_world_view, "F2 did not disable debug mode.")
        game.handle_keydown(pygame.K_F3)
        require(game.performance_overlay, "F3 did not enable the performance overlay.")
        game.handle_keydown(pygame.K_F3)
        require(not game.performance_overlay, "F3 did not disable the performance overlay.")

        require(game.creatures, "No creature was created for the current floor.")
        creature = game.creatures[0]
        creature.movement_enabled = False
        require(game.player is not None, "Player missing during creature smoke test.")

        scan_tile = find_scan_tile_for_creature(game, creature)
        place_player_at(game, scan_tile)
        while not game.scan_system.ready:
            game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
        require(game.trigger_scan(), "Creature snapshot scan did not trigger.")
        for _ in range(180):
            game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
            if game.snapshot_system.snapshots_for_source(creature.unique_id):
                break
        creature_snapshots = game.snapshot_system.snapshots_for_source(creature.unique_id)
        require(len(creature_snapshots) == 1, "Creature scan did not create exactly one snapshot.")
        captured_position = creature_snapshots[0].world_position.copy()
        floor = game.placeholder_run.generated_floor
        moved = False
        cx, cy = creature.current_tile
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            tile = (cx + dx, cy + dy)
            if floor.is_walkable(*tile):
                creature.place_at_tile(tile)
                moved = True
                break
        require(moved, "Could not move creature after snapshot capture.")
        require(
            creature_snapshots[0].world_position == captured_position,
            "Creature snapshot followed the real creature.",
        )

        game.player.world_position = creature.world_position.copy()
        game.player._sync_rects_from_world()
        game.camera.update(game.player.world_position)
        game.update_gameplay(0.0, pygame.Vector2())
        require(game.state == GameState.DEATH, "Contact with creature did not trigger death.")
        game.retry_same_seed()
        require(game.state == GameState.PLAYING, "Retry same seed did not return to PLAYING.")
        require(game.placeholder_run is not None and game.placeholder_run.restart_count == 1, "Retry same seed did not increment restart count.")
        require(game.creatures, "Creature was not recreated after retry.")
        require(game.snapshot_system.snapshots == [], "Retry retained creature snapshots.")

        door = find_powered_door(game)
        place_player_at(game, approach_tile_for_door(game, door))
        game.update_gameplay(1.0 / settings.FPS, pygame.Vector2(0, 0))
        require(door.state in (DoorState.OPENING, DoorState.OPEN), "Powered door did not begin opening on approach.")
        advance_until(game, lambda: door.is_fully_open)
        require(not game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.MOVEMENT), "Open door still blocks movement.")

        place_player_at(game, clear_tile_for_door(game, door))
        advance_until(game, lambda: door.state is DoorState.CLOSED, frames=180)
        require(game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.MOVEMENT), "Closed door did not block movement.")

        place_player_at(game, approach_tile_for_door(game, door))
        game.update_gameplay(1.0 / settings.FPS, pygame.Vector2(0, 0))
        require(door.state is DoorState.OPENING, "Door did not enter opening for pause test.")
        opening_frame = door.animation_frame_index
        game.transition_to(GameState.PAUSED)
        game.update(1.0)
        require(door.state is DoorState.OPENING, "Door state changed while paused.")
        require(door.animation_frame_index == opening_frame, "Door animation advanced while paused.")
        game.transition_to(GameState.PLAYING)
        advance_until(game, lambda: door.is_fully_open)

        pickup = next((item for item in game.material_pickups if item.scan_active), None)
        require(pickup is not None, "No active material remained for snapshot smoke test.")
        material_name = pickup.material_type.value
        place_player_at(game, pickup.tile)
        while not game.scan_system.ready:
            game.update_gameplay(1.0 / settings.FPS, pygame.Vector2(0, 0))
        require(game.trigger_scan(), "Material snapshot scan did not trigger.")
        game.update_gameplay(0.01, pygame.Vector2(0, 0))
        require(
            game.snapshot_system.snapshots_for_source(pickup.unique_id),
            "Scan did not create a material echo snapshot.",
        )
        require(not pickup.scan_active, "Material was not collected on player contact.")
        require(game.placeholder_run.material_counts[material_name] == 1, "Material counter did not update.")
        require(game.placeholder_run.score >= settings.MATERIAL_PICKUP_SCORE, "Material score did not update.")

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        game.run_one_frame(1.0 / settings.FPS)
        require(game.state == GameState.PAUSED, "Escape did not pause from PLAYING.")

        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        game.run_one_frame(1.0 / settings.FPS)
        require(game.state == GameState.PLAYING, "Resume did not return to PLAYING.")

        old_player = game.player
        old_camera = game.camera
        old_doors = list(game.doors)
        restart_count_before = game.placeholder_run.restart_count if game.placeholder_run is not None else 0
        game.transition_to(GameState.PAUSED)
        game.selected_indices[GameState.PAUSED] = 1
        game.activate_selected_button()
        require(game.state == GameState.PLAYING, "Restart Run did not return to PLAYING.")
        require(game.player is not None and game.player is not old_player, "Restart did not create a fresh player.")
        require(game.camera is not None and game.camera is not old_camera, "Restart did not create a fresh camera.")
        require(game.doors and all(door not in game.doors for door in old_doors), "Restart did not create fresh doors.")
        require(
            game.placeholder_run is not None
            and game.placeholder_run.restart_count == restart_count_before + 1,
            "Restart count was not updated.",
        )
        require(game.scan_system.active_wave is None, "Restart retained an active scan wave.")
        require(not game.scan_system.traces, "Restart retained scan traces.")
        require(not game.snapshot_system.snapshots, "Restart retained object echo snapshots.")
        require(
            game.placeholder_run.material_counts == {"scrap": 0, "circuit": 0, "power_cell": 0},
            "Restart retained material counters.",
        )

        game.request_quit()
        game.run_one_frame(1.0 / settings.FPS)
        require(not game.running, "Quit request did not stop the application loop.")
    finally:
        game.shutdown()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
