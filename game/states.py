from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class GameState(Enum):
    SPLASH = auto()
    MAIN_MENU = auto()
    HOW_TO_PLAY = auto()
    PLAYING = auto()
    PAUSED = auto()
    WORKSHOP = auto()
    FLOOR_TRANSITION = auto()
    DEATH = auto()
    VICTORY = auto()


@dataclass
class PlaceholderRun:
    seed: int
    floor: int = 1
    score: int = 0
    elapsed_time: float = 0.0
    restart_count: int = 0

    def reset_same_seed(self) -> "PlaceholderRun":
        return PlaceholderRun(
            seed=self.seed,
            floor=1,
            score=0,
            elapsed_time=0.0,
            restart_count=self.restart_count + 1,
        )
