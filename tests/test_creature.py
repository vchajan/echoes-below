import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.app import Game
from game.states import GameState


class CreatureIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = Game()
        self.game.start_new_run()

    def tearDown(self) -> None:
        self.game.shutdown()

    def test_new_run_creates_creatures_from_floor_candidates(self) -> None:
        self.assertTrue(self.game.creatures)
        self.assertEqual(
            len(self.game.creatures),
            min(1, len(self.game.placeholder_run.generated_floor.candidate_creature_spawns)),
        )


    def test_creature_spawn_is_safe_and_deterministic_for_same_seed(self) -> None:
        first_spawn = self.game.creatures[0].spawn_tile
        floor = self.game.placeholder_run.generated_floor
        self.assertNotEqual(first_spawn, floor.player_spawn)
        self.assertNotEqual(first_spawn, floor.elevator_tile)
        self.assertNotIn(first_spawn, {pickup.tile for pickup in self.game.material_pickups})
        seed = self.game.placeholder_run.seed
        self.game.retry_same_seed()
        self.assertEqual(self.game.placeholder_run.seed, seed)
        self.assertEqual(self.game.creatures[0].spawn_tile, first_spawn)

    def test_real_creature_is_hidden_normally_and_visible_in_debug(self) -> None:
        creature = self.game.creatures[0]
        creature.movement_enabled = False
        floor = self.game.placeholder_run.generated_floor
        player_tile = self.game.player.current_tile
        placement = None
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            tile = (player_tile[0] + dx, player_tile[1] + dy)
            if floor.is_walkable(*tile):
                placement = tile
                break
        self.assertIsNotNone(placement)
        creature.place_at_tile(placement)
        marker = (251, 3, 249, 255)
        creature.image = pygame.Surface(creature.image.get_size(), pygame.SRCALPHA)
        creature.image.fill(marker)
        creature._sync_rects_from_world()

        self.game.debug_world_view = False
        self.game.render()
        normal = pygame.surfarray.array3d(self.game.screen)
        normal_count = int(((normal[:, :, 0] == 251) & (normal[:, :, 1] == 3) & (normal[:, :, 2] == 249)).sum())

        self.game.debug_world_view = True
        self.game.render()
        debug = pygame.surfarray.array3d(self.game.screen)
        debug_count = int(((debug[:, :, 0] == 251) & (debug[:, :, 1] == 3) & (debug[:, :, 2] == 249)).sum())

        self.assertEqual(normal_count, 0)
        self.assertGreater(debug_count, 0)

    def test_scan_detects_creature_snapshot_and_creature_remains_moving(self) -> None:
        creature = self.game.creatures[0]
        floor = self.game.placeholder_run.generated_floor
        self.assertIsNotNone(floor)

        scan_tile = None
        for y in range(max(0, creature.spawn_tile[1] - 5), min(floor.height, creature.spawn_tile[1] + 6)):
            for x in range(max(0, creature.spawn_tile[0] - 5), min(floor.width, creature.spawn_tile[0] + 6)):
                if not floor.is_walkable(x, y):
                    continue
                scan_origin = pygame.Vector2((x + 0.5) * settings.TILE_SIZE, (y + 0.5) * settings.TILE_SIZE)
                if self.game.player is None:
                    continue
                if self.game.dynamic_blockers is None:
                    continue
                if self.game.placeholder_run is None:
                    continue
                if self.game.placeholder_run.generated_floor is None:
                    continue
                if self.game.placeholder_run.generated_floor is None:
                    continue
                from game.systems.raycasting import has_line_of_sight

                if has_line_of_sight(
                    scan_origin,
                    creature.scan_position,
                    floor,
                    self.game.dynamic_blockers,
                    settings.TILE_SIZE,
                ):
                    scan_tile = (x, y)
                    break
            if scan_tile is not None:
                break

        self.assertIsNotNone(scan_tile, "Could not find a walkable scan position for the creature.")
        self.game.player.place_at_tile(scan_tile)
        self.game.camera.update(self.game.player.world_position)

        original_position = creature.world_position.copy()
        self.assertTrue(self.game.trigger_scan())
        for _ in range(120):
            self.game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
            if self.game.snapshot_system.snapshots_for_source(creature.unique_id):
                break
        snapshots = self.game.snapshot_system.snapshots_for_source(creature.unique_id)
        self.assertEqual(len(snapshots), 1)
        self.assertNotEqual(creature.world_position, original_position)

    def test_contact_with_creature_transitions_to_death(self) -> None:
        creature = self.game.creatures[0]
        creature_tile = creature.spawn_tile
        self.game.player.place_at_tile(creature_tile)
        self.game.camera.update(self.game.player.world_position)
        self.game.update_gameplay(0.0, pygame.Vector2())
        self.assertEqual(self.game.state, GameState.DEATH)

    def test_retry_same_seed_recreates_creature_and_resets_snapshots(self) -> None:
        creature = self.game.creatures[0]
        self.assertTrue(self.game.trigger_scan())
        for _ in range(60):
            self.game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
            if self.game.snapshot_system.snapshots_for_source(creature.unique_id):
                break
        self.assertTrue(self.game.snapshot_system.snapshots)

        self.game.retry_same_seed()
        self.assertTrue(self.game.creatures)
        self.assertNotIn(creature, self.game.creatures)
        self.assertEqual(self.game.snapshot_system.snapshots, [])
        self.assertEqual(self.game.placeholder_run.restart_count, 1)


if __name__ == "__main__":
    unittest.main()
