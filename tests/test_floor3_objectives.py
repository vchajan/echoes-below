import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.app import Game
from game.entities.door import DoorState, DoorType
from game.entities.objectives import ContainmentControlState
from game.entities.scan_objects import ElevatorState
from game.states import GameState, PlaceholderRun
from game.systems.floor3_objectives import Floor3ObjectiveSystem
from game.systems.threat_events import ThreatSourceType
from game.world import navigation
from game.world.blockers import BlockerPurpose


def create_floor3_game(seed: int = 12345) -> Game:
    game = Game()
    game.placeholder_run = PlaceholderRun(
        seed=seed,
        floor=3,
        score=1100,
        completed_floor_count=2,
        material_counts={"scrap": 1, "circuit": 2, "power_cell": 3},
        floor_completion_summaries={1: {"floor": 1}, 2: {"floor": 2}},
    )
    game.run_exists = True
    game.prepare_generated_floor()
    game.state = GameState.PLAYING
    for creature in game.creatures:
        creature.movement_enabled = False
    return game


def place_player_at(game: Game, tile: tuple[int, int]) -> None:
    assert game.player is not None
    assert game.camera is not None
    game.player.place_at_tile(tile)
    game.camera.update(game.player.world_position)


def collect_component(game: Game) -> None:
    objectives = game.floor_objectives
    assert isinstance(objectives, Floor3ObjectiveSystem)
    place_player_at(game, objectives.component.tile)
    game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)


def activate_control(game: Game) -> None:
    objectives = game.floor_objectives
    assert isinstance(objectives, Floor3ObjectiveSystem)
    place_player_at(game, objectives.control.tile)
    for _ in range(4):
        game.update_gameplay(
            settings.CONTAINMENT_INSTALL_DURATION / 4.0,
            pygame.Vector2(),
            interact_held=True,
        )


def collect_core(game: Game) -> None:
    objectives = game.floor_objectives
    assert isinstance(objectives, Floor3ObjectiveSystem)
    place_player_at(game, objectives.echo_core.tile)
    game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)


def signature(game: Game) -> tuple[object, ...]:
    objectives = game.floor_objectives
    assert isinstance(objectives, Floor3ObjectiveSystem)
    p = objectives.placement
    return (
        p.containment_gate_edge,
        p.containment_door_tile,
        p.component_room_id,
        p.control_room_id,
        p.core_room_id,
        p.component_tile,
        p.control_tile,
        p.core_tile,
    )


class Floor3ObjectiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = create_floor3_game()
        self.objectives = self.game.floor_objectives
        assert isinstance(self.objectives, Floor3ObjectiveSystem)

    def tearDown(self) -> None:
        self.game.shutdown()

    def test_initial_floor3_runtime(self) -> None:
        self.assertEqual(self.objectives.state.floor_number, 3)
        self.assertEqual(len(self.game.creatures), 2)
        self.assertTrue(self.game.floor_power_available)
        self.assertEqual(self.objectives.containment_door.door_type, DoorType.CONTAINMENT)
        self.assertEqual(self.objectives.containment_door.state, DoorState.LOCKED)
        self.assertEqual(self.game.elevator_entity.state, ElevatorState.LOCKED)
        self.assertEqual(self.objectives.placement.validation_errors, [])

    def test_placement_is_deterministic_and_seeded(self) -> None:
        other = create_floor3_game()
        different = create_floor3_game(12346)
        try:
            self.assertEqual(signature(self.game), signature(other))
            self.assertNotEqual(signature(self.game), signature(different))
        finally:
            other.shutdown()
            different.shutdown()

    def test_gate_partition_places_core_behind_containment(self) -> None:
        p = self.objectives.placement
        floor = self.game.placeholder_run.generated_floor
        self.assertIn(floor.start_room_id, p.public_side_room_ids)
        self.assertIn(p.component_room_id, p.public_side_room_ids)
        self.assertIn(p.control_room_id, p.public_side_room_ids)
        self.assertIn(p.core_room_id, p.containment_side_room_ids)
        self.assertTrue(set(p.public_side_room_ids).isdisjoint(p.containment_side_room_ids))
        self.assertTrue(
            self.game.dynamic_blockers.blocks_tile(
                *p.containment_door_tile, BlockerPurpose.MOVEMENT
            )
        )
        self.assertFalse(self.objectives.state.control_active)
        self.assertFalse(self.objectives.state.echo_core_collected)

    def test_component_collection_is_single_use_and_scores_once(self) -> None:
        start_score = self.game.placeholder_run.score
        collect_component(self.game)
        self.assertTrue(self.objectives.state.component_collected)
        self.assertFalse(self.objectives.component.scan_active)
        self.assertEqual(
            self.game.placeholder_run.score,
            start_score + settings.CONTAINMENT_COMPONENT_SCORE,
        )
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        self.assertEqual(
            self.game.placeholder_run.score,
            start_score + settings.CONTAINMENT_COMPONENT_SCORE,
        )
        self.assertEqual(self.objectives.control.state, ContainmentControlState.READY)

    def test_control_requires_component_and_hold_interaction(self) -> None:
        place_player_at(self.game, self.objectives.control.tile)
        self.game.update_gameplay(0.5, pygame.Vector2(), interact_held=True)
        self.assertFalse(self.objectives.state.control_active)
        self.assertEqual(self.objectives.state.control_progress, 0.0)
        collect_component(self.game)
        place_player_at(self.game, self.objectives.control.tile)
        self.game.update_gameplay(0.5, pygame.Vector2(), interact_held=True)
        self.assertGreater(self.objectives.state.control_progress, 0.0)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        self.assertEqual(self.objectives.state.control_progress, 0.0)

    def test_pause_freezes_control_progress(self) -> None:
        collect_component(self.game)
        place_player_at(self.game, self.objectives.control.tile)
        self.game.update_gameplay(0.5, pygame.Vector2(), interact_held=True)
        progress = self.objectives.state.control_progress
        self.game.transition_to(GameState.PAUSED)
        self.game.update(1.0)
        self.assertEqual(self.objectives.state.control_progress, progress)

    def test_control_unlocks_door_and_emits_one_event(self) -> None:
        collect_component(self.game)
        activate_control(self.game)
        self.assertTrue(self.objectives.state.control_active)
        self.assertFalse(self.objectives.containment_door.is_locked)
        self.assertEqual(self.objectives.control.state, ContainmentControlState.ACTIVE)
        events = [
            e for e in self.game.threat_events.active_events
            if e.source_type is ThreatSourceType.CONTAINMENT_CONTROL
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].world_position, self.objectives.control.world_position)
        self.assertGreater(events[0].strength, settings.THREAT_PLAYER_SCAN_STRENGTH)
        place_player_at(self.game, self.objectives.control.tile)
        self.game.update_gameplay(1.0, pygame.Vector2(), interact_held=True)
        self.assertEqual(
            len([e for e in self.game.threat_events.active_events if e.source_type is ThreatSourceType.CONTAINMENT_CONTROL]),
            1,
        )

    def test_core_cannot_be_collected_before_control(self) -> None:
        start_score = self.game.placeholder_run.score
        place_player_at(self.game, self.objectives.echo_core.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        self.assertFalse(self.objectives.state.echo_core_collected)
        self.assertEqual(self.game.placeholder_run.score, start_score)

    def test_core_starts_extraction_and_unlocks_elevator(self) -> None:
        collect_component(self.game)
        activate_control(self.game)
        initial_creatures = len(self.game.creatures)
        collect_core(self.game)
        self.assertTrue(self.objectives.state.echo_core_collected)
        self.assertTrue(self.objectives.state.extraction_active)
        self.assertEqual(self.game.elevator_entity.state, ElevatorState.UNLOCKED)
        self.assertTrue(self.objectives.state.extraction_creature_spawned)
        self.assertGreaterEqual(len(self.game.creatures), initial_creatures)
        events = [
            e for e in self.game.threat_events.active_events
            if e.source_type is ThreatSourceType.ECHO_CORE
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].world_position, self.objectives.echo_core.world_position)
        self.assertGreater(events[0].strength, settings.CONTAINMENT_THREAT_STRENGTH)

    def test_extraction_phase_increases_existing_creature_speed_once(self) -> None:
        collect_component(self.game)
        activate_control(self.game)
        original = [c.speed for c in self.game.creatures]
        collect_core(self.game)
        boosted = [c.speed for c in self.game.creatures[: len(original)]]
        for before, after in zip(original, boosted):
            self.assertAlmostEqual(after, before * settings.EXTRACTION_CREATURE_SPEED_MULTIPLIER)
        self.game._start_extraction_phase()
        self.assertEqual(boosted, [c.speed for c in self.game.creatures[: len(original)]])

    def test_elevator_requires_core(self) -> None:
        place_player_at(self.game, self.game.elevator_entity.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        self.assertEqual(self.game.state, GameState.PLAYING)
        self.assertFalse(self.objectives.state.floor_complete)

    def test_victory_preserves_summary_and_clears_runtime(self) -> None:
        collect_component(self.game)
        activate_control(self.game)
        collect_core(self.game)
        expected = self.game.placeholder_run.score + settings.FLOOR3_COMPLETION_SCORE
        place_player_at(self.game, self.game.elevator_entity.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        self.assertEqual(self.game.state, GameState.VICTORY)
        self.assertEqual(self.game.placeholder_run.score, expected)
        self.assertEqual(self.game.placeholder_run.completed_floor_count, 3)
        self.assertEqual(self.game.last_completed_floor, 3)
        summary = self.game.placeholder_run.floor_completion_summaries[3]
        self.assertTrue(summary["echo_core_recovered"])
        self.assertTrue(summary["extraction_completed"])
        self.assertIsNone(self.game.placeholder_run.generated_floor)
        self.assertIsNone(self.game.player)
        self.assertIsNone(self.game.floor_objectives)
        self.assertEqual(self.game.creatures, [])
        self.assertEqual(self.game.doors, [])
        self.assertEqual(len(self.game.threat_events.active_events), 0)
        self.assertEqual(self.game.snapshot_system.snapshots, [])

    def test_floor2_workshop_progresses_into_floor3(self) -> None:
        game = Game()
        try:
            game.placeholder_run = PlaceholderRun(
                seed=12345,
                floor=2,
                score=1100,
                completed_floor_count=2,
                floor_completion_summaries={1: {"floor": 1}, 2: {"floor": 2}},
            )
            game.run_exists = True
            game.last_completed_floor = 2
            game.state = GameState.WORKSHOP
            game.perform_action("continue_floor")
            self.assertEqual(game.state, GameState.FLOOR_TRANSITION)
            self.assertEqual(game.placeholder_run.floor, 3)
            game.update(settings.FLOOR_TRANSITION_DURATION + 0.1)
            self.assertEqual(game.state, GameState.PLAYING)
            self.assertIsInstance(game.floor_objectives, Floor3ObjectiveSystem)
            self.assertEqual(game.placeholder_run.completed_floor_count, 2)
            self.assertEqual(game.placeholder_run.score, 1100)
        finally:
            game.shutdown()

    def test_death_retry_same_seed_restarts_whole_run_at_floor1(self) -> None:
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

    def test_objective_snapshots_are_historical(self) -> None:
        component_outline = self.objectives.component.capture_scan_outline().copy()
        collect_component(self.game)
        self.assertFalse(self.objectives.component.scan_active)
        self.assertEqual(component_outline.get_size(), self.objectives.component.capture_scan_outline().get_size())
        collect_component_state = self.objectives.control.capture_scan_outline().copy()
        activate_control(self.game)
        self.assertNotEqual(
            pygame.image.tostring(collect_component_state, "RGBA"),
            pygame.image.tostring(self.objectives.control.capture_scan_outline(), "RGBA"),
        )


    def test_floor3_uses_one_containment_door_and_no_security_gate(self) -> None:
        containment = [door for door in self.game.doors if door.door_type is DoorType.CONTAINMENT]
        security = [door for door in self.game.doors if door.door_type is DoorType.SECURITY]
        self.assertEqual(len(containment), 1)
        self.assertEqual(security, [])
        self.assertEqual(containment[0], self.objectives.containment_door)

    def test_objective_tiles_are_unique_and_walkable(self) -> None:
        floor = self.game.placeholder_run.generated_floor
        p = self.objectives.placement
        tiles = [p.component_tile, p.control_tile, p.core_tile]
        self.assertEqual(len(set(tiles)), 3)
        for tile in tiles:
            self.assertTrue(floor.is_walkable(*tile))
            self.assertNotIn(tile, floor.doorway_candidates)
            self.assertNotEqual(tile, floor.elevator_tile)

    def test_leaving_control_range_resets_install_progress(self) -> None:
        collect_component(self.game)
        place_player_at(self.game, self.objectives.control.tile)
        self.game.update_gameplay(0.5, pygame.Vector2(), interact_held=True)
        self.assertGreater(self.objectives.state.control_progress, 0.0)
        floor = self.game.placeholder_run.generated_floor
        far_tile = next(
            tile for tile in floor.walkable_tiles()
            if not self.objectives.control.interaction_rect.collidepoint(
                (tile[0] + 0.5) * settings.TILE_SIZE,
                (tile[1] + 0.5) * settings.TILE_SIZE,
            )
        )
        place_player_at(self.game, far_tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        self.assertEqual(self.objectives.state.control_progress, 0.0)
        self.assertEqual(self.objectives.control.state, ContainmentControlState.READY)

    def test_containment_door_blocks_until_control_then_opens_normally(self) -> None:
        door = self.objectives.containment_door
        self.assertTrue(self.game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.MOVEMENT))
        collect_component(self.game)
        activate_control(self.game)
        self.assertEqual(door.state, DoorState.CLOSED)
        self.assertTrue(self.game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.SCAN))
        door.begin_opening()
        for _ in range(20):
            door.update(0.1, None, floor_powered=True)
            if door.is_fully_open:
                break
        self.assertTrue(door.is_fully_open)
        self.assertFalse(self.game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.MOVEMENT))
        self.assertFalse(self.game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.SCAN))

    def test_control_and_core_rewards_and_events_are_idempotent(self) -> None:
        collect_component(self.game)
        activate_control(self.game)
        score_after_control = self.game.placeholder_run.score
        activate_control(self.game)
        self.assertEqual(self.game.placeholder_run.score, score_after_control)
        self.assertEqual(self.objectives.state.containment_event_count, 1)
        collect_core(self.game)
        score_after_core = self.game.placeholder_run.score
        collect_core(self.game)
        self.assertEqual(self.game.placeholder_run.score, score_after_core)
        self.assertEqual(self.objectives.state.echo_core_event_count, 1)

    def test_victory_preserves_materials_and_complete_score_breakdown(self) -> None:
        before_materials = dict(self.game.placeholder_run.material_counts)
        before_score = self.game.placeholder_run.score
        collect_component(self.game)
        activate_control(self.game)
        collect_core(self.game)
        place_player_at(self.game, self.game.elevator_entity.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        expected = (
            before_score
            + settings.CONTAINMENT_COMPONENT_SCORE
            + settings.CONTAINMENT_CONTROL_SCORE
            + settings.ECHO_CORE_SCORE
            + settings.FLOOR3_COMPLETION_SCORE
        )
        self.assertEqual(self.game.placeholder_run.score, expected)
        self.assertEqual(self.game.placeholder_run.material_counts, before_materials)

    def test_new_run_after_victory_starts_clean_floor1(self) -> None:
        old_seed = self.game.placeholder_run.seed
        collect_component(self.game)
        activate_control(self.game)
        collect_core(self.game)
        place_player_at(self.game, self.game.elevator_entity.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        self.assertEqual(self.game.state, GameState.VICTORY)
        self.game.perform_action("new_run")
        self.assertEqual(self.game.state, GameState.PLAYING)
        self.assertEqual(self.game.placeholder_run.floor, 1)
        self.assertNotEqual(self.game.placeholder_run.seed, old_seed)
        self.assertEqual(self.game.placeholder_run.score, 0)
        self.assertEqual(self.game.placeholder_run.completed_floor_count, 0)

    def test_main_menu_after_victory_clears_run(self) -> None:
        collect_component(self.game)
        activate_control(self.game)
        collect_core(self.game)
        place_player_at(self.game, self.game.elevator_entity.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        self.game.perform_action("main_menu")
        self.assertEqual(self.game.state, GameState.MAIN_MENU)
        self.assertIsNone(self.game.placeholder_run)
        self.assertFalse(self.game.run_exists)

    def test_extraction_creature_spawn_is_deterministic(self) -> None:
        other = create_floor3_game()
        try:
            collect_component(self.game)
            activate_control(self.game)
            collect_core(self.game)
            collect_component(other)
            activate_control(other)
            collect_core(other)
            self.assertEqual(
                [(c.unique_id, c.spawn_tile) for c in self.game.creatures],
                [(c.unique_id, c.spawn_tile) for c in other.creatures],
            )
        finally:
            other.shutdown()



if __name__ == "__main__":
    unittest.main()
