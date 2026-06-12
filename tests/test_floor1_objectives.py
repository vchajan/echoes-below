import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.app import Game
from game.entities.door import DoorState, DoorType
from game.entities.objectives import GeneratorState
from game.entities.scan_objects import ElevatorState
from game.states import GameState, PlaceholderRun
from game.systems.snapshots import EchoSnapshot
from game.systems.threat_events import ThreatSourceType
from game.world import collision
from game.world import navigation
from game.world.blockers import BlockerPurpose


def place_player_at(game: Game, tile: tuple[int, int]) -> None:
    assert game.player is not None
    assert game.camera is not None
    game.player.place_at_tile(tile)
    game.camera.update(game.player.world_position)


def freeze_creatures(game: Game) -> None:
    for creature in game.creatures:
        creature.movement_enabled = False


def collect_component(game: Game, index: int) -> None:
    assert game.floor_objectives is not None
    component = game.floor_objectives.components[index]
    place_player_at(game, component.tile)
    game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)


def collect_all_components(game: Game) -> None:
    collect_component(game, 0)
    collect_component(game, 1)


def repair_generator(game: Game) -> None:
    assert game.floor_objectives is not None
    place_player_at(game, game.floor_objectives.generator.tile)
    for _ in range(4):
        game.update_gameplay(settings.GENERATOR_REPAIR_DURATION / 4.0, pygame.Vector2(), interact_held=True)


def complete_floor_one(game: Game) -> None:
    assert game.floor_objectives is not None
    if not game.floor_objectives.state.generator_repaired:
        collect_all_components(game)
        repair_generator(game)
    assert game.elevator_entity is not None
    place_player_at(game, game.elevator_entity.tile)
    game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)


def objective_signature(game: Game) -> tuple[object, ...]:
    assert game.floor_objectives is not None
    objectives = game.floor_objectives
    return (
        objectives.placement.component_a_room_id,
        objectives.placement.component_b_room_id,
        objectives.placement.generator_room_id,
        objectives.placement.component_a_tile,
        objectives.placement.component_b_tile,
        objectives.placement.generator_tile,
        tuple(component.unique_id for component in objectives.components),
        objectives.generator.unique_id,
    )


def tile_rect(tile: tuple[int, int]) -> pygame.Rect:
    return collision.tile_to_world_rect(tile[0], tile[1], settings.TILE_SIZE)


def powered_door(game: Game):
    for door in game.doors:
        if door.door_type is DoorType.POWERED:
            return door
    raise AssertionError("No powered door was generated.")


def approach_tile_for_door(game: Game, door) -> tuple[int, int]:
    assert game.placeholder_run is not None
    floor = game.placeholder_run.generated_floor
    assert floor is not None
    candidates = (
        [(door.tile[0] - 1, door.tile[1]), (door.tile[0] + 1, door.tile[1])]
        if door.orientation == "vertical_door_plane"
        else [(door.tile[0], door.tile[1] - 1), (door.tile[0], door.tile[1] + 1)]
    )
    for tile in candidates:
        if floor.is_walkable(*tile) and door.approach_rect.colliderect(tile_rect(tile)):
            return tile
    for tile in floor.walkable_tiles():
        if tile != door.tile and door.approach_rect.colliderect(tile_rect(tile)):
            return tile
    raise AssertionError("No approach tile found for door.")


def clear_floor_runtime_assertions(test: unittest.TestCase, game: Game) -> None:
    test.assertEqual(game.state, GameState.WORKSHOP)
    test.assertEqual(game.last_completed_floor, 1)
    test.assertIsNotNone(game.placeholder_run)
    assert game.placeholder_run is not None
    test.assertEqual(game.placeholder_run.completed_floor_count, 1)
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


class Floor1ObjectiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game()
        self.game.start_new_run()
        freeze_creatures(self.game)

    def tearDown(self) -> None:
        self.game.shutdown()

    def test_new_run_creates_unpowered_floor_one_objective_flow(self) -> None:
        objectives = self.game.floor_objectives
        self.assertIsNotNone(objectives)
        assert objectives is not None
        self.assertFalse(self.game.floor_power_available)
        self.assertFalse(objectives.state.floor_power_active)
        self.assertFalse(objectives.state.elevator_unlocked)
        self.assertEqual(self.game.elevator_entity.state, ElevatorState.LOCKED)
        self.assertEqual(objectives.placement.validation_errors, [])
        self.assertEqual(len(objectives.active_components), 2)
        self.assertEqual(objectives.generator.state, GeneratorState.INACTIVE)
        self.assertEqual(objectives.state.current_objective_text, "Find generator components: 0 / 2")

    def test_objective_placement_is_deterministic_and_reachable_before_power(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        floor = self.game.placeholder_run.generated_floor
        assert floor is not None
        first_signature = (
            objectives.placement.component_a_room_id,
            objectives.placement.component_b_room_id,
            objectives.placement.generator_room_id,
            objectives.placement.component_a_tile,
            objectives.placement.component_b_tile,
            objectives.placement.generator_tile,
            [entity.unique_id for entity in objectives.active_entities],
        )
        self.assertEqual(len({objectives.placement.component_a_tile, objectives.placement.component_b_tile, objectives.placement.generator_tile}), 3)
        self.assertNotIn(objectives.placement.generator_room_id, {floor.start_room_id})
        for tile in (
            objectives.placement.component_a_tile,
            objectives.placement.component_b_tile,
            objectives.placement.generator_tile,
        ):
            self.assertTrue(floor.is_walkable(*tile))
            self.assertTrue(
                navigation.astar_path(
                    floor,
                    floor.player_spawn,
                    tile,
                    self.game.dynamic_blockers,
                    BlockerPurpose.MOVEMENT,
                )
            )

        self.game.restart_placeholder_run()
        freeze_creatures(self.game)
        objectives = self.game.floor_objectives
        assert objectives is not None
        second_signature = (
            objectives.placement.component_a_room_id,
            objectives.placement.component_b_room_id,
            objectives.placement.generator_room_id,
            objectives.placement.component_a_tile,
            objectives.placement.component_b_tile,
            objectives.placement.generator_tile,
            [entity.unique_id for entity in objectives.active_entities],
        )
        self.assertEqual(first_signature, second_signature)

    def test_components_are_distinct_reachable_rooms(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        floor = self.game.placeholder_run.generated_floor
        assert floor is not None
        self.assertNotEqual(objectives.components[0].unique_id, objectives.components[1].unique_id)
        self.assertNotEqual(objectives.placement.component_a_room_id, objectives.placement.component_b_room_id)
        self.assertNotEqual(objectives.placement.component_a_room_id, floor.start_room_id)
        self.assertNotEqual(objectives.placement.component_b_room_id, floor.start_room_id)
        for component in objectives.components:
            self.assertTrue(
                navigation.astar_path(
                    floor,
                    floor.player_spawn,
                    component.tile,
                    self.game.dynamic_blockers,
                    BlockerPurpose.MOVEMENT,
                )
            )

    def test_objectives_do_not_overlap_blockers_doors_or_elevator(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        floor = self.game.placeholder_run.generated_floor
        assert floor is not None
        door_tiles = {door.tile for door in self.game.doors}
        objective_tiles = {
            objectives.placement.component_a_tile,
            objectives.placement.component_b_tile,
            objectives.placement.generator_tile,
        }
        self.assertEqual(len(objective_tiles), 3)
        self.assertTrue(objective_tiles.isdisjoint(door_tiles))
        self.assertNotIn(floor.elevator_tile, objective_tiles)
        self.assertTrue(objective_tiles.isdisjoint(floor.elevator_approach_tiles))
        self.assertTrue(objective_tiles.isdisjoint(floor.doorway_candidates))
        self.assertTrue(objective_tiles.isdisjoint(floor.candidate_creature_spawns))
        for tile in objective_tiles:
            self.assertTrue(floor.is_walkable(*tile))
            self.assertFalse(self.game.dynamic_blockers.blocks_tile(*tile, BlockerPurpose.MOVEMENT))

    def test_component_collection_is_idempotent_and_gates_generator_repair(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        place_player_at(self.game, objectives.generator.tile)
        self.game.update_gameplay(0.25, pygame.Vector2(), interact_held=True)
        self.assertEqual(objectives.state.generator_repair_progress, 0.0)
        self.assertEqual(objectives.state.current_prompt, "Components required: 0 / 2")

        first_component = objectives.components[0]
        place_player_at(self.game, first_component.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        self.assertTrue(first_component.collected)
        self.assertFalse(first_component.scan_active)
        self.assertEqual(objectives.state.components_collected, 1)
        self.assertEqual(self.game.placeholder_run.score, settings.GENERATOR_COMPONENT_SCORE)

        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        self.assertEqual(objectives.state.components_collected, 1)
        self.assertEqual(self.game.placeholder_run.score, settings.GENERATOR_COMPONENT_SCORE)

        collect_component(self.game, 1)
        self.assertTrue(objectives.state.generator_repairable)
        self.assertTrue(objectives.state.generator_ready)
        self.assertEqual(objectives.generator.state, GeneratorState.READY)

    def test_generator_cannot_repair_with_one_component(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_component(self.game, 0)
        place_player_at(self.game, objectives.generator.tile)
        self.game.update_gameplay(settings.GENERATOR_REPAIR_DURATION, pygame.Vector2(), interact_held=True)
        self.assertFalse(objectives.state.generator_repaired)
        self.assertEqual(objectives.state.generator_repair_progress, 0.0)
        self.assertEqual(objectives.state.current_prompt, "Components required: 1 / 2")

    def test_hold_f_only_progresses_in_range_with_both_components(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_all_components(self.game)
        place_player_at(self.game, objectives.components[0].tile)
        self.game.update_gameplay(0.5, pygame.Vector2(), interact_held=True)
        self.assertEqual(objectives.state.generator_repair_progress, 0.0)
        place_player_at(self.game, objectives.generator.tile)
        self.game.update_gameplay(0.5, pygame.Vector2(), interact_held=False)
        self.assertEqual(objectives.state.generator_repair_progress, 0.0)
        self.game.update_gameplay(0.5, pygame.Vector2(), interact_held=True)
        self.assertGreater(objectives.state.generator_repair_progress, 0.0)

    def test_leaving_generator_range_resets_repair_progress(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_all_components(self.game)
        place_player_at(self.game, objectives.generator.tile)
        self.game.update_gameplay(settings.GENERATOR_REPAIR_DURATION * 0.5, pygame.Vector2(), interact_held=True)
        self.assertGreater(objectives.state.generator_repair_progress, 0.0)
        place_player_at(self.game, self.game.placeholder_run.generated_floor.player_spawn)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        self.assertEqual(objectives.state.generator_repair_progress, 0.0)
        self.assertEqual(objectives.generator.state, GeneratorState.READY)

    def test_generator_repair_requires_held_interaction_and_resets_on_release(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_all_components(self.game)
        place_player_at(self.game, objectives.components[0].tile)
        self.game.update_gameplay(settings.GENERATOR_REPAIR_DURATION, pygame.Vector2(), interact_held=True)
        self.assertEqual(objectives.state.generator_repair_progress, 0.0)

        place_player_at(self.game, objectives.generator.tile)
        self.game.update_gameplay(settings.GENERATOR_REPAIR_DURATION * 0.5, pygame.Vector2(), interact_held=True)
        self.assertGreater(objectives.state.generator_repair_progress, 0.0)
        self.assertEqual(objectives.generator.state, GeneratorState.REPAIRING)

        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        self.assertEqual(objectives.state.generator_repair_progress, 0.0)
        self.assertEqual(objectives.generator.state, GeneratorState.READY)

    def test_pause_freezes_repair_progress_and_death_resets_it(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_all_components(self.game)
        place_player_at(self.game, objectives.generator.tile)
        self.game.update_gameplay(settings.GENERATOR_REPAIR_DURATION * 0.5, pygame.Vector2(), interact_held=True)
        frozen_progress = objectives.state.generator_repair_progress

        self.game.transition_to(GameState.PAUSED)
        self.game.update(1.0)
        self.assertEqual(objectives.state.generator_repair_progress, frozen_progress)

        self.game.transition_to(GameState.PLAYING)
        creature = self.game.creatures[0]
        creature.world_position = self.game.player.world_position.copy()
        creature._sync_rects_from_world()
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        self.assertEqual(self.game.state, GameState.DEATH)
        self.assertEqual(objectives.state.generator_repair_progress, 0.0)

    def test_generator_repair_restores_power_unlocks_elevator_and_emits_single_threat(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_all_components(self.game)
        place_player_at(self.game, objectives.generator.tile)
        for _ in range(4):
            self.game.update_gameplay(settings.GENERATOR_REPAIR_DURATION / 4.0, pygame.Vector2(), interact_held=True)

        self.assertTrue(objectives.state.generator_repaired)
        self.assertTrue(objectives.state.floor_power_active)
        self.assertTrue(objectives.state.elevator_unlocked)
        self.assertTrue(self.game.floor_power_available)
        self.assertEqual(objectives.generator.state, GeneratorState.POWERED)
        self.assertEqual(self.game.elevator_entity.state, ElevatorState.UNLOCKED)
        self.assertEqual(objectives.state.generator_activation_event_count, 1)
        generator_events = [
            event for event in self.game.threat_events.active_events
            if event.source_type is ThreatSourceType.GENERATOR
        ]
        self.assertEqual(len(generator_events), 1)
        self.assertEqual(generator_events[0].source_entity_id, objectives.generator.unique_id)
        self.assertEqual(generator_events[0].floor_number, 1)
        self.assertEqual(generator_events[0].world_position, objectives.generator.world_position)
        self.assertGreater(generator_events[0].strength, settings.THREAT_PLAYER_SCAN_STRENGTH)
        self.assertIs(
            self.game.threat_events.select_relevant_event(objectives.generator.world_position, floor_number=1),
            generator_events[0],
        )
        self.assertEqual(self.game.placeholder_run.score, settings.GENERATOR_COMPONENT_SCORE * 2 + settings.GENERATOR_REPAIR_SCORE)

        self.game.update_gameplay(0.25, pygame.Vector2(), interact_held=True)
        self.assertEqual(objectives.state.generator_activation_event_count, 1)
        self.assertEqual(
            len([event for event in self.game.threat_events.active_events if event.source_type is ThreatSourceType.GENERATOR]),
            1,
        )

    def test_powered_door_inactive_before_repair_and_works_after_repair(self) -> None:
        door = powered_door(self.game)
        place_player_at(self.game, approach_tile_for_door(self.game, door))
        self.game.update_gameplay(1.0 / settings.FPS, pygame.Vector2(), interact_held=False)
        self.assertEqual(door.state, DoorState.CLOSED)
        self.assertTrue(self.game.dynamic_blockers.blocks_tile(*door.tile, BlockerPurpose.MOVEMENT))

        collect_all_components(self.game)
        repair_generator(self.game)
        place_player_at(self.game, approach_tile_for_door(self.game, door))
        self.game.update_gameplay(1.0 / settings.FPS, pygame.Vector2(), interact_held=False)
        self.assertIn(door.state, (DoorState.OPENING, DoorState.OPEN))

    def test_later_floor_security_and_containment_doors_remain_locked(self) -> None:
        later_game = Game()
        try:
            later_game.placeholder_run = PlaceholderRun(seed=12345, floor=2)
            later_game.run_exists = True
            later_game.prepare_generated_floor()
            security_doors = [door for door in later_game.doors if door.door_type is DoorType.SECURITY]
            self.assertEqual(len(security_doors), 1)
            self.assertTrue(security_doors[0].is_locked)
            security_doors[0].set_powered(True)
            security_doors[0].update(0.5, None, floor_powered=True)
            self.assertTrue(security_doors[0].is_locked)

            later_game.placeholder_run = PlaceholderRun(seed=12345, floor=3)
            later_game.prepare_generated_floor()
            containment_doors = [door for door in later_game.doors if door.door_type is DoorType.CONTAINMENT]
            self.assertEqual(len(containment_doors), 1)
            self.assertTrue(containment_doors[0].is_locked)
            containment_doors[0].set_powered(True)
            containment_doors[0].update(0.5, None, floor_powered=True)
            self.assertTrue(containment_doors[0].is_locked)
        finally:
            later_game.shutdown()

    def test_locked_and_unlocked_elevator_prompts_and_floor_completion_cleanup(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        assert self.game.elevator_entity is not None

        material = self.game.material_pickups[0]
        material_name = material.material_type.value
        place_player_at(self.game, material.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        self.assertEqual(self.game.placeholder_run.material_counts[material_name], 1)

        place_player_at(self.game, self.game.elevator_entity.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)
        self.assertEqual(objectives.state.current_prompt, "Elevator offline")
        self.assertEqual(self.game.state, GameState.PLAYING)

        collect_all_components(self.game)
        place_player_at(self.game, objectives.generator.tile)
        for _ in range(4):
            self.game.update_gameplay(settings.GENERATOR_REPAIR_DURATION / 4.0, pygame.Vector2(), interact_held=True)
        place_player_at(self.game, self.game.elevator_entity.tile)
        expected_score = self.game.placeholder_run.score + settings.FLOOR_COMPLETION_SCORE
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=True)

        clear_floor_runtime_assertions(self, self.game)
        self.assertEqual(self.game.placeholder_run.material_counts[material_name], 1)
        self.assertEqual(self.game.placeholder_run.score, expected_score)

    def test_floor_completion_preserves_score_materials_and_completed_count_only(self) -> None:
        material = self.game.material_pickups[0]
        material_name = material.material_type.value
        place_player_at(self.game, material.tile)
        self.game.update_gameplay(0.0, pygame.Vector2(), interact_held=False)
        collect_all_components(self.game)
        repair_generator(self.game)
        expected_score = self.game.placeholder_run.score + settings.FLOOR_COMPLETION_SCORE
        complete_floor_one(self.game)
        clear_floor_runtime_assertions(self, self.game)
        self.assertEqual(self.game.placeholder_run.score, expected_score)
        self.assertEqual(self.game.placeholder_run.material_counts[material_name], 1)
        self.assertEqual(self.game.placeholder_run.completed_floor_count, 1)
        self.assertFalse(self.game.floor_power_available)
        self.assertIsNone(self.game.elevator_entity)
        self.assertIsNone(self.game.floor_objectives)

    def test_restart_resets_partial_objective_state_and_runtime_objects(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        collect_component(self.game, 0)
        place_player_at(self.game, objectives.generator.tile)
        self.game.update_gameplay(0.2, pygame.Vector2(), interact_held=True)
        old_component_ids = [component.unique_id for component in objectives.components]
        old_generator = objectives.generator

        self.game.restart_placeholder_run()
        freeze_creatures(self.game)
        restarted = self.game.floor_objectives
        assert restarted is not None
        self.assertIsNot(restarted.generator, old_generator)
        self.assertEqual([component.unique_id for component in restarted.components], old_component_ids)
        self.assertEqual(restarted.state.components_collected, 0)
        self.assertFalse(restarted.state.generator_repaired)
        self.assertFalse(self.game.floor_power_available)
        self.assertEqual(len(self.game.threat_events.active_events), 0)
        self.assertEqual(self.game.snapshot_system.snapshots, [])

    def test_retry_same_seed_restores_placements_and_resets_progress(self) -> None:
        signature = objective_signature(self.game)
        collect_component(self.game, 0)
        objectives = self.game.floor_objectives
        assert objectives is not None
        place_player_at(self.game, objectives.generator.tile)
        self.game.update_gameplay(0.3, pygame.Vector2(), interact_held=True)
        self.assertGreater(self.game.placeholder_run.score, 0)

        self.game.retry_same_seed()
        freeze_creatures(self.game)
        restarted = self.game.floor_objectives
        assert restarted is not None
        self.assertEqual(objective_signature(self.game), signature)
        self.assertEqual(restarted.state.components_collected, 0)
        self.assertEqual(restarted.state.generator_repair_progress, 0.0)
        self.assertFalse(restarted.state.generator_repaired)
        self.assertFalse(self.game.floor_power_available)
        self.assertEqual(self.game.placeholder_run.score, 0)
        self.assertEqual(self.game.placeholder_run.material_counts, {"scrap": 0, "circuit": 0, "power_cell": 0})
        self.assertEqual(self.game.placeholder_run.completed_floor_count, 0)
        self.assertEqual(self.game.elevator_entity.state, ElevatorState.LOCKED)

    def test_new_run_resets_progress_and_normally_changes_placements(self) -> None:
        signature = objective_signature(self.game)
        collect_component(self.game, 0)
        self.game.start_new_run()
        freeze_creatures(self.game)
        restarted = self.game.floor_objectives
        assert restarted is not None
        self.assertNotEqual(objective_signature(self.game), signature)
        self.assertEqual(restarted.state.components_collected, 0)
        self.assertFalse(restarted.state.generator_repaired)
        self.assertFalse(self.game.floor_power_available)
        self.assertEqual(self.game.placeholder_run.score, 0)
        self.assertEqual(self.game.placeholder_run.completed_floor_count, 0)

    def test_main_menu_clears_floor1_runtime_state(self) -> None:
        collect_component(self.game, 0)
        self.game.perform_action("main_menu")
        self.assertEqual(self.game.state, GameState.MAIN_MENU)
        self.assertIsNone(self.game.placeholder_run)
        self.assertIsNone(self.game.player)
        self.assertIsNone(self.game.camera)
        self.assertEqual(self.game.doors, [])
        self.assertIsNone(self.game.floor_content)
        self.assertIsNone(self.game.floor_objectives)
        self.assertEqual(self.game.material_pickups, [])
        self.assertIsNone(self.game.elevator_entity)
        self.assertEqual(self.game.creatures, [])
        self.assertEqual(len(self.game.threat_events.active_events), 0)
        self.assertEqual(self.game.snapshot_system.snapshots, [])

    def test_repeated_retries_do_not_grow_objective_collections(self) -> None:
        signature = objective_signature(self.game)
        for expected_restart_count in range(1, 4):
            collect_component(self.game, 0)
            self.game.retry_same_seed()
            freeze_creatures(self.game)
            objectives = self.game.floor_objectives
            assert objectives is not None
            self.assertEqual(self.game.placeholder_run.restart_count, expected_restart_count)
            self.assertEqual(objective_signature(self.game), signature)
            self.assertEqual(len(objectives.components), 2)
            self.assertEqual(len(objectives.active_components), 2)
            self.assertEqual(objectives.state.components_collected, 0)
            self.assertEqual(self.game.placeholder_run.score, 0)

    def test_repeated_completions_leave_no_floor_runtime_collections(self) -> None:
        for index in range(2):
            collect_all_components(self.game)
            repair_generator(self.game)
            complete_floor_one(self.game)
            clear_floor_runtime_assertions(self, self.game)
            if index == 0:
                self.game.start_new_run()
                freeze_creatures(self.game)

    def test_scan_at_component_creates_historical_snapshot_before_collection(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        component = objectives.components[0]
        place_player_at(self.game, component.tile)
        self.assertTrue(self.game.trigger_scan())
        self.game.update_gameplay(0.01, pygame.Vector2(), interact_held=False)

        snapshots = self.game.snapshot_system.snapshots_for_source(component.unique_id)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].category, component.scan_category)
        self.assertFalse(component.scan_active)
        self.assertTrue(component.collected)

    def test_generator_outline_changes_between_inactive_and_powered_states(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        inactive = pygame.image.tobytes(objectives.generator.capture_scan_outline(), "RGBA")
        collect_all_components(self.game)
        place_player_at(self.game, objectives.generator.tile)
        for _ in range(4):
            self.game.update_gameplay(settings.GENERATOR_REPAIR_DURATION / 4.0, pygame.Vector2(), interact_held=True)
        powered = pygame.image.tobytes(objectives.generator.capture_scan_outline(), "RGBA")
        self.assertNotEqual(inactive, powered)

    def test_inactive_and_powered_generator_snapshots_remain_historically_distinct(self) -> None:
        objectives = self.game.floor_objectives
        assert objectives is not None
        inactive_snapshot = EchoSnapshot.capture(objectives.generator, scan_id=1, lifetime=5.0)
        inactive_bytes = pygame.image.tobytes(inactive_snapshot.image, "RGBA")

        collect_all_components(self.game)
        repair_generator(self.game)
        powered_snapshot = EchoSnapshot.capture(objectives.generator, scan_id=2, lifetime=5.0)
        powered_bytes = pygame.image.tobytes(powered_snapshot.image, "RGBA")

        self.assertNotEqual(inactive_bytes, powered_bytes)
        self.assertEqual(pygame.image.tobytes(inactive_snapshot.image, "RGBA"), inactive_bytes)

    def test_locked_and_unlocked_elevator_snapshots_remain_historically_distinct(self) -> None:
        assert self.game.elevator_entity is not None
        locked_snapshot = EchoSnapshot.capture(self.game.elevator_entity, scan_id=1, lifetime=5.0)
        locked_bytes = pygame.image.tobytes(locked_snapshot.image, "RGBA")

        collect_all_components(self.game)
        repair_generator(self.game)
        assert self.game.elevator_entity is not None
        unlocked_snapshot = EchoSnapshot.capture(self.game.elevator_entity, scan_id=2, lifetime=5.0)
        unlocked_bytes = pygame.image.tobytes(unlocked_snapshot.image, "RGBA")

        self.assertNotEqual(locked_bytes, unlocked_bytes)
        self.assertEqual(pygame.image.tobytes(locked_snapshot.image, "RGBA"), locked_bytes)


if __name__ == "__main__":
    unittest.main()
