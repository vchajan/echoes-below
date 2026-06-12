from __future__ import annotations

import math

import pygame

from game import settings
from game.assets import AssetManager
from game.world import collision


def movement_direction_from_bools(up: bool, down: bool, left: bool, right: bool) -> pygame.Vector2:
    x = (1 if right else 0) - (1 if left else 0)
    y = (1 if down else 0) - (1 if up else 0)
    direction = pygame.Vector2(x, y)
    if direction.length_squared() > 0:
        direction = direction.normalize()
    return direction


class Player(pygame.sprite.Sprite):
    def __init__(
        self,
        spawn_tile: tuple[int, int],
        assets: AssetManager,
        tile_size: int,
        speed: float = settings.PLAYER_SPEED,
    ) -> None:
        super().__init__()
        self.spawn_tile = spawn_tile
        self.spawn_position = pygame.Vector2((spawn_tile[0] + 0.5) * tile_size, (spawn_tile[1] + 0.5) * tile_size)
        self.world_position = self.spawn_position.copy()
        self.velocity = pygame.Vector2(0, 0)
        self.speed = speed
        self.tile_size = tile_size
        self.facing = "down"
        self.moving = False
        self._animation_state = "idle"

        self.animations = {
            "idle_down": assets.get_animation("player", "idle_down", looping=True),
            "idle_left": assets.get_animation("player", "idle_left", looping=True),
            "idle_right": assets.get_animation("player", "idle_right", looping=True),
            "idle_up": assets.get_animation("player", "idle_up", looping=True),
            "walk_down": assets.get_animation("player", "walk_down", looping=True),
            "walk_left": assets.get_animation("player", "walk_left", looping=True),
            "walk_right": assets.get_animation("player", "walk_right", looping=True),
            "walk_up": assets.get_animation("player", "walk_up", looping=True),
        }

        self.image = self.animations["idle_down"].current_frame
        self.visual_rect = self.image.get_rect(center=self._rounded_world_center())
        self.rect = self.visual_rect
        self.collision_rect = pygame.Rect(0, 0, settings.PLAYER_COLLISION_WIDTH, settings.PLAYER_COLLISION_HEIGHT)
        self._sync_rects_from_world()

    def place_at_tile(self, tile: tuple[int, int]) -> None:
        self.spawn_tile = tile
        self.spawn_position.update((tile[0] + 0.5) * self.tile_size, (tile[1] + 0.5) * self.tile_size)
        self.world_position = self.spawn_position.copy()
        self.velocity.update(0, 0)
        self._sync_rects_from_world()

    @property
    def feet_position(self) -> pygame.Vector2:
        return pygame.Vector2(self.collision_rect.centerx, self.collision_rect.bottom - 1)

    @property
    def current_tile(self) -> tuple[int, int]:
        return collision.world_to_tile(self.feet_position, self.tile_size)

    @property
    def animation_key(self) -> str:
        return f"{self._animation_state}_{self.facing}"

    def set_movement_direction(self, direction: pygame.Vector2) -> pygame.Vector2:
        if direction.length_squared() > 1:
            direction = direction.normalize()
        self.velocity = direction * self.speed
        self._update_facing(direction)
        return direction

    def update(self, direction: pygame.Vector2, dt: float, generated_floor, dynamic_blockers=None) -> None:
        direction = self.set_movement_direction(direction)
        self.moving = direction.length_squared() > 0
        next_state = "walk" if self.moving else "idle"
        if next_state != self._animation_state:
            self._animation_state = next_state
            self.animations[self.animation_key].reset()

        if self.moving:
            movement = direction * self.speed * dt
            self._move_with_substeps(movement, generated_floor, dynamic_blockers)

        self.animations[self.animation_key].update(dt if self.moving else 0.0)
        old_center = self.visual_rect.center
        self.image = self.animations[self.animation_key].current_frame
        self.visual_rect = self.image.get_rect(center=old_center)
        self.rect = self.visual_rect
        self._sync_rects_from_world()

    def _move_with_substeps(self, movement: pygame.Vector2, generated_floor, dynamic_blockers=None) -> None:
        distance = movement.length()
        if distance <= 0:
            return
        steps = max(1, min(settings.MOVEMENT_MAX_SUBSTEPS, math.ceil(distance / settings.MOVEMENT_SUBSTEP_MAX)))
        step = movement / steps
        for _ in range(steps):
            self._move_single_step(step, generated_floor, dynamic_blockers)

    def _move_single_step(self, movement: pygame.Vector2, generated_floor, dynamic_blockers=None) -> None:
        if movement.x:
            candidate = self.collision_rect.copy()
            candidate, collided = collision.resolve_axis(
                candidate,
                movement.x,
                "x",
                generated_floor,
                self.tile_size,
                dynamic_blockers,
            )
            if not collided:
                self.world_position.x += movement.x
            else:
                self.collision_rect = candidate
                self.world_position.x = float(self.collision_rect.centerx)
            self._sync_rects_from_world()

        if movement.y:
            candidate = self.collision_rect.copy()
            candidate, collided = collision.resolve_axis(
                candidate,
                movement.y,
                "y",
                generated_floor,
                self.tile_size,
                dynamic_blockers,
            )
            if not collided:
                self.world_position.y += movement.y
            else:
                self.collision_rect = candidate
                self.world_position.y = self._world_y_from_collision_rect()
            self._sync_rects_from_world()

    def _update_facing(self, direction: pygame.Vector2) -> None:
        if direction.length_squared() == 0:
            return
        abs_x = abs(direction.x)
        abs_y = abs(direction.y)
        if abs_x > abs_y:
            self.facing = "right" if direction.x > 0 else "left"
        elif abs_y > abs_x:
            self.facing = "down" if direction.y > 0 else "up"
        elif self.facing in ("left", "right") and direction.x:
            self.facing = "right" if direction.x > 0 else "left"
        elif direction.y:
            self.facing = "down" if direction.y > 0 else "up"

    def _sync_rects_from_world(self) -> None:
        self.visual_rect = self.image.get_rect(center=self._rounded_world_center())
        self.rect = self.visual_rect
        self.collision_rect.size = (settings.PLAYER_COLLISION_WIDTH, settings.PLAYER_COLLISION_HEIGHT)
        self.collision_rect.centerx = round(self.world_position.x)
        self.collision_rect.bottom = self.visual_rect.bottom - settings.PLAYER_COLLISION_BOTTOM_OFFSET

    def _world_y_from_collision_rect(self) -> float:
        return float(
            self.collision_rect.bottom
            + settings.PLAYER_COLLISION_BOTTOM_OFFSET
            - self.image.get_height() / 2
        )

    def _rounded_world_center(self) -> tuple[int, int]:
        return (round(self.world_position.x), round(self.world_position.y))
