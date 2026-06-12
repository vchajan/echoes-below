from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Iterable

import pygame

from game import settings
from game.camera import Camera
from game.systems.raycasting import RayHit, TileFloor, cast_rays
from game.world.blockers import DynamicBlockerRegistry


@dataclass(frozen=True)
class ScanConfig:
    ray_count: int = settings.SCAN_RAY_COUNT
    max_radius: float = settings.SCAN_MAX_RADIUS
    wave_speed: float = settings.SCAN_WAVE_SPEED
    cooldown: float = settings.SCAN_COOLDOWN
    trace_lifetime: float = settings.STATIC_TRACE_LIFETIME
    point_radius: int = settings.SCAN_POINT_RADIUS
    connection_max_gap: float = settings.SCAN_LINE_MAX_GAP
    connection_max_distance_delta: float = settings.SCAN_LINE_MAX_DISTANCE_DELTA
    dedupe_quantum: float = settings.SCAN_TRACE_DEDUPE_QUANTUM


@dataclass(frozen=True)
class ScanThreatEvent:
    origin: tuple[float, float]
    source_type: str
    strength: float
    session_time: float
    scan_id: int


@dataclass
class ScanTrace:
    hit: RayHit
    lifetime: float
    age: float = 0.0

    @property
    def expired(self) -> bool:
        return self.age >= self.lifetime

    @property
    def alpha(self) -> int:
        if self.lifetime <= 0:
            return 0
        fraction = max(0.0, min(1.0, 1.0 - self.age / self.lifetime))
        # Smooth fade gives a bright initial echo without a separate hold timer.
        return round(255 * fraction * fraction)


@dataclass
class ScanWave:
    scan_id: int
    origin: pygame.Vector2
    hits: list[RayHit]
    max_radius: float
    wave_speed: float
    current_radius: float = 0.0
    previous_radius: float = 0.0
    pending_index: int = 0
    active: bool = True

    def update_radius(self, dt: float) -> None:
        self.previous_radius = self.current_radius
        self.current_radius = min(self.max_radius, self.current_radius + self.wave_speed * max(0.0, dt))
        if self.current_radius >= self.max_radius:
            self.active = False




@dataclass(frozen=True)
class ScanWaveStep:
    scan_id: int
    origin: pygame.Vector2
    previous_radius: float
    current_radius: float
    max_radius: float

@dataclass
class ScanDiagnostics:
    last_raycast_ms: float = 0.0
    max_raycast_ms: float = 0.0
    raw_hit_count: int = 0
    deduplicated_hit_count: int = 0
    last_dynamic_door_count: int = 0
    segments_drawn: int = 0


class ScanSystem:
    def __init__(self, config: ScanConfig | None = None) -> None:
        self.config = config or ScanConfig()
        self.active_wave: ScanWave | None = None
        self.traces: list[ScanTrace] = []
        self.cooldown_remaining = 0.0
        self._next_scan_id = 1
        self._revealed_keys: set[tuple[int, int, int, str, str | None]] = set()
        self.threat_events: list[ScanThreatEvent] = []
        self.diagnostics = ScanDiagnostics()
        self.last_wave_step: ScanWaveStep | None = None

    @property
    def ready(self) -> bool:
        return self.cooldown_remaining <= 0.0

    @property
    def cooldown_fraction(self) -> float:
        if self.config.cooldown <= 0:
            return 0.0
        return max(0.0, min(1.0, self.cooldown_remaining / self.config.cooldown))

    def trigger(
        self,
        origin: pygame.Vector2 | tuple[float, float],
        floor: TileFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
        tile_size: int,
        *,
        session_time: float = 0.0,
    ) -> bool:
        if not self.ready:
            return False

        scan_id = self._next_scan_id
        self._next_scan_id += 1
        fixed_origin = pygame.Vector2(origin)

        started = time.perf_counter()
        raw_hits = cast_rays(
            fixed_origin,
            floor,
            dynamic_blockers,
            tile_size,
            self.config.max_radius,
            self.config.ray_count,
            scan_id=scan_id,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        hits = self._deduplicate_hits(raw_hits)
        hits.sort(key=lambda hit: (hit.distance, hit.ray_index))

        self.active_wave = ScanWave(
            scan_id=scan_id,
            origin=fixed_origin,
            hits=hits,
            max_radius=self.config.max_radius,
            wave_speed=self.config.wave_speed,
        )
        self.cooldown_remaining = self.config.cooldown
        self._revealed_keys.clear()
        self.threat_events.append(
            ScanThreatEvent(
                origin=(float(fixed_origin.x), float(fixed_origin.y)),
                source_type="player_scan",
                strength=1.0,
                session_time=session_time,
                scan_id=scan_id,
            )
        )
        if len(self.threat_events) > 32:
            del self.threat_events[:-32]

        self.diagnostics.last_raycast_ms = elapsed_ms
        self.diagnostics.max_raycast_ms = max(self.diagnostics.max_raycast_ms, elapsed_ms)
        self.diagnostics.raw_hit_count = len(raw_hits)
        self.diagnostics.deduplicated_hit_count = len(hits)
        self.diagnostics.last_dynamic_door_count = len(dynamic_blockers.doors) if dynamic_blockers else 0
        return True

    def update(self, dt: float) -> None:
        dt = max(0.0, dt)
        self.last_wave_step = None
        self.cooldown_remaining = max(0.0, self.cooldown_remaining - dt)

        for trace in self.traces:
            trace.age += dt
        self.traces = [trace for trace in self.traces if not trace.expired]

        wave = self.active_wave
        if wave is None:
            return

        wave.update_radius(dt)
        self.last_wave_step = ScanWaveStep(
            scan_id=wave.scan_id,
            origin=wave.origin.copy(),
            previous_radius=wave.previous_radius,
            current_radius=wave.current_radius,
            max_radius=wave.max_radius,
        )
        while wave.pending_index < len(wave.hits):
            hit = wave.hits[wave.pending_index]
            if hit.distance > wave.current_radius + 1e-7:
                break
            wave.pending_index += 1
            if hit.distance + 1e-7 < wave.previous_radius:
                continue
            key = self._trace_key(hit)
            if key in self._revealed_keys:
                continue
            self._revealed_keys.add(key)
            self.traces.append(ScanTrace(hit=hit, lifetime=self.config.trace_lifetime))

        if not wave.active and wave.pending_index >= len(wave.hits):
            # Keep the completed wave object only as long as the front is relevant.
            self.active_wave = None

    def reset(self) -> None:
        self.active_wave = None
        self.traces.clear()
        self.cooldown_remaining = 0.0
        self._revealed_keys.clear()
        self.threat_events.clear()
        self.diagnostics = ScanDiagnostics()
        self.last_wave_step = None

    def _trace_key(self, hit: RayHit) -> tuple[int, int, int, str, str | None]:
        quantum = max(0.5, self.config.dedupe_quantum)
        return (
            hit.scan_id,
            round(hit.world_position[0] / quantum),
            round(hit.world_position[1] / quantum),
            hit.category,
            hit.blocker_id,
        )

    def _deduplicate_hits(self, hits: Iterable[RayHit]) -> list[RayHit]:
        unique: dict[tuple[int, int, int, str, str | None], RayHit] = {}
        for hit in hits:
            key = self._trace_key(hit)
            existing = unique.get(key)
            if existing is None or hit.distance < existing.distance:
                unique[key] = hit
        return list(unique.values())


def can_connect_hits(
    first: RayHit,
    second: RayHit,
    *,
    max_gap: float,
    max_distance_delta: float,
) -> bool:
    if first.scan_id != second.scan_id:
        return False
    if second.ray_index - first.ray_index != 1:
        return False
    if first.category != second.category or first.blocker_id != second.blocker_id:
        return False
    if first.side != second.side or first.side == "corner":
        return False
    if abs(first.distance - second.distance) > max_distance_delta:
        return False
    if pygame.Vector2(first.world_position).distance_to(second.world_position) > max_gap:
        return False

    if first.blocker_id is not None:
        return True
    first_x, first_y = first.tile
    second_x, second_y = second.tile
    if first.side == "vertical":
        return first_x == second_x and abs(first_y - second_y) <= 1
    if first.side == "horizontal":
        return first_y == second_y and abs(first_x - second_x) <= 1
    return first.tile == second.tile


def trace_segments(traces: Iterable[ScanTrace], config: ScanConfig) -> list[tuple[ScanTrace, ScanTrace]]:
    by_scan: dict[int, list[ScanTrace]] = {}
    for trace in traces:
        by_scan.setdefault(trace.hit.scan_id, []).append(trace)

    segments: list[tuple[ScanTrace, ScanTrace]] = []
    for scan_traces in by_scan.values():
        ordered = sorted(scan_traces, key=lambda trace: trace.hit.ray_index)
        for first, second in zip(ordered, ordered[1:]):
            if can_connect_hits(
                first.hit,
                second.hit,
                max_gap=config.connection_max_gap,
                max_distance_delta=config.connection_max_distance_delta,
            ):
                segments.append((first, second))
    return segments


class ScanRenderer:
    def __init__(self, viewport_size: tuple[int, int]) -> None:
        self.surface = pygame.Surface(viewport_size, pygame.SRCALPHA)

    def render(self, target: pygame.Surface, scan: ScanSystem, camera: Camera) -> None:
        self.surface.fill((0, 0, 0, 0))
        screen_rect = self.surface.get_rect()
        visible_traces = [
            trace
            for trace in scan.traces
            if screen_rect.collidepoint(tuple(round(v) for v in camera.world_to_screen(trace.hit.world_position)))
        ]

        segments = trace_segments(visible_traces, scan.config)
        for first, second in segments:
            alpha = min(first.alpha, second.alpha)
            color = (70, 235, 255, alpha)
            start = tuple(round(v) for v in camera.world_to_screen(first.hit.world_position))
            end = tuple(round(v) for v in camera.world_to_screen(second.hit.world_position))
            pygame.draw.line(self.surface, color, start, end, 2)

        for trace in visible_traces:
            position = tuple(round(v) for v in camera.world_to_screen(trace.hit.world_position))
            pygame.draw.circle(
                self.surface,
                (100, 245, 255, trace.alpha),
                position,
                scan.config.point_radius,
            )

        wave = scan.active_wave
        if wave is not None and wave.active:
            center = tuple(round(v) for v in camera.world_to_screen(wave.origin))
            radius = round(wave.current_radius)
            if radius > 0:
                pygame.draw.circle(self.surface, (60, 220, 245, 110), center, radius, 2)
                pygame.draw.circle(self.surface, (120, 250, 255, 42), center, max(1, radius - 3), 1)

        scan.diagnostics.segments_drawn = len(segments)
        target.blit(self.surface, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

    def render_debug(
        self,
        target: pygame.Surface,
        scan: ScanSystem,
        camera: Camera,
        *,
        sample_every: int = 60,
        font: pygame.font.Font | None = None,
    ) -> None:
        wave = scan.active_wave
        if wave is None:
            return
        origin = tuple(round(v) for v in camera.world_to_screen(wave.origin))
        pygame.draw.circle(target, (255, 255, 255), origin, 5, 1)
        for hit in wave.hits:
            if hit.ray_index % max(1, sample_every) != 0:
                continue
            point = tuple(round(v) for v in camera.world_to_screen(hit.world_position))
            pygame.draw.line(target, (90, 170, 190), origin, point, 1)
            pygame.draw.circle(target, (255, 220, 80), point, 3)
            if font is not None:
                label_text = hit.category if hit.blocker_id is None else f"{hit.category}:{hit.blocker_id}"
                label = font.render(label_text, True, (255, 220, 80))
                target.blit(label, (point[0] + 4, point[1] - 9))
