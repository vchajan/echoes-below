from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

import pygame

from game import settings
from game.camera import Camera
from game.systems.raycasting import TileFloor, has_line_of_sight
from game.systems.scan import ScanWaveStep
from game.world.blockers import DynamicBlockerRegistry


class ScanDetectable(Protocol):
    unique_id: str
    scan_category: str
    scan_active: bool

    @property
    def scan_position(self) -> pygame.Vector2: ...

    def capture_scan_outline(self) -> pygame.Surface: ...


@dataclass
class EchoSnapshot:
    source_id: str
    category: str
    scan_id: int
    world_position: pygame.Vector2
    image: pygame.Surface
    lifetime: float
    age: float = 0.0
    facing: str | None = None

    @classmethod
    def capture(
        cls,
        entity: ScanDetectable,
        scan_id: int,
        lifetime: float,
        *,
        facing: str | None = None,
    ) -> "EchoSnapshot":
        return cls(
            source_id=entity.unique_id,
            category=entity.scan_category,
            scan_id=scan_id,
            world_position=pygame.Vector2(entity.scan_position),
            image=entity.capture_scan_outline().copy(),
            lifetime=lifetime,
            facing=facing,
        )

    @property
    def expired(self) -> bool:
        return self.age >= self.lifetime

    @property
    def alpha(self) -> int:
        if self.lifetime <= 0:
            return 0
        fraction = max(0.0, min(1.0, 1.0 - self.age / self.lifetime))
        return round(255 * fraction * fraction)

    @property
    def visual_rect(self) -> pygame.Rect:
        return self.image.get_rect(center=(round(self.world_position.x), round(self.world_position.y)))


@dataclass
class SnapshotDiagnostics:
    evaluated_entities: int = 0
    visible_entities: int = 0
    blocked_entities: int = 0
    active_snapshots: int = 0




def wave_intersects_moving_distance(
    previous_radius: float,
    current_radius: float,
    previous_distance: float,
    current_distance: float,
    *,
    epsilon: float = 1e-7,
) -> bool:
    """Return True when an expanding front and a moving radial target intersect.

    Comparing relative distance catches both cases required by the game:
    the front overtakes a target, or a fast target crosses outward through
    the front between updates. A target that was already behind the front
    and remains there is not evaluated late.
    """
    previous_relative = previous_distance - previous_radius
    current_relative = current_distance - current_radius
    if abs(previous_relative) <= epsilon or abs(current_relative) <= epsilon:
        return True
    return (previous_relative > 0 > current_relative) or (previous_relative < 0 < current_relative)


class EchoSnapshotSystem:
    """Captures scan-detectable entities exactly when the wave front overtakes them."""

    def __init__(self, default_lifetime: float = settings.OBJECT_SNAPSHOT_LIFETIME) -> None:
        self.default_lifetime = default_lifetime
        self.snapshots: list[EchoSnapshot] = []
        self._evaluated_by_scan: dict[int, set[str]] = {}
        self._previous_distances: dict[tuple[int, str], float] = {}
        self.diagnostics = SnapshotDiagnostics()

    def update(
        self,
        dt: float,
        wave_step: ScanWaveStep | None,
        entities: Iterable[ScanDetectable],
        floor: TileFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
        tile_size: int,
    ) -> None:
        dt = max(0.0, dt)
        for snapshot in self.snapshots:
            snapshot.age += dt
        self.snapshots = [snapshot for snapshot in self.snapshots if not snapshot.expired]
        self.diagnostics.active_snapshots = len(self.snapshots)

        if wave_step is None:
            return

        evaluated = self._evaluated_by_scan.setdefault(wave_step.scan_id, set())
        self._prune_scan_state(wave_step.scan_id)

        for entity in entities:
            if not entity.scan_active or entity.unique_id in evaluated:
                continue
            key = (wave_step.scan_id, entity.unique_id)
            current_distance = pygame.Vector2(entity.scan_position).distance_to(wave_step.origin)
            previous_distance = self._previous_distances.get(key, current_distance)
            self._previous_distances[key] = current_distance

            if not wave_intersects_moving_distance(
                wave_step.previous_radius,
                wave_step.current_radius,
                previous_distance,
                current_distance,
            ):
                continue

            evaluated.add(entity.unique_id)
            self.diagnostics.evaluated_entities += 1
            if not has_line_of_sight(
                wave_step.origin,
                entity.scan_position,
                floor,
                dynamic_blockers,
                tile_size,
            ):
                self.diagnostics.blocked_entities += 1
                continue

            facing = getattr(entity, "facing", None)
            lifetime = float(getattr(entity, "snapshot_lifetime", self.default_lifetime))
            self.snapshots.append(
                EchoSnapshot.capture(entity, wave_step.scan_id, lifetime, facing=facing)
            )
            self.diagnostics.visible_entities += 1
            self.diagnostics.active_snapshots = len(self.snapshots)

    def reset(self) -> None:
        self.snapshots.clear()
        self._evaluated_by_scan.clear()
        self._previous_distances.clear()
        self.diagnostics = SnapshotDiagnostics()

    def snapshots_for_source(self, source_id: str) -> list[EchoSnapshot]:
        return [snapshot for snapshot in self.snapshots if snapshot.source_id == source_id]

    def processed_ids_for_scan(self, scan_id: int) -> frozenset[str]:
        return frozenset(self._evaluated_by_scan.get(scan_id, set()))

    def snapshot_count_for_category(self, category: str) -> int:
        return sum(1 for snapshot in self.snapshots if snapshot.category == category)

    def _prune_scan_state(self, newest_scan_id: int) -> None:
        minimum_scan_id = max(0, newest_scan_id - 3)
        self._evaluated_by_scan = {
            scan_id: values
            for scan_id, values in self._evaluated_by_scan.items()
            if scan_id >= minimum_scan_id
        }
        self._previous_distances = {
            key: distance
            for key, distance in self._previous_distances.items()
            if key[0] >= minimum_scan_id
        }


class EchoSnapshotRenderer:
    def render(self, target: pygame.Surface, snapshots: Iterable[EchoSnapshot], camera: Camera) -> None:
        screen_rect = target.get_rect()
        for snapshot in snapshots:
            world_rect = snapshot.visual_rect
            screen_snapshot_rect = camera.world_rect_to_screen(world_rect)
            if not screen_rect.colliderect(screen_snapshot_rect):
                continue
            snapshot.image.set_alpha(snapshot.alpha)
            target.blit(snapshot.image, screen_snapshot_rect, special_flags=pygame.BLEND_RGBA_ADD)

    def render_debug(
        self,
        target: pygame.Surface,
        snapshots: Iterable[EchoSnapshot],
        camera: Camera,
        font: pygame.font.Font | None = None,
    ) -> None:
        for snapshot in snapshots:
            position = tuple(round(value) for value in camera.world_to_screen(snapshot.world_position))
            pygame.draw.circle(target, (255, 210, 80), position, 5, 1)
            if font is not None:
                label = font.render(
                    f"{snapshot.category}:{snapshot.source_id} a={snapshot.alpha}",
                    True,
                    (255, 210, 80),
                )
                target.blit(label, (position[0] + 6, position[1] - 9))
