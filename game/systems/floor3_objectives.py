from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from game import settings
from game.assets import AssetManager
from game.entities.door import DoorType, DynamicDoor
from game.entities.objectives import (
    ContainmentComponentPickup,
    ContainmentControlEntity,
    ContainmentControlState,
    EchoCorePickup,
)
from game.entities.scan_objects import ElevatorEntity
from game.systems.floor_objectives import (
    ContextMessage,
    Floor1ObjectiveUpdate,
    _choose_floor2_tile,
    _floor2_room_order,
    _has_interaction_space,
    _reachable_from_spawn_with,
)
from game.systems.threat_events import ThreatEventSystem, ThreatSourceType
from game.world.blockers import BlockerPurpose, DynamicBlockerRegistry
from game.world.floor import GateCandidate, GeneratedFloor
from game.world.tiles import TileType


@dataclass
class Floor3ObjectiveState:
    floor_number: int = 3
    component_entity_id: str = ""
    component_collected: bool = False
    control_entity_id: str = ""
    control_active: bool = False
    control_progress: float = 0.0
    containment_door_id: str = ""
    containment_door_unlocked: bool = False
    echo_core_entity_id: str = ""
    echo_core_collected: bool = False
    extraction_active: bool = False
    extraction_creature_spawned: bool = False
    elevator_unlocked: bool = False
    floor_complete: bool = False
    current_objective_text: str = "Find the containment component"
    current_prompt: str = ""
    interaction_target_id: str | None = None
    interaction_progress: float = 0.0
    component_collected_time: float | None = None
    control_active_time: float | None = None
    core_collected_time: float | None = None
    floor_complete_time: float | None = None
    containment_threat_event_id: int | None = None
    echo_core_threat_event_id: int | None = None
    containment_event_count: int = 0
    echo_core_event_count: int = 0

    @property
    def objective_stage(self) -> str:
        if self.floor_complete:
            return "complete"
        if self.echo_core_collected:
            return "return_to_elevator"
        if self.control_active:
            return "retrieve_echo_core"
        if self.component_collected:
            return "install_component"
        return "find_component"


@dataclass
class Floor3PlacementMetadata:
    containment_gate_edge: tuple[int, int]
    public_side_room_ids: tuple[int, ...]
    containment_side_room_ids: tuple[int, ...]
    containment_door_id: str
    containment_door_tile: tuple[int, int]
    component_room_id: int
    control_room_id: int
    core_room_id: int
    component_tile: tuple[int, int]
    control_tile: tuple[int, int]
    core_tile: tuple[int, int]
    validation_errors: list[str] = field(default_factory=list)
    placement_attempts: int = 1


class Floor3ObjectiveSystem:
    def __init__(
        self,
        state: Floor3ObjectiveState,
        component: ContainmentComponentPickup,
        control: ContainmentControlEntity,
        echo_core: EchoCorePickup,
        containment_door: DynamicDoor,
        placement: Floor3PlacementMetadata,
    ) -> None:
        self.state = state
        self.component = component
        self.control = control
        self.echo_core = echo_core
        self.containment_door = containment_door
        self.placement = placement
        self.messages: list[ContextMessage] = []
        self._message_history: set[str] = set()

    @property
    def scan_entities(self) -> list[object]:
        entities: list[object] = [self.control, self.containment_door]
        if self.component.scan_active:
            entities.append(self.component)
        if self.echo_core.scan_active:
            entities.append(self.echo_core)
        return entities

    @property
    def active_entities(self) -> list[object]:
        return self.scan_entities

    @classmethod
    def create_for_floor(
        cls,
        generated_floor: GeneratedFloor,
        assets: AssetManager,
        tile_size: int,
        doors: list[DynamicDoor],
        *,
        reserved_tiles: set[tuple[int, int]] | None = None,
    ) -> "Floor3ObjectiveSystem":
        containment_door, gate = _select_containment_gate(generated_floor, doors)
        public_rooms = tuple(gate.key_side_rooms)
        secure_rooms = tuple(gate.gated_rooms)
        reserved = set(reserved_tiles or set())
        reserved.update(
            {
                generated_floor.player_spawn,
                generated_floor.elevator_tile,
                *generated_floor.elevator_approach_tiles,
                *generated_floor.doorway_candidates,
            }
        )
        reserved.update(door.tile for door in doors)
        containment_blockers = DynamicBlockerRegistry([containment_door], tile_size)

        component_choice = _choose_floor2_tile(
            generated_floor,
            _floor2_room_order(generated_floor, public_rooms, prefer_public=True),
            reserved,
            containment_blockers,
            require_reachable=True,
            require_interaction_space=False,
            avoid_start_when_possible=True,
        )
        if component_choice is None:
            raise ValueError("Could not place Floor 3 containment component.")
        component_room_id, component_tile = component_choice
        reserved.add(component_tile)

        control_choice = _choose_floor2_tile(
            generated_floor,
            _floor2_room_order(
                generated_floor,
                public_rooms,
                prefer_public=True,
                excluded={component_room_id},
            ),
            reserved,
            containment_blockers,
            require_reachable=True,
            require_interaction_space=True,
            avoid_start_when_possible=True,
        )
        if control_choice is None:
            control_choice = _choose_floor2_tile(
                generated_floor,
                _floor2_room_order(generated_floor, public_rooms, prefer_public=True),
                reserved,
                containment_blockers,
                require_reachable=True,
                require_interaction_space=True,
                avoid_start_when_possible=True,
            )
        if control_choice is None:
            raise ValueError("Could not place Floor 3 containment control.")
        control_room_id, control_tile = control_choice
        reserved.add(control_tile)

        preferred_secure = [
            room_id
            for room_id in generated_floor.containment_room_candidates
            if room_id in secure_rooms
        ]
        preferred_secure.extend(room_id for room_id in secure_rooms if room_id not in preferred_secure)
        core_choice = _choose_floor2_tile(
            generated_floor,
            _floor2_room_order(generated_floor, preferred_secure, prefer_public=False),
            reserved,
            None,
            require_reachable=False,
            require_interaction_space=False,
        )
        if core_choice is None:
            raise ValueError("Could not place Floor 3 Echo Core.")
        core_room_id, core_tile = core_choice

        prefix = f"f3-a{generated_floor.generation_attempt}"
        component = ContainmentComponentPickup(
            f"{prefix}-containment-component-{component_tile[0]}-{component_tile[1]}",
            component_room_id,
            component_tile,
            assets,
            tile_size,
        )
        control = ContainmentControlEntity(
            f"{prefix}-containment-control-{control_tile[0]}-{control_tile[1]}",
            control_room_id,
            control_tile,
            assets,
            tile_size,
        )
        echo_core = EchoCorePickup(
            f"{prefix}-echo-core-{core_tile[0]}-{core_tile[1]}",
            core_room_id,
            core_tile,
            assets,
            tile_size,
        )
        state = Floor3ObjectiveState(
            component_entity_id=component.unique_id,
            control_entity_id=control.unique_id,
            containment_door_id=containment_door.unique_id,
            echo_core_entity_id=echo_core.unique_id,
        )
        placement = Floor3PlacementMetadata(
            containment_gate_edge=gate.edge,
            public_side_room_ids=public_rooms,
            containment_side_room_ids=secure_rooms,
            containment_door_id=containment_door.unique_id,
            containment_door_tile=containment_door.tile,
            component_room_id=component_room_id,
            control_room_id=control_room_id,
            core_room_id=core_room_id,
            component_tile=component_tile,
            control_tile=control_tile,
            core_tile=core_tile,
        )
        placement.validation_errors = validate_floor3_placement(
            generated_floor,
            placement,
            reserved_tiles=set(reserved_tiles or set()),
            containment_door=containment_door,
        )
        system = cls(state, component, control, echo_core, containment_door, placement)
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
        self.component.update(dt)
        self.control.update(dt)
        self.echo_core.update(dt)
        self.state.current_prompt = ""
        self.state.interaction_target_id = None

        if self.state.interaction_progress > 0.0 and not self.control.interaction_rect.colliderect(player_rect):
            self._reset_control_progress()

        if self.component.scan_active and self.component.collision_rect.colliderect(player_rect):
            if self.component.collect():
                self.state.component_collected = True
                self.state.component_collected_time = session_time
                self.control.set_state(ContainmentControlState.READY)
                result.score_delta += self.component.score_value
                self.add_message("Containment component recovered")

        self._update_control(
            dt,
            player_rect,
            interact_held=interact_held,
            session_time=session_time,
            threat_events=threat_events,
            result=result,
        )

        if (
            self.state.control_active
            and self.echo_core.scan_active
            and self.echo_core.collision_rect.colliderect(player_rect)
        ):
            if self.echo_core.collect():
                self.state.echo_core_collected = True
                self.state.core_collected_time = session_time
                self.state.extraction_active = True
                self.state.elevator_unlocked = True
                if elevator is not None:
                    elevator.unlock()
                event = threat_events.add_event(
                    self.echo_core.world_position,
                    ThreatSourceType.ECHO_CORE,
                    strength=settings.ECHO_CORE_THREAT_STRENGTH,
                    lifetime=settings.ECHO_CORE_THREAT_LIFETIME,
                    creation_time=session_time,
                    source_entity_id=self.echo_core.unique_id,
                    floor_number=3,
                )
                self.state.echo_core_threat_event_id = event.event_id
                self.state.echo_core_event_count += 1
                result.echo_core_threat_event_id = event.event_id
                result.extraction_started = True
                result.score_delta += self.echo_core.score_value
                self.add_message("Echo Core secured")
                self.add_message("Extraction signal detected")
                self.add_message("Return to the elevator")

        self._update_elevator(
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
        self._reset_control_progress()

    def reset_messages(self) -> None:
        self.messages.clear()
        self._message_history.clear()
        self.state.current_prompt = ""

    def mark_extraction_creature_spawned(self) -> None:
        self.state.extraction_creature_spawned = True

    def _update_control(
        self,
        dt: float,
        player_rect: pygame.Rect,
        *,
        interact_held: bool,
        session_time: float,
        threat_events: ThreatEventSystem,
        result: Floor1ObjectiveUpdate,
    ) -> None:
        if self.state.control_active:
            if self.control.interaction_rect.colliderect(player_rect):
                self.state.current_prompt = "Containment section open"
                self.state.interaction_target_id = self.control.unique_id
            return
        if not self.control.interaction_rect.colliderect(player_rect):
            return
        self.state.interaction_target_id = self.control.unique_id
        if not self.state.component_collected:
            self.state.current_prompt = "Containment component required"
            if interact_held:
                self.add_message("Containment component required")
            self._reset_control_progress()
            return
        self.state.current_prompt = "Hold F to install containment component"
        if not interact_held:
            self.add_message_once("Hold F to install containment component")
            self._reset_control_progress()
            return

        self.state.current_prompt = "Installing containment component"
        self.control.set_state(ContainmentControlState.INSTALLING)
        self.state.interaction_progress = min(
            settings.CONTAINMENT_INSTALL_DURATION,
            self.state.interaction_progress + max(0.0, dt),
        )
        self.state.control_progress = self.state.interaction_progress
        self.control.install_progress = self.state.control_progress
        if self.state.interaction_progress + 1e-7 < settings.CONTAINMENT_INSTALL_DURATION:
            return

        self.state.control_active = True
        self.state.control_active_time = session_time
        self.state.containment_door_unlocked = True
        self.state.control_progress = settings.CONTAINMENT_INSTALL_DURATION
        self.state.interaction_progress = settings.CONTAINMENT_INSTALL_DURATION
        self.control.install_progress = settings.CONTAINMENT_INSTALL_DURATION
        self.control.set_state(ContainmentControlState.ACTIVE)
        self.containment_door.unlock_containment()
        self.containment_door.set_powered(True)
        event = threat_events.add_event(
            self.control.world_position,
            ThreatSourceType.CONTAINMENT_CONTROL,
            strength=settings.CONTAINMENT_THREAT_STRENGTH,
            lifetime=settings.CONTAINMENT_THREAT_LIFETIME,
            creation_time=session_time,
            source_entity_id=self.control.unique_id,
            floor_number=3,
        )
        self.state.containment_threat_event_id = event.event_id
        self.state.containment_event_count += 1
        result.containment_threat_event_id = event.event_id
        result.score_delta += settings.CONTAINMENT_CONTROL_SCORE
        self.add_message("Containment section open")
        self.add_message("Retrieve the Echo Core")

    def _update_elevator(
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
        if not elevator.interaction_rect.colliderect(player_rect):
            return
        self.state.interaction_target_id = elevator.unique_id
        if not self.state.echo_core_collected:
            self.state.current_prompt = "Echo Core required for extraction"
            if interact_held:
                self.add_message("Echo Core required for extraction")
            return
        self.state.current_prompt = "Press F to extract"
        if not interact_held:
            self.add_message_once("Press F to extract")
            return
        elevator.activate()
        self.state.floor_complete = True
        self.state.floor_complete_time = session_time
        result.floor_completed = True
        result.score_delta += settings.FLOOR3_COMPLETION_SCORE
        self.add_message("Extraction complete")

    def _reset_control_progress(self) -> None:
        if self.state.control_active:
            return
        self.state.interaction_progress = 0.0
        self.state.control_progress = 0.0
        self.control.install_progress = 0.0
        self.control.set_state(
            ContainmentControlState.READY
            if self.state.component_collected
            else ContainmentControlState.INACTIVE
        )

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
            self.state.current_objective_text = "Extraction complete"
        elif self.state.echo_core_collected:
            self.state.current_objective_text = "Return to the elevator"
        elif self.state.control_active:
            self.state.current_objective_text = "Retrieve the Echo Core"
        elif self.state.component_collected:
            self.state.current_objective_text = "Install component at containment control"
        else:
            self.state.current_objective_text = "Find the containment component"


def _select_containment_gate(
    generated_floor: GeneratedFloor,
    doors: list[DynamicDoor],
) -> tuple[DynamicDoor, GateCandidate]:
    containment_doors = [door for door in doors if door.door_type is DoorType.CONTAINMENT]
    if len(containment_doors) != 1:
        raise ValueError("Floor 3 requires exactly one containment door.")
    door = containment_doors[0]
    for gate in generated_floor.gate_candidates:
        if door.edge == gate.edge and door.tile in gate.doorway_tiles:
            return door, gate
    for gate in generated_floor.gate_candidates:
        if door.edge == gate.edge:
            return door, gate
    raise ValueError("Generated containment door does not match a gate candidate.")


def validate_floor3_placement(
    generated_floor: GeneratedFloor,
    placement: Floor3PlacementMetadata,
    *,
    reserved_tiles: set[tuple[int, int]] | None,
    containment_door: DynamicDoor,
) -> list[str]:
    errors: list[str] = []
    reserved = set(reserved_tiles or set())
    public_rooms = set(placement.public_side_room_ids)
    secure_rooms = set(placement.containment_side_room_ids)
    objective_tiles = {
        "component": placement.component_tile,
        "control": placement.control_tile,
        "echo_core": placement.core_tile,
    }
    blockers = DynamicBlockerRegistry([containment_door], settings.TILE_SIZE)
    if generated_floor.start_room_id not in public_rooms:
        errors.append("start room is not on containment public side")
    if not public_rooms or not secure_rooms:
        errors.append("containment gate partition is empty")
    if placement.component_room_id not in public_rooms:
        errors.append("containment component is not on public side")
    if placement.control_room_id not in public_rooms:
        errors.append("containment control is not on public side")
    if placement.core_room_id not in secure_rooms:
        errors.append("Echo Core is not in containment side")
    if len(set(objective_tiles.values())) != 3:
        errors.append("Floor 3 objective entities overlap")
    for name, tile in objective_tiles.items():
        if not generated_floor.is_walkable(*tile):
            errors.append(f"{name} is not on walkable tile")
            continue
        if generated_floor.tile_at(*tile) in (
            TileType.OBSTACLE,
            TileType.PILLAR,
            TileType.WALL,
            TileType.DAMAGED_WALL,
            TileType.VOID,
        ):
            errors.append(f"{name} overlaps blocker")
        if tile in generated_floor.doorway_candidates:
            errors.append(f"{name} overlaps doorway")
        if tile == generated_floor.elevator_tile or tile in generated_floor.elevator_approach_tiles:
            errors.append(f"{name} overlaps elevator")
        if tile in generated_floor.candidate_creature_spawns:
            errors.append(f"{name} overlaps creature spawn candidate")
        if tile in reserved:
            errors.append(f"{name} overlaps reserved runtime tile")
    if not _reachable_from_spawn_with(
        generated_floor, placement.component_tile, blockers, BlockerPurpose.MOVEMENT
    ):
        errors.append("containment component is not reachable before unlock")
    if not _reachable_from_spawn_with(
        generated_floor, placement.control_tile, blockers, BlockerPurpose.MOVEMENT
    ):
        errors.append("containment control is not reachable before unlock")
    if not _reachable_from_spawn_with(
        generated_floor, placement.core_tile, None, BlockerPurpose.MOVEMENT
    ):
        errors.append("Echo Core is not reachable after unlock")
    if not _has_interaction_space(generated_floor, placement.control_tile):
        errors.append("containment control lacks interaction space")
    return errors
