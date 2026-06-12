from __future__ import annotations

from dataclasses import dataclass
import random

from game.assets import AssetManager
from game.entities.door import DoorType, DynamicDoor
from game.world.blockers import DynamicBlockerRegistry
from game.world.floor import DoorwayCandidate, GeneratedFloor


@dataclass
class DoorGenerationResult:
    doors: list[DynamicDoor]
    blockers: DynamicBlockerRegistry


def create_doors_for_floor(
    generated_floor: GeneratedFloor,
    assets: AssetManager,
    tile_size: int,
    floor_powered: bool = True,
) -> DoorGenerationResult:
    records = _unique_doorway_records(generated_floor)
    if not records:
        blockers = DynamicBlockerRegistry([], tile_size)
        return DoorGenerationResult([], blockers)

    selected: dict[tuple[int, int], DoorwayCandidate] = {}
    door_types: dict[tuple[int, int], DoorType] = {}
    record_by_tile = {record.tile: record for record in records}
    candidate_tiles = set(record_by_tile)

    security_tile: tuple[int, int] | None = None
    containment_tile: tuple[int, int] | None = None

    if generated_floor.floor_number >= 2:
        security_tile = _first_gate_tile(generated_floor, candidate_tiles)
        if security_tile is not None:
            door_types[security_tile] = DoorType.SECURITY
            selected[security_tile] = record_by_tile[security_tile]

    if generated_floor.floor_number >= 3:
        containment_tile = _first_gate_tile(generated_floor, candidate_tiles - set(door_types))
        if containment_tile is not None:
            door_types[containment_tile] = DoorType.CONTAINMENT
            selected[containment_tile] = record_by_tile[containment_tile]

    powered_target = min(len(records), max(2, min(4 + generated_floor.floor_number, 7)))
    ordered = list(records)
    rng = random.Random(generated_floor.attempt_seed + generated_floor.floor_number * 60_013 + 6)
    rng.shuffle(ordered)
    ordered.sort(key=lambda record: _door_score(record, generated_floor, rng), reverse=True)

    for record in ordered:
        if len(selected) >= powered_target:
            break
        if record.tile in selected:
            continue
        door_types[record.tile] = DoorType.POWERED
        selected[record.tile] = record

    for record in records:
        if record.tile in selected:
            continue
        if len(selected) >= powered_target:
            break
        door_types[record.tile] = DoorType.POWERED
        selected[record.tile] = record

    doors = [
        DynamicDoor(
            door_id=_door_id(generated_floor, index, door_types[tile], record),
            door_type=door_types[tile],
            doorway=record,
            assets=assets,
            tile_size=tile_size,
            powered=floor_powered,
        )
        for index, (tile, record) in enumerate(sorted(selected.items(), key=lambda item: item[0]))
    ]
    blockers = DynamicBlockerRegistry(doors, tile_size)
    return DoorGenerationResult(doors, blockers)


def _unique_doorway_records(generated_floor: GeneratedFloor) -> list[DoorwayCandidate]:
    forbidden = {generated_floor.player_spawn, generated_floor.elevator_tile}
    records: dict[tuple[int, int], DoorwayCandidate] = {}
    for record in sorted(generated_floor.doorway_data, key=lambda item: (item.tile, item.edge)):
        if record.tile in forbidden:
            continue
        if record.orientation not in ("vertical_door_plane", "horizontal_door_plane"):
            continue
        records.setdefault(record.tile, record)
    return list(records.values())


def _first_gate_tile(generated_floor: GeneratedFloor, candidate_tiles: set[tuple[int, int]]) -> tuple[int, int] | None:
    for gate in generated_floor.gate_candidates:
        for tile in gate.doorway_tiles:
            if tile in candidate_tiles:
                return tile
    return None


def _door_score(record: DoorwayCandidate, generated_floor: GeneratedFloor, rng: random.Random) -> tuple[int, int, float]:
    gated_edges = {gate.edge for gate in generated_floor.gate_candidates[:3]}
    return (
        1 if record.edge in gated_edges else 0,
        -abs(record.tile[0] - generated_floor.player_spawn[0]) - abs(record.tile[1] - generated_floor.player_spawn[1]),
        rng.random(),
    )


def _door_id(
    generated_floor: GeneratedFloor,
    index: int,
    door_type: DoorType,
    record: DoorwayCandidate,
) -> str:
    return (
        f"f{generated_floor.floor_number}-a{generated_floor.generation_attempt}-"
        f"{index:02d}-{door_type.value}-{record.tile[0]}-{record.tile[1]}"
    )
