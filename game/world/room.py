from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoomRect:
    """Tile rectangle with left/top inclusive and right/bottom exclusive bounds."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

    @property
    def area(self) -> int:
        return self.width * self.height

    def intersects(self, other: "RoomRect", padding: int = 0) -> bool:
        return not (
            self.right + padding <= other.left
            or other.right + padding <= self.left
            or self.bottom + padding <= other.top
            or other.bottom + padding <= self.top
        )

    def contains(self, tile: tuple[int, int]) -> bool:
        x, y = tile
        return self.left <= x < self.right and self.top <= y < self.bottom

    def interior_tiles(self, margin: int = 1) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(self.top + margin, self.bottom - margin)
            for x in range(self.left + margin, self.right - margin)
        ]


@dataclass
class Room:
    room_id: int
    rect: RoomRect
    tag: str = "ordinary"
    connected_room_ids: set[int] = field(default_factory=set)
    doorway_candidates: list[tuple[int, int]] = field(default_factory=list)
    role_flags: set[str] = field(default_factory=set)

    @property
    def center(self) -> tuple[int, int]:
        return self.rect.center
