from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from game import settings
from game.assets import AssetManager
from game.entities.door import DoorType, DynamicDoor
from game.entities.objectives import (
    GeneratorComponentPickup,
    GeneratorEntity,
    GeneratorState,
    RelayEntity,
    RelayState,
    SecurityKeycardPickup,
)
from game.entities.scan_objects import ElevatorEntity
from game.systems.threat_events import ThreatEventSystem, ThreatSourceType
from game.world import navigation
from game.world.blockers import BlockerPurpose, DynamicBlockerRegistry
from game.world.floor import GateCandidate, GeneratedFloor
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


@dataclass
class Floor2ObjectiveState:
    floor_number: int = 2
    keycard_entity_id: str = ""
    keycard_collected: bool = False
    security_door_id: str = ""
    security_door_unlocked: bool = False
    relay_a_entity_id: str = ""
    relay_b_entity_id: str = ""
    relay_a_active: bool = False
    relay_b_active: bool = False
    relay_a_progress: float = 0.0
    relay_b_progress: float = 0.0
    active_relay_id: str | None = None
    interaction_target_id: str | None = None
    interaction_progress: float = 0.0
    elevator_unlocked: bool = False
    floor_power_active: bool = True
    floor_complete: bool = False
    current_objective_text: str = "Find the security keycard"
    current_prompt: str = ""
    keycard_collected_time: float | None = None
    relay_a_active_time: float | None = None
    relay_b_active_time: float | None = None
    floor_complete_time: float | None = None
    relay_a_threat_event_id: int | None = None
    relay_b_threat_event_id: int | None = None
    relay_activation_event_count: int = 0

    @property
    def relays_active_count(self) -> int:
        return int(self.relay_a_active) + int(self.relay_b_active)

    @property
    def both_relays_active(self) -> bool:
        return self.relays_active_count == 2

    @property
    def objective_stage(self) -> str:
        if self.floor_complete:
            return "complete"
        if self.both_relays_active:
            return "return_to_elevator"
        if self.keycard_collected:
            return "activate_relays"
        return "find_keycard"


@dataclass
class Floor2PlacementMetadata:
    security_gate_edge: tuple[int, int]
    public_side_room_ids: tuple[int, ...]
    secure_side_room_ids: tuple[int, ...]
    security_door_id: str
    security_door_tile: tuple[int, int]
    keycard_room_id: int
    relay_a_room_id: int
    relay_b_room_id: int
    keycard_tile: tuple[int, int]
    relay_a_tile: tuple[int, int]
    relay_b_tile: tuple[int, int]
    validation_errors: list[str] = field(default_factory=list)
    placement_attempts: int = 1


class Floor2ObjectiveSystem:
    def __init__(
        self,
        state: Floor2ObjectiveState,
        keycard: SecurityKeycardPickup,
        relays: list[RelayEntity],
        security_door: DynamicDoor,
        placement: Floor2PlacementMetadata,
    ) -> None:
        self.state = state
        self.keycard = keycard
        self.relays = relays
        self.security_door = security_door
        self.placement = placement
        self.messages: list[ContextMessage] = []
        self._message_history: set[str] = set()

    @property
    def active_keycards(self) -> list[SecurityKeycardPickup]:
        return [self.keycard] if self.keycard.scan_active else []

    @property
    def scan_entities(self) -> list[object]:
        return [*self.active_keycards, *self.relays, self.security_door]

    @property
    def active_entities(self) -> list[object]:
        return [*self.active_keycards, *self.relays, self.security_door]

    @classmethod
    def create_for_floor(
        cls,
        generated_floor: GeneratedFloor,
        assets: AssetManager,
        tile_size: int,
        doors: list[DynamicDoor],
        *,
        reserved_tiles: set[tuple[int, int]] | None = None,
    ) -> "Floor2ObjectiveSystem":
        security_door, gate = _select_floor2_security_gate(generated_floor, doors)
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

        security_blockers = DynamicBlockerRegistry([security_door], tile_size)
        public_rooms = tuple(gate.key_side_rooms)
        secure_rooms = tuple(gate.gated_rooms)

        keycard_choice = _choose_floor2_tile(
            generated_floor,
            _floor2_room_order(generated_floor, public_rooms, prefer_public=True),
            reserved,
            security_blockers,
            require_reachable=True,
            require_interaction_space=False,
            avoid_start_when_possible=True,
        )
        if keycard_choice is None:
            raise ValueError("Could not place Floor 2 security keycard.")
        keycard_room_id, keycard_tile = keycard_choice
        reserved.add(keycard_tile)

        relay_a_choice = _choose_floor2_tile(
            generated_floor,
            _floor2_room_order(generated_floor, secure_rooms, prefer_public=False),
            reserved,
            None,
            require_reachable=False,
            require_interaction_space=True,
        )
        if relay_a_choice is None:
            raise ValueError("Could not place Floor 2 relay A.")
        relay_a_room_id, relay_a_tile = relay_a_choice
        reserved.add(relay_a_tile)

        relay_b_choice = _choose_floor2_tile(
            generated_floor,
            _floor2_room_order(
                generated_floor,
                secure_rooms,
                prefer_public=False,
                excluded={relay_a_room_id},
            ),
            reserved,
            None,
            require_reachable=False,
            require_interaction_space=True,
        )
        if relay_b_choice is None:
            relay_b_choice = _choose_floor2_tile(
                generated_floor,
                _floor2_room_order(generated_floor, secure_rooms, prefer_public=False),
                reserved,
                None,
                require_reachable=False,
                require_interaction_space=True,
            )
        if relay_b_choice is None:
            raise ValueError("Could not place Floor 2 relay B.")
        relay_b_room_id, relay_b_tile = relay_b_choice

        prefix = f"f2-a{generated_floor.generation_attempt}"
        keycard = SecurityKeycardPickup(
            f"{prefix}-keycard-{keycard_tile[0]}-{keycard_tile[1]}",
            keycard_room_id,
            keycard_tile,
            assets,
            tile_size,
        )
        relay_a = RelayEntity(
            f"{prefix}-relay-a-{relay_a_tile[0]}-{relay_a_tile[1]}",
            "A",
            relay_a_room_id,
            relay_a_tile,
            assets,
            tile_size,
        )
        relay_b = RelayEntity(
            f"{prefix}-relay-b-{relay_b_tile[0]}-{relay_b_tile[1]}",
            "B",
            relay_b_room_id,
            relay_b_tile,
            assets,
            tile_size,
        )
        state = Floor2ObjectiveState(
            floor_number=2,
            keycard_entity_id=keycard.unique_id,
            security_door_id=security_door.unique_id,
            relay_a_entity_id=relay_a.unique_id,
            relay_b_entity_id=relay_b.unique_id,
        )
        placement = Floor2PlacementMetadata(
            security_gate_edge=gate.edge,
            public_side_room_ids=public_rooms,
            secure_side_room_ids=secure_rooms,
            security_door_id=security_door.unique_id,
            security_door_tile=security_door.tile,
            keycard_room_id=keycard_room_id,
            relay_a_room_id=relay_a_room_id,
            relay_b_room_id=relay_b_room_id,
            keycard_tile=keycard_tile,
            relay_a_tile=relay_a_tile,
            relay_b_tile=relay_b_tile,
        )
        placement.validation_errors = validate_floor2_placement(
            generated_floor,
            placement,
            reserved_tiles=set(reserved_tiles or set()),
            security_door=security_door,
        )
        system = cls(state, keycard, [relay_a, relay_b], security_door, placement)
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
        self.keycard.update(dt)
        for relay in self.relays:
            relay.update(dt)

        if self.state.active_relay_id is not None:
            relay = self._relay_by_id(self.state.active_relay_id)
            if relay is None or relay.state is RelayState.ACTIVE or not relay.interaction_rect.colliderect(player_rect):
                self._reset_relay_progress(relay)

        self.state.current_prompt = ""
        self.state.interaction_target_id = None

        if self.keycard.scan_active:
            if self.keycard.collision_rect.colliderect(player_rect):
                if self.keycard.collect():
                    self.state.keycard_collected = True
                    self.state.keycard_collected_time = session_time
                    self.state.security_door_unlocked = True
                    self.security_door.unlock()
                    self.security_door.set_powered(True)
                    result.score_delta += self.keycard.score_value
                    self.add_message("Security keycard recovered")
                    self.add_message("Security door unlocked")
            elif self.keycard.collision_rect.inflate(settings.TILE_SIZE * 2, settings.TILE_SIZE * 2).colliderect(player_rect):
                self.state.current_prompt = "Security keycard detected"
                self.add_message_once("Security keycard detected")

        self._update_security_door_prompt(player_rect, interact_held)
        self._update_relay_interaction(
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
        relay = self._relay_by_id(self.state.active_relay_id)
        self._reset_relay_progress(relay)

    def reset_messages(self) -> None:
        self.messages.clear()
        self._message_history.clear()
        self.state.current_prompt = ""

    def _update_security_door_prompt(self, player_rect: pygame.Rect, interact_held: bool) -> None:
        if self.state.keycard_collected:
            return
        if not self.security_door.approach_rect.colliderect(player_rect):
            return
        self.state.interaction_target_id = self.security_door.unique_id
        self.state.current_prompt = "Security door locked"
        if interact_held:
            self.add_message("Security door locked")

    def _update_relay_interaction(
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
        relay = self._relay_in_range(player_rect)
        if relay is None:
            return
        self.state.interaction_target_id = relay.unique_id
        if relay.state is RelayState.ACTIVE:
            self.state.current_prompt = f"Relay {relay.label} active"
            return
        if not self.state.keycard_collected:
            self.state.current_prompt = "Security door locked"
            if interact_held:
                self.add_message("Security door locked")
            return

        self.state.current_prompt = f"Hold F to activate Relay {relay.label}"
        if not interact_held:
            self.add_message_once(f"Hold F to activate Relay {relay.label}")
            self._reset_relay_progress(relay)
            return

        if self.state.active_relay_id not in (None, relay.unique_id):
            self._reset_relay_progress(self._relay_by_id(self.state.active_relay_id))
        self.state.active_relay_id = relay.unique_id
        self.state.current_prompt = f"Activating Relay {relay.label}"
        relay.set_state(RelayState.ACTIVATING)
        self.state.interaction_progress = min(
            settings.RELAY_ACTIVATION_DURATION,
            self.state.interaction_progress + max(0.0, dt),
        )
        relay.activation_progress = self.state.interaction_progress
        if relay.label == "A":
            self.state.relay_a_progress = relay.activation_progress
        else:
            self.state.relay_b_progress = relay.activation_progress
        if self.state.interaction_progress + 1e-7 < settings.RELAY_ACTIVATION_DURATION:
            return

        relay.activation_progress = settings.RELAY_ACTIVATION_DURATION
        relay.set_state(RelayState.ACTIVE)
        self.state.interaction_progress = 0.0
        self.state.active_relay_id = None
        if relay.label == "A":
            self.state.relay_a_active = True
            self.state.relay_a_progress = settings.RELAY_ACTIVATION_DURATION
            self.state.relay_a_active_time = session_time
        else:
            self.state.relay_b_active = True
            self.state.relay_b_progress = settings.RELAY_ACTIVATION_DURATION
            self.state.relay_b_active_time = session_time
        event = threat_events.add_event(
            relay.world_position,
            ThreatSourceType.RELAY,
            strength=settings.RELAY_THREAT_STRENGTH,
            lifetime=settings.RELAY_THREAT_LIFETIME,
            creation_time=session_time,
            source_entity_id=relay.unique_id,
            floor_number=2,
        )
        if relay.label == "A":
            self.state.relay_a_threat_event_id = event.event_id
        else:
            self.state.relay_b_threat_event_id = event.event_id
        self.state.relay_activation_event_count += 1
        result.score_delta += settings.RELAY_ACTIVATION_SCORE
        self.add_message(f"Relay {relay.label} active")
        if self.state.both_relays_active:
            self.state.elevator_unlocked = True
            if elevator is not None:
                elevator.unlock()
            self.add_message("Security override complete")
            self.add_message("Return to the elevator")

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
        if not self.state.both_relays_active:
            self.state.current_prompt = f"Elevator locked: relays {self.state.relays_active_count} / 2"
            if interact_held:
                self.add_message(f"Elevator locked: relays {self.state.relays_active_count} / 2")
            return
        self.state.elevator_unlocked = True
        elevator.unlock()
        self.state.current_prompt = "Press F to enter elevator"
        if not interact_held:
            self.add_message_once("Press F to enter elevator")
            return
        elevator.activate()
        self.state.floor_complete = True
        self.state.floor_complete_time = session_time
        result.floor_completed = True
        result.score_delta += settings.FLOOR2_COMPLETION_SCORE
        self.add_message("Floor 2 complete")

    def _relay_in_range(self, player_rect: pygame.Rect) -> RelayEntity | None:
        current = self._relay_by_id(self.state.active_relay_id)
        if current is not None and current.state is not RelayState.ACTIVE and current.interaction_rect.colliderect(player_rect):
            return current
        for relay in self.relays:
            if relay.state is not RelayState.ACTIVE and relay.interaction_rect.colliderect(player_rect):
                return relay
        for relay in self.relays:
            if relay.interaction_rect.colliderect(player_rect):
                return relay
        return None

    def _relay_by_id(self, relay_id: str | None) -> RelayEntity | None:
        if relay_id is None:
            return None
        return next((relay for relay in self.relays if relay.unique_id == relay_id), None)

    def _reset_relay_progress(self, relay: RelayEntity | None) -> None:
        if relay is not None and relay.state is not RelayState.ACTIVE:
            relay.activation_progress = 0.0
            relay.set_state(RelayState.INACTIVE)
            if relay.label == "A":
                self.state.relay_a_progress = 0.0
            else:
                self.state.relay_b_progress = 0.0
        self.state.interaction_progress = 0.0
        self.state.active_relay_id = None

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
            self.state.current_objective_text = "Floor 2 complete"
        elif self.state.both_relays_active:
            self.state.current_objective_text = "Return to the elevator"
        elif self.state.keycard_collected:
            self.state.current_objective_text = f"Activate relay terminals: {self.state.relays_active_count} / 2"
        else:
            self.state.current_objective_text = "Find the security keycard"


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


def validate_floor2_placement(
    generated_floor: GeneratedFloor,
    placement: Floor2PlacementMetadata,
    *,
    reserved_tiles: set[tuple[int, int]] | None = None,
    security_door: DynamicDoor,
) -> list[str]:
    errors: list[str] = []
    reserved = set(reserved_tiles or set())
    public_rooms = set(placement.public_side_room_ids)
    secure_rooms = set(placement.secure_side_room_ids)
    objective_tiles = {
        "keycard": placement.keycard_tile,
        "relay_a": placement.relay_a_tile,
        "relay_b": placement.relay_b_tile,
    }
    security_blockers = DynamicBlockerRegistry([security_door], settings.TILE_SIZE)

    if not placement.security_door_id:
        errors.append("missing required security door")
    if not placement.public_side_room_ids:
        errors.append("public side is empty")
    if not placement.secure_side_room_ids:
        errors.append("secure side is empty")
    if generated_floor.start_room_id not in public_rooms:
        errors.append("start room is not on public side")
    if placement.relay_a_room_id == placement.relay_b_room_id:
        errors.append("relay rooms are not distinct")
    if placement.keycard_room_id not in public_rooms:
        errors.append("keycard is not on public side")
    if placement.relay_a_room_id not in secure_rooms:
        errors.append("relay A is not on secure side")
    if placement.relay_b_room_id not in secure_rooms:
        errors.append("relay B is not on secure side")
    if len(set(objective_tiles.values())) != 3:
        errors.append("Floor 2 objective entities overlap each other")

    for name, tile in objective_tiles.items():
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

    if not _reachable_from_spawn_with(
        generated_floor,
        placement.keycard_tile,
        security_blockers,
        BlockerPurpose.MOVEMENT,
    ):
        errors.append("keycard is not reachable before security unlock")
    for name, tile in (("relay A", placement.relay_a_tile), ("relay B", placement.relay_b_tile)):
        if not _reachable_from_spawn_with(generated_floor, tile, None, BlockerPurpose.MOVEMENT):
            errors.append(f"{name} is not reachable after security unlock")
    if not _reachable_from_spawn_with(
        generated_floor,
        generated_floor.elevator_tile,
        security_blockers,
        BlockerPurpose.MOVEMENT,
    ):
        errors.append("elevator is not reachable before security unlock")
    if not _has_interaction_space(generated_floor, placement.relay_a_tile):
        errors.append("relay A lacks walkable interaction space")
    if not _has_interaction_space(generated_floor, placement.relay_b_tile):
        errors.append("relay B lacks walkable interaction space")
    return errors


def _select_floor2_security_gate(
    generated_floor: GeneratedFloor,
    doors: list[DynamicDoor],
) -> tuple[DynamicDoor, GateCandidate]:
    security_doors = [door for door in doors if door.door_type is DoorType.SECURITY]
    if not security_doors:
        raise ValueError("Floor 2 requires one generated security door.")
    for gate in generated_floor.gate_candidates:
        for door in security_doors:
            if door.edge == gate.edge and door.tile in gate.doorway_tiles:
                return door, gate
    for gate in generated_floor.gate_candidates:
        if security_doors[0].edge == gate.edge:
            return security_doors[0], gate
    raise ValueError("Generated security door does not match a gate candidate.")


def _floor2_room_order(
    generated_floor: GeneratedFloor,
    room_ids: tuple[int, ...] | list[int],
    *,
    prefer_public: bool,
    excluded: set[int] | None = None,
) -> list[int]:
    excluded = excluded or set()
    allowed = [room_id for room_id in room_ids if room_id not in excluded]
    allowed.sort(
        key=lambda room_id: (
            generated_floor.start_room_id == room_id if prefer_public else False,
            -(generated_floor.graph_distance(generated_floor.start_room_id, room_id) or 0),
            -generated_floor.rooms[room_id].rect.area,
            room_id,
        )
    )
    if prefer_public:
        non_start = [room_id for room_id in allowed if room_id != generated_floor.start_room_id]
        return non_start + [room_id for room_id in allowed if room_id == generated_floor.start_room_id]
    return allowed


def _choose_floor2_tile(
    generated_floor: GeneratedFloor,
    room_ids: list[int],
    reserved: set[tuple[int, int]],
    dynamic_blockers: DynamicBlockerRegistry | None,
    *,
    require_reachable: bool,
    require_interaction_space: bool,
    avoid_start_when_possible: bool = False,
) -> tuple[int, tuple[int, int]] | None:
    room_order = list(room_ids)
    if avoid_start_when_possible and len(room_order) > 1:
        room_order = [room_id for room_id in room_order if room_id != generated_floor.start_room_id] + [
            room_id for room_id in room_order if room_id == generated_floor.start_room_id
        ]
    for room_id in room_order:
        room = generated_floor.rooms[room_id]
        for margin in (2, 1, 0):
            candidates = [
                tile
                for tile in room.rect.interior_tiles(margin=margin)
                if _valid_floor2_tile(
                    generated_floor,
                    tile,
                    reserved,
                    dynamic_blockers,
                    require_reachable=require_reachable,
                    require_interaction_space=require_interaction_space,
                )
            ]
            candidates.sort(key=lambda tile: (_distance_squared(tile, room.center), tile[1], tile[0]))
            if candidates:
                return (room_id, candidates[0])
    return None


def _valid_floor2_tile(
    generated_floor: GeneratedFloor,
    tile: tuple[int, int],
    reserved: set[tuple[int, int]],
    dynamic_blockers: DynamicBlockerRegistry | None,
    *,
    require_reachable: bool,
    require_interaction_space: bool,
) -> bool:
    if tile in reserved or tile in generated_floor.doorway_candidates:
        return False
    if tile in generated_floor.candidate_creature_spawns:
        return False
    if tile == generated_floor.elevator_tile or tile in generated_floor.elevator_approach_tiles:
        return False
    if not generated_floor.is_walkable(*tile):
        return False
    if require_interaction_space and not _has_interaction_space(generated_floor, tile):
        return False
    if require_reachable and not _reachable_from_spawn_with(
        generated_floor,
        tile,
        dynamic_blockers,
        BlockerPurpose.MOVEMENT,
    ):
        return False
    return True


def _reachable_from_spawn_with(
    generated_floor: GeneratedFloor,
    tile: tuple[int, int],
    dynamic_blockers: DynamicBlockerRegistry | None,
    purpose: BlockerPurpose,
) -> bool:
    start = generated_floor.player_spawn
    return start == tile or bool(navigation.astar_path(generated_floor, start, tile, dynamic_blockers, purpose))
