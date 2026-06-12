import unittest

import pygame

from game import settings
from game.systems.threat_events import ThreatEventSystem, ThreatSourceType


class ThreatEventTests(unittest.TestCase):
    def test_event_is_created_with_expected_data(self) -> None:
        system = ThreatEventSystem()
        event = system.add_player_scan((10, 20), creation_time=4.0, floor_number=2, scan_id=9)
        self.assertEqual(event.event_id, 1)
        self.assertEqual(event.source_type, ThreatSourceType.PLAYER_SCAN)
        self.assertEqual(event.world_position, pygame.Vector2(10, 20))
        self.assertEqual(event.floor_number, 2)
        self.assertEqual(event.scan_id, 9)
        self.assertEqual(len(system.active_events), 1)

    def test_event_age_increases_and_expires(self) -> None:
        system = ThreatEventSystem()
        system.add_event((0, 0), ThreatSourceType.GENERATOR, lifetime=1.0)
        system.update(0.4)
        self.assertAlmostEqual(system.active_events[0].age, 0.4)
        system.update(0.7)
        self.assertEqual(system.active_events, ())

    def test_paused_update_does_not_age(self) -> None:
        system = ThreatEventSystem()
        event = system.add_player_scan((0, 0))
        system.update(3.0, paused=True)
        self.assertEqual(event.age, 0.0)

    def test_reset_clears_events_and_resets_ids(self) -> None:
        system = ThreatEventSystem()
        system.add_player_scan((0, 0))
        system.reset()
        event = system.add_player_scan((1, 1))
        self.assertEqual(len(system.active_events), 1)
        self.assertEqual(event.event_id, 1)

    def test_one_scan_event_is_not_per_ray(self) -> None:
        system = ThreatEventSystem()
        event = system.add_player_scan((5, 5), scan_id=11)
        self.assertEqual(event.scan_id, 11)
        self.assertEqual(len(system.active_events), 1)

    def test_relevance_decreases_with_age(self) -> None:
        system = ThreatEventSystem()
        event = system.add_player_scan((0, 0))
        fresh = event.relevance_for((settings.TILE_SIZE, 0))
        system.update(2.0)
        aged = event.relevance_for((settings.TILE_SIZE, 0))
        self.assertLess(aged, fresh)

    def test_relevance_decreases_with_distance(self) -> None:
        system = ThreatEventSystem()
        event = system.add_player_scan((0, 0))
        near = event.relevance_for((settings.TILE_SIZE, 0))
        far = event.relevance_for((settings.TILE_SIZE * 6, 0))
        self.assertLess(far, near)

    def test_stronger_nearby_event_can_replace_current(self) -> None:
        system = ThreatEventSystem()
        weak = system.add_event((settings.TILE_SIZE * 5, 0), ThreatSourceType.GENERATOR, strength=0.5)
        strong = system.add_event((settings.TILE_SIZE, 0), ThreatSourceType.RELAY, strength=2.0)
        selected = system.select_relevant_event((0, 0), current_event_id=weak.event_id)
        self.assertEqual(selected, strong)

    def test_tiny_relevance_difference_keeps_current_event(self) -> None:
        system = ThreatEventSystem()
        current = system.add_event((settings.TILE_SIZE, 0), ThreatSourceType.GENERATOR, strength=1.0)
        system.add_event((settings.TILE_SIZE, 1), ThreatSourceType.RELAY, strength=1.01)
        selected = system.select_relevant_event((0, 0), current_event_id=current.event_id)
        self.assertEqual(selected, current)

    def test_expired_selected_event_is_handled_safely(self) -> None:
        system = ThreatEventSystem()
        expired = system.add_event((settings.TILE_SIZE, 0), ThreatSourceType.GENERATOR, lifetime=0.1)
        replacement = system.add_player_scan((settings.TILE_SIZE * 2, 0))
        system.update(0.2)
        selected = system.select_relevant_event((0, 0), current_event_id=expired.event_id)
        self.assertEqual(selected, replacement)

    def test_floor_filter_ignores_other_floor_events(self) -> None:
        system = ThreatEventSystem()
        system.add_player_scan((0, 0), floor_number=2)
        selected = system.select_relevant_event((0, 0), floor_number=1)
        self.assertIsNone(selected)

    def test_event_collection_is_bounded(self) -> None:
        system = ThreatEventSystem(max_events=3)
        for index in range(8):
            system.add_player_scan((index, 0))
        self.assertEqual(len(system.active_events), 3)
        self.assertEqual([event.event_id for event in system.active_events], [6, 7, 8])


if __name__ == "__main__":
    unittest.main()
