import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game import settings
from game.assets import AssetManager
from game.entities.door import DoorState, DoorType, DynamicDoor
from game.world.floor import DoorwayCandidate


class DoorStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.assets = AssetManager(audio_available=False)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def make_door(
        self,
        door_type: DoorType = DoorType.POWERED,
        orientation: str = "vertical_door_plane",
        powered: bool = True,
    ) -> DynamicDoor:
        doorway = DoorwayCandidate(tile=(4, 3), room_id=0, connected_room_id=1, orientation=orientation)
        return DynamicDoor("door-test", door_type, doorway, self.assets, settings.TILE_SIZE, powered=powered)

    def test_locked_door_reports_locked(self) -> None:
        door = self.make_door(DoorType.SECURITY)
        self.assertTrue(door.is_locked)
        self.assertEqual(door.state, DoorState.LOCKED)

    def test_locked_door_blocks_movement_and_scan(self) -> None:
        door = self.make_door(DoorType.SECURITY)
        self.assertTrue(door.blocks_player)
        self.assertTrue(door.blocks_scan)

    def test_closed_door_blocks_movement_and_scan(self) -> None:
        door = self.make_door()
        self.assertEqual(door.state, DoorState.CLOSED)
        self.assertTrue(door.blocks_player)
        self.assertTrue(door.blocks_scan)

    def test_open_door_allows_movement_and_scan(self) -> None:
        door = self.make_door()
        door.force_open()
        self.assertFalse(door.blocks_player)
        self.assertFalse(door.blocks_scan)
        self.assertTrue(door.is_fully_open)

    def test_opening_transition_reaches_open(self) -> None:
        door = self.make_door()
        self.assertTrue(door.begin_opening())
        door.update(1.0, floor_powered=True)
        self.assertEqual(door.state, DoorState.OPEN)

    def test_closing_transition_reaches_closed(self) -> None:
        door = self.make_door()
        door.force_open()
        self.assertTrue(door.begin_closing())
        door.update(1.0, floor_powered=True)
        self.assertEqual(door.state, DoorState.CLOSED)

    def test_unlock_transitions_locked_to_closed(self) -> None:
        door = self.make_door(DoorType.SECURITY)
        self.assertTrue(door.unlock_security())
        self.assertEqual(door.state, DoorState.CLOSED)
        self.assertFalse(door.is_locked)

    def test_repeated_unlock_is_safe(self) -> None:
        door = self.make_door(DoorType.CONTAINMENT)
        self.assertTrue(door.unlock_containment())
        self.assertTrue(door.unlock_containment())
        self.assertEqual(door.state, DoorState.CLOSED)

    def test_wrong_unlock_type_fails_safely(self) -> None:
        door = self.make_door(DoorType.POWERED)
        self.assertFalse(door.unlock_security())
        self.assertFalse(door.unlock_containment())
        self.assertEqual(door.state, DoorState.CLOSED)

    def test_powered_door_opens_near_player(self) -> None:
        door = self.make_door()
        player_rect = pygame.Rect(door.approach_rect.centerx, door.approach_rect.centery, 10, 10)
        door.update(0.05, player_rect, floor_powered=True)
        self.assertEqual(door.state, DoorState.OPENING)

    def test_unpowered_door_remains_closed(self) -> None:
        door = self.make_door()
        player_rect = pygame.Rect(door.approach_rect.centerx, door.approach_rect.centery, 10, 10)
        door.update(0.05, player_rect, floor_powered=False)
        self.assertEqual(door.state, DoorState.CLOSED)

    def test_door_remains_open_while_player_occupies_approach(self) -> None:
        door = self.make_door()
        door.force_open()
        door.close_timer = 0.01
        player_rect = pygame.Rect(door.approach_rect.centerx, door.approach_rect.centery, 10, 10)
        door.update(1.0, player_rect, floor_powered=True)
        self.assertEqual(door.state, DoorState.OPEN)

    def test_door_does_not_close_on_player(self) -> None:
        door = self.make_door()
        door.force_open()
        door.close_timer = 0.01
        door.update(1.0, door.collision_rect.copy(), floor_powered=True)
        self.assertEqual(door.state, DoorState.OPEN)

    def test_door_closes_after_delay_when_clear(self) -> None:
        door = self.make_door()
        door.force_open()
        door.close_timer = 0.01
        door.update(0.02, floor_powered=True)
        self.assertEqual(door.state, DoorState.CLOSING)
        door.update(1.0, floor_powered=True)
        self.assertEqual(door.state, DoorState.CLOSED)

    def test_reentering_approach_reverses_closing(self) -> None:
        door = self.make_door()
        door.force_open()
        door.begin_closing()
        player_rect = pygame.Rect(door.approach_rect.centerx, door.approach_rect.centery, 10, 10)
        door.update(0.05, player_rect, floor_powered=True)
        self.assertEqual(door.state, DoorState.OPENING)

    def test_power_loss_closes_when_clear_and_prevents_reopen(self) -> None:
        door = self.make_door()
        door.force_open()
        door.close_timer = 0.01
        door.update(0.02, floor_powered=False)
        door.update(1.0, floor_powered=False)
        self.assertEqual(door.state, DoorState.CLOSED)
        door.update(0.05, door.approach_rect.copy(), floor_powered=False)
        self.assertEqual(door.state, DoorState.CLOSED)

    def test_open_door_can_become_wedged_open(self) -> None:
        door = self.make_door()
        door.force_open()
        self.assertTrue(door.wedge())
        self.assertEqual(door.state, DoorState.WEDGED_OPEN)

    def test_closed_door_can_become_wedged_closed(self) -> None:
        door = self.make_door()
        self.assertTrue(door.wedge())
        self.assertEqual(door.state, DoorState.WEDGED_CLOSED)

    def test_locked_door_cannot_be_wedged(self) -> None:
        door = self.make_door(DoorType.SECURITY)
        self.assertFalse(door.wedge())
        self.assertEqual(door.state, DoorState.LOCKED)

    def test_mid_animation_door_cannot_be_wedged(self) -> None:
        door = self.make_door()
        door.begin_opening()
        self.assertFalse(door.wedge())
        self.assertEqual(door.state, DoorState.OPENING)

    def test_removing_wedge_restores_state(self) -> None:
        door = self.make_door()
        door.force_open()
        door.wedge()
        self.assertTrue(door.remove_wedge())
        self.assertEqual(door.state, DoorState.OPEN)
        door.force_closed()
        door.wedge()
        self.assertTrue(door.remove_wedge())
        self.assertEqual(door.state, DoorState.CLOSED)

    def test_wedged_closed_blocks_scan_and_movement(self) -> None:
        door = self.make_door()
        door.wedge()
        self.assertTrue(door.blocks_player)
        self.assertTrue(door.blocks_scan)

    def test_wedged_open_blocks_neither(self) -> None:
        door = self.make_door()
        door.force_open()
        door.wedge()
        self.assertFalse(door.blocks_player)
        self.assertFalse(door.blocks_scan)

    def test_horizontal_orientation_uses_horizontal_collision_plane(self) -> None:
        door = self.make_door(orientation="horizontal_door_plane")
        self.assertGreater(door.collision_rect.width, door.collision_rect.height)


if __name__ == "__main__":
    unittest.main()
