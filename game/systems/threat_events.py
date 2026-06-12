from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterable

import pygame

from game import settings


class ThreatSourceType(Enum):
    PLAYER_SCAN = auto()
    GENERATOR = auto()
    RELAY = auto()
    CONTAINMENT_CONTROL = auto()
    ECHO_CORE = auto()
    SHOCK_PULSE = auto()
    DECOY_BEACON = auto()
    SCAN_PROJECTOR = auto()


@dataclass
class ThreatEvent:
    event_id: int
    world_position: pygame.Vector2
    source_type: ThreatSourceType
    strength: float
    lifetime: float
    creation_time: float = 0.0
    age: float = 0.0
    source_entity_id: str | None = None
    floor_number: int | None = None
    scan_id: int | None = None

    @property
    def expired(self) -> bool:
        return self.age >= self.lifetime

    @property
    def remaining_lifetime(self) -> float:
        return max(0.0, self.lifetime - self.age)

    def relevance_for(
        self,
        world_position: pygame.Vector2 | tuple[float, float],
        *,
        hearing_radius: float = settings.CREATURE_HEARING_RADIUS,
    ) -> float:
        """Simple documented relevance: strength * age decay / distance factor."""
        if self.expired or self.lifetime <= 0.0:
            return 0.0
        position = pygame.Vector2(world_position)
        distance = position.distance_to(self.world_position)
        effective_radius = max(0.0, hearing_radius * max(0.1, self.strength))
        if distance > effective_radius:
            return 0.0
        age_decay = max(0.0, 1.0 - (self.age / self.lifetime))
        distance_factor = 1.0 + distance / max(1.0, settings.TILE_SIZE * 2.0)
        return self.strength * age_decay / distance_factor


class ThreatEventSystem:
    def __init__(self, max_events: int = settings.THREAT_EVENT_MAX_ACTIVE) -> None:
        self.max_events = max(1, max_events)
        self._events: list[ThreatEvent] = []
        self._next_event_id = 1

    @property
    def active_events(self) -> tuple[ThreatEvent, ...]:
        return tuple(event for event in self._events if not event.expired)

    def add_event(
        self,
        world_position: pygame.Vector2 | tuple[float, float],
        source_type: ThreatSourceType,
        *,
        strength: float | None = None,
        lifetime: float | None = None,
        creation_time: float = 0.0,
        source_entity_id: str | None = None,
        floor_number: int | None = None,
        scan_id: int | None = None,
    ) -> ThreatEvent:
        event = ThreatEvent(
            event_id=self._next_event_id,
            world_position=pygame.Vector2(world_position),
            source_type=source_type,
            strength=float(strength if strength is not None else self.default_strength(source_type)),
            lifetime=float(lifetime if lifetime is not None else self.default_lifetime(source_type)),
            creation_time=float(creation_time),
            source_entity_id=source_entity_id,
            floor_number=floor_number,
            scan_id=scan_id,
        )
        self._next_event_id += 1
        self._events.append(event)
        self._events = [active for active in self._events if not active.expired]
        if len(self._events) > self.max_events:
            del self._events[: len(self._events) - self.max_events]
        return event

    def add_player_scan(
        self,
        world_position: pygame.Vector2 | tuple[float, float],
        *,
        creation_time: float = 0.0,
        floor_number: int | None = None,
        scan_id: int | None = None,
    ) -> ThreatEvent:
        return self.add_event(
            world_position,
            ThreatSourceType.PLAYER_SCAN,
            strength=settings.THREAT_PLAYER_SCAN_STRENGTH,
            lifetime=settings.THREAT_PLAYER_SCAN_LIFETIME,
            creation_time=creation_time,
            floor_number=floor_number,
            scan_id=scan_id,
        )

    def update(self, dt: float, *, paused: bool = False) -> None:
        if paused:
            return
        dt = max(0.0, dt)
        for event in self._events:
            event.age += dt
        self._events = [event for event in self._events if not event.expired]

    def reset(self) -> None:
        self._events.clear()
        self._next_event_id = 1

    def get_event(self, event_id: int | None) -> ThreatEvent | None:
        if event_id is None:
            return None
        return next((event for event in self._events if event.event_id == event_id and not event.expired), None)

    def select_relevant_event(
        self,
        world_position: pygame.Vector2 | tuple[float, float],
        *,
        current_event_id: int | None = None,
        floor_number: int | None = None,
        hearing_radius: float = settings.CREATURE_HEARING_RADIUS,
        minimum_relevance: float = settings.CREATURE_THREAT_MIN_RELEVANCE,
        switch_hysteresis: float = settings.CREATURE_THREAT_SWITCH_HYSTERESIS,
    ) -> ThreatEvent | None:
        candidates = [
            event
            for event in self.active_events
            if floor_number is None or event.floor_number is None or event.floor_number == floor_number
        ]
        scored = [
            (event.relevance_for(world_position, hearing_radius=hearing_radius), event)
            for event in candidates
        ]
        scored = [(score, event) for score, event in scored if score >= minimum_relevance]
        if not scored:
            return None

        scored.sort(key=lambda item: (-item[0], item[1].age, item[1].event_id))
        best_score, best_event = scored[0]
        current_event = self.get_event(current_event_id)
        if current_event is None:
            return best_event

        current_score = current_event.relevance_for(world_position, hearing_radius=hearing_radius)
        if current_score < minimum_relevance:
            return best_event
        if best_event.event_id == current_event.event_id:
            return current_event
        if best_score >= current_score * (1.0 + switch_hysteresis):
            return best_event
        return current_event

    def source_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self.active_events:
            key = event.source_type.name
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def default_strength(source_type: ThreatSourceType) -> float:
        if source_type is ThreatSourceType.PLAYER_SCAN:
            return settings.THREAT_PLAYER_SCAN_STRENGTH
        return 1.0

    @staticmethod
    def default_lifetime(source_type: ThreatSourceType) -> float:
        if source_type is ThreatSourceType.PLAYER_SCAN:
            return settings.THREAT_PLAYER_SCAN_LIFETIME
        return settings.THREAT_DEFAULT_LIFETIME

    def extend(self, events: Iterable[ThreatEvent]) -> None:
        for event in events:
            if not event.expired:
                self._events.append(event)
        if len(self._events) > self.max_events:
            del self._events[: len(self._events) - self.max_events]
