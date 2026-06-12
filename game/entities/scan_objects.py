from __future__ import annotations

from enum import Enum
from typing import Iterable

import pygame

from game import settings
from game.animation import Animation
from game.assets import AssetManager


class MaterialType(Enum):
    SCRAP = "scrap"
    CIRCUIT = "circuit"
    POWER_CELL = "power_cell"


class ElevatorState(Enum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"
    ACTIVE = "active"


class AnimatedScanObject(pygame.sprite.Sprite):
    """Base for world objects that are normally visible only as scan echoes."""

    def __init__(
        self,
        *,
        entity_id: str,
        category: str,
        world_position: pygame.Vector2 | tuple[float, float],
        animation: Animation,
        outline_frames: list[pygame.Surface],
        collision_size: tuple[int, int],
    ) -> None:
        super().__init__()
        if len(outline_frames) != len(animation.frames):
            raise ValueError("Outline frame count must match animation frame count.")
        self.entity_id = entity_id
        self.scan_category = category
        self.world_position = pygame.Vector2(world_position)
        self.animation = animation
        self.outline_frames = outline_frames
        self.scan_active = True
        self.image = self.animation.current_frame
        self.visual_rect = self.image.get_rect(center=self._rounded_center())
        self.rect = self.visual_rect
        self.collision_rect = pygame.Rect(0, 0, *collision_size)
        self.collision_rect.center = self._rounded_center()

    @property
    def unique_id(self) -> str:
        return self.entity_id

    @property
    def scan_position(self) -> pygame.Vector2:
        return self.world_position

    def update(self, dt: float) -> None:
        if not self.scan_active:
            return
        self.animation.update(max(0.0, dt))
        self.image = self.animation.current_frame
        self._sync_rects()

    def capture_scan_outline(self) -> pygame.Surface:
        return self.outline_frames[self.animation.frame_index]

    def _sync_rects(self) -> None:
        self.visual_rect = self.image.get_rect(center=self._rounded_center())
        self.rect = self.visual_rect
        self.collision_rect.center = self._rounded_center()

    def _rounded_center(self) -> tuple[int, int]:
        return (round(self.world_position.x), round(self.world_position.y))


class MaterialPickup(AnimatedScanObject):
    def __init__(
        self,
        pickup_id: str,
        material_type: MaterialType,
        tile: tuple[int, int],
        assets: AssetManager,
        tile_size: int,
    ) -> None:
        self.pickup_id = pickup_id
        self.material_type = material_type
        self.tile = tile
        world_position = ((tile[0] + 0.5) * tile_size, (tile[1] + 0.5) * tile_size)
        super().__init__(
            entity_id=pickup_id,
            category=f"material:{material_type.value}",
            world_position=world_position,
            animation=assets.get_animation("materials", material_type.value, looping=True),
            outline_frames=assets.get_outline_frames("materials", material_type.value),
            collision_size=(settings.MATERIAL_COLLISION_SIZE, settings.MATERIAL_COLLISION_SIZE),
        )
        self.collected = False
        self.score_value = settings.MATERIAL_PICKUP_SCORE

    def collect(self) -> bool:
        if self.collected or not self.scan_active:
            return False
        self.collected = True
        self.scan_active = False
        self.kill()
        return True


class ElevatorEntity(pygame.sprite.Sprite):
    def __init__(
        self,
        elevator_id: str,
        tile: tuple[int, int],
        approach_tiles: Iterable[tuple[int, int]],
        assets: AssetManager,
        tile_size: int,
        state: ElevatorState = ElevatorState.LOCKED,
    ) -> None:
        super().__init__()
        self.elevator_id = elevator_id
        self.entity_id = elevator_id
        self.scan_category = "elevator"
        self.tile = tile
        self.tile_size = tile_size
        self.world_position = pygame.Vector2((tile[0] + 0.5) * tile_size, (tile[1] + 0.5) * tile_size)
        self.scan_active = True
        self.state = state
        self._animations = {
            ElevatorState.LOCKED: assets.get_animation("elevator", "locked", looping=True),
            ElevatorState.UNLOCKED: assets.get_animation("elevator", "unlocked", looping=True),
            ElevatorState.ACTIVE: assets.get_animation("elevator", "active", looping=True),
        }
        self._outlines = {
            ElevatorState.LOCKED: assets.get_outline_frames(
                "elevator", "locked", color=(255, 104, 96, 220)
            ),
            ElevatorState.UNLOCKED: assets.get_outline_frames(
                "elevator", "unlocked", color=(72, 226, 255, 220)
            ),
            ElevatorState.ACTIVE: assets.get_outline_frames(
                "elevator", "active", color=(118, 241, 173, 230)
            ),
        }
        self.image = self._animations[self.state].current_frame
        self.visual_rect = self.image.get_rect(center=self._rounded_center())
        self.rect = self.visual_rect
        self.interaction_rect = self._build_interaction_rect(list(approach_tiles))

    @property
    def unique_id(self) -> str:
        return self.elevator_id

    @property
    def scan_position(self) -> pygame.Vector2:
        return self.world_position

    @property
    def animation_frame_index(self) -> int:
        return self._animations[self.state].frame_index

    def set_state(self, state: ElevatorState) -> None:
        if state is self.state:
            return
        self.state = state
        self._animations[state].reset()
        self.image = self._animations[state].current_frame
        self._sync_visual_rect()

    def unlock(self) -> None:
        self.set_state(ElevatorState.UNLOCKED)

    def lock(self) -> None:
        self.set_state(ElevatorState.LOCKED)

    def activate(self) -> None:
        self.set_state(ElevatorState.ACTIVE)

    def update(self, dt: float) -> None:
        animation = self._animations[self.state]
        animation.update(max(0.0, dt))
        self.image = animation.current_frame
        self._sync_visual_rect()

    def capture_scan_outline(self) -> pygame.Surface:
        animation = self._animations[self.state]
        return self._outlines[self.state][animation.frame_index]

    def _build_interaction_rect(self, approach_tiles: list[tuple[int, int]]) -> pygame.Rect:
        tiles = [self.tile, *approach_tiles]
        left = min(tile[0] for tile in tiles) * self.tile_size
        top = min(tile[1] for tile in tiles) * self.tile_size
        right = (max(tile[0] for tile in tiles) + 1) * self.tile_size
        bottom = (max(tile[1] for tile in tiles) + 1) * self.tile_size
        return pygame.Rect(left, top, right - left, bottom - top)

    def _sync_visual_rect(self) -> None:
        self.visual_rect = self.image.get_rect(center=self._rounded_center())
        self.rect = self.visual_rect

    def _rounded_center(self) -> tuple[int, int]:
        return (round(self.world_position.x), round(self.world_position.y))
