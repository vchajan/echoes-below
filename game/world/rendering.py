from __future__ import annotations

import math

import pygame

from game import settings
from game.assets import AssetManager
from game.camera import Camera
from game.entities.door import DynamicDoor
from game.entities.player import Player
from game.world.floor import GeneratedFloor
from game.world import collision
from game.world.tiles import tile_asset_index


FloorRenderKey = tuple[int, int, int]


def floor_render_key(generated_floor: GeneratedFloor) -> FloorRenderKey:
    return (generated_floor.seed, generated_floor.floor_number, generated_floor.attempt_seed)


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


class StaticWorldRenderer:
    def __init__(self, assets: AssetManager, tile_size: int) -> None:
        self.assets = assets
        self.tile_size = tile_size
        self.cache_key: FloorRenderKey | None = None
        self.world_surface: pygame.Surface | None = None
        self.rebuild_count = 0

    def build_for_floor(self, generated_floor: GeneratedFloor) -> pygame.Surface:
        key = floor_render_key(generated_floor)
        if self.world_surface is None or self.cache_key != key:
            self.world_surface = render_floor_surface(generated_floor, self.assets, self.tile_size)
            self.cache_key = key
            self.rebuild_count += 1
        return self.world_surface

    def clear(self) -> None:
        self.cache_key = None
        self.world_surface = None

    def render_view(
        self,
        target: pygame.Surface,
        generated_floor: GeneratedFloor,
        camera: Camera,
    ) -> pygame.Surface:
        world_surface = self.build_for_floor(generated_floor)
        target.blit(world_surface, (0, 0), camera.visible_world_rect)
        return world_surface


def scale_floor_surface(
    floor_surface: pygame.Surface,
    max_size: tuple[int, int],
) -> tuple[pygame.Surface, float]:
    width, height = floor_surface.get_size()
    scale = min(max_size[0] / width, max_size[1] / height)
    scaled_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return pygame.transform.scale(floor_surface, scaled_size), scale


def visible_tile_range(
    camera: Camera,
    tile_size: int,
    floor_width: int,
    floor_height: int,
    margin: int = 1,
) -> tuple[range, range]:
    visible = camera.visible_world_rect
    left = max(0, math.floor(visible.left / tile_size) - margin)
    top = max(0, math.floor(visible.top / tile_size) - margin)
    right = min(floor_width, math.ceil(visible.right / tile_size) + margin)
    bottom = min(floor_height, math.ceil(visible.bottom / tile_size) + margin)
    return range(left, right), range(top, bottom)


def build_local_glow_surface(radius: int) -> pygame.Surface:
    size = radius * 2
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    center = (radius, radius)
    # Draw from a faint outer halo to a bright centre.  The surface is
    # subtracted from the darkness overlay, so higher alpha means more light.
    rings = [
        (radius, 36),
        (int(radius * 0.78), 88),
        (int(radius * 0.56), 164),
        (int(radius * 0.34), 238),
    ]
    for ring_radius, alpha in rings:
        pygame.draw.circle(surface, (0, 0, 0, alpha), center, ring_radius)
    return surface


def apply_darkness(
    target: pygame.Surface,
    darkness_surface: pygame.Surface,
    glow_surface: pygame.Surface,
    player_screen_center: tuple[int, int],
    darkness_alpha: int = 250,
) -> None:
    darkness_surface.fill((0, 0, 0, darkness_alpha))
    glow_rect = glow_surface.get_rect(center=player_screen_center)
    darkness_surface.blit(glow_surface, glow_rect, special_flags=pygame.BLEND_RGBA_SUB)
    target.blit(darkness_surface, (0, 0))


def draw_doors(
    surface: pygame.Surface,
    doors: list[DynamicDoor],
    camera: Camera,
) -> None:
    screen_rect = surface.get_rect()
    for door in doors:
        rect = camera.world_rect_to_screen(door.visual_rect)
        if screen_rect.colliderect(rect):
            surface.blit(door.image, rect)


def draw_door_debug_overlay(
    surface: pygame.Surface,
    doors: list[DynamicDoor],
    camera: Camera,
    font: pygame.font.Font | None = None,
) -> None:
    screen_rect = surface.get_rect()
    for door in doors:
        collision_rect = camera.world_rect_to_screen(door.collision_rect)
        approach_rect = camera.world_rect_to_screen(door.approach_rect)
        if not screen_rect.colliderect(approach_rect) and not screen_rect.colliderect(collision_rect):
            continue

        movement_color = (255, 96, 96) if door.blocks_player else (118, 241, 173)
        scan_color = (255, 220, 80) if door.blocks_scan else (72, 226, 255)
        pygame.draw.rect(surface, (72, 226, 255), approach_rect, 1)
        pygame.draw.rect(surface, movement_color, collision_rect, 2)
        pygame.draw.circle(
            surface,
            scan_color,
            tuple(round(value) for value in camera.world_to_screen(door.world_center)),
            4,
        )

        if font is not None:
            label = (
                f"{door.door_id} {door.door_type.value} {door.state.value} "
                f"{door.orientation} move:{int(door.blocks_player)} scan:{int(door.blocks_scan)} "
                f"power:{int(door.powered)} lock:{int(door.is_locked)}"
            )
            image = font.render(label, True, (221, 235, 232))
            surface.blit(image, (collision_rect.left, max(0, collision_rect.top - 18)))


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


def draw_camera_debug_overlay(
    surface: pygame.Surface,
    generated_floor: GeneratedFloor,
    camera: Camera,
    tile_size: int,
    font: pygame.font.Font | None = None,
    player: Player | None = None,
) -> None:
    x_range, y_range = visible_tile_range(camera, tile_size, generated_floor.width, generated_floor.height)
    for tile_y in y_range:
        for tile_x in x_range:
            world_rect = collision.tile_to_world_rect(tile_x, tile_y, tile_size)
            screen_rect = camera.world_rect_to_screen(world_rect)
            pygame.draw.rect(surface, (255, 255, 255, 18), screen_rect, 1)

    def tile_center(tile: tuple[int, int]) -> tuple[int, int]:
        screen = camera.world_to_screen(((tile[0] + 0.5) * tile_size, (tile[1] + 0.5) * tile_size))
        return (round(screen.x), round(screen.y))

    objective_colors = {
        "near": (120, 180, 255),
        "middle": (255, 220, 80),
        "far": (255, 128, 64),
    }
    containment_set = set(generated_floor.containment_room_candidates)
    gated_set = {room_id for gate in generated_floor.gate_candidates[:3] for room_id in gate.gated_rooms}
    visible_screen = surface.get_rect()

    for room_a, room_b in sorted(generated_floor.graph_edges):
        start = tile_center(generated_floor.rooms[room_a].center)
        end = tile_center(generated_floor.rooms[room_b].center)
        if visible_screen.clipline(start, end):
            pygame.draw.line(surface, (230, 126, 45), start, end, 1)

    for gate in generated_floor.gate_candidates[:3]:
        room_a, room_b = gate.edge
        start = tile_center(generated_floor.rooms[room_a].center)
        end = tile_center(generated_floor.rooms[room_b].center)
        if visible_screen.clipline(start, end):
            pygame.draw.line(surface, (190, 128, 255), start, end, 3)

    for room in generated_floor.rooms:
        world_rect = pygame.Rect(
            room.rect.left * tile_size,
            room.rect.top * tile_size,
            room.rect.width * tile_size,
            room.rect.height * tile_size,
        )
        screen_rect = camera.world_rect_to_screen(world_rect)
        if not screen_rect.colliderect(visible_screen):
            continue
        color = (118, 241, 173) if room.room_id == generated_floor.start_room_id else (72, 226, 255)
        for group, room_ids in generated_floor.objective_room_groups.items():
            if room.room_id in room_ids:
                color = objective_colors.get(group, color)
        if room.room_id in gated_set:
            color = (190, 128, 255)
        if room.room_id in containment_set:
            color = (255, 80, 180)
        pygame.draw.rect(surface, color, screen_rect, 2)
        pygame.draw.circle(surface, color, tile_center(room.center), 4)
        if font is not None:
            label = font.render(str(room.room_id), True, color)
            surface.blit(label, screen_rect.topleft)

    for doorway in generated_floor.doorway_candidates:
        point = tile_center(doorway)
        if visible_screen.collidepoint(point):
            pygame.draw.circle(surface, (255, 220, 80), point, 3)

    for candidate in generated_floor.candidate_creature_spawns:
        point = tile_center(candidate)
        if visible_screen.collidepoint(point):
            pygame.draw.circle(surface, (255, 96, 96), point, 4, 1)

    for room_id in generated_floor.candidate_objective_rooms:
        point = tile_center(generated_floor.rooms[room_id].center)
        if visible_screen.collidepoint(point):
            pygame.draw.circle(surface, (255, 255, 120), point, 8, 1)

    spawn_point = tile_center(generated_floor.player_spawn)
    elevator_point = tile_center(generated_floor.elevator_tile)
    if visible_screen.collidepoint(spawn_point):
        pygame.draw.circle(surface, (255, 255, 255), spawn_point, 6)
    if visible_screen.collidepoint(elevator_point):
        pygame.draw.circle(surface, (72, 226, 255), elevator_point, 8, 2)

    if player is not None:
        visual_rect = camera.world_rect_to_screen(player.visual_rect)
        collision_rect = camera.world_rect_to_screen(player.collision_rect)
        pygame.draw.rect(surface, (255, 255, 255), visual_rect, 1)
        pygame.draw.rect(surface, (255, 96, 96), collision_rect, 2)
        tile_rect = collision.tile_to_world_rect(*player.current_tile, tile_size)
        pygame.draw.rect(surface, (118, 241, 173), camera.world_rect_to_screen(tile_rect), 2)

        if font is not None:
            label = font.render(
                f"tile {player.current_tile} | camera {camera.visible_world_rect}",
                True,
                (221, 235, 232),
            )
            surface.blit(label, (16, surface.get_height() - 34))


def draw_floor_content_debug(
    surface: pygame.Surface,
    floor_content,
    camera: Camera,
    font: pygame.font.Font | None = None,
) -> None:
    screen_rect = surface.get_rect()
    entities = [*floor_content.materials, floor_content.elevator]
    for entity in entities:
        if not getattr(entity, "scan_active", True):
            continue
        rect = camera.world_rect_to_screen(entity.visual_rect)
        if not screen_rect.colliderect(rect):
            continue
        surface.blit(entity.image, rect)
        pygame.draw.rect(surface, (118, 241, 173), rect, 1)
        if font is not None:
            label = font.render(
                f"{entity.scan_category}:{entity.unique_id}",
                True,
                (118, 241, 173),
            )
            surface.blit(label, (rect.left, max(0, rect.top - 17)))


def draw_material_contact_hints(
    surface: pygame.Surface,
    materials,
    player_world_position: pygame.Vector2,
    camera: Camera,
) -> None:
    screen_rect = surface.get_rect()
    for pickup in materials:
        if not pickup.scan_active:
            continue
        distance = pickup.world_position.distance_to(player_world_position)
        if distance > settings.MATERIAL_CONTACT_HINT_RADIUS:
            continue
        position = tuple(round(value) for value in camera.world_to_screen(pickup.world_position))
        if not screen_rect.collidepoint(position):
            continue
        radius = 2 if distance > settings.MATERIAL_CONTACT_HINT_RADIUS * 0.45 else 3
        pygame.draw.circle(surface, (90, 230, 242), position, radius)
