from __future__ import annotations

import os
from pathlib import Path
import statistics
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

from game import settings
from game.app import Game
from game.systems.modules import MODULE_DEFINITIONS, ModuleType
from tools.smoke_test import freeze_creatures


def main() -> int:
    game = Game()
    timings: list[float] = []
    try:
        game.next_seed = 12344
        game.start_new_run()
        assert game.placeholder_run is not None
        run = game.placeholder_run
        run.material_counts = {"scrap": 20, "circuit": 20, "power_cell": 20}
        for definition in MODULE_DEFINITIONS:
            run.module_loadout.craft(definition.module_type, run.material_counts)
        run.module_loadout.equip(ModuleType.DECOY_BEACON, 0)
        run.module_loadout.equip(ModuleType.SCAN_PROJECTOR, 1)
        freeze_creatures(game)
        game.activate_module_slot(0)
        game.activate_module_slot(1)

        for _ in range(360):
            started = time.perf_counter()
            game.update_gameplay(1.0 / settings.FPS, pygame.Vector2())
            timings.append((time.perf_counter() - started) * 1000.0)

        print(f"frames: {len(timings)}")
        print(f"average_update_ms: {statistics.fmean(timings):0.3f}")
        print(f"median_update_ms: {statistics.median(timings):0.3f}")
        print(f"maximum_update_ms: {max(timings):0.3f}")
        print(f"projector_scans: {game.module_effects.diagnostics.projector_scans}")
        print(f"decoy_pulses: {game.module_effects.diagnostics.decoy_pulses}")
        print(f"active_devices: {game.module_effects.active_device_count}")
        print(f"active_threats: {len(game.threat_events.active_events)}")
        print(f"scan_traces: {len(game.scan_system.traces)}")
        print(f"snapshots: {len(game.snapshot_system.snapshots)}")
        if game.module_effects.diagnostics.projector_scans < 1:
            raise RuntimeError("Performance audit did not exercise projector scans")
        return 0
    finally:
        game.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
