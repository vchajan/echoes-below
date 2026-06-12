from __future__ import annotations

import pygame


class Animation:
    def __init__(
        self,
        frames: list[pygame.Surface],
        frame_duration: float,
        looping: bool = True,
    ) -> None:
        if not frames:
            raise ValueError("Animation requires at least one frame.")
        if frame_duration <= 0:
            raise ValueError("frame_duration must be positive.")

        self.frames = frames
        self.frame_duration = frame_duration
        self.looping = looping
        self.elapsed = 0.0
        self.frame_index = 0
        self.complete = False

    def reset(self) -> None:
        self.elapsed = 0.0
        self.frame_index = 0
        self.complete = False

    def update(self, dt: float) -> None:
        if self.complete or len(self.frames) == 1:
            return

        self.elapsed += dt
        while self.elapsed >= self.frame_duration and not self.complete:
            self.elapsed -= self.frame_duration
            self.frame_index += 1

            if self.frame_index >= len(self.frames):
                if self.looping:
                    self.frame_index = 0
                else:
                    self.frame_index = len(self.frames) - 1
                    self.complete = True

    @property
    def current_frame(self) -> pygame.Surface:
        return self.frames[self.frame_index]

    @property
    def is_complete(self) -> bool:
        return self.complete
