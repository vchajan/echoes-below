from __future__ import annotations

from enum import Enum, auto
import random
import time
from typing import TYPE_CHECKING

import pygame

from game import settings
from game.systems.raycasting import has_line_of_sight
from game.systems.threat_events import ThreatEvent, ThreatEventSystem
from game.world import navigation
from game.world.blockers import BlockerPurpose, DynamicBlockerRegistry

if TYPE_CHECKING:
    from game.entities.creature import Creature
    from game.entities.player import Player
    from game.world.floor import GeneratedFloor


class CreatureState(Enum):
    PATROL = auto()
    INVESTIGATE = auto()
    SEARCH = auto()
    CHASE = auto()
    STUNNED = auto()


class CreatureAI:
    def __init__(
        self,
        creature: Creature,
        rng: random.Random,
        *,
        floor_number: int | None = None,
        creature_index: int = 0,
    ) -> None:
        self.creature = creature
        self.rng = rng
        self.floor_number = floor_number
        self.creature_index = creature_index

        self.state = CreatureState.PATROL
        self.previous_state = CreatureState.PATROL
        self.state_timer = 0.0
        self.transition_reason = "spawn"
        self.state_before_stun = CreatureState.PATROL

        self.current_path_index = 0
        self.current_target_position: pygame.Vector2 | None = None
        self.current_target_tile: tuple[int, int] | None = None
        self.current_patrol_target: tuple[int, int] | None = None
        self.investigation_target_position: pygame.Vector2 | None = None
        self.investigation_target_tile: tuple[int, int] | None = None
        self.search_centre: pygame.Vector2 | None = None
        self.search_centre_tile: tuple[int, int] | None = None
        self.search_points: list[tuple[int, int]] = []
        self.last_known_player_position: pygame.Vector2 | None = None
        self.last_known_player_tile: tuple[int, int] | None = None
        self.time_since_player_was_visible = 999.0
        self.stun_timer = 0.0
        self.next_permitted_pathfinding_time = 0.0
        self.pathfinding_call_count = 0
        self.selected_threat_event_id: int | None = None
        self.selected_threat_creation_time: float | None = None

        self.pathfinding_calls_this_session = 0
        self.last_pathfinding_ms = 0.0
        self.max_pathfinding_ms = 0.0
        self.perception_check_count = 0
        self.last_perception_result = False
        self.last_los_result = False
        self.last_perception_distance = 0.0
        self.last_path_reason = "none"
        self.current_path_target: tuple[int, int] | None = None

        self._time = 0.0
        self._perception_cooldown = (creature_index % 3) * (settings.CREATURE_PERCEPTION_INTERVAL / 3.0)
        self._threat_cooldown = 0.0
        self._stuck_elapsed = 0.0
        self._last_world_position = creature.world_position.copy()
        self._patrol_candidates: list[tuple[int, int]] | None = None
        self._patrol_history: list[tuple[int, int]] = []
        self._path_invalid = False

    @property
    def current_path(self) -> list[tuple[int, int]]:
        return self.creature.current_path

    @current_path.setter
    def current_path(self, value: list[tuple[int, int]]) -> None:
        self.creature.current_path = value
        self.current_path_index = 0

    @property
    def current_path_length(self) -> int:
        return len(self.current_path)

    def reset(self) -> None:
        self.change_state(CreatureState.PATROL, "reset")
        self.creature.current_path.clear()
        self.creature.current_waypoint = None
        self.current_path_index = 0
        self.current_target_position = None
        self.current_target_tile = None
        self.current_patrol_target = None
        self.investigation_target_position = None
        self.investigation_target_tile = None
        self.search_centre = None
        self.search_centre_tile = None
        self.search_points = []
        self.last_known_player_position = None
        self.last_known_player_tile = None
        self.time_since_player_was_visible = 999.0
        self.stun_timer = 0.0
        self.state_before_stun = CreatureState.PATROL
        self.next_permitted_pathfinding_time = 0.0
        self.pathfinding_call_count = 0
        self.pathfinding_calls_this_session = 0
        self.selected_threat_event_id = None
        self.selected_threat_creation_time = None
        self.current_path_target = None
        self._path_invalid = False
        self._stuck_elapsed = 0.0

    def on_creature_repositioned(self) -> None:
        self.creature.current_path.clear()
        self.current_path_index = 0
        self.current_path_target = None
        self._path_invalid = True
        self._stuck_elapsed = 0.0
        self._last_world_position = self.creature.world_position.copy()

    def change_state(self, new_state: CreatureState, reason: str) -> None:
        if new_state is self.state:
            self.transition_reason = reason
            return
        self.previous_state = self.state
        self.state = new_state
        self.state_timer = 0.0
        self.transition_reason = reason

    def apply_stun(self, duration: float) -> None:
        if duration <= 0.0:
            raise ValueError("stun duration must be positive")
        if self.state is not CreatureState.STUNNED:
            self.state_before_stun = self.state
        self.stun_timer = max(self.stun_timer, float(duration))
        self.creature.velocity.update(0, 0)
        self.creature.moving = False
        self.change_state(CreatureState.STUNNED, "stunned")

    def update(
        self,
        dt: float,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None = None,
        *,
        player: Player | None = None,
        threat_events: ThreatEventSystem | None = None,
        session_time: float = 0.0,
        paused: bool = False,
    ) -> None:
        if paused:
            return
        dt = max(0.0, dt)
        self._time += dt
        self.state_timer += dt
        self._threat_cooldown = max(0.0, self._threat_cooldown - dt)
        self._last_world_position = self.creature.world_position.copy()

        if self.state is CreatureState.STUNNED:
            self._update_stunned(dt, generated_floor, dynamic_blockers)
            return

        player_visible = self._maybe_update_perception(dt, generated_floor, dynamic_blockers, player)
        if player_visible and player is not None:
            self._record_visible_player(player)
            if self.state is not CreatureState.CHASE:
                self._enter_chase(generated_floor, dynamic_blockers, reason="player visible")
        elif self.state is CreatureState.CHASE:
            self.time_since_player_was_visible += dt

        if self.state is not CreatureState.CHASE:
            self._maybe_select_threat(generated_floor, dynamic_blockers, threat_events)

        if self.state is CreatureState.PATROL:
            self._update_patrol(dt, generated_floor, dynamic_blockers)
        elif self.state is CreatureState.INVESTIGATE:
            self._update_investigate(dt, generated_floor, dynamic_blockers)
        elif self.state is CreatureState.SEARCH:
            self._update_search(dt, generated_floor, dynamic_blockers)
        elif self.state is CreatureState.CHASE:
            self._update_chase(dt, generated_floor, dynamic_blockers, player_visible)

        self._advance_animation(dt)

    def direct_perception(
        self,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
        player: Player | None,
    ) -> bool:
        if player is None:
            self.last_perception_result = False
            self.last_los_result = False
            self.last_perception_distance = 0.0
            return False
        distance = self.creature.world_position.distance_to(player.world_position)
        self.last_perception_distance = distance
        if distance > settings.CREATURE_DETECTION_DISTANCE:
            self.last_perception_result = False
            self.last_los_result = False
            return False
        self.perception_check_count += 1
        self.last_los_result = has_line_of_sight(
            self.creature.world_position,
            player.world_position,
            generated_floor,
            dynamic_blockers,
            self.creature.tile_size,
        )
        self.last_perception_result = self.last_los_result
        return self.last_perception_result

    def _maybe_update_perception(
        self,
        dt: float,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
        player: Player | None,
    ) -> bool:
        self._perception_cooldown -= dt
        if self._perception_cooldown > 0.0:
            return False
        self._perception_cooldown = settings.CREATURE_PERCEPTION_INTERVAL
        return self.direct_perception(generated_floor, dynamic_blockers, player)

    def _record_visible_player(self, player: Player) -> None:
        self.last_known_player_position = player.world_position.copy()
        self.last_known_player_tile = player.current_tile
        self.time_since_player_was_visible = 0.0

    def _maybe_select_threat(
        self,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
        threat_events: ThreatEventSystem | None,
    ) -> None:
        if threat_events is None or self._threat_cooldown > 0.0:
            return
        self._threat_cooldown = settings.CREATURE_THREAT_EVALUATION_INTERVAL
        event = threat_events.select_relevant_event(
            self.creature.world_position,
            current_event_id=self.selected_threat_event_id,
            floor_number=self.floor_number,
        )
        if event is None:
            if threat_events.get_event(self.selected_threat_event_id) is None:
                self.selected_threat_event_id = None
            return
        if self.state is CreatureState.INVESTIGATE and event.event_id == self.selected_threat_event_id:
            return
        if self.state is CreatureState.SEARCH or event.event_id != self.selected_threat_event_id:
            self._enter_investigate(event, generated_floor, dynamic_blockers)

    def _enter_investigate(
        self,
        event: ThreatEvent,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> None:
        target_tile = self._world_to_tile(event.world_position)
        reachable = navigation.nearest_reachable_tile(
            generated_floor,
            self.creature.current_tile,
            target_tile,
            dynamic_blockers,
            BlockerPurpose.CREATURE_MOVEMENT,
            max_radius=settings.CREATURE_SEARCH_RADIUS_TILES,
        )
        if reachable is None:
            return
        self.selected_threat_event_id = event.event_id
        self.selected_threat_creation_time = event.creation_time
        self.investigation_target_position = event.world_position.copy()
        self.investigation_target_tile = reachable
        self.search_centre = event.world_position.copy()
        self.search_centre_tile = reachable
        self.current_patrol_target = None
        self.creature.current_waypoint = reachable
        self.change_state(CreatureState.INVESTIGATE, f"heard {event.source_type.name.lower()} #{event.event_id}")
        self._request_path(reachable, generated_floor, dynamic_blockers, "investigate event", force=True)

    def _enter_chase(
        self,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
        *,
        reason: str,
    ) -> None:
        if self.last_known_player_tile is None:
            return
        self.selected_threat_event_id = None
        self.current_patrol_target = None
        self.change_state(CreatureState.CHASE, reason)
        self._request_path(self.last_known_player_tile, generated_floor, dynamic_blockers, "chase player", force=True)

    def _enter_search(
        self,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
        centre_position: pygame.Vector2 | tuple[float, float] | None,
        *,
        reason: str,
    ) -> None:
        if centre_position is None:
            centre_position = self.creature.world_position
        centre = pygame.Vector2(centre_position)
        self.search_centre = centre
        self.search_centre_tile = self._world_to_tile(centre)
        self.search_points = self._build_search_points(generated_floor, dynamic_blockers)
        self.current_patrol_target = None
        self.change_state(CreatureState.SEARCH, reason)
        self.creature.current_path.clear()
        self.current_path_target = None

    def _update_patrol(
        self,
        dt: float,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> None:
        if not self.current_path:
            self._choose_patrol_target(generated_floor, dynamic_blockers)
        if not self._follow_path(dt, generated_floor, dynamic_blockers, self.creature.speed):
            if self.current_patrol_target is not None and self._at_tile(self.current_patrol_target):
                self._patrol_history.append(self.current_patrol_target)
                self._patrol_history = self._patrol_history[-4:]
                self.current_patrol_target = None
                self.creature.current_waypoint = None

    def _update_investigate(
        self,
        dt: float,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> None:
        if self.investigation_target_tile is None:
            self._enter_search(generated_floor, dynamic_blockers, self.search_centre, reason="lost investigation target")
            return
        if self._at_tile(self.investigation_target_tile):
            self._enter_search(generated_floor, dynamic_blockers, self.investigation_target_position, reason="reached investigation")
            return
        if self._path_invalid and self._time >= self.next_permitted_pathfinding_time:
            self._request_path(self.investigation_target_tile, generated_floor, dynamic_blockers, "investigation path invalid")
        self._follow_path(dt, generated_floor, dynamic_blockers, self.creature.speed)
        if not self.current_path and self._near_tile(self.investigation_target_tile, radius=1):
            self._enter_search(generated_floor, dynamic_blockers, self.investigation_target_position, reason="near investigation")

    def _update_search(
        self,
        dt: float,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> None:
        if self.state_timer >= settings.CREATURE_SEARCH_DURATION:
            self.selected_threat_event_id = None
            self.change_state(CreatureState.PATROL, "search expired")
            self.current_patrol_target = None
            self.creature.current_path.clear()
            return
        if not self.search_points:
            self.search_points = self._build_search_points(generated_floor, dynamic_blockers)
        if not self.current_path:
            self._choose_next_search_point(generated_floor, dynamic_blockers)
        self._follow_path(dt, generated_floor, dynamic_blockers, self.creature.speed)

    def _update_chase(
        self,
        dt: float,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
        player_visible: bool,
    ) -> None:
        if self.last_known_player_tile is None:
            self._enter_search(generated_floor, dynamic_blockers, self.creature.world_position, reason="no chase memory")
            return
        if player_visible and self._time >= self.next_permitted_pathfinding_time:
            self._request_path(self.last_known_player_tile, generated_floor, dynamic_blockers, "chase refresh")
        elif self._path_invalid and self._time >= self.next_permitted_pathfinding_time:
            self._request_path(self.last_known_player_tile, generated_floor, dynamic_blockers, "chase path invalid")
        if not self.current_path and not self._at_tile(self.last_known_player_tile):
            self._request_path(self.last_known_player_tile, generated_floor, dynamic_blockers, "chase no path")
        self._follow_path(dt, generated_floor, dynamic_blockers, settings.CREATURE_CHASE_SPEED)
        if (
            not player_visible
            and (
                self.time_since_player_was_visible >= settings.CREATURE_LOST_SIGHT_TIMEOUT
                or (self.last_known_player_tile is not None and self._near_tile(self.last_known_player_tile, radius=1))
            )
        ):
            self._enter_search(generated_floor, dynamic_blockers, self.last_known_player_position, reason="lost player")

    def _update_stunned(
        self,
        dt: float,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> None:
        self.stun_timer = max(0.0, self.stun_timer - dt)
        self.creature.velocity.update(0, 0)
        self.creature.moving = False
        self._advance_animation(0.0)
        if self.stun_timer > 0.0:
            return
        previous = self.state_before_stun
        if previous is CreatureState.INVESTIGATE:
            self._enter_search(
                generated_floor,
                dynamic_blockers,
                self.investigation_target_position,
                reason="stun expired",
            )
        elif previous is CreatureState.CHASE and self.last_known_player_tile is not None:
            self.change_state(CreatureState.CHASE, "stun expired")
            self._request_path(self.last_known_player_tile, generated_floor, dynamic_blockers, "resume chase", force=True)
        elif previous is CreatureState.SEARCH and self.search_centre is not None:
            self.change_state(CreatureState.SEARCH, "stun expired")
        else:
            self.change_state(CreatureState.PATROL, "stun expired")

    def _choose_patrol_target(
        self,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> None:
        if self._patrol_candidates is None:
            self._patrol_candidates = self._build_patrol_candidates(generated_floor, dynamic_blockers)
        if not self._patrol_candidates:
            return

        candidates = [
            tile
            for tile in self._patrol_candidates
            if tile != self.creature.current_tile
            and tile not in self._patrol_history[-2:]
            and navigation.manhattan_distance(tile, self.creature.current_tile) >= 2
            and navigation.is_tile_walkable(generated_floor, tile, dynamic_blockers, BlockerPurpose.CREATURE_MOVEMENT)
        ]
        if not candidates:
            candidates = [
                tile
                for tile in self._patrol_candidates
                if tile != self.creature.current_tile
                and navigation.is_tile_walkable(generated_floor, tile, dynamic_blockers, BlockerPurpose.CREATURE_MOVEMENT)
            ]
        if not candidates:
            return
        for _ in range(min(settings.CREATURE_PATROL_TARGET_ATTEMPTS, len(candidates))):
            target = candidates[self.rng.randrange(len(candidates))]
            if self._request_path(target, generated_floor, dynamic_blockers, "patrol target"):
                self.current_patrol_target = target
                self.creature.current_waypoint = target
                return

    def _build_patrol_candidates(
        self,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> list[tuple[int, int]]:
        preferred: list[tuple[int, int]] = []
        rooms = getattr(generated_floor, "rooms", [])
        for room in rooms:
            centre = room.center
            if navigation.is_tile_walkable(generated_floor, centre, dynamic_blockers, BlockerPurpose.CREATURE_MOVEMENT):
                preferred.append(centre)
        for tile in generated_floor.walkable_tiles():
            if tile not in preferred:
                preferred.append(tile)
        return preferred

    def _build_search_points(
        self,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> list[tuple[int, int]]:
        if self.search_centre_tile is None:
            self.search_centre_tile = self.creature.current_tile
        cx, cy = self.search_centre_tile
        radius = settings.CREATURE_SEARCH_RADIUS_TILES
        candidates: list[tuple[int, int]] = []
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                tile = (x, y)
                distance = navigation.manhattan_distance(tile, self.search_centre_tile)
                if distance == 0 or distance > radius:
                    continue
                if navigation.is_tile_walkable(generated_floor, tile, dynamic_blockers, BlockerPurpose.CREATURE_MOVEMENT):
                    candidates.append(tile)
        candidates.sort(key=lambda tile: (navigation.manhattan_distance(tile, self.search_centre_tile), tile[1], tile[0]))
        if candidates:
            self.rng.shuffle(candidates)
        return candidates[:10]

    def _choose_next_search_point(
        self,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
    ) -> None:
        while self.search_points:
            target = self.search_points.pop(0)
            if self._request_path(target, generated_floor, dynamic_blockers, "search point"):
                return
        if self.search_centre_tile is not None:
            self._request_path(self.search_centre_tile, generated_floor, dynamic_blockers, "search centre")

    def _request_path(
        self,
        target_tile: tuple[int, int],
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
        reason: str,
        *,
        force: bool = False,
    ) -> bool:
        if not force and self._time < self.next_permitted_pathfinding_time:
            return bool(self.current_path)
        start = self.creature.current_tile
        if start == target_tile:
            self.current_path = []
            self.current_target_tile = target_tile
            self.current_target_position = self._tile_center(target_tile)
            self.current_path_target = target_tile
            self._path_invalid = False
            return True

        path_target = navigation.nearest_reachable_tile(
            generated_floor,
            start,
            target_tile,
            dynamic_blockers,
            BlockerPurpose.CREATURE_MOVEMENT,
            max_radius=settings.CREATURE_SEARCH_RADIUS_TILES,
        )
        if path_target is None:
            self.current_path = []
            self.current_target_tile = target_tile
            self.current_target_position = self._tile_center(target_tile)
            self.current_path_target = None
            self._set_next_path_time()
            return False

        started = time.perf_counter()
        path = navigation.astar_path(
            generated_floor,
            start,
            path_target,
            dynamic_blockers,
            BlockerPurpose.CREATURE_MOVEMENT,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.last_pathfinding_ms = elapsed_ms
        self.max_pathfinding_ms = max(self.max_pathfinding_ms, elapsed_ms)
        self.pathfinding_call_count += 1
        self.pathfinding_calls_this_session += 1
        self.last_path_reason = reason
        self._set_next_path_time()
        if path_target != start and not path:
            self.current_path = []
            self.current_path_target = None
            self._path_invalid = False
            return False
        self.current_path = path
        self.current_target_tile = path_target
        self.current_target_position = self._tile_center(path_target)
        self.current_path_target = path_target
        self._path_invalid = False
        return True

    def _set_next_path_time(self) -> None:
        interval = {
            CreatureState.PATROL: settings.CREATURE_PATROL_REPATH_INTERVAL,
            CreatureState.INVESTIGATE: settings.CREATURE_INVESTIGATE_REPATH_INTERVAL,
            CreatureState.SEARCH: settings.CREATURE_SEARCH_REPATH_INTERVAL,
            CreatureState.CHASE: settings.CREATURE_CHASE_REPATH_INTERVAL,
            CreatureState.STUNNED: settings.CREATURE_INVESTIGATE_REPATH_INTERVAL,
        }[self.state]
        self.next_permitted_pathfinding_time = self._time + interval

    def _follow_path(
        self,
        dt: float,
        generated_floor: GeneratedFloor,
        dynamic_blockers: DynamicBlockerRegistry | None,
        speed: float,
    ) -> bool:
        if self.current_path and not navigation.is_path_valid(
            generated_floor,
            self.current_path,
            dynamic_blockers,
            BlockerPurpose.CREATURE_MOVEMENT,
            start_tile=self.creature.current_tile,
        ):
            self._path_invalid = True
            self.creature.set_movement_direction(pygame.Vector2())
            return False
        while self.current_path:
            next_tile = self.current_path[0]
            if not navigation.is_tile_walkable(generated_floor, next_tile, dynamic_blockers, BlockerPurpose.CREATURE_MOVEMENT):
                self._path_invalid = True
                self.creature.set_movement_direction(pygame.Vector2())
                return False
            target_position = self._tile_center(next_tile)
            delta = target_position - self.creature.world_position
            if delta.length() <= settings.CREATURE_WAYPOINT_REACHED_DISTANCE:
                self.current_path.pop(0)
                continue
            direction = delta.normalize()
            self.creature.set_movement_direction(direction, speed=speed)
            self.creature.move_by(self.creature.velocity * dt, generated_floor, dynamic_blockers)
            moved_distance = self.creature.world_position.distance_to(self._last_world_position)
            if moved_distance <= 0.05:
                self._stuck_elapsed += dt
                if self._stuck_elapsed >= settings.CREATURE_STUCK_REPATH_TIME:
                    self._path_invalid = True
                    self.creature.current_path.clear()
                    self._stuck_elapsed = 0.0
            else:
                self._stuck_elapsed = 0.0
            return True
        self.creature.set_movement_direction(pygame.Vector2())
        return False

    def _advance_animation(self, dt: float) -> None:
        animation = self.creature.animations[self.creature.facing]
        animation.update(dt if self.creature.moving else 0.0)
        self.creature.image = animation.current_frame
        self.creature._sync_rects_from_world()

    def _world_to_tile(self, position: pygame.Vector2 | tuple[float, float]) -> tuple[int, int]:
        point = pygame.Vector2(position)
        return (int(point.x // self.creature.tile_size), int(point.y // self.creature.tile_size))

    def _tile_center(self, tile: tuple[int, int]) -> pygame.Vector2:
        return pygame.Vector2(
            (tile[0] + 0.5) * self.creature.tile_size,
            (tile[1] + 0.5) * self.creature.tile_size,
        )

    def _at_tile(self, tile: tuple[int, int]) -> bool:
        return self.creature.current_tile == tile or self.creature.world_position.distance_to(self._tile_center(tile)) <= settings.CREATURE_WAYPOINT_REACHED_DISTANCE

    def _near_tile(self, tile: tuple[int, int], *, radius: int) -> bool:
        return navigation.manhattan_distance(self.creature.current_tile, tile) <= radius
