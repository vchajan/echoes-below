from __future__ import annotations

from enum import Enum, auto

import pygame

from game import settings
from game.animation import Animation
from game.assets import AssetManager
from game.entities.scan_objects import AnimatedScanObject


class GeneratorState(Enum):
    INACTIVE = auto()
    READY = auto()
    REPAIRING = auto()
    POWERED = auto()


class RelayState(Enum):
    INACTIVE = auto()
    ACTIVATING = auto()
    ACTIVE = auto()


class GeneratorComponentPickup(AnimatedScanObject):
    def __init__(
        self,
        component_id: str,
        component_key: str,
        room_id: int,
        tile: tuple[int, int],
        assets: AssetManager,
        tile_size: int,
    ) -> None:
        self.component_id = component_id
        self.component_key = component_key
        self.room_id = room_id
        self.tile = tile
        world_position = ((tile[0] + 0.5) * tile_size, (tile[1] + 0.5) * tile_size)
        super().__init__(
            entity_id=component_id,
            category=f"generator_component:{component_key.lower()}",
            world_position=world_position,
            animation=assets.get_animation("generator_component", "pulse", looping=True),
            outline_frames=assets.get_outline_frames(
                "generator_component",
                "pulse",
                color=(255, 220, 80, 225) if component_key == "A" else (118, 241, 173, 225),
            ),
            collision_size=(
                settings.GENERATOR_COMPONENT_COLLISION_SIZE,
                settings.GENERATOR_COMPONENT_COLLISION_SIZE,
            ),
        )
        self.collected = False
        self.score_value = settings.GENERATOR_COMPONENT_SCORE

    def collect(self) -> bool:
        if self.collected or not self.scan_active:
            return False
        self.collected = True
        self.scan_active = False
        self.kill()
        return True


class SecurityKeycardPickup(AnimatedScanObject):
    def __init__(
        self,
        keycard_id: str,
        room_id: int,
        tile: tuple[int, int],
        assets: AssetManager,
        tile_size: int,
    ) -> None:
        self.keycard_id = keycard_id
        self.room_id = room_id
        self.tile = tile
        world_position = ((tile[0] + 0.5) * tile_size, (tile[1] + 0.5) * tile_size)
        super().__init__(
            entity_id=keycard_id,
            category="keycard:security",
            world_position=world_position,
            animation=assets.get_animation("keycard", "glow", looping=True),
            outline_frames=assets.get_outline_frames(
                "keycard",
                "glow",
                color=(72, 226, 255, 225),
            ),
            collision_size=(
                settings.SECURITY_KEYCARD_COLLISION_SIZE,
                settings.SECURITY_KEYCARD_COLLISION_SIZE,
            ),
        )
        self.collected = False
        self.score_value = settings.SECURITY_KEYCARD_SCORE

    def collect(self) -> bool:
        if self.collected or not self.scan_active:
            return False
        self.collected = True
        self.scan_active = False
        self.kill()
        return True


class GeneratorEntity(pygame.sprite.Sprite):
    def __init__(
        self,
        generator_id: str,
        room_id: int,
        tile: tuple[int, int],
        assets: AssetManager,
        tile_size: int,
        state: GeneratorState = GeneratorState.INACTIVE,
    ) -> None:
        super().__init__()
        self.generator_id = generator_id
        self.entity_id = generator_id
        self.scan_category = "generator"
        self.room_id = room_id
        self.tile = tile
        self.tile_size = tile_size
        self.world_position = pygame.Vector2((tile[0] + 0.5) * tile_size, (tile[1] + 0.5) * tile_size)
        self.scan_active = True
        self.state = state
        self.repair_progress = 0.0
        self.repair_duration = settings.GENERATOR_REPAIR_DURATION
        self._animations = {
            GeneratorState.INACTIVE: assets.get_animation("generator", "broken", looping=True),
            GeneratorState.READY: assets.get_animation("generator", "repair", looping=True),
            GeneratorState.REPAIRING: assets.get_animation("generator", "repair", looping=True),
            GeneratorState.POWERED: assets.get_animation("generator", "powered", looping=True),
        }
        self._outlines = {
            GeneratorState.INACTIVE: assets.get_outline_frames(
                "generator", "broken", color=(255, 104, 96, 225)
            ),
            GeneratorState.READY: assets.get_outline_frames(
                "generator", "repair", color=(255, 220, 80, 225)
            ),
            GeneratorState.REPAIRING: assets.get_outline_frames(
                "generator", "repair", color=(255, 220, 80, 235)
            ),
            GeneratorState.POWERED: assets.get_outline_frames(
                "generator", "powered", color=(118, 241, 173, 235)
            ),
        }
        self.image = self._animations[self.state].current_frame
        self.visual_rect = self.image.get_rect(center=self._rounded_center())
        self.rect = self.visual_rect
        self.interaction_rect = self._build_interaction_rect()

    @property
    def unique_id(self) -> str:
        return self.generator_id

    @property
    def scan_position(self) -> pygame.Vector2:
        return self.world_position

    @property
    def animation_frame_index(self) -> int:
        return self._animations[self.state].frame_index

    def set_state(self, state: GeneratorState) -> None:
        if state is self.state:
            return
        self.state = state
        self._animations[state].reset()
        self.image = self._animations[state].current_frame
        self._sync_visual_rect()

    def update(self, dt: float) -> None:
        animation = self._animations[self.state]
        animation.update(max(0.0, dt))
        self.image = animation.current_frame
        self._sync_visual_rect()

    def capture_scan_outline(self) -> pygame.Surface:
        animation = self._animations[self.state]
        return self._outlines[self.state][animation.frame_index]

    def _build_interaction_rect(self) -> pygame.Rect:
        size = int(self.tile_size * settings.GENERATOR_INTERACTION_RADIUS_TILES * 2)
        rect = pygame.Rect(0, 0, size, size)
        rect.center = self._rounded_center()
        return rect

    def _sync_visual_rect(self) -> None:
        self.visual_rect = self.image.get_rect(center=self._rounded_center())
        self.rect = self.visual_rect

    def _rounded_center(self) -> tuple[int, int]:
        return (round(self.world_position.x), round(self.world_position.y))


class RelayEntity(pygame.sprite.Sprite):
    def __init__(
        self,
        relay_id: str,
        label: str,
        room_id: int,
        tile: tuple[int, int],
        assets: AssetManager,
        tile_size: int,
        state: RelayState = RelayState.INACTIVE,
    ) -> None:
        super().__init__()
        self.relay_id = relay_id
        self.entity_id = relay_id
        self.label = label
        self.scan_category = f"relay:{label.lower()}"
        self.room_id = room_id
        self.tile = tile
        self.tile_size = tile_size
        self.world_position = pygame.Vector2((tile[0] + 0.5) * tile_size, (tile[1] + 0.5) * tile_size)
        self.scan_active = True
        self.state = state
        self.activation_progress = 0.0
        self.activation_duration = settings.RELAY_ACTIVATION_DURATION
        self._animations = {
            RelayState.INACTIVE: assets.get_animation("relay", "inactive", looping=True),
            RelayState.ACTIVATING: assets.get_animation("relay", "activate", looping=True),
            RelayState.ACTIVE: assets.get_animation("relay", "active", looping=True),
        }
        self._outlines = {
            RelayState.INACTIVE: assets.get_outline_frames(
                "relay", "inactive", color=(72, 226, 255, 220)
            ),
            RelayState.ACTIVATING: assets.get_outline_frames(
                "relay", "activate", color=(255, 220, 80, 235)
            ),
            RelayState.ACTIVE: assets.get_outline_frames(
                "relay", "active", color=(118, 241, 173, 235)
            ),
        }
        self.image = self._animations[self.state].current_frame
        self.visual_rect = self.image.get_rect(center=self._rounded_center())
        self.rect = self.visual_rect
        self.interaction_rect = self._build_interaction_rect()

    @property
    def unique_id(self) -> str:
        return self.relay_id

    @property
    def scan_position(self) -> pygame.Vector2:
        return self.world_position

    @property
    def animation_frame_index(self) -> int:
        return self._animations[self.state].frame_index

    def set_state(self, state: RelayState) -> None:
        if state is self.state:
            return
        self.state = state
        self._animations[state].reset()
        self.image = self._animations[state].current_frame
        self._sync_visual_rect()

    def update(self, dt: float) -> None:
        animation = self._animations[self.state]
        animation.update(max(0.0, dt))
        self.image = animation.current_frame
        self._sync_visual_rect()

    def capture_scan_outline(self) -> pygame.Surface:
        animation = self._animations[self.state]
        return self._outlines[self.state][animation.frame_index]

    def _build_interaction_rect(self) -> pygame.Rect:
        size = int(self.tile_size * settings.RELAY_INTERACTION_RADIUS_TILES * 2)
        rect = pygame.Rect(0, 0, size, size)
        rect.center = self._rounded_center()
        return rect

    def _sync_visual_rect(self) -> None:
        self.visual_rect = self.image.get_rect(center=self._rounded_center())
        self.rect = self.visual_rect

    def _rounded_center(self) -> tuple[int, int]:
        return (round(self.world_position.x), round(self.world_position.y))
