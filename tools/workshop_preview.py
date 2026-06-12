from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

if "--headless" in sys.argv:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game.app import Game
from game.states import GameState, PlaceholderRun
from game.systems.modules import MODULE_DEFINITIONS, ModuleType


def save_frame(game: Game, path: Path) -> None:
    game.render()
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(game.screen, str(path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview workshop crafting and module loadout.")
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    game = Game()
    try:
        game.placeholder_run = PlaceholderRun(
            seed=args.seed,
            floor=1,
            score=550,
            completed_floor_count=1,
            material_counts={"scrap": 4, "circuit": 4, "power_cell": 4},
            floor_completion_summaries={1: {"floor": 1, "score": 550}},
        )
        game.run_exists = True
        game.last_completed_floor = 1
        game.transition_to(GameState.WORKSHOP)

        if not args.headless:
            print("Controls: Up/Down select, Left/Right or Q/E choose slot, Enter craft/equip.")
            game.run()
            return 0

        artifact_dir = ROOT / "artifacts"
        paths = {
            "initial": artifact_dir / f"workshop_preview_{args.seed}_initial.png",
            "shock": artifact_dir / f"workshop_preview_{args.seed}_shock_crafted.png",
            "two_slots": artifact_dir / f"workshop_preview_{args.seed}_two_slots.png",
            "replacement": artifact_dir / f"workshop_preview_{args.seed}_replacement.png",
            "floor2": artifact_dir / f"workshop_preview_{args.seed}_floor2.png",
        }

        save_frame(game, paths["initial"])

        game.activate_workshop_selection()  # Shock Pulse -> slot 1
        save_frame(game, paths["shock"])

        game.workshop_system.selected_index = 1
        game.workshop_system.select_slot(1)
        game.activate_workshop_selection()  # Decoy Beacon -> slot 2
        save_frame(game, paths["two_slots"])

        game.workshop_system.selected_index = 2
        game.workshop_system.select_slot(1)
        game.activate_workshop_selection()  # Door Wedge replaces slot 2
        save_frame(game, paths["replacement"])

        loadout_after_floor1 = game.placeholder_run.module_loadout.snapshot()
        score_after_floor1 = game.placeholder_run.score
        materials_after_floor1 = dict(game.placeholder_run.material_counts)

        game.last_completed_floor = 2
        game.placeholder_run.floor = 2
        game.placeholder_run.completed_floor_count = 2
        game.placeholder_run.score = 1100
        game.placeholder_run.material_counts["scrap"] += 2
        game.placeholder_run.material_counts["circuit"] += 2
        game.placeholder_run.material_counts["power_cell"] += 1
        game.transition_to(GameState.WORKSHOP)
        save_frame(game, paths["floor2"])

        for name, path in paths.items():
            print(f"{name}_preview: {path}")
        print("recipes:")
        for definition in MODULE_DEFINITIONS:
            print(f"  {definition.module_type.value}: {dict(definition.recipe)}")
        print(f"floor1_loadout: {loadout_after_floor1}")
        print(f"floor1_score_unchanged: {score_after_floor1 == 550}")
        print(f"floor1_materials_after_crafting: {materials_after_floor1}")
        print(f"floor2_loadout_preserved: {game.placeholder_run.module_loadout.snapshot() == loadout_after_floor1}")
        print(f"floor2_score: {game.placeholder_run.score}")
        print(f"floor2_materials: {game.placeholder_run.material_counts}")
        print(f"selected_slot: {game.workshop_system.target_slot + 1}")
        print(f"crafted_count: {len(game.placeholder_run.module_loadout.crafted_modules)}")
        print(f"equipped_slots: {game.placeholder_run.module_loadout.equipped_slots}")
        return 0
    finally:
        game.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
