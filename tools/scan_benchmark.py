from __future__ import annotations

import os
from pathlib import Path
import statistics
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from game import settings
from game.assets import AssetManager
from game.systems.scan import ScanSystem
from game.world.door_generation import create_doors_for_floor
from game.world.generator import FloorGenerator


def tile_center(tile: tuple[int, int]) -> tuple[float, float]:
    return ((tile[0] + 0.5) * settings.TILE_SIZE, (tile[1] + 0.5) * settings.TILE_SIZE)


def main() -> int:
    pygame.init()
    pygame.display.set_mode((1, 1))
    assets = AssetManager(audio_available=False)
    generator = FloorGenerator()
    durations: list[float] = []
    raw_hits: list[int] = []
    deduplicated_hits: list[int] = []
    scans = 0
    started = time.perf_counter()

    try:
        for floor_number in (1, 2, 3):
            for seed in (1001, 12345, 27182):
                floor = generator.generate(seed=seed, floor_number=floor_number)
                door_result = create_doors_for_floor(
                    floor,
                    assets,
                    settings.TILE_SIZE,
                    floor_powered=True,
                )
                # Alternate states so the benchmark covers both blocked and open passages.
                for index, door in enumerate(door_result.doors):
                    if index % 2:
                        door.force_open()

                candidate_tiles = [floor.player_spawn]
                candidate_tiles.extend(floor.rooms[room_id].center for room_id in floor.candidate_objective_rooms[:2])
                for tile in candidate_tiles:
                    scan = ScanSystem()
                    if not scan.trigger(
                        tile_center(tile),
                        floor,
                        door_result.blockers,
                        settings.TILE_SIZE,
                    ):
                        raise RuntimeError("Benchmark scan unexpectedly rejected.")
                    diagnostics = scan.diagnostics
                    durations.append(diagnostics.last_raycast_ms)
                    raw_hits.append(diagnostics.raw_hit_count)
                    deduplicated_hits.append(diagnostics.deduplicated_hit_count)
                    if any(hit.distance > settings.SCAN_MAX_RADIUS + 1e-6 for hit in scan.active_wave.hits):
                        raise AssertionError(f"Out-of-range hit for seed {seed}, floor {floor_number}")
                    scans += 1
    except Exception as exc:
        print(f"scan benchmark failed: {exc}", file=sys.stderr)
        return 1
    finally:
        pygame.quit()

    total = time.perf_counter() - started
    print(f"scans: {scans}")
    print(f"rays_per_scan: {settings.SCAN_RAY_COUNT}")
    print(f"average_raycast_ms: {statistics.fmean(durations):.3f}")
    print(f"median_raycast_ms: {statistics.median(durations):.3f}")
    print(f"maximum_raycast_ms: {max(durations):.3f}")
    print(f"average_raw_hits: {statistics.fmean(raw_hits):.1f}")
    print(f"average_deduplicated_hits: {statistics.fmean(deduplicated_hits):.1f}")
    print(f"total_seconds: {total:.3f}")
    if max(durations) > 100.0:
        print("warning: at least one scan exceeded 100 ms on this machine")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
