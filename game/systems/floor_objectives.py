from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from game import settings
from game.assets import AssetManager
from game.entities.objectives import GeneratorComponentPickup, GeneratorEntity, GeneratorState
from game.entities.scan_objects import ElevatorEntity
from game.systems.threat_events import ThreatEventSystem, ThreatSourceType
from game.world import navigation
from game.world.blockers import BlockerPurpose, DynamicBlockerRegistry
from game.world.floor import GeneratedFloor
from game.world.tiles import TileType


@dataclass
class ContextMessage:
    text: str
    lifetime: float = settings.CONTEXT_MESSAGE_DURATION
    age: float = 0.0

    @property
    def expired(self) -> bool:
        return self.age >= self.lifetime


@dataclass
class Floor1ObjectiveState:
    floor_number: int = 1
    component_a_entity_id: str = ""
    component_b_entity_id: str = ""
    component_a_collected: bool = False
    component_b_collected: bool = False
    generator_entity_id: str = ""
    generator_repair_progress: float = 0.0
    generator_repairable: bool = False
    generator_repaired: bool = False
    floor_power_active: bool = False
    elevator_unlocked: bool = False
    floor_complete: bool = False
    current_objective_text: str = "Find generator components: 0 / 2"
    current_prompt: str = ""
    interaction_target_id: str | None = None
    interaction_progress: float = 0.0
    component_a_collected_time: float | None = None
    component_b_collected_time: float | None = None
    generator_repaired_time: float | None = None
    floor_complete_time: float | None = None
    generator_threat_event_id: int | None = None
    generator_activation_event_count: int = 0

    @property
    def components_collected(self) -> int:
        return int(self.component_a_collected) + int(self.component_b_collected)

    @property
    def components_collected_complete(self) -> bool:
        return self.components_collected == 2

    @property
    def generator_ready(self) -> bool:
        return self.components_collected_complete and not self.generator_repaired


@dataclass
class ObjectivePlacementMetadata:
    component_a_room_id: int
    component_b_room_id: int
    generator_room_id: int
    component_a_tile: tuple[int, int]
    component_b_tile: tuple[int, int]
    generator_tile: tuple[int, int]
    validation_errors: list[str] = field(default_factory=list)


@dataclass
class Floor1ObjectiveUpdate:
    score_delta: int = 0
    floor_completed: bool = False
    power_changed: bool = False
    generator_threat_event_id: int | None = None


class Floor1ObjectiveSystem:
    def __init__(
        self,
        state: Floor1ObjectiveState,
        components: list[GeneratorComponentPickup],
        generator: GeneratorEntity,
        placement: ObjectivePlacementMetadata,
    ) -> None:
        self.state = state
        self.components = components
        self.generator = generator
        self.placement = placement
        self.messages: list[ContextMessage] = []
        self._message_history: set[str] = set()

    @property
    def active_components(self) -> list[GeneratorComponentPickup]:
        return [component for component in self.components if component.scan_active]

    @property
    def scan_entities(self) -> list[object]:
        return [*self.active_components, self.generator]

    @property
    def active_entities(self) -> list[object]:
        return [*self.active_components, self.generator]

    @classmethod
    def create_for_floor(
        cls,
        generated_floor: GeneratedFloor,
        assets: AssetManager,
        tile_size: int,
        dynamic_blockers: DynamicBlockerRegistry | None,
        *,
        reserved_tiles: set[tuple[int, int]] | None = None,
    ) -> "Floor1ObjectiveSystem":
        reserved = set(reserved_tiles or set())
        reserved.update(
            {
                generated_floor.player_spawn,
                generated_floor.elevator_tile,
                *generated_floor.elevator_approach_tiles,
                *generated_floor.doorway_candidates,
            }
        )

        generator_choice = _choose_objective_tile(
            generated_floor,
            dynamic_blockers,
            _room_order(generated_floor, ("far", "middle", "near")),
            reserved,
            require_interaction_space=True,
        )
        if generator_choice is None:
            raise ValueError("Could not place Floor 1 generator.")
        generator_room_id, generator_tile = generator_choice
        reserved.add(generator_tile)

        component_a_choice = _choose_objective_tile(
            generated_floor,
            dynamic_blockers,
            _room_order(generated_floor, ("middle", "near", "far"), excluded={generator_room_id}),
            reserved,
        )
        if component_a_choice is None:
            component_a_choice = _choose_objective_tile(
                generated_floor,
                dynamic_blockers,
                _room_order(generated_floor, ("middle", "near", "far")),
                reserved,
            )
        if component_a_choice is None:
            raise ValueError("Could not place Floor 1 generator component A.")
        component_a_room_id, component_a_tile = component_a_choice
        reserved.add(component_a_tile)

        component_b_choice = _choose_objective_tile(
            generated_floor,
            dynamic_blockers,
            _room_order(
                generated_floor,
                ("far", "middle", "near"),
                excluded={generator_room_id, component_a_room_id},
            ),
            reserved,
        )
        if component_b_choice is None:
            component_b_choice = _choose_objective_tile(
                generated_floor,
                dynamic_blockers,
                _room_order(generated_floor, ("far", "middle", "near"), excluded={component_a_room_id}),
                reserved,
            )
        if component_b_choice is None:
            raise ValueError("Could not place Floor 1 generator component B.")
        component_b_room_id, component_b_tile = component_b_choice

        prefix = f"f1-a{generated_floor.generation_attempt}"
        component_a = GeneratorComponentPickup(
            f"{prefix}-component-a-{component_a_tile[0]}-{component_a_tile[1]}",
            "A",
            component_a_room_id,
            component_a_tile,
            assets,
            tile_size,
        )
        component_b = GeneratorComponentPickup(
            f"{prefix}-component-b-{component_b_tile[0]}-{component_b_tile[1]}",
            "B",
            component_b_room_id,
            component_b_tile,
            assets,
            tile_size,
        )
        generator = GeneratorEntity(
            f"{prefix}-generator-{generator_tile[0]}-{generator_tile[1]}",
            generator_room_id,
            generator_tile,
            assets,
            tile_size,
        )
        state = Floor1ObjectiveState(
            floor_number=1,
            component_a_entity_id=component_a.unique_id,
            component_b_entity_id=component_b.unique_id,
            generator_entity_id=generator.unique_id,
        )
        placement = ObjectivePlacementMetadata(
            component_a_room_id=component_a_room_id,
            component_b_room_id=component_b_room_id,
            generator_room_id=generator_room_id,
            component_a_tile=component_a_tile,
            component_b_tile=component_b_tile,
            generator_tile=generator_tile,
        )
        placement.validation_errors = validate_floor1_placement(
            generated_floor,
            placement,
            reserved_tiles=set(reserved_tiles or set()),
            dynamic_blockers=dynamic_blockers,
        )
        system = cls(state, [component_a, component_b], generator, placement)
        system._refresh_objective_text()
        return system

    def update(
        self,
        dt: float,
        player_rect: pygame.Rect,
        *,
        interact_held: bool,
        session_time: float,
        threat_events: ThreatEventSystem,
        elevator: ElevatorEntity | None,
    ) -> Floor1ObjectiveUpdate:
        result = Floor1ObjectiveUpdate()
        self._update_messages(dt)
        for component in self.components:
            component.update(dt)
        self.generator.update(dt)
        if (
            not self.state.generator_repaired
            and self.state.interaction_progress > 0.0
            and not self.generator.interaction_rect.colliderect(player_rect)
        ):
            self._reset_repair_progress()
        self.state.current_prompt = ""
        self.state.interaction_target_id = None

        for component in self.components:
            if not component.scan_active or not component.collision_rect.colliderect(player_rect):
                continue
            if component.collect():
                self._mark_component_collected(component, session_time)
                result.score_delta += component.score_value

        self._update_generator_interaction(
            dt,
            player_rect,
            interact_held=interact_held,
            session_time=session_time,
            threat_events=threat_events,
            elevator=elevator,
            result=result,
        )
        self._update_elevator_interaction(
            player_rect,
            interact_held=interact_held,
            session_time=session_time,
            elevator=elevator,
            result=result,
        )
        self._refresh_objective_text()
        return result

    def clear_interaction(self) -> None:
        self.state.current_prompt = ""
        self.state.interaction_target_id = None
        self.state.interaction_progress = 0.0
        if not self.state.generator_repaired:
            self.state.generator_repair_progress = 0.0
            self.generator.repair_progress = 0.0
            self.generator.set_state(GeneratorState.READY if self.state.generator_ready else GeneratorState.INACTIVE)

    def reset_messages(self) -> None:
        self.messages.clear()
        self._message_history.clear()
        self.state.current_prompt = ""

    def _mark_component_collected(self, component: GeneratorComponentPickup, session_time: float) -> None:
        if component.component_key == "A":
            self.state.component_a_collected = True
            self.state.component_a_collected_time = session_time
            self.add_message("Generator Component A recovered")
        else:
            self.state.component_b_collected = True
            self.state.component_b_collected_time = session_time
            self.add_message("Generator Component B recovered")
        if self.state.components_collected_complete:
            self.state.generator_repairable = True
            self.generator.set_state(GeneratorState.READY)
            self.add_message("Both components recovered")

    def _update_generator_interaction(
        self,
        dt: float,
        player_rect: pygame.Rect,
        *,
        interact_held: bool,
        session_time: float,
        threat_events: ThreatEventSystem,
        elevator: ElevatorEntity | None,
        result: Floor1ObjectiveUpdate,
    ) -> None:
        if self.state.generator_repaired:
            if self.generator.interaction_rect.colliderect(player_rect):
                self.state.current_prompt = "Power restored"
                self.state.interaction_target_id = self.generator.unique_id
            return

        in_range = self.generator.interaction_rect.colliderect(player_rect)
        if not in_range:
            if self.state.interaction_target_id == self.generator.unique_id:
                self.clear_interaction()
            return

        self.state.interaction_target_id = self.generator.unique_id
        if not self.state.components_collected_complete:
            self.state.current_prompt = f"Components required: {self.state.components_collected} / 2"
            if interact_held:
                self.add_message("Missing generator components")
            self._reset_repair_progress()
            return

        self.state.current_prompt = "Hold F to repair generator"
        if not interact_held:
            self.add_message_once("Hold F to repair generator")
            self._reset_repair_progress()
            return

        self.state.current_prompt = "Repairing generator"
        self.generator.set_state(GeneratorState.REPAIRING)
        self.state.interaction_progress = min(
            settings.GENERATOR_REPAIR_DURATION,
            self.state.interaction_progress + max(0.0, dt),
        )
        self.state.generator_repair_progress = self.state.interaction_progress
        self.generator.repair_progress = self.state.generator_repair_progress
        if self.state.interaction_progress + 1e-7 < settings.GENERATOR_REPAIR_DURATION:
            return

        self.state.generator_repaired = True
        self.state.generator_repaired_time = session_time
        self.state.floor_power_active = True
        self.state.elevator_unlocked = True
        self.state.generator_repair_progress = settings.GENERATOR_REPAIR_DURATION
        self.state.interaction_progress = settings.GENERATOR_REPAIR_DURATION
        self.generator.repair_progress = settings.GENERATOR_REPAIR_DURATION
        self.generator.set_state(GeneratorState.POWERED)
        if elevator is not None:
            elevator.unlock()
        event = threat_events.add_event(
            self.generator.world_position,
            ThreatSourceType.GENERATOR,
            strength=settings.GENERATOR_THREAT_STRENGTH,
            lifetime=settings.GENERATOR_THREAT_LIFETIME,
            creation_time=session_time,
            source_entity_id=self.generator.unique_id,
            floor_number=1,
        )
        self.state.generator_threat_event_id = event.event_id
        self.state.generator_activation_event_count += 1
        result.generator_threat_event_id = event.event_id
        result.power_changed = True
        result.score_delta += settings.GENERATOR_REPAIR_SCORE
        self.add_message("Power restored")
        self.add_message("Elevator unlocked")

    def _update_elevator_interaction(
        self,
        player_rect: pygame.Rect,
        *,
        interact_held: bool,
        session_time: float,
        elevator: ElevatorEntity | None,
        result: Floor1ObjectiveUpdate,
    ) -> None:
        if elevator is None or self.state.floor_complete:
            return
        in_range = elevator.interaction_rect.colliderect(player_rect)
        if not in_range:
            return
        self.state.interaction_target_id = elevator.unique_id
        if not self.state.elevator_unlocked:
            self.state.current_prompt = "Elevator offline"
            if interact_held:
                self.add_message("Elevator offline")
            return
        self.state.current_prompt = "Press F to enter elevator"
        if not interact_held:
            self.add_message_once("Press F to enter elevator")
            return
        elevator.activate()
        self.state.floor_complete = True
        self.state.floor_complete_time = session_time
        result.floor_completed = True
        result.score_delta += settings.FLOOR_COMPLETION_SCORE
        self.add_message("Floor 1 complete")

    def _reset_repair_progress(self) -> None:
        self.state.interaction_progress = 0.0
        self.state.generator_repair_progress = 0.0
        self.generator.repair_progress = 0.0
        self.generator.set_state(GeneratorState.READY if self.state.generator_ready else GeneratorState.INACTIVE)

    def add_message(self, text: str) -> None:
        self._message_history.add(text)
        if self.messages and self.messages[-1].text == text and self.messages[-1].age < 0.25:
            return
        self.messages.append(ContextMessage(text))
        if len(self.messages) > 4:
            del self.messages[:-4]

    def add_message_once(self, text: str) -> None:
        if text in self._message_history:
            return
        self.add_message(text)

    def _update_messages(self, dt: float) -> None:
        for message in self.messages:
            message.age += max(0.0, dt)
        self.messages = [message for message in self.messages if not message.expired]

    def _refresh_objective_text(self) -> None:
        if self.state.floor_complete:
            self.state.current_objective_text = "Floor 1 complete"
        elif self.state.floor_power_active:
            self.state.current_objective_text = "Return to the elevator"
        elif self.state.components_collected_complete:
            self.state.current_objective_text = "Repair the generator"
        else:
            self.state.current_objective_text = f"Find generator components: {self.state.components_collected} / 2"


def validate_floor1_placement(
    generated_floor: GeneratedFloor,
    placement: ObjectivePlacementMetadata,
    *,
    reserved_tiles: set[tuple[int, int]] | None = None,
    dynamic_blockers: DynamicBlockerRegistry | None = None,
) -> list[str]:
    errors: list[str] = []
    reserved = set(reserved_tiles or set())
    tiles = {
        "component_a": placement.component_a_tile,
        "component_b": placement.component_b_tile,
        "generator": placement.generator_tile,
    }
    if placement.component_a_room_id == placement.component_b_room_id:
        errors.append("component rooms are not distinct")
    if placement.generator_room_id == generated_floor.start_room_id:
        errors.append("generator is in start room")
    if placement.component_a_room_id == generated_floor.start_room_id:
        errors.append("component A is in start room")
    if placement.component_b_room_id == generated_floor.start_room_id:
        errors.append("component B is in start room")
    if len(set(tiles.values())) != 3:
        errors.append("objective entities overlap each other")

    for name, tile in tiles.items():
        if not generated_floor.is_walkable(*tile):
            errors.append(f"{name} is not on a walkable tile")
            continue
        tile_type = generated_floor.tile_at(*tile)
        if tile_type in (TileType.OBSTACLE, TileType.PILLAR, TileType.WALL, TileType.DAMAGED_WALL, TileType.VOID):
            errors.append(f"{name} overlaps blocking tile")
        if tile in generated_floor.doorway_candidates:
            errors.append(f"{name} overlaps doorway")
        if tile == generated_floor.elevator_tile or tile in generated_floor.elevator_approach_tiles:
            errors.append(f"{name} overlaps elevator")
        if tile in generated_floor.candidate_creature_spawns:
            errors.append(f"{name} overlaps creature spawn candidate")
        if tile in reserved:
            errors.append(f"{name} overlaps reserved runtime tile")
        if not _reachable_from_spawn(generated_floor, tile, dynamic_blockers):
            errors.append(f"{name} is not reachable before power")

    if not _has_interaction_space(generated_floor, placement.generator_tile):
        errors.append("generator lacks walkable interaction space")
    return errors


def _room_order(
    generated_floor: GeneratedFloor,
    groups: tuple[str, ...],
    *,
    excluded: set[int] | None = None,
) -> list[int]:
    excluded = excluded or set()
    ordered: list[int] = []
    for group in groups:
        for room_id in generated_floor.objective_room_groups.get(group, []):
            if room_id != generated_floor.start_room_id and room_id not in excluded and room_id not in ordered:
                ordered.append(room_id)
    remaining = [
        room.room_id
        for room in generated_floor.rooms
        if room.room_id != generated_floor.start_room_id
        and room.room_id not in excluded
        and room.room_id not in ordered
    ]
    remaining.sort(
        key=lambda room_id: (
            -(generated_floor.graph_distance(generated_floor.start_room_id, room_id) or 0),
            -generated_floor.rooms[room_id].rect.area,
            room_id,
        )
    )
    ordered.extend(remaining)
    return ordered


def _choose_objective_tile(
    generated_floor: GeneratedFloor,
    dynamic_blockers: DynamicBlockerRegistry | None,
    room_ids: list[int],
    reserved: set[tuple[int, int]],
    *,
    require_interaction_space: bool = False,
) -> tuple[int, tuple[int, int]] | None:
    for room_id in room_ids:
        room = generated_floor.rooms[room_id]
        for margin in (2, 1, 0):
            candidates = [
                tile
                for tile in room.rect.interior_tiles(margin=margin)
                if _valid_objective_tile(
                    generated_floor,
                    tile,
                    reserved,
                    dynamic_blockers,
                    require_interaction_space=require_interaction_space,
                )
            ]
            candidates.sort(key=lambda tile: (_distance_squared(tile, room.center), tile[1], tile[0]))
            if candidates:
                return (room_id, candidates[0])
    return None


def _valid_objective_tile(
    generated_floor: GeneratedFloor,
    tile: tuple[int, int],
    reserved: set[tuple[int, int]],
    dynamic_blockers: DynamicBlockerRegistry | None,
    *,
    require_interaction_space: bool,
) -> bool:
    if tile in reserved or tile in generated_floor.doorway_candidates:
        return False
    if tile in generated_floor.candidate_creature_spawns:
        return False
    if not generated_floor.is_walkable(*tile):
        return False
    if not _reachable_from_spawn(generated_floor, tile, dynamic_blockers):
        return False
    if require_interaction_space and not _has_interaction_space(generated_floor, tile):
        return False
    return True


def _reachable_from_spawn(
    generated_floor: GeneratedFloor,
    tile: tuple[int, int],
    dynamic_blockers: DynamicBlockerRegistry | None,
) -> bool:
    start = generated_floor.player_spawn
    return start == tile or bool(
        navigation.astar_path(
            generated_floor,
            start,
            tile,
            dynamic_blockers,
            BlockerPurpose.MOVEMENT,
        )
    )


def _has_interaction_space(generated_floor: GeneratedFloor, tile: tuple[int, int]) -> bool:
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        candidate = (tile[0] + dx, tile[1] + dy)
        if generated_floor.is_walkable(*candidate) and candidate not in generated_floor.doorway_candidates:
            return True
    return False


def _distance_squared(first: tuple[int, int], second: tuple[int, int]) -> int:
    return (first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2
