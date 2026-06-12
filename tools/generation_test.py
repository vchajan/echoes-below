from __future__ import annotations

from collections import Counter
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from game.world.generator import FloorGenerator
from game.world.validation import validate_floor


def floor_signature(floor) -> tuple[object, ...]:
    return (
        tuple((room.rect.left, room.rect.top, room.rect.width, room.rect.height) for room in floor.rooms),
        tuple(sorted(floor.graph_edges)),
        floor.player_spawn,
        floor.elevator_tile,
        tuple(floor.candidate_creature_spawns),
        tuple(floor.candidate_objective_rooms),
        tuple(floor.candidate_material_rooms),
        floor.generation_attempt,
        floor.attempt_seed,
    )


def main() -> int:
    generator = FloorGenerator()
    failures: list[str] = []
    attempts: list[int] = []
    room_counts: list[int] = []
    connectivity_ratios: list[float] = []
    cycle_counts: Counter[int] = Counter()
    start_time = time.perf_counter()
    floors_generated = 0

    for floor_number in (1, 2, 3):
        profile = generator.config_for_floor(floor_number)
        for index in range(150):
            seed = floor_number * 100_000 + index
            try:
                floor = generator.generate(seed=seed, floor_number=floor_number)
                report = floor.validation_report or validate_floor(floor, profile)
                floors_generated += 1

                if not report.is_valid:
                    failures.append(f"floor {floor_number}, seed {seed}: {report.errors}")
                if not (profile.minimum_rooms <= len(floor.rooms) <= profile.maximum_rooms):
                    failures.append(f"floor {floor_number}, seed {seed}: invalid room count")
                if floor_number >= 2 and report.graph_cycle_rank < 1:
                    failures.append(f"floor {floor_number}, seed {seed}: missing required cycle")
                if report.reachable_walkable_tiles != report.total_walkable_tiles:
                    failures.append(f"floor {floor_number}, seed {seed}: disconnected walkable tiles")
                if floor.elevator_tile not in floor.walkable_tiles():
                    failures.append(f"floor {floor_number}, seed {seed}: elevator not walkable")
                if len(floor.candidate_creature_spawns) < profile.minimum_creature_candidates:
                    failures.append(f"floor {floor_number}, seed {seed}: not enough creature candidates")
                if len(floor.candidate_objective_rooms) < profile.minimum_objective_candidates:
                    failures.append(f"floor {floor_number}, seed {seed}: not enough objective candidates")
                if len(floor.candidate_material_rooms) < profile.minimum_material_candidates:
                    failures.append(f"floor {floor_number}, seed {seed}: not enough material candidates")
                if not floor.doorway_candidates:
                    failures.append(f"floor {floor_number}, seed {seed}: no doorway candidates")

                if index % 25 == 0:
                    again = generator.generate(seed=seed, floor_number=floor_number)
                    if not np.array_equal(floor.tiles, again.tiles) or floor_signature(floor) != floor_signature(again):
                        failures.append(f"floor {floor_number}, seed {seed}: deterministic regeneration mismatch")

                attempts.append(floor.generation_attempt)
                room_counts.append(len(floor.rooms))
                connectivity_ratios.append(report.connectivity_ratio)
                cycle_counts[report.graph_cycle_rank] += 1
            except Exception as exc:
                failures.append(f"floor {floor_number}, seed {seed}: {exc}")

    elapsed = time.perf_counter() - start_time

    if failures:
        print("Generation stress test failed:")
        for failure in failures[:50]:
            print(f"- {failure}")
        if len(failures) > 50:
            print(f"... {len(failures) - 50} additional failures")
        return 1

    average_attempt = sum(attempts) / len(attempts)
    average_rooms = sum(room_counts) / len(room_counts)
    average_connectivity = sum(connectivity_ratios) / len(connectivity_ratios)

    print("Generation stress test passed.")
    print(f"floors_generated: {floors_generated}")
    print("failures: 0")
    print(f"retries_used: {sum(1 for attempt in attempts if attempt > 1)}")
    print(f"maximum_attempt_index: {max(attempts)}")
    print(f"average_attempt_index: {average_attempt:0.3f}")
    print(f"average_room_count: {average_rooms:0.3f}")
    print(f"cycle_rank_distribution: {dict(sorted(cycle_counts.items()))}")
    print(f"average_connectivity_ratio: {average_connectivity:0.3f}")
    print(f"total_execution_time: {elapsed:0.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
