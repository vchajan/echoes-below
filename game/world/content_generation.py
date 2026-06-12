from __future__ import annotations

from dataclasses import dataclass
import random

from game.assets import AssetManager
from game.entities.scan_objects import ElevatorEntity, MaterialPickup, MaterialType
from game.world.floor import GeneratedFloor


@dataclass
class FloorContent:
    materials: list[MaterialPickup]
    elevator: ElevatorEntity

    @property
    def scan_entities(self) -> list[object]:
        return [*(pickup for pickup in self.materials if pickup.scan_active), self.elevator]

    def update(self, dt: float) -> None:
        for pickup in self.materials:
            pickup.update(dt)
        self.elevator.update(dt)


def create_floor_content(
    generated_floor: GeneratedFloor,
    assets: AssetManager,
    tile_size: int,
) -> FloorContent:
    rng = random.Random(_content_seed(generated_floor))
    material_count = {1: 3, 2: 4, 3: 5}.get(generated_floor.floor_number, 3)
    room_ids = _content_room_order(generated_floor)
    reserved = {
        generated_floor.player_spawn,
        generated_floor.elevator_tile,
        *generated_floor.elevator_approach_tiles,
        *generated_floor.doorway_candidates,
    }
    used_tiles: set[tuple[int, int]] = set()
    material_types = [MaterialType.SCRAP, MaterialType.CIRCUIT, MaterialType.POWER_CELL]
    rng.shuffle(material_types)

    materials: list[MaterialPickup] = []
    for index in range(material_count):
        room_id = room_ids[index % len(room_ids)]
        tile = _choose_room_tile(generated_floor, room_id, reserved | used_tiles, rng)
        if tile is None:
            tile = _choose_global_tile(generated_floor, reserved | used_tiles, rng)
        if tile is None:
            break
        used_tiles.add(tile)
        material_type = material_types[index % len(material_types)]
        pickup_id = (
            f"f{generated_floor.floor_number}-a{generated_floor.generation_attempt}-"
            f"material-{index:02d}-{material_type.value}-{tile[0]}-{tile[1]}"
        )
        materials.append(MaterialPickup(pickup_id, material_type, tile, assets, tile_size))

    elevator_id = (
        f"f{generated_floor.floor_number}-a{generated_floor.generation_attempt}-"
        f"elevator-{generated_floor.elevator_tile[0]}-{generated_floor.elevator_tile[1]}"
    )
    elevator = ElevatorEntity(
        elevator_id,
        generated_floor.elevator_tile,
        generated_floor.elevator_approach_tiles,
        assets,
        tile_size,
    )
    return FloorContent(materials=materials, elevator=elevator)


def _content_seed(generated_floor: GeneratedFloor) -> int:
    return (
        generated_floor.seed * 1_000_003
        + generated_floor.floor_number * 97_409
        + generated_floor.attempt_seed * 65_537
        + generated_floor.generation_attempt * 257
    ) & 0xFFFFFFFFFFFFFFFF


def _content_room_order(generated_floor: GeneratedFloor) -> list[int]:
    ordered: list[int] = []
    for room_id in generated_floor.candidate_material_rooms:
        if room_id != generated_floor.start_room_id and room_id not in ordered:
            ordered.append(room_id)
    for group_name in ("far", "middle", "near"):
        for room_id in generated_floor.objective_room_groups.get(group_name, []):
            if room_id != generated_floor.start_room_id and room_id not in ordered:
                ordered.append(room_id)
    for room in generated_floor.rooms:
        if room.room_id != generated_floor.start_room_id and room.room_id not in ordered:
            ordered.append(room.room_id)
    if not ordered:
        ordered.append(generated_floor.start_room_id)
    return ordered


def _choose_room_tile(
    generated_floor: GeneratedFloor,
    room_id: int,
    reserved: set[tuple[int, int]],
    rng: random.Random,
) -> tuple[int, int] | None:
    room = generated_floor.rooms[room_id]
    for margin in (2, 1, 0):
        candidates = [
            tile
            for tile in room.rect.interior_tiles(margin=margin)
            if generated_floor.is_walkable(*tile) and tile not in reserved
        ]
        if candidates:
            candidates.sort()
            return candidates[rng.randrange(len(candidates))]
    return None


def _choose_global_tile(
    generated_floor: GeneratedFloor,
    reserved: set[tuple[int, int]],
    rng: random.Random,
) -> tuple[int, int] | None:
    candidates = [tile for tile in generated_floor.walkable_tiles() if tile not in reserved]
    if not candidates:
        return None
    candidates.sort()
    return candidates[rng.randrange(len(candidates))]
