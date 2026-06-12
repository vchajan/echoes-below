import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.app import Game
from game.entities.door import DoorState
from game.entities.objectives import RelayState
from game.entities.scan_objects import ElevatorState
from game.systems.creature_ai import CreatureState
from game.states import GameState, PlaceholderRun
from game.systems.raycasting import has_line_of_sight
from game.systems.snapshots import EchoSnapshot
from game.systems.threat_events import ThreatSourceType
from game.world import collision, navigation
from game.world.blockers import BlockerPurpose


def place_player_at(game: Game, tile: tuple[int, int]) -> None:
    assert game.player is not None
    assert game.camera is not None
    game.player.place_at_tile(tile)
    game.camera.update(game.player.world_position)


def freeze_creatures(game: Game) -> None:
    for creature in game.creatures:
        creature.movement_enabled = False


def create_floor2_game(seed: int = 12345) -> Game:
    game = Game()
    game.placeholder_run = PlaceholderRun(
        seed=seed,
        floor=2,
        score=550,
        completed_floor_count=1,
        material_counts={"scrap": 1, "circuit": 2, "power_cell": 3},
    )
    game.run_exists = True
    game.prepare_generated_floor()
    game.state = GameState.PLAYING
    freeze_creatures(game)
    return game


def collect_keycard(game: Game) -> None:
    assert game.floor_objectives is not None
    place_player_at(game, game.floor_objectives.keycard.tile)
    game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)


def activate_relay(game: Game, index: int) -> None:
    assert game.floor_objectives is not None
    relay = game.floor_objectives.relays[index]
    place_player_at(game, relay.tile)
    for _ in range(4):
        game.update_gameplay(settings.RELAY_ACTIVATION_DURATION / 4.0, pygame.Vector2(), interact_held=True)


def complete_floor2(game: Game) -> None:
    collect_keycard(game)
    activate_relay(game, 0)
    activate_relay(game, 1)
    assert game.elevator_entity is not None
    place_player_at(game, game.elevator_entity.tile)
    game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)


def hidden_tile_for_all_creatures(game: Game) -> tuple[int, int]:
    floor = game.placeholder_run.generated_floor
    assert floor is not None
    best: tuple[float, tuple[int, int]] | None = None
    for tile in floor.walkable_tiles():
        world = pygame.Vector2((tile[0] + 0.5) * settings.TILE_SIZE, (tile[1] + 0.5) * settings.TILE_SIZE)
        distances = [world.distance_to(creature.world_position) for creature in game.creatures]
        if not distances or min(distances) <= settings.CREATURE_DETECTION_DISTANCE + settings.TILE_SIZE:
            continue
        score = min(distances)
        if best is None or score > best[0]:
            best = (score, tile)
    assert best is not None
    return best[1]


def objective_signature(game: Game) -> tuple[object, ...]:
    assert game.floor_objectives is not None
    placement = game.floor_objectives.placement
    return (
        placement.security_gate_edge,
        placement.security_door_tile,
        placement.keycard_room_id,
        placement.relay_a_room_id,
        placement.relay_b_room_id,
        placement.keycard_tile,
        placement.relay_a_tile,
        placement.relay_b_tile,
        game.floor_objectives.keycard.unique_id,
        tuple(relay.unique_id for relay in game.floor_objectives.relays),
    )


def clear_runtime_assertions(test: unittest.TestCase, game: Game) -> None:
    test.assertEqual(game.state, GameState.WORKSHOP)
    test.assertEqual(game.last_completed_floor, 2)
    test.assertIsNotNone(game.placeholder_run)
    assert game.placeholder_run is not None
    test.assertEqual(game.placeholder_run.completed_floor_count, 2)
    test.assertIsNone(game.placeholder_run.generated_floor)
    test.assertIsNone(game.player)
    test.assertIsNone(game.camera)
    test.assertEqual(game.doors, [])
    test.assertFalse(game.floor_power_available)
    test.assertIsNone(game.floor_content)
    test.assertIsNone(game.floor_objectives)
    test.assertEqual(game.material_pickups, [])
    test.assertIsNone(game.elevator_entity)
    test.assertEqual(game.creatures, [])
    test.assertIsNone(game.creatures_rng)
    test.assertIsNone(game.scan_system.active_wave)
    test.assertEqual(game.scan_system.traces, [])
    test.assertEqual(game.snapshot_system.snapshots, [])
    test.assertEqual(len(game.threat_events.active_events), 0)


def door_side_points(door) -> tuple[pygame.Vector2, pygame.Vector2]:
    if door.orientation == "vertical_door_plane":
        return (
            pygame.Vector2(door.world_center.x - settings.TILE_SIZE, door.world_center.y),
            pygame.Vector2(door.world_center.x + settings.TILE_SIZE, door.world_center.y),
        )
    return (
        pygame.Vector2(door.world_center.x, door.world_center.y - settings.TILE_SIZE),
        pygame.Vector2(door.world_center.x, door.world_center.y + settings.TILE_SIZE),
    )


class Floor2ObjectiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = create_floor2_game()

    def tearDown(self) -> None:
        self.game.shutdown()

    def test_floor2_initial_state(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        self.assertEqual(objectives.state.floor_number, 2)
        self.assertTrue(self.game.floor_power_available)
        self.assertEqual(len(self.game.creatures), 2)
        self.assertEqual(len(objectives.relays), 2)
        self.assertTrue(objectives.keycard.scan_active)
        self.assertEqual(self.game.elevator_entity.state, ElevatorState.LOCKED)
        self.assertEqual(objectives.security_door.state, DoorState.LOCKED)
        self.assertEqual(objectives.placement.validation_errors, [])

    def test_progression_from_floor1_workshop_to_floor2_preserves_run_summary(self) -> None:
        game = Game()
        try:
            game.start_new_run()
            freeze_creatures(game)
            for component in game.floor_objectives.components:
                place_player_at(game, component.tile)
                game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
            place_player_at(game, game.floor_objectives.generator.tile)
            for _ in range(4):
                game.update_gameplay(settings.GENERATOR_REPAIR_DURATION / 4.0, pygame.Vector2(), interact_held=True)
            score_before = game.placeholder_run.score
            game.placeholder_run.material_counts["scrap"] = 2
            place_player_at(game, game.elevator_entity.tile)
            game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
            self.assertEqual(game.state, GameState.WORKSHOP)

            game.perform_action("continue_floor")
            self.assertEqual(game.state, GameState.FLOOR_TRANSITION)
            self.assertEqual(game.placeholder_run.floor, 2)
            game.update(settings.FLOOR_TRANSITION_DURATION + 0.1)
            self.assertEqual(game.state, GameState.PLAYING)
            self.assertEqual(game.placeholder_run.generated_floor.floor_number, 2)
            self.assertEqual(game.placeholder_run.seed, game.next_seed)
            self.assertEqual(game.placeholder_run.score, score_before + settings.FLOOR_COMPLETION_SCORE)
            self.assertEqual(game.placeholder_run.material_counts["scrap"], 2)
            self.assertEqual(game.placeholder_run.completed_floor_count, 1)
            self.assertIsNotNone(game.floor_objectives)
            self.assertEqual(game.floor_objectives.state.floor_number, 2)
        finally:
            game.shutdown()

    def test_floor2_placement_is_deterministic_and_seeded(self) -> None:
        first = objective_signature(self.game)
        other = create_floor2_game()
        different = create_floor2_game(seed=12346)
        try:
            self.assertEqual(objective_signature(other), first)
            self.assertNotEqual(objective_signature(different), first)
        finally:
            other.shutdown()
            different.shutdown()

    def test_floor2_generation_retries_until_gate_candidate_exists(self) -> None:
        game = create_floor2_game(seed=1001)
        try:
            floor = game.placeholder_run.generated_floor
            assert floor is not None
            self.assertGreaterEqual(floor.generation_attempt, 2)
            self.assertGreaterEqual(len(floor.gate_candidates), 1)
            self.assertEqual(game.floor_objectives.placement.validation_errors, [])
        finally:
            game.shutdown()

    def test_gate_partition_and_objective_tiles_are_valid(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        floor = self.game.placeholder_run.generated_floor
        assert floor is not None
        placement = objectives.placement
        public_rooms = set(placement.public_side_room_ids)
        secure_rooms = set(placement.secure_side_room_ids)
        self.assertIn(floor.start_room_id, public_rooms)
        self.assertTrue(public_rooms.isdisjoint(secure_rooms))
        gate_a, gate_b = placement.security_gate_edge
        self.assertTrue(
            (gate_a in public_rooms and gate_b in secure_rooms)
            or (gate_b in public_rooms and gate_a in secure_rooms)
        )
        self.assertIn(placement.keycard_room_id, public_rooms)
        self.assertIn(placement.relay_a_room_id, secure_rooms)
        self.assertIn(placement.relay_b_room_id, secure_rooms)
        self.assertNotEqual(placement.relay_a_room_id, placement.relay_b_room_id)
        objective_tiles = {placement.keycard_tile, placement.relay_a_tile, placement.relay_b_tile}
        reserved = {floor.elevator_tile, *floor.elevator_approach_tiles, *floor.doorway_candidates}
        reserved.update(pickup.tile for pickup in self.game.material_pickups)
        reserved.update(creature.current_tile for creature in self.game.creatures)
        self.assertTrue(objective_tiles.isdisjoint(reserved))
        for tile in objective_tiles:
            self.assertTrue(floor.is_walkable(*tile))

    def test_keycard_collection_unlocks_security_door_once(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        starting_score = self.game.placeholder_run.score
        collect_keycard(self.game)
        self.assertTrue(objectives.state.keycard_collected)
        self.assertFalse(objectives.keycard.scan_active)
        self.assertFalse(objectives.security_door.is_locked)
        self.assertEqual(objectives.security_door.state, DoorState.CLOSED)
        self.assertEqual(self.game.placeholder_run.score, starting_score + settings.SECURITY_KEYCARD_SCORE)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        self.assertEqual(self.game.placeholder_run.score, starting_score + settings.SECURITY_KEYCARD_SCORE)

    def test_keycard_historical_snapshot_survives_collection(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        snapshot = EchoSnapshot.capture(objectives.keycard, scan_id=1, lifetime=5.0)
        before = pygame.image.tobytes(snapshot.image, "RGBA")
        collect_keycard(self.game)
        self.assertFalse(objectives.keycard.scan_active)
        self.assertEqual(pygame.image.tobytes(snapshot.image, "RGBA"), before)

    def test_scan_at_keycard_creates_snapshot_before_collection(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        place_player_at(self.game, objectives.keycard.tile)
        self.assertTrue(self.game.trigger_scan())
        self.game.update_gameplay(0.01, pygame.Vector2(), interact_held=False)
        snapshots = self.game.snapshot_system.snapshots_for_source(objectives.keycard.unique_id)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].category, objectives.keycard.scan_category)
        self.assertTrue(objectives.state.keycard_collected)
        self.assertFalse(objectives.keycard.scan_active)

    def test_security_door_blocker_semantics_before_and_after_unlock(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        door = objectives.security_door
        floor = self.game.placeholder_run.generated_floor
        assert floor is not None
        left, right = door_side_points(door)
        self.assertTrue(self.game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.MOVEMENT))
        self.assertTrue(self.game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.SCAN))
        self.assertTrue(self.game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.LINE_OF_SIGHT))
        self.assertFalse(has_line_of_sight(left, right, floor, self.game.dynamic_blockers, settings.TILE_SIZE))
        self.assertEqual(
            navigation.astar_path(floor, floor.player_spawn, door.tile, self.game.dynamic_blockers, BlockerPurpose.MOVEMENT),
            [],
        )
        collect_keycard(self.game)
        self.assertTrue(self.game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.MOVEMENT))
        door.force_open()
        self.assertFalse(self.game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.MOVEMENT))
        self.assertFalse(self.game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.SCAN))
        self.assertTrue(has_line_of_sight(left, right, floor, self.game.dynamic_blockers, settings.TILE_SIZE))
        self.assertTrue(
            navigation.astar_path(floor, floor.player_spawn, door.tile, self.game.dynamic_blockers, BlockerPurpose.MOVEMENT)
            or floor.player_spawn == door.tile
        )

    def test_relay_interaction_requires_range_hold_and_resets(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_keycard(self.game)
        relay = objectives.relays[0]
        place_player_at(self.game, self.game.placeholder_run.generated_floor.player_spawn)
        self.game.update_gameplay(0.5, pygame.Vector2(), interact_held=True)
        self.assertEqual(relay.activation_progress, 0.0)
        place_player_at(self.game, relay.tile)
        self.game.update_gameplay(0.5, pygame.Vector2(), interact_held=True)
        self.assertGreater(relay.activation_progress, 0.0)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        self.assertEqual(relay.activation_progress, 0.0)
        self.game.update_gameplay(0.5, pygame.Vector2(), interact_held=True)
        place_player_at(self.game, self.game.placeholder_run.generated_floor.player_spawn)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        self.assertEqual(relay.activation_progress, 0.0)

    def test_pause_freezes_relay_progress_and_progress_does_not_transfer(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_keycard(self.game)
        relay_a, relay_b = objectives.relays
        place_player_at(self.game, relay_a.tile)
        self.game.update_gameplay(0.5, pygame.Vector2(), interact_held=True)
        frozen = relay_a.activation_progress
        self.game.transition_to(GameState.PAUSED)
        self.game.update(1.0)
        self.assertEqual(relay_a.activation_progress, frozen)
        self.game.transition_to(GameState.PLAYING)
        place_player_at(self.game, relay_b.tile)
        self.game.update_gameplay(0.1, pygame.Vector2(), interact_held=True)
        self.assertEqual(relay_a.activation_progress, 0.0)
        self.assertGreater(relay_b.activation_progress, 0.0)

    def test_relay_activation_emits_one_strong_threat_and_scores_once(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_keycard(self.game)
        starting_score = self.game.placeholder_run.score
        activate_relay(self.game, 0)
        relay = objectives.relays[0]
        self.assertEqual(relay.state, RelayState.ACTIVE)
        self.assertEqual(self.game.placeholder_run.score, starting_score + settings.RELAY_ACTIVATION_SCORE)
        relay_events = [event for event in self.game.threat_events.active_events if event.source_type is ThreatSourceType.RELAY]
        self.assertEqual(len(relay_events), 1)
        self.assertEqual(relay_events[0].world_position, relay.world_position)
        self.assertEqual(relay_events[0].source_entity_id, relay.unique_id)
        self.assertGreater(relay_events[0].strength, settings.THREAT_PLAYER_SCAN_STRENGTH)
        activate_relay(self.game, 0)
        self.assertEqual(
            len([event for event in self.game.threat_events.active_events if event.source_type is ThreatSourceType.RELAY]),
            1,
        )
        self.assertEqual(self.game.placeholder_run.score, starting_score + settings.RELAY_ACTIVATION_SCORE)

    def test_relay_threat_can_send_creatures_to_investigate_without_forcing_chase(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_keycard(self.game)
        objectives.security_door.force_open()
        for creature in self.game.creatures:
            creature.movement_enabled = True
        activate_relay(self.game, 0)
        relay_event_id = objectives.state.relay_a_threat_event_id
        self.assertIsNotNone(relay_event_id)
        place_player_at(self.game, hidden_tile_for_all_creatures(self.game))
        investigated = False
        for _ in range(120):
            self.game.update_gameplay(1.0 / settings.FPS, pygame.Vector2(), interact_held=False)
            for creature in self.game.creatures:
                ai = creature.ai
                if ai is None:
                    continue
                self.assertIsNot(ai.state, CreatureState.CHASE)
                if ai.state is CreatureState.INVESTIGATE and ai.selected_threat_event_id == relay_event_id:
                    self.assertEqual(ai.investigation_target_tile, objectives.relays[0].tile)
                    investigated = True
            if investigated:
                break
        self.assertTrue(investigated)

    def test_one_relay_keeps_elevator_locked_both_unlock_it(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_keycard(self.game)
        activate_relay(self.game, 0)
        self.assertFalse(objectives.state.elevator_unlocked)
        self.assertEqual(self.game.elevator_entity.state, ElevatorState.LOCKED)
        activate_relay(self.game, 1)
        self.assertTrue(objectives.state.elevator_unlocked)
        self.assertEqual(self.game.elevator_entity.state, ElevatorState.UNLOCKED)

    def test_elevator_completion_cleans_runtime_and_preserves_summary(self) -> None:
        expected_materials = dict(self.game.placeholder_run.material_counts)
        material_name = self.game.material_pickups[0].material_type.value
        place_player_at(self.game, self.game.material_pickups[0].tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        expected_materials[material_name] += 1
        self.assertEqual(self.game.placeholder_run.material_counts, expected_materials)
        collect_keycard(self.game)
        assert self.game.elevator_entity is not None
        place_player_at(self.game, self.game.elevator_entity.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        self.assertEqual(self.game.state, GameState.PLAYING)
        activate_relay(self.game, 0)
        activate_relay(self.game, 1)
        expected_score = self.game.placeholder_run.score + settings.FLOOR2_COMPLETION_SCORE
        place_player_at(self.game, self.game.elevator_entity.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        clear_runtime_assertions(self, self.game)
        self.assertEqual(self.game.placeholder_run.score, expected_score)
        summary = self.game.placeholder_run.floor_completion_summaries[2]
        self.assertTrue(summary["keycard_recovered"])
        self.assertTrue(summary["relay_a_active"])
        self.assertTrue(summary["relay_b_active"])
        self.assertTrue(summary["security_override_completed"])

    def test_floor2_workshop_continue_transitions_to_floor3(self) -> None:
        complete_floor2(self.game)
        self.assertEqual(self.game.state, GameState.WORKSHOP)
        self.game.perform_action("continue_floor")
        self.assertEqual(self.game.state, GameState.FLOOR_TRANSITION)
        self.assertEqual(self.game.placeholder_run.floor, 3)
        self.game.update(settings.FLOOR_TRANSITION_DURATION + 0.1)
        self.assertEqual(self.game.state, GameState.PLAYING)
        self.assertIsNotNone(self.game.placeholder_run.generated_floor)
        self.assertEqual(self.game.placeholder_run.generated_floor.floor_number, 3)
        self.assertIsNotNone(self.game.floor_objectives)
        self.assertEqual(self.game.floor_objectives.state.floor_number, 3)

    def test_retry_same_seed_after_floor2_death_restarts_whole_run_at_floor1(self) -> None:
        creature = self.game.creatures[0]
        self.game.player.world_position = creature.world_position.copy()
        self.game.player._sync_rects_from_world()
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        self.assertEqual(self.game.state, GameState.DEATH)
        self.game.retry_same_seed()
        self.assertEqual(self.game.state, GameState.PLAYING)
        self.assertEqual(self.game.placeholder_run.floor, 1)
        self.assertEqual(self.game.placeholder_run.completed_floor_count, 0)
        self.assertEqual(self.game.placeholder_run.score, 0)
        self.assertEqual(self.game.placeholder_run.material_counts, {"scrap": 0, "circuit": 0, "power_cell": 0})
        self.assertEqual(self.game.floor_objectives.state.floor_number, 1)

    def test_new_run_and_main_menu_clear_floor2_progression(self) -> None:
        collect_keycard(self.game)
        old_seed = self.game.placeholder_run.seed
        self.game.start_new_run()
        self.assertNotEqual(self.game.placeholder_run.seed, old_seed)
        self.assertEqual(self.game.placeholder_run.floor, 1)
        self.assertEqual(self.game.placeholder_run.completed_floor_count, 0)
        self.assertEqual(self.game.floor_objectives.state.floor_number, 1)
        self.game.perform_action("main_menu")
        self.assertEqual(self.game.state, GameState.MAIN_MENU)
        self.assertIsNone(self.game.placeholder_run)
        self.assertIsNone(self.game.floor_objectives)
        self.assertEqual(self.game.creatures, [])
        self.assertEqual(len(self.game.threat_events.active_events), 0)

    def test_relay_elevator_and_security_snapshots_remain_historical(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        relay = objectives.relays[0]
        inactive_relay = EchoSnapshot.capture(relay, scan_id=1, lifetime=5.0)
        locked_door = EchoSnapshot.capture(objectives.security_door, scan_id=1, lifetime=5.0)
        locked_elevator = EchoSnapshot.capture(self.game.elevator_entity, scan_id=1, lifetime=5.0)
        inactive_relay_bytes = pygame.image.tobytes(inactive_relay.image, "RGBA")
        locked_door_bytes = pygame.image.tobytes(locked_door.image, "RGBA")
        locked_elevator_bytes = pygame.image.tobytes(locked_elevator.image, "RGBA")

        collect_keycard(self.game)
        objectives.security_door.force_open()
        activate_relay(self.game, 0)
        activate_relay(self.game, 1)
        active_relay = EchoSnapshot.capture(relay, scan_id=2, lifetime=5.0)
        open_door = EchoSnapshot.capture(objectives.security_door, scan_id=2, lifetime=5.0)
        unlocked_elevator = EchoSnapshot.capture(self.game.elevator_entity, scan_id=2, lifetime=5.0)
        self.assertNotEqual(inactive_relay_bytes, pygame.image.tobytes(active_relay.image, "RGBA"))
        self.assertNotEqual(locked_door_bytes, pygame.image.tobytes(open_door.image, "RGBA"))
        self.assertNotEqual(locked_elevator_bytes, pygame.image.tobytes(unlocked_elevator.image, "RGBA"))
        self.assertEqual(pygame.image.tobytes(inactive_relay.image, "RGBA"), inactive_relay_bytes)
        self.assertEqual(pygame.image.tobytes(locked_door.image, "RGBA"), locked_door_bytes)
        self.assertEqual(pygame.image.tobytes(locked_elevator.image, "RGBA"), locked_elevator_bytes)

    def test_relay_snapshots_preserve_inactive_activating_and_active_frames(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        relay = objectives.relays[0]
        inactive_snapshot = EchoSnapshot.capture(relay, scan_id=1, lifetime=5.0)
        inactive_bytes = pygame.image.tobytes(inactive_snapshot.image, "RGBA")

        collect_keycard(self.game)
        place_player_at(self.game, relay.tile)
        self.game.update_gameplay(settings.RELAY_ACTIVATION_DURATION * 0.5, pygame.Vector2(), interact_held=True)
        activating_snapshot = EchoSnapshot.capture(relay, scan_id=2, lifetime=5.0)
        activating_bytes = pygame.image.tobytes(activating_snapshot.image, "RGBA")

        activate_relay(self.game, 0)
        active_snapshot = EchoSnapshot.capture(relay, scan_id=3, lifetime=5.0)
        active_bytes = pygame.image.tobytes(active_snapshot.image, "RGBA")

        self.assertNotEqual(inactive_bytes, activating_bytes)
        self.assertNotEqual(activating_bytes, active_bytes)
        self.assertEqual(pygame.image.tobytes(inactive_snapshot.image, "RGBA"), inactive_bytes)
        self.assertEqual(pygame.image.tobytes(activating_snapshot.image, "RGBA"), activating_bytes)


if __name__ == "__main__":
    unittest.main()
