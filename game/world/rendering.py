from __future__ import annotations

import pygame

from game.assets import AssetManager
from game.world.floor import GeneratedFloor
from game.world.tiles import tile_asset_index


def render_floor_surface(
    generated_floor: GeneratedFloor,
    assets: AssetManager,
    tile_size: int,
) -> pygame.Surface:
    tile_frames = assets.get_sheet_frames("industrial_tiles")
    surface = pygame.Surface(generated_floor.world_size_pixels(tile_size)).convert()

    for y in range(generated_floor.height):
        for x in range(generated_floor.width):
            tile = generated_floor.tile_at(x, y)
            frame = tile_frames[tile_asset_index(tile)]
            surface.blit(frame, (x * tile_size, y * tile_size))
    return surface


def scale_floor_surface(
    floor_surface: pygame.Surface,
    max_size: tuple[int, int],
) -> tuple[pygame.Surface, float]:
    width, height = floor_surface.get_size()
    scale = min(max_size[0] / width, max_size[1] / height)
    scaled_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return pygame.transform.scale(floor_surface, scaled_size), scale


def draw_debug_overlay(
    surface: pygame.Surface,
    generated_floor: GeneratedFloor,
    preview_rect: pygame.Rect,
    font: pygame.font.Font | None = None,
) -> None:
    tile_w = preview_rect.width / generated_floor.width
    tile_h = preview_rect.height / generated_floor.height

    def point(tile: tuple[int, int]) -> tuple[int, int]:
        return (
            int(preview_rect.left + (tile[0] + 0.5) * tile_w),
            int(preview_rect.top + (tile[1] + 0.5) * tile_h),
        )

    objective_colors = {
        "near": (120, 180, 255),
        "middle": (255, 220, 80),
        "far": (255, 128, 64),
    }
    containment_set = set(generated_floor.containment_room_candidates)
    gated_set = {room_id for gate in generated_floor.gate_candidates[:3] for room_id in gate.gated_rooms}

    for room in generated_floor.rooms:
        rect = pygame.Rect(
            int(preview_rect.left + room.rect.left * tile_w),
            int(preview_rect.top + room.rect.top * tile_h),
            max(1, int(room.rect.width * tile_w)),
            max(1, int(room.rect.height * tile_h)),
        )
        color = (118, 241, 173) if room.room_id == generated_floor.start_room_id else (72, 226, 255)
        for group, room_ids in generated_floor.objective_room_groups.items():
            if room.room_id in room_ids:
                color = objective_colors.get(group, color)
        if room.room_id in gated_set:
            color = (190, 128, 255)
        if room.room_id in containment_set:
            color = (255, 80, 180)
        pygame.draw.rect(surface, color, rect, 1)
        pygame.draw.circle(surface, color, point(room.center), 3)
        if font is not None:
            label = font.render(str(room.room_id), True, color)
            surface.blit(label, rect.topleft)

    for room_a, room_b in sorted(generated_floor.graph_edges):
        pygame.draw.line(
            surface,
            (230, 126, 45),
            point(generated_floor.rooms[room_a].center),
            point(generated_floor.rooms[room_b].center),
            1,
        )

    for gate in generated_floor.gate_candidates[:3]:
        room_a, room_b = gate.edge
        pygame.draw.line(
            surface,
            (190, 128, 255),
            point(generated_floor.rooms[room_a].center),
            point(generated_floor.rooms[room_b].center),
            3,
        )

    for doorway in generated_floor.doorway_candidates:
        pygame.draw.circle(surface, (255, 220, 80), point(doorway), 2)

    for candidate in generated_floor.candidate_creature_spawns:
        pygame.draw.circle(surface, (255, 96, 96), point(candidate), 3, 1)

    pygame.draw.circle(surface, (255, 255, 255), point(generated_floor.player_spawn), 5)
    pygame.draw.circle(surface, (72, 226, 255), point(generated_floor.elevator_tile), 6, 2)
