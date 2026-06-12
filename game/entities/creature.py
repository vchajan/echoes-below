from __future__ import annotations

from collections import deque
import math
import random
from typing import TYPE_CHECKING

import pygame

from game import settings
from game.animation import Animation
from game.assets import AssetManager
from game.world import collision
from game.world.blockers import BlockerPurpose

if TYPE_CHECKING:
    from game.world.blockers import DynamicBlockerRegistry
    from game.world.floor import GeneratedFloor


class Creature(pygame.sprite.Sprite):
    """Invisible patrol creature whose position is only exposed by scan echoes.

    Phase 9 intentionally keeps the behaviour simple: a path is calculated only
    when a patrol target changes or the creature becomes stuck. Full threat-aware
    AI belongs to Phase 10.
    """

    def __init__(
        self,
        creature_id: str,
        spawn_tile: tuple[int, int],
        assets: AssetManager,
        tile_size: int,
        rng: random.Random,
        speed: float = settings.CREATURE_SPEED,
    ) -> None:
        super().__init__()
        self.creature_id = creature_id
        self.entity_id = creature_id
        self.unique_id = creature_id
        self.scan_category = "creature"
        self.scan_active = True
        self.snapshot_lifetime = settings.CREATURE_SNAPSHOT_LIFETIME

        self.spawn_tile = spawn_tile
        self.spawn_position = self._tile_center(spawn_tile, tile_size)
        self.world_position = self.spawn_position.copy()
        self.velocity = pygame.Vector2()
        self.speed = float(speed)
        self.tile_size = tile_size
        self.facing = "down"
        self.moving = False
        self.movement_enabled = True

        base_animation = assets.get_animation("creature", "move", looping=True)
        base_frames = assets.get_frames("creature", "move")
        flipped_frames = assets.get_flipped_frames("creature", "move")
        duration = base_animation.frame_duration
        self.animations = {
            "down": Animation(base_frames, duration, looping=True),
            "right": Animation(base_frames, duration, looping=True),
            "up": Animation(base_frames, duration, looping=True),
            "left": Animation(flipped_frames, duration, looping=True),
        }
        self.outline_frames = assets.get_outline_frames("creature", "move")
        self.outline_frames_flipped = [pygame.transform.flip(frame, True, False) for frame in self.outline_frames]

        self.image = self.animations[self.facing].current_frame
        self.visual_rect = self.image.get_rect(center=self._rounded_world_center())
        self.rect = self.visual_rect
        self.collision_rect = pygame.Rect(
            0,
            0,
            settings.CREATURE_COLLISION_SIZE,
            settings.CREATURE_COLLISION_SIZE,
        )
        self._sync_rects_from_world()

        self.rng = rng
        self.current_waypoint: tuple[int, int] | None = None
        self.current_path: list[tuple[int, int]] = []
        self.path_recalculations = 0
        self._patrol_candidates: list[tuple[int, int]] | None = None
        self._repath_cooldown = 0.0
        self._stuck_elapsed = 0.0
        self._last_world_position = self.world_position.copy()

    @property
    def feet_position(self) -> pygame.Vector2:
        return pygame.Vector2(self.collision_rect.centerx, self.collision_rect.centery)

    @property
    def current_tile(self) -> tuple[int, int]:
        return collision.world_to_tile(self.feet_position, self.tile_size)

    @property
    def scan_position(self) -> pygame.Vector2:
        return self.world_position.copy()

    @property
    def patrol_target(self) -> tuple[int, int] | None:
        return self.current_waypoint

    @property
    def animation_frame_index(self) -> int:
        return self.animations[self.facing].frame_index

    def capture_scan_outline(self) -> pygame.Surface:
        frame_index = self.animation_frame_index
        frames = self.outline_frames_flipped if self.facing == "left" else self.outline_frames
        return frames[min(frame_index, len(frames) - 1)]

    def place_at_tile(self, tile: tuple[int, int]) -> None:
        self.world_position = self._tile_center(tile, self.tile_size)
        self.velocity.update(0, 0)
        self.current_waypoint = None
        self.current_path.clear()
        self._stuck_elapsed = 0.0
        self._sync_rects_from_world()

    def set_world_position(self, position: pygame.Vector2 | tuple[float, float]) -> None:
        """Test/preview helper that preserves all Rect invariants."""
        self.world_position = pygame.Vector2(position)
        self._sync_rects_from_world()

    def update(
        self,
        dt: float,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None = None,
    ) -> None:
        dt = max(0.0, dt)
        self._repath_cooldown = max(0.0, self._repath_cooldown - dt)
        self._last_world_position = self.world_position.copy()

        if not self.movement_enabled:
            self.velocity.update(0, 0)
            self.moving = False
            self._sync_rects_from_world()
            return

        self._ensure_patrol_path(generated_floor, dynamic_blockers)
        direction = self._direction_to_next_path_tile()
        self.set_movement_direction(direction)

        if self.moving:
            self.move_by(self.velocity * dt, generated_floor, dynamic_blockers)

        moved_distance = self.world_position.distance_to(self._last_world_position)
        if self.moving and moved_distance <= 0.05:
            self._stuck_elapsed += dt
            if self._stuck_elapsed >= settings.CREATURE_STUCK_REPATH_TIME:
                self.current_path.clear()
                self.current_waypoint = None
                self._repath_cooldown = settings.CREATURE_REPATH_COOLDOWN
                self._stuck_elapsed = 0.0
        else:
            self._stuck_elapsed = 0.0

        animation = self.animations[self.facing]
        animation.update(dt if self.moving else 0.0)
        self.image = animation.current_frame
        self._sync_rects_from_world()

    def set_movement_direction(self, direction: pygame.Vector2) -> pygame.Vector2:
        direction = pygame.Vector2(direction)
        if direction.length_squared() > 1.0:
            direction = direction.normalize()
        self.velocity = direction * self.speed
        self.moving = direction.length_squared() > 1e-8
        if self.moving:
            self._update_facing(direction)
        return direction

    def move_by(
        self,
        movement: pygame.Vector2 | tuple[float, float],
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None = None,
    ) -> pygame.Vector2:
        """Move with bounded substeps and return the actual displacement."""
        movement_vector = pygame.Vector2(movement)
        start = self.world_position.copy()
        distance = movement_vector.length()
        if distance <= 1e-8:
            return pygame.Vector2()

        steps = max(
            1,
            min(
                settings.MOVEMENT_MAX_SUBSTEPS,
                math.ceil(distance / settings.MOVEMENT_SUBSTEP_MAX),
            ),
        )
        step = movement_vector / steps
        for _ in range(steps):
            self._move_single_step(step, generated_floor, dynamic_blockers)
        return self.world_position - start

    def _move_single_step(
        self,
        movement: pygame.Vector2,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> None:
        if abs(movement.x) > 1e-8:
            candidate, collided = collision.resolve_axis(
                self.collision_rect,
                movement.x,
                "x",
                generated_floor,
                self.tile_size,
                dynamic_blockers,
                BlockerPurpose.CREATURE_MOVEMENT,
            )
            if collided:
                self.collision_rect = candidate
                self.world_position.x = float(candidate.centerx)
            else:
                self.world_position.x += movement.x
            self._sync_rects_from_world()

        if abs(movement.y) > 1e-8:
            candidate, collided = collision.resolve_axis(
                self.collision_rect,
                movement.y,
                "y",
                generated_floor,
                self.tile_size,
                dynamic_blockers,
                BlockerPurpose.CREATURE_MOVEMENT,
            )
            if collided:
                self.collision_rect = candidate
                self.world_position.y = float(candidate.centery)
            else:
                self.world_position.y += movement.y
            self._sync_rects_from_world()

    def _ensure_patrol_path(
        self,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> None:
        while self.current_path and self.current_tile == self.current_path[0]:
            self.current_path.pop(0)

        if self.current_path or self._repath_cooldown > 0:
            return

        if self._patrol_candidates is None:
            self._patrol_candidates = [
                tile
                for tile in generated_floor.walkable_tiles()
                if tile != self.spawn_tile
                and not (
                    dynamic_blockers
                    and dynamic_blockers.blocks_tile(
                        *tile,
                        purpose=BlockerPurpose.CREATURE_MOVEMENT,
                    )
                )
            ]

        if not self._patrol_candidates:
            self.current_waypoint = None
            return

        attempts = min(settings.CREATURE_PATROL_TARGET_ATTEMPTS, len(self._patrol_candidates))
        for target in self.rng.sample(self._patrol_candidates, attempts):
            path = self._find_tile_path(
                self.current_tile,
                target,
                generated_floor,
                dynamic_blockers,
            )
            if len(path) >= settings.CREATURE_MIN_PATROL_PATH_TILES:
                self.current_waypoint = target
                self.current_path = path[1:]
                self.path_recalculations += 1
                return

        self.current_waypoint = None
        self._repath_cooldown = settings.CREATURE_REPATH_COOLDOWN

    def _direction_to_next_path_tile(self) -> pygame.Vector2:
        while self.current_path:
            target = self._tile_center(self.current_path[0], self.tile_size)
            delta = target - self.world_position
            if delta.length() <= settings.CREATURE_WAYPOINT_REACHED_DISTANCE:
                self.current_path.pop(0)
                continue
            return delta.normalize()
        self.current_waypoint = None
        return pygame.Vector2()

    def _find_tile_path(
        self,
        start: tuple[int, int],
        target: tuple[int, int],
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> list[tuple[int, int]]:
        if start == target:
            return [start]
        queue: deque[tuple[int, int]] = deque([start])
        predecessors: dict[tuple[int, int], tuple[int, int] | None] = {start: None}

        while queue:
            current = queue.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                neighbour = (current[0] + dx, current[1] + dy)
                if neighbour in predecessors or not generated_floor.is_walkable(*neighbour):
                    continue
                if dynamic_blockers and dynamic_blockers.blocks_tile(
                    *neighbour,
                    purpose=BlockerPurpose.CREATURE_MOVEMENT,
                ):
                    continue
                predecessors[neighbour] = current
                if neighbour == target:
                    return self._reconstruct_path(predecessors, target)
                queue.append(neighbour)
        return []

    @staticmethod
    def _reconstruct_path(
        predecessors: dict[tuple[int, int], tuple[int, int] | None],
        target: tuple[int, int],
    ) -> list[tuple[int, int]]:
        path = [target]
        current = target
        while predecessors[current] is not None:
            current = predecessors[current]  # type: ignore[assignment]
            path.append(current)
        path.reverse()
        return path

    def _update_facing(self, direction: pygame.Vector2) -> None:
        if abs(direction.x) > abs(direction.y):
            self.facing = "right" if direction.x > 0 else "left"
        elif abs(direction.y) > 1e-8:
            self.facing = "down" if direction.y > 0 else "up"

    def _sync_rects_from_world(self) -> None:
        center = self._rounded_world_center()
        self.visual_rect = self.image.get_rect(center=center)
        self.rect = self.visual_rect
        self.collision_rect.size = (
            settings.CREATURE_COLLISION_SIZE,
            settings.CREATURE_COLLISION_SIZE,
        )
        self.collision_rect.center = center

    def _rounded_world_center(self) -> tuple[int, int]:
        return (round(self.world_position.x), round(self.world_position.y))

    @staticmethod
    def _tile_center(tile: tuple[int, int], tile_size: int) -> pygame.Vector2:
        return pygame.Vector2(
            (tile[0] + 0.5) * tile_size,
            (tile[1] + 0.5) * tile_size,
        )
