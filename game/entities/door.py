from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

import pygame

from game import settings
from game.animation import Animation
from game.assets import AssetManager
from game.world.floor import DoorwayCandidate


class DoorType(Enum):
    POWERED = "powered"
    SECURITY = "security"
    CONTAINMENT = "containment"


class DoorState(Enum):
    LOCKED = "locked"
    CLOSED = "closed"
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"
    WEDGED_OPEN = "wedged_open"
    WEDGED_CLOSED = "wedged_closed"


@dataclass(frozen=True)
class DoorBlockingProfile:
    movement: bool
    creature_movement: bool
    scan: bool
    line_of_sight: bool


class DynamicDoor(pygame.sprite.Sprite):
    def __init__(
        self,
        door_id: str,
        door_type: DoorType,
        doorway: DoorwayCandidate,
        assets: AssetManager,
        tile_size: int,
        powered: bool = True,
    ) -> None:
        super().__init__()
        self.door_id = door_id
        self.door_type = door_type
        self.tile = doorway.tile
        self.room_id = doorway.room_id
        self.connected_room_id = doorway.connected_room_id
        self.edge = doorway.edge
        self.orientation = doorway.orientation
        self.tile_size = tile_size
        self.powered = powered
        self.close_delay = settings.DOOR_CLOSE_DELAY
        self.close_timer = settings.DOOR_CLOSE_DELAY
        self.wedge_remaining: float | None = None

        self.world_center = pygame.Vector2((self.tile[0] + 0.5) * tile_size, (self.tile[1] + 0.5) * tile_size)
        self.world_position = self.world_center
        self.scan_position = self.world_center
        self.scan_category = f"door:{door_type.value}"
        self.scan_active = True
        self.collision_rect = self._make_collision_rect()
        self.approach_rect = self._make_approach_rect()
        self.interaction_rect = self.approach_rect.copy()

        self._animations = self._build_animations(assets)
        self.state = DoorState.CLOSED if door_type is DoorType.POWERED else DoorState.LOCKED
        self.image = self._image_for_state()
        self.visual_rect = self.image.get_rect(center=self._rounded_world_center())
        self.rect = self.visual_rect

    @property
    def unique_id(self) -> str:
        return self.door_id

    @property
    def is_fully_open(self) -> bool:
        return self.state in (DoorState.OPEN, DoorState.WEDGED_OPEN)

    @property
    def is_fully_closed(self) -> bool:
        return self.state in (DoorState.CLOSED, DoorState.LOCKED, DoorState.WEDGED_CLOSED)

    @property
    def is_locked(self) -> bool:
        return self.state is DoorState.LOCKED

    @property
    def is_wedged(self) -> bool:
        return self.state in (DoorState.WEDGED_OPEN, DoorState.WEDGED_CLOSED)

    @property
    def blocks_player(self) -> bool:
        return self.blocking_profile().movement

    @property
    def blocks_creatures(self) -> bool:
        return self.blocking_profile().creature_movement

    @property
    def blocks_scan(self) -> bool:
        return self.blocking_profile().scan

    @property
    def blocks_line_of_sight(self) -> bool:
        return self.blocking_profile().line_of_sight

    @property
    def current_frame(self) -> pygame.Surface:
        return self.image

    @property
    def animation_frame_index(self) -> int:
        return self._animations[self._animation_key_for_state()].frame_index

    def capture_scan_outline(self) -> pygame.Surface:
        return self.image

    def blocking_profile(self) -> DoorBlockingProfile:
        blocked = self.state not in (DoorState.OPEN, DoorState.WEDGED_OPEN)
        return DoorBlockingProfile(
            movement=blocked,
            creature_movement=blocked,
            scan=blocked,
            line_of_sight=blocked,
        )

    def blocks_purpose(self, purpose: object) -> bool:
        name = getattr(purpose, "value", purpose)
        profile = self.blocking_profile()
        if name == "movement":
            return profile.movement
        if name == "creature_movement":
            return profile.creature_movement
        if name == "scan":
            return profile.scan
        if name == "line_of_sight":
            return profile.line_of_sight
        return profile.movement

    def update(
        self,
        dt: float,
        player_rect: pygame.Rect | None = None,
        other_entity_rects: Iterable[pygame.Rect] = (),
        floor_powered: bool = True,
    ) -> None:
        entity_rects = [rect for rect in (player_rect, *tuple(other_entity_rects)) if rect is not None]

        if self.is_wedged:
            if self.wedge_remaining is not None:
                self.wedge_remaining = max(0.0, self.wedge_remaining - max(0.0, dt))
                if self.wedge_remaining <= 0.0:
                    self.remove_wedge()
                else:
                    self._refresh_image()
                    return
            else:
                self._refresh_image()
                return
        if self.state is DoorState.LOCKED:
            self._refresh_image()
            return

        if self.state is DoorState.CLOSED:
            if self._can_auto_open(floor_powered) and self._approach_occupied(entity_rects):
                self.begin_opening()
        elif self.state is DoorState.OPENING:
            self._animations["opening"].update(dt)
            if self._animations["opening"].is_complete:
                self.state = DoorState.OPEN
                self.close_timer = self.close_delay
        elif self.state is DoorState.OPEN:
            if self._approach_or_doorway_occupied(entity_rects):
                self.close_timer = self.close_delay
            else:
                self.close_timer -= dt
                if self.close_timer <= 0 and not self._doorway_occupied(entity_rects):
                    self.begin_closing()
        elif self.state is DoorState.CLOSING:
            if self._approach_or_doorway_occupied(entity_rects) and self._can_auto_open(floor_powered):
                self.begin_opening()
            elif self._doorway_occupied(entity_rects):
                self.state = DoorState.OPEN
                self.close_timer = self.close_delay
            else:
                self._animations["closing"].update(dt)
                if self._animations["closing"].is_complete:
                    self.state = DoorState.CLOSED
                    self.close_timer = self.close_delay

        self._refresh_image()

    def unlock_security(self) -> bool:
        if self.door_type is not DoorType.SECURITY:
            return False
        return self._unlock()

    def unlock_containment(self) -> bool:
        if self.door_type is not DoorType.CONTAINMENT:
            return False
        return self._unlock()

    def unlock(self) -> bool:
        if self.door_type is DoorType.SECURITY:
            return self.unlock_security()
        if self.door_type is DoorType.CONTAINMENT:
            return self.unlock_containment()
        return False

    def lock(self) -> bool:
        if self.door_type is DoorType.POWERED:
            return False
        if self.state in (DoorState.OPENING, DoorState.CLOSING, DoorState.WEDGED_OPEN, DoorState.WEDGED_CLOSED):
            return False
        self.state = DoorState.LOCKED
        self.close_timer = self.close_delay
        self._refresh_image()
        return True

    def set_powered(self, powered: bool) -> None:
        self.powered = powered

    def begin_opening(self) -> bool:
        if self.state in (DoorState.LOCKED, DoorState.OPEN, DoorState.WEDGED_OPEN, DoorState.WEDGED_CLOSED):
            return False
        self.state = DoorState.OPENING
        self._animations["opening"].reset()
        self._refresh_image()
        return True

    def begin_closing(self) -> bool:
        if self.state not in (DoorState.OPEN, DoorState.OPENING):
            return False
        self.state = DoorState.CLOSING
        self._animations["closing"].reset()
        self._refresh_image()
        return True

    def force_open(self) -> None:
        self.state = DoorState.OPEN
        self.close_timer = self.close_delay
        self._refresh_image()

    def force_closed(self) -> None:
        self.state = DoorState.CLOSED
        self.close_timer = self.close_delay
        self._refresh_image()

    def wedge(self, duration: float | None = None) -> bool:
        if self.state is DoorState.OPEN:
            self.state = DoorState.WEDGED_OPEN
        elif self.state is DoorState.CLOSED:
            self.state = DoorState.WEDGED_CLOSED
        else:
            return False
        self.wedge_remaining = duration
        self._refresh_image()
        return True

    def remove_wedge(self) -> bool:
        if self.state is DoorState.WEDGED_OPEN:
            self.state = DoorState.OPEN
        elif self.state is DoorState.WEDGED_CLOSED:
            self.state = DoorState.CLOSED
        else:
            return False
        self.wedge_remaining = None
        self._refresh_image()
        return True

    def debug_toggle_open_closed(self) -> None:
        if self.state in (DoorState.OPEN, DoorState.OPENING, DoorState.WEDGED_OPEN):
            self.force_closed()
        elif self.state is DoorState.LOCKED:
            self.unlock()
            self.force_open()
        else:
            self.force_open()

    def _unlock(self) -> bool:
        if self.state is DoorState.LOCKED:
            self.state = DoorState.CLOSED
            self.close_timer = self.close_delay
            self._refresh_image()
        return True

    def _can_auto_open(self, floor_powered: bool) -> bool:
        return self.powered and floor_powered and self.state is not DoorState.LOCKED

    def _approach_occupied(self, rects: Iterable[pygame.Rect]) -> bool:
        return any(self.approach_rect.colliderect(rect) for rect in rects)

    def _doorway_occupied(self, rects: Iterable[pygame.Rect]) -> bool:
        return any(self.collision_rect.colliderect(rect) for rect in rects)

    def _approach_or_doorway_occupied(self, rects: Iterable[pygame.Rect]) -> bool:
        return any(self.approach_rect.colliderect(rect) or self.collision_rect.colliderect(rect) for rect in rects)

    def _make_collision_rect(self) -> pygame.Rect:
        tile_rect = pygame.Rect(self.tile[0] * self.tile_size, self.tile[1] * self.tile_size, self.tile_size, self.tile_size)
        thickness = settings.DOOR_COLLISION_THICKNESS
        if self.orientation == "vertical_door_plane":
            rect = pygame.Rect(0, 0, thickness, self.tile_size)
        else:
            rect = pygame.Rect(0, 0, self.tile_size, thickness)
        rect.center = tile_rect.center
        return rect

    def _make_approach_rect(self) -> pygame.Rect:
        tile_rect = pygame.Rect(self.tile[0] * self.tile_size, self.tile[1] * self.tile_size, self.tile_size, self.tile_size)
        distance = settings.DOOR_APPROACH_TILES * self.tile_size
        if self.orientation == "vertical_door_plane":
            return tile_rect.inflate(distance * 2, self.tile_size)
        return tile_rect.inflate(self.tile_size, distance * 2)

    def _build_animations(self, assets: AssetManager) -> dict[str, Animation]:
        sheet_name = {
            DoorType.POWERED: "powered_door",
            DoorType.SECURITY: "security_door",
            DoorType.CONTAINMENT: "containment_door",
        }[self.door_type]
        closed_name = {
            DoorType.POWERED: "closed",
            DoorType.SECURITY: "unlocked",
            DoorType.CONTAINMENT: "powered",
        }[self.door_type]
        locked_name = "locked" if self.door_type is not DoorType.POWERED else closed_name

        def oriented(animation_name: str) -> list[pygame.Surface]:
            if self.orientation == "horizontal_door_plane":
                return assets.get_rotated_frames(sheet_name, animation_name, 90)
            return assets.get_frames(sheet_name, animation_name)

        opening = oriented("opening")
        if self.door_type is DoorType.POWERED:
            closing = oriented("closing")
        else:
            closing = list(reversed(opening))
        return {
            "locked": Animation(oriented(locked_name), settings.DOOR_OPEN_FRAME_DURATION, looping=False),
            "closed": Animation(oriented(closed_name), settings.DOOR_OPEN_FRAME_DURATION, looping=False),
            "opening": Animation(opening, settings.DOOR_OPEN_FRAME_DURATION, looping=False),
            "open": Animation(oriented("open"), settings.DOOR_OPEN_FRAME_DURATION, looping=False),
            "closing": Animation(closing, settings.DOOR_OPEN_FRAME_DURATION, looping=False),
        }

    def _animation_key_for_state(self) -> str:
        if self.state is DoorState.LOCKED:
            return "locked"
        if self.state in (DoorState.CLOSED, DoorState.WEDGED_CLOSED):
            return "closed"
        if self.state is DoorState.OPENING:
            return "opening"
        if self.state in (DoorState.OPEN, DoorState.WEDGED_OPEN):
            return "open"
        if self.state is DoorState.CLOSING:
            return "closing"
        return "closed"

    def _image_for_state(self) -> pygame.Surface:
        return self._animations[self._animation_key_for_state()].current_frame

    def _refresh_image(self) -> None:
        center = self.visual_rect.center if hasattr(self, "visual_rect") else self._rounded_world_center()
        self.image = self._image_for_state()
        self.visual_rect = self.image.get_rect(center=center)
        self.rect = self.visual_rect

    def _rounded_world_center(self) -> tuple[int, int]:
        return (round(self.world_center.x), round(self.world_center.y))
