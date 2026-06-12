from __future__ import annotations

from game.world.blockers import BlockerPurpose, DynamicBlockerRegistry


def doorway_passable_for_creature(
    blockers: DynamicBlockerRegistry,
    tile: tuple[int, int],
) -> bool:
    return not blockers.blocks_tile(tile[0], tile[1], BlockerPurpose.CREATURE_MOVEMENT)
