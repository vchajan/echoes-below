import unittest

import numpy as np
import pygame

from game.systems.raycasting import RayHit
from game.systems.scan import ScanConfig, ScanSystem, ScanTrace, can_connect_hits, trace_segments
from game.world.tiles import TileType


class FakeFloor:
    def __init__(self, width: int = 7, height: int = 7) -> None:
        self.width = width
        self.height = height
        self.tiles = np.full((height, width), int(TileType.FLOOR), dtype=np.int16)
        self.tiles[0, :] = int(TileType.WALL)
        self.tiles[-1, :] = int(TileType.WALL)
        self.tiles[:, 0] = int(TileType.WALL)
        self.tiles[:, -1] = int(TileType.WALL)

    def tile_at(self, tile_x: int, tile_y: int) -> TileType:
        if not (0 <= tile_x < self.width and 0 <= tile_y < self.height):
            raise IndexError((tile_x, tile_y))
        return TileType(int(self.tiles[tile_y, tile_x]))


def make_hit(
    ray_index: int,
    position: tuple[float, float],
    *,
    distance: float = 20.0,
    tile: tuple[int, int] = (3, 2),
    side: str = "vertical",
    category: str = "wall",
    scan_id: int = 1,
    blocker_id: str | None = None,
) -> RayHit:
    return RayHit(
        scan_id=scan_id,
        ray_index=ray_index,
        ray_count=16,
        angle=0.0,
        world_position=position,
        distance=distance,
        tile=tile,
        category=category,
        blocker_id=blocker_id,
        side=side,
    )


class ScanSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.floor = FakeFloor()
        self.config = ScanConfig(
            ray_count=16,
            max_radius=60.0,
            wave_speed=30.0,
            cooldown=1.0,
            trace_lifetime=2.0,
            dedupe_quantum=0.5,
        )
        self.scan = ScanSystem(self.config)

    def test_trigger_copies_fixed_origin(self) -> None:
        origin = pygame.Vector2(25, 35)
        self.assertTrue(self.scan.trigger(origin, self.floor, None, 10))
        origin.update(100, 100)
        self.assertEqual(self.scan.active_wave.origin, pygame.Vector2(25, 35))

    def test_radius_increases_with_dt_and_clamps(self) -> None:
        self.scan.trigger((25, 35), self.floor, None, 10)
        self.scan.update(0.5)
        self.assertAlmostEqual(self.scan.active_wave.current_radius, 15.0)
        self.scan.update(10.0)
        self.assertIsNone(self.scan.active_wave)

    def test_hits_reveal_only_after_wave_crossing(self) -> None:
        self.scan.trigger((25, 35), self.floor, None, 10)
        self.scan.update(0.1)
        self.assertEqual(self.scan.traces, [])
        self.scan.update(1.0)
        self.assertGreater(len(self.scan.traces), 0)

    def test_large_dt_reveals_every_crossed_hit(self) -> None:
        self.scan.trigger((25, 35), self.floor, None, 10)
        expected = len(self.scan.active_wave.hits)
        self.scan.update(2.0)
        self.assertEqual(len(self.scan.traces), expected)

    def test_trace_fades_and_expires(self) -> None:
        trace = ScanTrace(make_hit(0, (20, 20)), lifetime=2.0)
        self.assertEqual(trace.alpha, 255)
        trace.age = 1.0
        self.assertGreater(trace.alpha, 0)
        self.assertLess(trace.alpha, 255)
        trace.age = 2.0
        self.assertTrue(trace.expired)
        self.assertEqual(trace.alpha, 0)

    def test_cooldown_prevents_immediate_second_scan(self) -> None:
        self.assertTrue(self.scan.trigger((25, 35), self.floor, None, 10))
        self.assertFalse(self.scan.trigger((35, 35), self.floor, None, 10))
        self.scan.update(1.0)
        self.assertTrue(self.scan.ready)
        self.assertTrue(self.scan.trigger((35, 35), self.floor, None, 10))

    def test_old_traces_remain_when_new_scan_starts(self) -> None:
        self.scan.trigger((25, 35), self.floor, None, 10)
        self.scan.update(1.0)
        old_trace_ids = {id(trace) for trace in self.scan.traces}
        self.scan.update(0.1)
        self.assertTrue(self.scan.trigger((35, 35), self.floor, None, 10))
        self.assertTrue(old_trace_ids.issubset({id(trace) for trace in self.scan.traces}))

    def test_reset_clears_transient_state(self) -> None:
        self.scan.trigger((25, 35), self.floor, None, 10)
        self.scan.update(1.0)
        self.scan.reset()
        self.assertIsNone(self.scan.active_wave)
        self.assertEqual(self.scan.traces, [])
        self.assertTrue(self.scan.ready)
        self.assertEqual(self.scan.threat_events, [])

    def test_trigger_creates_bounded_threat_event(self) -> None:
        self.scan.trigger((25, 35), self.floor, None, 10, session_time=4.2)
        event = self.scan.threat_events[-1]
        self.assertEqual(event.source_type, "player_scan")
        self.assertEqual(event.origin, (25.0, 35.0))
        self.assertAlmostEqual(event.session_time, 4.2)

    def test_trace_count_does_not_grow_after_expiry(self) -> None:
        for _ in range(4):
            self.scan.trigger((25, 35), self.floor, None, 10)
            self.scan.update(2.0)
            self.scan.update(2.1)
        self.assertEqual(self.scan.traces, [])


class ScanConnectionTests(unittest.TestCase):
    def test_nearby_same_surface_hits_connect(self) -> None:
        first = make_hit(2, (30, 20), tile=(3, 2), side="vertical")
        second = make_hit(3, (30, 26), tile=(3, 3), side="vertical", distance=21)
        self.assertTrue(can_connect_hits(first, second, max_gap=10, max_distance_delta=5))

    def test_distant_depth_jump_and_corner_do_not_connect(self) -> None:
        first = make_hit(2, (30, 20), distance=20)
        distant = make_hit(3, (30, 50), distance=50)
        corner = make_hit(3, (31, 21), distance=21, side="horizontal")
        self.assertFalse(can_connect_hits(first, distant, max_gap=10, max_distance_delta=5))
        self.assertFalse(can_connect_hits(first, corner, max_gap=10, max_distance_delta=5))

    def test_different_category_or_scan_does_not_connect(self) -> None:
        first = make_hit(2, (30, 20))
        different_category = make_hit(3, (30, 22), category="obstacle")
        different_scan = make_hit(3, (30, 22), scan_id=2)
        self.assertFalse(can_connect_hits(first, different_category, max_gap=10, max_distance_delta=5))
        self.assertFalse(can_connect_hits(first, different_scan, max_gap=10, max_distance_delta=5))

    def test_door_hits_require_same_blocker(self) -> None:
        first = make_hit(2, (30, 20), category="powered_door", blocker_id="a")
        second = make_hit(3, (30, 22), category="powered_door", blocker_id="b")
        same = make_hit(3, (30, 22), category="powered_door", blocker_id="a")
        self.assertFalse(can_connect_hits(first, second, max_gap=10, max_distance_delta=5))
        self.assertTrue(can_connect_hits(first, same, max_gap=10, max_distance_delta=5))

    def test_trace_segments_only_contains_safe_pairs(self) -> None:
        config = ScanConfig(connection_max_gap=10, connection_max_distance_delta=5)
        traces = [
            ScanTrace(make_hit(0, (30, 20), tile=(3, 2)), 2),
            ScanTrace(make_hit(1, (30, 25), tile=(3, 3), distance=21), 2),
            ScanTrace(make_hit(2, (50, 50), tile=(5, 5), distance=60), 2),
        ]
        segments = trace_segments(traces, config)
        self.assertEqual(len(segments), 1)


if __name__ == "__main__":
    unittest.main()
