from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pygame

from game.animation import Animation


class PlayableSound(Protocol):
    def play(self) -> object:
        ...


class NoOpSound:
    def play(self) -> None:
        return None


@dataclass(frozen=True)
class SpriteSheetMetadata:
    path: str
    frame_width: int
    frame_height: int
    rows: int
    columns: int
    animations: dict[str, list[int]]
    default_frame_duration: float
    scale: int | None = None


# Spritesheets use regular left-to-right, top-to-bottom grids. Frame index 0 is
# the top-left cell, then indices continue across each row.
SPRITESHEETS: dict[str, SpriteSheetMetadata] = {
    "industrial_tiles": SpriteSheetMetadata(
        path="assets/tiles/industrial_tileset.png",
        frame_width=48,
        frame_height=48,
        rows=2,
        columns=6,
        animations={
            "floor": [0],
            "floor_alt": [1],
            "floor_damaged": [2],
            "wall": [3],
            "wall_damaged": [4],
            "machinery": [5],
            "pillar": [6],
            "doorway": [7],
            "elevator": [8],
            "containment": [9],
            "cable": [10],
            "void": [11],
        },
        default_frame_duration=0.2,
    ),
    "player": SpriteSheetMetadata(
        path="assets/sprites/player_sheet.png",
        frame_width=48,
        frame_height=64,
        rows=4,
        columns=5,
        animations={
            "idle_down": [0],
            "walk_down": [0, 1, 2, 3, 4],
            "idle_left": [5],
            "walk_left": [5, 6, 7, 8, 9],
            "idle_right": [10],
            "walk_right": [10, 11, 12, 13, 14],
            "idle_up": [15],
            "walk_up": [15, 16, 17, 18, 19],
        },
        default_frame_duration=0.13,
    ),
    "creature": SpriteSheetMetadata(
        path="assets/sprites/creature_sheet.png",
        frame_width=64,
        frame_height=64,
        rows=1,
        columns=4,
        animations={"move": [0, 1, 2, 3]},
        default_frame_duration=0.16,
    ),
    "powered_door": SpriteSheetMetadata(
        path="assets/objects/powered_door_sheet.png",
        frame_width=96,
        frame_height=96,
        rows=1,
        columns=4,
        animations={"closed": [0], "open": [3], "opening": [0, 1, 2, 3], "closing": [3, 2, 1, 0]},
        default_frame_duration=0.12,
    ),
    "security_door": SpriteSheetMetadata(
        path="assets/objects/security_door_sheet.png",
        frame_width=96,
        frame_height=96,
        rows=1,
        columns=4,
        animations={"locked": [0], "unlocked": [1], "opening": [1, 2, 3], "open": [3]},
        default_frame_duration=0.12,
    ),
    "containment_door": SpriteSheetMetadata(
        path="assets/objects/containment_door_sheet.png",
        frame_width=96,
        frame_height=96,
        rows=1,
        columns=4,
        animations={"locked": [0], "powered": [1], "opening": [1, 2, 3], "open": [3]},
        default_frame_duration=0.12,
    ),
    "generator_component": SpriteSheetMetadata(
        path="assets/objects/generator_component_sheet.png",
        frame_width=64,
        frame_height=64,
        rows=1,
        columns=2,
        animations={"pulse": [0, 1]},
        default_frame_duration=0.35,
    ),
    "generator": SpriteSheetMetadata(
        path="assets/objects/generator_sheet.png",
        frame_width=96,
        frame_height=96,
        rows=1,
        columns=5,
        animations={"broken": [0], "repair": [1], "powered": [2, 3, 4]},
        default_frame_duration=0.18,
    ),
    "keycard": SpriteSheetMetadata(
        path="assets/objects/keycard_sheet.png",
        frame_width=48,
        frame_height=48,
        rows=1,
        columns=2,
        animations={"glow": [0, 1]},
        default_frame_duration=0.35,
    ),
    "relay": SpriteSheetMetadata(
        path="assets/objects/relay_sheet.png",
        frame_width=72,
        frame_height=72,
        rows=1,
        columns=5,
        animations={"inactive": [0], "activate": [1, 2, 3], "active": [4]},
        default_frame_duration=0.16,
    ),
    "containment_component": SpriteSheetMetadata(
        path="assets/objects/containment_component_sheet.png",
        frame_width=64,
        frame_height=64,
        rows=1,
        columns=2,
        animations={"pulse": [0, 1]},
        default_frame_duration=0.35,
    ),
    "containment_control": SpriteSheetMetadata(
        path="assets/objects/containment_control_sheet.png",
        frame_width=72,
        frame_height=72,
        rows=1,
        columns=3,
        animations={"inactive": [0], "powered": [1], "active": [2]},
        default_frame_duration=0.2,
    ),
    "echo_core": SpriteSheetMetadata(
        path="assets/objects/echo_core_sheet.png",
        frame_width=72,
        frame_height=72,
        rows=1,
        columns=4,
        animations={"pulse": [0, 1, 2, 3]},
        default_frame_duration=0.18,
    ),
    "elevator": SpriteSheetMetadata(
        path="assets/objects/elevator_sheet.png",
        frame_width=96,
        frame_height=96,
        rows=1,
        columns=3,
        animations={"locked": [0], "unlocked": [1], "active": [2]},
        default_frame_duration=0.25,
    ),
    "materials": SpriteSheetMetadata(
        path="assets/objects/materials_sheet.png",
        frame_width=48,
        frame_height=48,
        rows=3,
        columns=2,
        animations={"scrap": [0, 1], "circuit": [2, 3], "power_cell": [4, 5]},
        default_frame_duration=0.3,
    ),
    "scan_origin_pulse": SpriteSheetMetadata(
        path="assets/effects/scan_origin_pulse_sheet.png",
        frame_width=64,
        frame_height=64,
        rows=1,
        columns=4,
        animations={"pulse": [0, 1, 2, 3]},
        default_frame_duration=0.08,
    ),
}

MODULE_ICON_PATHS = {
    "shock_pulse_ready": "assets/ui/shock_pulse_ready.png",
    "shock_pulse_cooldown": "assets/ui/shock_pulse_cooldown.png",
    "decoy_beacon_ready": "assets/ui/decoy_beacon_ready.png",
    "decoy_beacon_cooldown": "assets/ui/decoy_beacon_cooldown.png",
    "door_wedge_ready": "assets/ui/door_wedge_ready.png",
    "door_wedge_cooldown": "assets/ui/door_wedge_cooldown.png",
    "scan_projector_ready": "assets/ui/scan_projector_ready.png",
    "scan_projector_cooldown": "assets/ui/scan_projector_cooldown.png",
    "scan_ready": "assets/ui/scan_ready.png",
    "scan_cooldown": "assets/ui/scan_cooldown.png",
    "scrap": "assets/ui/scrap.png",
    "circuit": "assets/ui/circuit.png",
    "power_cell": "assets/ui/power_cell.png",
    "score": "assets/ui/score.png",
    "floor": "assets/ui/floor.png",
}

EFFECT_IMAGE_PATHS = {
    "scan_point": "assets/effects/scan_point.png",
    "shock_pulse_ring": "assets/effects/shock_pulse_ring.png",
    "beacon_pulse": "assets/effects/beacon_pulse.png",
    "projector_activation": "assets/effects/projector_activation.png",
    "material_pickup": "assets/effects/material_pickup.png",
    "objective_activation": "assets/effects/objective_activation.png",
    "creature_warning": "assets/effects/creature_warning.png",
}

SOUND_PATHS = {
    "menu_select": "assets/audio/menu_select.wav",
    "scan": "assets/audio/scan.wav",
    "pickup": "assets/audio/pickup.wav",
    "generator": "assets/audio/generator.wav",
    "relay": "assets/audio/relay.wav",
    "creature_alert": "assets/audio/creature_alert.wav",
    "death": "assets/audio/death.wav",
    "shock_pulse": "assets/audio/shock_pulse.wav",
    "beacon": "assets/audio/beacon.wav",
    "projector": "assets/audio/projector.wav",
    "victory": "assets/audio/victory.wav",
}


class AssetManager:
    def __init__(self, project_root: Path | None = None, audio_available: bool = True) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[1]
        self.audio_available = audio_available
        self._image_cache: dict[str, pygame.Surface] = {}
        self._fallback_cache: dict[tuple[str, tuple[int, int]], pygame.Surface] = {}
        self._frame_cache: dict[str, list[pygame.Surface]] = {}
        self._animation_frame_cache: dict[tuple[str, str], list[pygame.Surface]] = {}
        self._scaled_cache: dict[tuple[str, tuple[int, int]], pygame.Surface] = {}
        self._outline_cache: dict[tuple[str, str, int, tuple[int, int, int, int]], list[pygame.Surface]] = {}
        self._image_outline_cache: dict[tuple[str, int, tuple[int, int, int, int]], pygame.Surface] = {}
        self._flipped_cache: dict[tuple[str, str], list[pygame.Surface]] = {}
        self._sound_cache: dict[str, PlayableSound] = {}
        self._warned_missing: set[str] = set()

    def asset_path(self, relative_path: str) -> Path:
        return self.project_root / relative_path

    def load_image(self, relative_path: str, fallback_size: tuple[int, int] = (48, 48)) -> pygame.Surface:
        if relative_path in self._image_cache:
            return self._image_cache[relative_path]

        path = self.asset_path(relative_path)
        if not path.exists():
            return self._missing_image(relative_path, fallback_size)

        image = pygame.image.load(str(path))
        if pygame.display.get_surface() is not None:
            image = image.convert_alpha()
        else:
            image = image.copy()
        self._image_cache[relative_path] = image
        return image

    def get_scaled_image(self, relative_path: str, size: tuple[int, int]) -> pygame.Surface:
        key = (relative_path, size)
        if key not in self._scaled_cache:
            source = self.load_image(relative_path, size)
            self._scaled_cache[key] = pygame.transform.scale(source, size)
        return self._scaled_cache[key]

    def get_sheet_frames(self, sheet_name: str) -> list[pygame.Surface]:
        if sheet_name not in self._frame_cache:
            metadata = SPRITESHEETS[sheet_name]
            sheet = self.load_image(metadata.path, self._sheet_size(metadata))
            frames: list[pygame.Surface] = []
            for row in range(metadata.rows):
                for column in range(metadata.columns):
                    rect = pygame.Rect(
                        column * metadata.frame_width,
                        row * metadata.frame_height,
                        metadata.frame_width,
                        metadata.frame_height,
                    )
                    frame = pygame.Surface((metadata.frame_width, metadata.frame_height), pygame.SRCALPHA)
                    frame.blit(sheet, (0, 0), rect)
                    if metadata.scale is not None:
                        frame = pygame.transform.scale(
                            frame,
                            (metadata.frame_width * metadata.scale, metadata.frame_height * metadata.scale),
                        )
                    frames.append(frame)
            self._frame_cache[sheet_name] = frames
        return self._frame_cache[sheet_name]

    def get_frames(self, sheet_name: str, animation_name: str | None = None) -> list[pygame.Surface]:
        if animation_name is None:
            return self.get_sheet_frames(sheet_name)

        key = (sheet_name, animation_name)
        if key not in self._animation_frame_cache:
            metadata = SPRITESHEETS[sheet_name]
            source_frames = self.get_sheet_frames(sheet_name)
            indices = metadata.animations[animation_name]
            self._animation_frame_cache[key] = [source_frames[index] for index in indices]
        return self._animation_frame_cache[key]

    def get_animation(
        self,
        sheet_name: str,
        animation_name: str,
        frame_duration: float | None = None,
        looping: bool = True,
    ) -> Animation:
        metadata = SPRITESHEETS[sheet_name]
        return Animation(
            self.get_frames(sheet_name, animation_name),
            frame_duration or metadata.default_frame_duration,
            looping=looping,
        )

    def get_outline_frames(
        self,
        sheet_name: str,
        animation_name: str | None = None,
        thickness: int = 1,
        color: tuple[int, int, int, int] = (72, 226, 255, 210),
    ) -> list[pygame.Surface]:
        cache_name = animation_name or "__all__"
        key = (sheet_name, cache_name, thickness, color)
        if key not in self._outline_cache:
            self._outline_cache[key] = [
                self.create_outline(frame, thickness=thickness, color=color)
                for frame in self.get_frames(sheet_name, animation_name)
            ]
        return self._outline_cache[key]

    def get_outline_image(
        self,
        relative_path: str,
        fallback_size: tuple[int, int] = (48, 48),
        thickness: int = 1,
        color: tuple[int, int, int, int] = (72, 226, 255, 210),
    ) -> pygame.Surface:
        key = (relative_path, thickness, color)
        if key not in self._image_outline_cache:
            self._image_outline_cache[key] = self.create_outline(
                self.load_image(relative_path, fallback_size),
                thickness=thickness,
                color=color,
            )
        return self._image_outline_cache[key]

    def get_flipped_frames(self, sheet_name: str, animation_name: str) -> list[pygame.Surface]:
        key = (sheet_name, animation_name)
        if key not in self._flipped_cache:
            self._flipped_cache[key] = [
                pygame.transform.flip(frame, True, False) for frame in self.get_frames(sheet_name, animation_name)
            ]
        return self._flipped_cache[key]

    def load_sound(self, sound_name: str) -> PlayableSound:
        if sound_name in self._sound_cache:
            return self._sound_cache[sound_name]

        if not self.audio_available:
            self._sound_cache[sound_name] = NoOpSound()
            return self._sound_cache[sound_name]

        relative_path = SOUND_PATHS.get(sound_name, f"assets/audio/{sound_name}.wav")
        path = self.asset_path(relative_path)
        if not path.exists():
            self._warn_missing(relative_path)
            self._sound_cache[sound_name] = NoOpSound()
            return self._sound_cache[sound_name]

        try:
            sound: PlayableSound = pygame.mixer.Sound(str(path))
        except pygame.error:
            sound = NoOpSound()
        self._sound_cache[sound_name] = sound
        return sound

    def create_outline(
        self,
        source: pygame.Surface,
        thickness: int = 1,
        color: tuple[int, int, int, int] = (72, 226, 255, 210),
    ) -> pygame.Surface:
        mask = pygame.mask.from_surface(source)
        outline_mask = pygame.Mask(source.get_size())

        for dx in range(-thickness, thickness + 1):
            for dy in range(-thickness, thickness + 1):
                if dx == 0 and dy == 0:
                    continue
                outline_mask.draw(mask, (dx, dy))
        outline_mask.erase(mask, (0, 0))
        return outline_mask.to_surface(setcolor=color, unsetcolor=(0, 0, 0, 0))

    def _missing_image(self, relative_path: str, size: tuple[int, int]) -> pygame.Surface:
        self._warn_missing(relative_path)
        key = (relative_path, size)
        if key not in self._fallback_cache:
            surface = pygame.Surface(size, pygame.SRCALPHA)
            surface.fill((220, 0, 180, 255))
            tile = 8
            for x in range(0, size[0], tile):
                for y in range(0, size[1], tile):
                    if (x // tile + y // tile) % 2 == 0:
                        pygame.draw.rect(surface, (10, 10, 10, 255), (x, y, tile, tile))
            pygame.draw.rect(surface, (255, 255, 255, 255), surface.get_rect(), 1)
            self._fallback_cache[key] = surface
        return self._fallback_cache[key]

    def _warn_missing(self, relative_path: str) -> None:
        if relative_path not in self._warned_missing:
            print(f"Warning: missing asset '{relative_path}', using fallback.")
            self._warned_missing.add(relative_path)

    def _sheet_size(self, metadata: SpriteSheetMetadata) -> tuple[int, int]:
        return (metadata.frame_width * metadata.columns, metadata.frame_height * metadata.rows)
