import os
import random
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.assets import AssetManager
from game.entities.creature import Creature
from game.systems.creature_ai import CreatureAI, CreatureState
from game.systems.threat_events import ThreatEventSystem, ThreatSourceType
from game.world.blockers import DynamicBlockerRegistry
from game.world.tiles import TileType, is_walkable


TILE = 48


class GridFloor:
    def __init__(self, width: int = 16, height: int = 10) -> None:
        self.width = width
        self.height = height
        self._tiles = [[TileType.FLOOR for _ in range(width)] for _ in range(height)]
        self.rooms = []
        for x in range(width):
            self._tiles[0][x] = TileType.WALL
            self._tiles[height - 1][x] = TileType.WALL
        for y in range(height):
            self._tiles[y][0] = TileType.WALL
            self._tiles[y][width - 1] = TileType.WALL

    def tile_at(self, x: int, y: int) -> TileType:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError((x, y))
        return self._tiles[y][x]

    def is_walkable(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and is_walkable(self._tiles[y][x])

    def walkable_tiles(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if self.is_walkable(x, y)
        ]

    def set_tile(self, tile: tuple[int, int], tile_type: TileType) -> None:
        self._tiles[tile[1]][tile[0]] = tile_type


class FakePlayer:
    def __init__(self, tile: tuple[int, int]) -> None:
        self.place_at_tile(tile)

    @property
    def current_tile(self) -> tuple[int, int]:
        return (int(self.world_position.x // TILE), int(self.world_position.y // TILE))

    def place_at_tile(self, tile: tuple[int, int]) -> None:
        self.world_position = pygame.Vector2((tile[0] + 0.5) * TILE, (tile[1] + 0.5) * TILE)
        self.collision_rect = pygame.Rect(0, 0, 24, 24)
        self.collision_rect.center = (round(self.world_position.x), round(self.world_position.y))


class FakeDoor:
    def __init__(self, tile: tuple[int, int], *, blocked: bool) -> None:
        self.door_id = f"door-{tile[0]}-{tile[1]}"
        self.tile = tile
        self.blocked = blocked
        self.collision_rect = pygame.Rect(tile[0] * TILE, tile[1] * TILE, TILE, TILE)

    def blocks_purpose(self, _purpose) -> bool:
        return self.blocked


class CreatureAITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.assets = AssetManager(audio_available=False)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def make_creature(self, tile: tuple[int, int] = (3, 4), seed: int = 7) -> Creature:
        creature = Creature("ai-creature", tile, self.assets, TILE, random.Random(seed))
        creature.ai = CreatureAI(creature, random.Random(seed + 100), floor_number=1)
        return creature

    def test_creature_begins_in_patrol(self) -> None:
        creature = self.make_creature()
        self.assertEqual(creature.ai.state, CreatureState.PATROL)
        self.assertEqual(creature.ai.previous_state, CreatureState.PATROL)

    def test_patrol_target_is_walkable_and_path_is_created(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        creature.update(0.1, floor)
        self.assertIsNotNone(creature.ai.current_patrol_target)
        self.assertTrue(floor.is_walkable(*creature.ai.current_patrol_target))
        self.assertGreaterEqual(creature.ai.pathfinding_call_count, 1)

    def test_creature_follows_patrol_path(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        start = creature.world_position.copy()
        for _ in range(20):
            creature.update(1.0 / settings.FPS, floor)
        self.assertGreater(creature.world_position.distance_to(start), 1.0)

    def test_patrol_is_deterministic_for_same_seed(self) -> None:
        floor = GridFloor()
        first = self.make_creature(seed=33)
        second = self.make_creature(seed=33)
        first.update(0.1, floor)
        second.update(0.1, floor)
        self.assertEqual(first.ai.current_patrol_target, second.ai.current_patrol_target)
        self.assertEqual(first.ai.current_path, second.ai.current_path)

    def test_patrol_does_not_pathfind_every_frame(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        creature.update(0.1, floor)
        calls = creature.ai.pathfinding_call_count
        for _ in range(15):
            creature.update(1.0 / settings.FPS, floor)
        self.assertEqual(creature.ai.pathfinding_call_count, calls)

    def test_scan_event_triggers_investigate(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        threats = ThreatEventSystem()
        event = threats.add_player_scan((6.5 * TILE, 4.5 * TILE), floor_number=1)
        creature.update(0.1, floor, threat_events=threats)
        self.assertEqual(creature.ai.state, CreatureState.INVESTIGATE)
        self.assertEqual(creature.ai.selected_threat_event_id, event.event_id)
        self.assertEqual(creature.ai.investigation_target_tile, (6, 4))

    def test_weak_distant_event_is_ignored(self) -> None:
        floor = GridFloor(width=40, height=10)
        creature = self.make_creature()
        threats = ThreatEventSystem()
        threats.add_event((35.5 * TILE, 4.5 * TILE), source_type=ThreatSourceType.GENERATOR, strength=0.1)
        creature.update(0.1, floor, threat_events=threats)
        self.assertEqual(creature.ai.state, CreatureState.PATROL)

    def test_reaching_investigation_target_enters_search(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        threats = ThreatEventSystem()
        threats.add_player_scan((6.5 * TILE, 4.5 * TILE), floor_number=1)
        creature.update(0.1, floor, threat_events=threats)
        creature.place_at_tile(creature.ai.investigation_target_tile)
        creature.update(0.1, floor, threat_events=threats)
        self.assertEqual(creature.ai.state, CreatureState.SEARCH)
        self.assertIsNotNone(creature.ai.search_centre_tile)

    def test_new_stronger_event_replaces_investigation(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        threats = ThreatEventSystem()
        first = threats.add_player_scan((6.5 * TILE, 4.5 * TILE), floor_number=1)
        creature.update(0.1, floor, threat_events=threats)
        stronger = threats.add_event((4.5 * TILE, 6.5 * TILE), ThreatSourceType.RELAY, strength=3.0, floor_number=1)
        creature.ai._threat_cooldown = 0.0
        creature.update(0.2, floor, threat_events=threats)
        self.assertNotEqual(creature.ai.selected_threat_event_id, first.event_id)
        self.assertEqual(creature.ai.selected_threat_event_id, stronger.event_id)

    def test_unreachable_event_is_handled_safely(self) -> None:
        floor = GridFloor()
        for tile in ((6, 3), (5, 4), (7, 4), (6, 5)):
            floor.set_tile(tile, TileType.WALL)
        creature = self.make_creature()
        threats = ThreatEventSystem()
        threats.add_player_scan((6.5 * TILE, 4.5 * TILE), floor_number=1)
        creature.update(0.1, floor, threat_events=threats)
        self.assertIn(creature.ai.state, (CreatureState.PATROL, CreatureState.INVESTIGATE))

    def test_search_chooses_valid_nearby_points_and_expires(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        creature.ai._enter_search(floor, None, pygame.Vector2(6.5 * TILE, 4.5 * TILE), reason="test")
        self.assertEqual(creature.ai.state, CreatureState.SEARCH)
        self.assertTrue(creature.ai.search_points)
        for tile in creature.ai.search_points:
            self.assertTrue(floor.is_walkable(*tile))
        creature.update(settings.CREATURE_SEARCH_DURATION + 0.1, floor)
        self.assertEqual(creature.ai.state, CreatureState.PATROL)

    def test_threat_during_search_triggers_investigate(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        creature.ai._enter_search(floor, None, creature.world_position, reason="test")
        threats = ThreatEventSystem()
        threats.add_player_scan((8.5 * TILE, 4.5 * TILE), floor_number=1)
        creature.update(0.2, floor, threat_events=threats)
        self.assertEqual(creature.ai.state, CreatureState.INVESTIGATE)

    def test_visible_player_during_search_triggers_chase(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        player = FakePlayer((6, 4))
        creature.ai._enter_search(floor, None, creature.world_position, reason="test")
        creature.update(0.2, floor, player=player)
        self.assertEqual(creature.ai.state, CreatureState.CHASE)

    def test_pause_freezes_search_timer(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        creature.ai._enter_search(floor, None, creature.world_position, reason="test")
        creature.update(1.0, floor, paused=True)
        self.assertEqual(creature.ai.state_timer, 0.0)

    def test_player_visible_in_open_corridor_triggers_chase(self) -> None:
        floor = GridFloor()
        creature = self.make_creature((3, 4))
        player = FakePlayer((6, 4))
        creature.update(0.2, floor, player=player)
        self.assertEqual(creature.ai.state, CreatureState.CHASE)
        self.assertEqual(creature.ai.last_known_player_tile, (6, 4))

    def test_wall_blocks_detection(self) -> None:
        floor = GridFloor()
        floor.set_tile((4, 4), TileType.WALL)
        creature = self.make_creature((3, 4))
        player = FakePlayer((6, 4))
        creature.update(0.2, floor, player=player)
        self.assertNotEqual(creature.ai.state, CreatureState.CHASE)

    def test_corner_blocks_detection(self) -> None:
        floor = GridFloor()
        floor.set_tile((4, 3), TileType.WALL)
        floor.set_tile((3, 4), TileType.WALL)
        creature = self.make_creature((3, 3))
        player = FakePlayer((5, 5))
        creature.update(0.2, floor, player=player)
        self.assertNotEqual(creature.ai.state, CreatureState.CHASE)

    def test_closed_door_blocks_and_open_door_allows_detection(self) -> None:
        floor = GridFloor()
        creature = self.make_creature((3, 4))
        player = FakePlayer((6, 4))
        closed = DynamicBlockerRegistry([FakeDoor((4, 4), blocked=True)], TILE)
        creature.update(0.2, floor, closed, player=player)
        self.assertNotEqual(creature.ai.state, CreatureState.CHASE)

        open_creature = self.make_creature((3, 4))
        opened = DynamicBlockerRegistry([FakeDoor((4, 4), blocked=False)], TILE)
        open_creature.update(0.2, floor, opened, player=player)
        self.assertEqual(open_creature.ai.state, CreatureState.CHASE)

    def test_player_outside_detection_range_does_not_chase(self) -> None:
        floor = GridFloor(width=30, height=10)
        creature = self.make_creature((3, 4))
        player = FakePlayer((20, 4))
        creature.update(0.2, floor, player=player)
        self.assertNotEqual(creature.ai.state, CreatureState.CHASE)

    def test_chase_updates_last_known_only_with_los_and_eventually_searches(self) -> None:
        floor = GridFloor()
        creature = self.make_creature((3, 4))
        player = FakePlayer((6, 4))
        creature.update(0.2, floor, player=player)
        self.assertEqual(creature.ai.state, CreatureState.CHASE)
        known = creature.ai.last_known_player_position.copy()
        player.place_at_tile((14, 8))
        for _ in range(130):
            creature.update(1.0 / settings.FPS, floor, player=player)
        self.assertEqual(creature.ai.last_known_player_position, known)
        self.assertEqual(creature.ai.state, CreatureState.SEARCH)

    def test_chase_pathfinding_is_throttled(self) -> None:
        floor = GridFloor()
        creature = self.make_creature((3, 4))
        player = FakePlayer((6, 4))
        creature.update(0.2, floor, player=player)
        calls = creature.ai.pathfinding_call_count
        for _ in range(5):
            creature.update(1.0 / settings.FPS, floor, player=player)
        self.assertEqual(creature.ai.pathfinding_call_count, calls)

    def test_stun_enters_stunned_and_stops_movement(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        creature.update(0.2, floor)
        creature.stun(1.0)
        position = creature.world_position.copy()
        creature.update(0.5, floor)
        self.assertEqual(creature.ai.state, CreatureState.STUNNED)
        self.assertEqual(creature.world_position, position)

    def test_stun_timer_freezes_when_paused_and_repeated_stun_extends(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        creature.stun(0.5)
        creature.update(0.25, floor, paused=True)
        self.assertAlmostEqual(creature.ai.stun_timer, 0.5)
        creature.stun(1.2)
        self.assertAlmostEqual(creature.ai.stun_timer, 1.2)

    def test_stun_expiry_restores_previous_patrol(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        creature.update(0.1, floor)
        creature.stun(0.1)
        creature.update(0.2, floor)
        self.assertEqual(creature.ai.state, CreatureState.PATROL)

    def test_stun_during_investigate_resumes_search_not_expired_threat(self) -> None:
        floor = GridFloor()
        creature = self.make_creature()
        threats = ThreatEventSystem()
        threats.add_player_scan((6.5 * TILE, 4.5 * TILE), floor_number=1)
        creature.update(0.1, floor, threat_events=threats)
        self.assertEqual(creature.ai.state, CreatureState.INVESTIGATE)
        creature.stun(0.1)
        threats.update(10.0)
        creature.update(0.2, floor, threat_events=threats)
        self.assertEqual(creature.ai.state, CreatureState.SEARCH)

    def test_stun_during_chase_keeps_creature_alive_and_contact_dangerous_state(self) -> None:
        floor = GridFloor()
        creature = self.make_creature((3, 4))
        player = FakePlayer((6, 4))
        creature.update(0.2, floor, player=player)
        creature.stun(0.3)
        self.assertTrue(creature.scan_active)
        self.assertEqual(creature.ai.state, CreatureState.STUNNED)

    def test_door_closing_invalidates_current_path(self) -> None:
        floor = GridFloor()
        creature = self.make_creature((3, 4))
        door = FakeDoor((5, 4), blocked=False)
        blockers = DynamicBlockerRegistry([door], TILE)
        creature.ai._request_path((7, 4), floor, blockers, "test", force=True)
        self.assertIn((5, 4), creature.ai.current_path)
        door.blocked = True
        creature.update(0.1, floor, blockers)
        self.assertTrue(creature.ai._path_invalid or (5, 4) not in creature.ai.current_path)


if __name__ == "__main__":
    unittest.main()
