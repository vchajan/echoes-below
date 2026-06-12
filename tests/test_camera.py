import unittest

import pygame

from game.camera import Camera


class CameraTests(unittest.TestCase):
    def test_camera_centres_on_player_away_from_edges(self) -> None:
        camera = Camera((200, 120), (600, 500))
        camera.update(pygame.Vector2(300, 260))
        self.assertEqual(camera.offset, pygame.Vector2(200, 200))

    def test_camera_clamps_at_left_edge(self) -> None:
        camera = Camera((200, 120), (600, 500))
        camera.update(pygame.Vector2(40, 260))
        self.assertEqual(camera.offset.x, 0)

    def test_camera_clamps_at_right_edge(self) -> None:
        camera = Camera((200, 120), (600, 500))
        camera.update(pygame.Vector2(590, 260))
        self.assertEqual(camera.offset.x, 400)

    def test_camera_clamps_at_top_edge(self) -> None:
        camera = Camera((200, 120), (600, 500))
        camera.update(pygame.Vector2(300, 20))
        self.assertEqual(camera.offset.y, 0)

    def test_camera_clamps_at_bottom_edge(self) -> None:
        camera = Camera((200, 120), (600, 500))
        camera.update(pygame.Vector2(300, 490))
        self.assertEqual(camera.offset.y, 380)

    def test_camera_handles_world_smaller_than_viewport(self) -> None:
        camera = Camera((500, 400), (300, 200))
        camera.update(pygame.Vector2(150, 100))
        self.assertEqual(camera.offset, pygame.Vector2(0, 0))
        self.assertEqual(camera.visible_world_rect.size, (300, 200))

    def test_world_to_screen_and_screen_to_world_are_inverse(self) -> None:
        camera = Camera((200, 120), (600, 500))
        camera.update(pygame.Vector2(300, 260))
        world_position = pygame.Vector2(345.5, 288.25)
        screen_position = camera.world_to_screen(world_position)
        self.assertLess(camera.screen_to_world(screen_position).distance_to(world_position), 0.001)


if __name__ == "__main__":
    unittest.main()
