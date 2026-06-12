from __future__ import annotations

import pygame


class Camera:
    def __init__(self, viewport_size: tuple[int, int], world_size: tuple[int, int]) -> None:
        self.viewport_width, self.viewport_height = viewport_size
        self.world_width, self.world_height = world_size
        self.offset = pygame.Vector2(0, 0)

    def update(self, target_position: pygame.Vector2 | tuple[float, float], dt: float = 0.0) -> None:
        target = pygame.Vector2(target_position)
        self.offset.x = target.x - self.viewport_width / 2
        self.offset.y = target.y - self.viewport_height / 2
        self.clamp_to_world()

    def clamp_to_world(self) -> None:
        max_x = max(0, self.world_width - self.viewport_width)
        max_y = max(0, self.world_height - self.viewport_height)
        self.offset.x = min(max(self.offset.x, 0), max_x)
        self.offset.y = min(max(self.offset.y, 0), max_y)

    def world_to_screen(self, position: pygame.Vector2 | tuple[float, float]) -> pygame.Vector2:
        return pygame.Vector2(position) - self.offset

    def screen_to_world(self, position: pygame.Vector2 | tuple[float, float]) -> pygame.Vector2:
        return pygame.Vector2(position) + self.offset

    def world_rect_to_screen(self, rect: pygame.Rect) -> pygame.Rect:
        return pygame.Rect(
            round(rect.x - self.offset.x),
            round(rect.y - self.offset.y),
            rect.width,
            rect.height,
        )

    @property
    def visible_world_rect(self) -> pygame.Rect:
        return pygame.Rect(
            round(self.offset.x),
            round(self.offset.y),
            min(self.viewport_width, self.world_width),
            min(self.viewport_height, self.world_height),
        )
