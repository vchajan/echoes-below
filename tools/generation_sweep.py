from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from game.world.generator import FloorGenerator


def main() -> int:
    generator = FloorGenerator()
    config = generator.config_for_floor(1)
    failures: list[str] = []

    for seed in range(1000, 1050):
        try:
            generated_floor = generator.generate(seed=seed, floor_number=1)
            if len(generated_floor.rooms) < config.minimum_rooms:
                failures.append(f"{seed}: room minimum not met")
            if generated_floor.player_spawn is None:
                failures.append(f"{seed}: missing player spawn")
            if generated_floor.elevator_tile is None:
                failures.append(f"{seed}: missing elevator")
        except Exception as exc:
            failures.append(f"{seed}: {exc}")

    if failures:
        print("Generation sweep failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Generation sweep passed for 50 Floor 1 seeds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
