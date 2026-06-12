import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame

from game import settings
from game.app import Game
from game.states import GameState
from game.systems.snapshots import EchoSnapshot


class DeathRestartTests(unittest.TestCase):
    def setUp(self):
        self.game = Game()
        self.game.start_new_run()

    def tearDown(self):
        self.game.shutdown()

    def freeze_creature(self):
        creature = self.game.creatures[0]
        creature.movement_enabled = False
        return creature

    def force_contact(self):
        creature = self.freeze_creature()
        self.game.player.world_position = creature.world_position.copy()
        self.game.player._sync_rects_from_world()
        self.game.camera.update(self.game.player.world_position)
        self.game.update_gameplay(0.0, pygame.Vector2())
        return creature

    def test_contact_enters_death_and_preserves_summary(self):
        run = self.game.placeholder_run
        run.floor = 1
        run.score = 35
        run.elapsed_time = 12.5
        creature = self.force_contact()
        self.assertEqual(self.game.state, GameState.DEATH)
        self.assertEqual(self.game.death_creature_id, creature.unique_id)
        self.assertEqual(run.score, 35)
        self.assertEqual(run.elapsed_time, 12.5)
        self.assertEqual(run.seed, self.game.placeholder_run.seed)

    def test_player_moving_into_creature_dies_same_update(self):
        creature = self.freeze_creature()
        floor = self.game.placeholder_run.generated_floor
        target = creature.current_tile
        adjacent = None
        direction = None
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            candidate = (target[0] + dx, target[1] + dy)
            if floor.is_walkable(*candidate):
                adjacent = candidate
                direction = pygame.Vector2(-dx, -dy)
                break
        self.assertIsNotNone(adjacent)
        self.game.player.place_at_tile(adjacent)
        self.game.camera.update(self.game.player.world_position)
        self.game.update_gameplay(0.35, direction)
        self.assertEqual(self.game.state, GameState.DEATH)

    def test_pause_freezes_creature_and_snapshot_age(self):
        creature = self.freeze_creature()
        snapshot = EchoSnapshot.capture(creature, 77, 10.0, facing=creature.facing)
        self.game.snapshot_system.snapshots.append(snapshot)
        position = creature.world_position.copy()
        self.game.transition_to(GameState.PAUSED)
        self.game.update(1.0)
        self.assertEqual(creature.world_position, position)
        self.assertEqual(snapshot.age, 0.0)

    def test_retry_same_seed_reproduces_floor_and_creature_spawn(self):
        old_seed = self.game.placeholder_run.seed
        old_tiles = self.game.placeholder_run.generated_floor.tiles.copy()
        old_spawn = self.game.creatures[0].spawn_tile
        self.force_contact()
        self.game.retry_same_seed()
        self.assertEqual(self.game.state, GameState.PLAYING)
        self.assertEqual(self.game.placeholder_run.seed, old_seed)
        self.assertTrue(np.array_equal(self.game.placeholder_run.generated_floor.tiles, old_tiles))
        self.assertEqual(self.game.creatures[0].spawn_tile, old_spawn)

    def test_new_run_changes_seed_and_clears_transient_state(self):
        old_seed = self.game.placeholder_run.seed
        creature = self.freeze_creature()
        self.game.snapshot_system.snapshots.append(EchoSnapshot.capture(creature, 1, 5.0))
        self.game.scan_system.traces.append(object())
        old_creatures = list(self.game.creatures)
        self.game.start_new_run()
        self.assertNotEqual(self.game.placeholder_run.seed, old_seed)
        self.assertEqual(self.game.snapshot_system.snapshots, [])
        self.assertEqual(self.game.scan_system.traces, [])
        self.assertFalse(any(creature in self.game.creatures for creature in old_creatures))

    def test_main_menu_cleanup_removes_runtime_entities(self):
        self.game.end_placeholder_run()
        self.assertIsNone(self.game.placeholder_run)
        self.assertEqual(self.game.creatures, [])
        self.assertEqual(self.game.snapshot_system.snapshots, [])
        self.assertEqual(self.game.scan_system.traces, [])
        self.assertEqual(self.game.doors, [])

    def test_repeated_death_retry_does_not_grow_collections(self):
        seed = self.game.placeholder_run.seed
        for _ in range(4):
            self.force_contact()
            self.assertEqual(self.game.state, GameState.DEATH)
            self.game.retry_same_seed()
            self.assertEqual(self.game.placeholder_run.seed, seed)
            self.assertEqual(len(self.game.creatures), 1)
            self.assertEqual(self.game.snapshot_system.snapshots, [])
            self.assertEqual(self.game.scan_system.traces, [])


if __name__ == "__main__":
    unittest.main()
