from __future__ import annotations

from dataclasses import dataclass

import pygame

from game import settings


@dataclass
class Button:
    text: str
    action: str
    rect: pygame.Rect
    hovered: bool = False

    @classmethod
    def centered(
        cls,
        text: str,
        action: str,
        center: tuple[int, int],
        size: tuple[int, int] = (settings.BUTTON_WIDTH, settings.BUTTON_HEIGHT),
    ) -> "Button":
        rect = pygame.Rect(0, 0, size[0], size[1])
        rect.center = center
        return cls(text=text, action=action, rect=rect)

    def update_hover(self, mouse_pos: tuple[int, int]) -> bool:
        self.hovered = self.rect.collidepoint(mouse_pos)
        return self.hovered

    def was_clicked(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return False
        return self.rect.collidepoint(event.pos)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font, selected: bool) -> None:
        if selected:
            fill = settings.COLOR_PANEL_SELECTED
            border = settings.COLOR_ACCENT
        elif self.hovered:
            fill = settings.COLOR_PANEL_HOVER
            border = settings.COLOR_ACCENT_DIM
        else:
            fill = settings.COLOR_PANEL
            border = settings.COLOR_ACCENT_DIM

        pygame.draw.rect(surface, fill, self.rect, border_radius=6)
        pygame.draw.rect(surface, border, self.rect, width=2, border_radius=6)

        label = font.render(self.text, True, settings.COLOR_TEXT)
        label_rect = label.get_rect(center=self.rect.center)
        surface.blit(label, label_rect)
