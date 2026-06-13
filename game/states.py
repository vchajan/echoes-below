from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from game.systems.modules import ModuleLoadout, ModuleRuntimeState


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
    completed_floor_count: int = 0
    generated_floor: Any | None = None
    material_counts: dict[str, int] = field(default_factory=lambda: {"scrap": 0, "circuit": 0, "power_cell": 0})
    materials_collected: int = 0
    floor_completion_summaries: dict[int, dict[str, Any]] = field(default_factory=dict)
    module_loadout: ModuleLoadout = field(default_factory=ModuleLoadout)
    module_runtime: ModuleRuntimeState = field(default_factory=ModuleRuntimeState)

    def reset_same_seed(self) -> "PlaceholderRun":
        return PlaceholderRun(
            seed=self.seed,
            floor=1,
            score=0,
            elapsed_time=0.0,
            restart_count=self.restart_count + 1,
            completed_floor_count=0,
            material_counts={"scrap": 0, "circuit": 0, "power_cell": 0},
            materials_collected=0,
            floor_completion_summaries={},
            module_loadout=ModuleLoadout(),
            module_runtime=ModuleRuntimeState(),
        )
