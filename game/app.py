from __future__ import annotations

import pygame

import random

from game.assets import EFFECT_IMAGE_PATHS, MODULE_ICON_PATHS, AssetManager
from game.camera import Camera
from game.entities.creature import Creature
from game.entities.door import DoorType, DynamicDoor
from game.entities.scan_objects import ElevatorEntity, MaterialPickup
from game.entities.player import Player, movement_direction_from_bools
from game import settings
from game.systems.creature_ai import CreatureAI, CreatureState
from game.systems.crafting import WorkshopAction, WorkshopSystem
from game.systems.modules import MODULE_BY_VALUE, MODULE_DEFINITIONS
from game.systems.floor_objectives import Floor1ObjectiveSystem, Floor2ObjectiveSystem
from game.systems.floor3_objectives import Floor3ObjectiveSystem
from game.systems.scan import ScanRenderer, ScanSystem
from game.systems.snapshots import EchoSnapshotRenderer, EchoSnapshotSystem
from game.systems.threat_events import ThreatEventSystem
from game.states import GameState, PlaceholderRun
from game.ui.buttons import Button
from game.world.blockers import DynamicBlockerRegistry
from game.world.content_generation import FloorContent, create_floor_content
from game.world.door_generation import create_doors_for_floor
from game.world.generator import FloorGenerator, GenerationError
from game.world.rendering import (
    StaticWorldRenderer,
    apply_darkness,
    build_local_glow_surface,
    draw_door_debug_overlay,
    draw_doors,
    draw_floor_content_debug,
    draw_material_contact_hints,
    draw_camera_debug_overlay,
    draw_debug_overlay,
)


class Game:
    def __init__(self) -> None:
        pygame.init()
        self.audio_available = self._init_audio()

        self.screen = pygame.display.set_mode(settings.WINDOW_SIZE)
        pygame.display.set_caption(settings.WINDOW_TITLE)
        self.clock = pygame.time.Clock()

        self.fonts = self._load_fonts()
        self.assets = AssetManager(audio_available=self.audio_available)
        self.visual_assets = self._load_visual_assets()
        self.overlay_surface = pygame.Surface(settings.WINDOW_SIZE, pygame.SRCALPHA)
        self.darkness_surface = pygame.Surface(settings.WINDOW_SIZE, pygame.SRCALPHA)
        self.local_glow_surface = build_local_glow_surface(settings.LOCAL_VISIBILITY_RADIUS)
        self.scan_system = ScanSystem()
        self.threat_events = ThreatEventSystem()
        self.scan_renderer = ScanRenderer(settings.WINDOW_SIZE)
        self.snapshot_system = EchoSnapshotSystem()
        self.snapshot_renderer = EchoSnapshotRenderer()
        self.performance_overlay = False
        self.last_frame_dt = 0.0
        self.floor_generator = FloorGenerator()
        self.world_renderer = StaticWorldRenderer(self.assets, settings.TILE_SIZE)
        self.debug_world_view = False
        self.floor_power_available = True
        self.player: Player | None = None
        self.camera: Camera | None = None
        self.doors: list[DynamicDoor] = []
        self.floor_content: FloorContent | None = None
        self.floor_objectives: Floor1ObjectiveSystem | Floor2ObjectiveSystem | Floor3ObjectiveSystem | None = None
        self.material_pickups: list[MaterialPickup] = []
        self.elevator_entity: ElevatorEntity | None = None
        self.creatures: list[Creature] = []
        self.creatures_rng: random.Random | None = None
        self.death_creature_id: str | None = None
        self.death_world_position: pygame.Vector2 | None = None
        self.dynamic_blockers = DynamicBlockerRegistry([], settings.TILE_SIZE)
        self.floor_world_surface: pygame.Surface | None = None
        self.floor_preview_surface: pygame.Surface | None = None
        self.floor_preview_rect = pygame.Rect(0, 0, 0, 0)
        self.generation_error: str | None = None
        self.last_completed_floor: int | None = None
        self.workshop_system = WorkshopSystem()
        self.workshop_notice = self.workshop_system.notice

        self.running = True
        self._shutdown_complete = False
        self.state = GameState.SPLASH
        self.previous_state = GameState.SPLASH

        self.splash_elapsed = 0.0
        self.floor_transition_elapsed = 0.0
        self.next_seed = 1000
        self.run_exists = False
        self.placeholder_run: PlaceholderRun | None = None

        self.buttons = self._build_buttons()
        self.selected_indices = {state: 0 for state in self.buttons}

    def _init_audio(self) -> bool:
        try:
            pygame.mixer.init()
        except pygame.error:
            return False
        return True

    def _load_fonts(self) -> dict[str, pygame.font.Font]:
        return {
            "title": pygame.font.SysFont("consolas", settings.FONT_TITLE_SIZE, bold=True),
            "subtitle": pygame.font.SysFont("consolas", settings.FONT_SUBTITLE_SIZE),
            "body": pygame.font.SysFont("consolas", settings.FONT_BODY_SIZE),
            "small": pygame.font.SysFont("consolas", settings.FONT_SMALL_SIZE),
            "button": pygame.font.SysFont("consolas", settings.FONT_BUTTON_SIZE, bold=True),
        }

    def _build_buttons(self) -> dict[GameState, list[Button]]:
        center_x = settings.WINDOW_WIDTH // 2
        return {
            GameState.MAIN_MENU: [
                Button.centered("New Run", "new_run", (center_x, 330)),
                Button.centered("How to Play", "how_to_play", (center_x, 400)),
                Button.centered("Quit", "quit", (center_x, 470)),
            ],
            GameState.HOW_TO_PLAY: [
                Button.centered("Back", "main_menu", (center_x, 645), (220, settings.BUTTON_HEIGHT)),
            ],
            GameState.PAUSED: [
                Button.centered("Resume", "resume", (center_x, 330)),
                Button.centered("Restart Run", "restart_run", (center_x, 400)),
                Button.centered("Main Menu", "main_menu", (center_x, 470)),
            ],
            GameState.DEATH: [
                Button.centered("New Run", "new_run", (center_x, 420)),
                Button.centered("Retry Same Seed", "retry_seed", (center_x, 490)),
                Button.centered("Main Menu", "main_menu", (center_x, 560)),
            ],
            GameState.VICTORY: [
                Button.centered("New Run", "new_run", (center_x, 460)),
                Button.centered("Main Menu", "main_menu", (center_x, 530)),
            ],
        }

    def _load_visual_assets(self) -> dict[str, object]:
        visuals: dict[str, object] = {
            "tiles": self.assets.get_sheet_frames("industrial_tiles"),
            "player_idle": self.assets.get_frames("player", "idle_down")[0],
            "player_outline": self.assets.get_outline_frames("player", "idle_down")[0],
            "creature": self.assets.get_frames("creature", "move")[0],
            "creature_outline": self.assets.get_outline_frames("creature", "move")[0],
            "echo_core": self.assets.get_frames("echo_core", "pulse")[1],
            "elevator": self.assets.get_frames("elevator", "unlocked")[0],
            "module_icons": {
                name: self.assets.load_image(path, (48, 48)) for name, path in MODULE_ICON_PATHS.items()
            },
            "effect_icons": {
                name: self.assets.load_image(path, (64, 64)) for name, path in EFFECT_IMAGE_PATHS.items()
            },
        }

        outline_sheet_names = [
            "player",
            "creature",
            "materials",
            "powered_door",
            "security_door",
            "containment_door",
            "generator_component",
            "generator",
            "keycard",
            "relay",
            "containment_component",
            "containment_control",
            "echo_core",
            "elevator",
        ]
        for sheet_name in outline_sheet_names:
            self.assets.get_outline_frames(sheet_name)

        for icon_path in MODULE_ICON_PATHS.values():
            self.assets.get_outline_image(icon_path, (48, 48))
        self.assets.get_flipped_frames("creature", "move")
        return visuals

    def run(self) -> None:
        try:
            while self.running:
                self.run_one_frame()
        finally:
            self.shutdown()

    def run_one_frame(self, dt: float | None = None) -> float:
        if dt is None:
            dt = self.clock.tick(settings.FPS) / 1000.0
        dt = min(dt, settings.MAX_DELTA_TIME)
        self.last_frame_dt = dt

        for event in pygame.event.get():
            self.handle_event(event)

        self.update(dt)
        self.render()
        pygame.display.flip()
        return dt

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.request_quit()
            return

        if event.type == pygame.KEYDOWN:
            self.handle_keydown(event.key)
        elif event.type == pygame.MOUSEMOTION:
            self.handle_mouse_motion(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            self.handle_mouse_button(event)

    def handle_keydown(self, key: int) -> None:
        if key == pygame.K_F2:
            self.debug_world_view = not self.debug_world_view
            return
        if key == pygame.K_F3:
            self.performance_overlay = not self.performance_overlay
            return

        if self.state == GameState.PLAYING and self.debug_world_view:
            if key == pygame.K_F6:
                self.debug_toggle_nearest_door()
                return
            if key == pygame.K_F7:
                self.debug_toggle_nearest_security_door()
                return
            if key == pygame.K_F8:
                self.floor_power_available = not self.floor_power_available
                for door in self.doors:
                    door.set_powered(self.floor_power_available)
                return

        if self.state == GameState.SPLASH:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_ESCAPE):
                self.transition_to(GameState.MAIN_MENU)
            return

        if self.state == GameState.FLOOR_TRANSITION:
            if key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.transition_to(GameState.PLAYING)
            return

        if self.state == GameState.PLAYING:
            if key == pygame.K_SPACE:
                self.trigger_scan()
            elif key == pygame.K_ESCAPE:
                self.transition_to(GameState.PAUSED)
            return

        if self.state == GameState.WORKSHOP:
            if key in (pygame.K_UP, pygame.K_w):
                self.workshop_system.move_selection(-1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.workshop_system.move_selection(1)
            elif key in (pygame.K_LEFT, pygame.K_a):
                self.workshop_system.change_target_slot(-1)
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.workshop_system.change_target_slot(1)
            elif key == pygame.K_q:
                self.workshop_system.select_slot(0)
            elif key == pygame.K_e:
                self.workshop_system.select_slot(1)
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.activate_workshop_selection()
            return

        if self.state == GameState.HOW_TO_PLAY:
            if key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                self.transition_to(GameState.MAIN_MENU)
                return

        if self.state == GameState.PAUSED and key == pygame.K_ESCAPE:
            self.transition_to(GameState.PLAYING)
            return

        if key in (pygame.K_UP, pygame.K_w):
            self.move_selection(-1)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.move_selection(1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.activate_selected_button()

    def handle_mouse_motion(self, pos: tuple[int, int]) -> None:
        group = self.buttons.get(self.state, [])
        for index, button in enumerate(group):
            if button.update_hover(pos):
                self.selected_indices[self.state] = index

    def handle_mouse_button(self, event: pygame.event.Event) -> None:
        group = self.buttons.get(self.state, [])
        for index, button in enumerate(group):
            if button.was_clicked(event):
                self.selected_indices[self.state] = index
                self.perform_action(button.action)
                return

    def move_selection(self, direction: int) -> None:
        group = self.buttons.get(self.state)
        if not group:
            return
        self.selected_indices[self.state] = (self.selected_indices[self.state] + direction) % len(group)

    def activate_selected_button(self) -> None:
        group = self.buttons.get(self.state)
        if not group:
            return
        index = self.selected_indices[self.state]
        self.perform_action(group[index].action)

    def perform_action(self, action: str) -> None:
        if action == "new_run":
            self.start_new_run()
        elif action == "how_to_play":
            self.transition_to(GameState.HOW_TO_PLAY)
        elif action == "quit":
            self.request_quit()
        elif action == "resume":
            self.transition_to(GameState.PLAYING)
        elif action == "restart_run":
            self.restart_placeholder_run()
        elif action == "main_menu":
            self.end_placeholder_run()
            self.transition_to(GameState.MAIN_MENU)
        elif action == "continue_floor":
            if self.state is GameState.WORKSHOP:
                if self.placeholder_run is not None and self.last_completed_floor == 1:
                    self.placeholder_run.floor = 2
                    self.placeholder_run.generated_floor = None
                    self.floor_world_surface = None
                    self.floor_preview_surface = None
                    self.transition_to(GameState.FLOOR_TRANSITION)
                    return
                if self.placeholder_run is not None and self.last_completed_floor == 2:
                    self.placeholder_run.floor = 3
                    self.placeholder_run.generated_floor = None
                    self.floor_world_surface = None
                    self.floor_preview_surface = None
                    self.transition_to(GameState.FLOOR_TRANSITION)
                    return
                self.workshop_notice = "Workshop online"
                return
            if self.placeholder_run is not None:
                self.placeholder_run.floor += 1
                self.placeholder_run.generated_floor = None
                self.player = None
                self.camera = None
                self.doors = []
                self.dynamic_blockers.replace_doors([])
                self.floor_content = None
                self.floor_objectives = None
                self.material_pickups = []
                self.elevator_entity = None
                self.creatures = []
                self.creatures_rng = None
                self.snapshot_system.reset()
                self.floor_world_surface = None
                self.floor_preview_surface = None
                self.scan_system.reset()
                self.threat_events.reset()
            self.transition_to(GameState.FLOOR_TRANSITION)
        elif action == "retry_seed":
            self.retry_same_seed()

    def activate_workshop_selection(self) -> None:
        if self.state is not GameState.WORKSHOP or self.placeholder_run is None:
            return
        activation = self.workshop_system.activate(
            self.placeholder_run.module_loadout,
            self.placeholder_run.material_counts,
        )
        self.workshop_notice = activation.message or self.workshop_system.notice
        if activation.action is WorkshopAction.CONTINUE:
            self.perform_action("continue_floor")
        elif activation.action is WorkshopAction.MAIN_MENU:
            self.perform_action("main_menu")

    def update(self, dt: float) -> None:
        if self.state == GameState.SPLASH:
            self.splash_elapsed += dt
            if self.splash_elapsed >= settings.SPLASH_DURATION:
                self.transition_to(GameState.MAIN_MENU)
        elif self.state == GameState.FLOOR_TRANSITION:
            self.floor_transition_elapsed += dt
            if self.floor_transition_elapsed >= settings.FLOOR_TRANSITION_DURATION:
                self.transition_to(GameState.PLAYING)
        elif self.state == GameState.PLAYING and self.placeholder_run is not None:
            self.placeholder_run.elapsed_time += dt
            self.update_gameplay(dt)

    def update_gameplay(
        self,
        dt: float,
        movement_direction: pygame.Vector2 | tuple[float, float] | None = None,
        interact_held: bool | None = None,
    ) -> None:
        if (
            self.state is not GameState.PLAYING
            or self.placeholder_run is None
            or self.placeholder_run.generated_floor is None
            or self.player is None
            or self.camera is None
        ):
            return

        if self._player_touches_creature():
            self._enter_death_state()
            return

        keys = None
        if movement_direction is None or interact_held is None:
            keys = pygame.key.get_pressed()
        if movement_direction is None:
            movement_direction = movement_direction_from_bools(
                keys[pygame.K_w] or keys[pygame.K_UP],
                keys[pygame.K_s] or keys[pygame.K_DOWN],
                keys[pygame.K_a] or keys[pygame.K_LEFT],
                keys[pygame.K_d] or keys[pygame.K_RIGHT],
            )
        if interact_held is None:
            interact_held = bool(keys[pygame.K_f])
        direction = pygame.Vector2(movement_direction)
        if direction.length_squared() > 1:
            direction = direction.normalize()

        self.player.update(direction, dt, self.placeholder_run.generated_floor, self.dynamic_blockers)
        if self._player_touches_creature():
            self._enter_death_state()
            return

        creature_rects = [creature.collision_rect for creature in self.creatures]
        for door in self.doors:
            door.update(
                dt,
                self.player.collision_rect,
                other_entity_rects=creature_rects,
                floor_powered=self.floor_power_available,
            )
        if self.floor_content is not None:
            self.floor_content.update(dt)

        self.threat_events.update(dt)
        for creature in self.creatures:
            creature.update(
                dt,
                self.placeholder_run.generated_floor,
                self.dynamic_blockers,
                player=self.player,
                threat_events=self.threat_events,
                session_time=self.placeholder_run.elapsed_time,
            )
        if self._player_touches_creature():
            self._enter_death_state()
            return

        creature_rects = [creature.collision_rect for creature in self.creatures]
        for door in self.doors:
            door.update(
                0.0,
                self.player.collision_rect,
                other_entity_rects=creature_rects,
                floor_powered=self.floor_power_available,
            )

        self.camera.update(self.player.world_position, dt)
        self.scan_system.update(dt)
        self.snapshot_system.update(
            dt,
            self.scan_system.last_wave_step,
            self.scan_detectable_entities(),
            self.placeholder_run.generated_floor,
            self.dynamic_blockers,
            settings.TILE_SIZE,
        )
        if self.floor_objectives is not None:
            objective_result = self.floor_objectives.update(
                dt,
                self.player.collision_rect,
                interact_held=interact_held,
                session_time=self.placeholder_run.elapsed_time,
                threat_events=self.threat_events,
                elevator=self.elevator_entity,
            )
            if objective_result.score_delta:
                self.placeholder_run.score += objective_result.score_delta
            if objective_result.power_changed:
                self.floor_power_available = True
                for door in self.doors:
                    door.set_powered(True)
            if objective_result.extraction_started:
                self._start_extraction_phase()
            if objective_result.floor_completed:
                if self.placeholder_run.floor == 3:
                    self.complete_floor_three()
                elif self.placeholder_run.floor == 2:
                    self.complete_floor_two()
                else:
                    self.complete_floor_one()
                return
        self.collect_material_pickups()

    def _player_touches_creature(self) -> Creature | None:
        if self.player is None:
            return None
        return next(
            (
                creature
                for creature in self.creatures
                if self.player.collision_rect.colliderect(creature.collision_rect)
            ),
            None,
        )

    def _enter_death_state(self) -> None:
        creature = self._player_touches_creature()
        self.death_creature_id = creature.unique_id if creature is not None else None
        self.death_world_position = (
            creature.world_position.copy() if creature is not None else None
        )
        if self.floor_objectives is not None:
            self.floor_objectives.clear_interaction()
            self.floor_objectives.reset_messages()
        self.transition_to(GameState.DEATH)

    def scan_detectable_entities(self) -> list[object]:
        entities: list[object] = []
        if self.floor_content is not None:
            entities.extend(self.floor_content.scan_entities)
        if self.floor_objectives is not None:
            entities.extend(self.floor_objectives.scan_entities)
        entities.extend(self.creatures)
        return entities

    def collect_material_pickups(self) -> None:
        if self.player is None or self.placeholder_run is None:
            return
        for pickup in self.material_pickups:
            if not pickup.scan_active or not pickup.collision_rect.colliderect(self.player.collision_rect):
                continue
            if not pickup.collect():
                continue
            material_name = pickup.material_type.value
            self.placeholder_run.material_counts[material_name] = (
                self.placeholder_run.material_counts.get(material_name, 0) + 1
            )
            self.placeholder_run.materials_collected += 1
            self.placeholder_run.score += pickup.score_value

    def trigger_scan(self) -> bool:
        if (
            self.state is not GameState.PLAYING
            or self.placeholder_run is None
            or self.placeholder_run.generated_floor is None
            or self.player is None
        ):
            return False
        triggered = self.scan_system.trigger(
            self.player.world_position,
            self.placeholder_run.generated_floor,
            self.dynamic_blockers,
            settings.TILE_SIZE,
            session_time=self.placeholder_run.elapsed_time,
        )
        if triggered and self.scan_system.active_wave is not None:
            self.threat_events.add_player_scan(
                self.scan_system.active_wave.origin,
                creation_time=self.placeholder_run.elapsed_time,
                floor_number=self.placeholder_run.floor,
                scan_id=self.scan_system.active_wave.scan_id,
            )
        return triggered

    def transition_to(self, new_state: GameState) -> None:
        self.previous_state = self.state
        self.state = new_state

        if new_state in self.selected_indices:
            self.selected_indices[new_state] = 0
        if new_state == GameState.SPLASH:
            self.splash_elapsed = 0.0
        elif new_state == GameState.FLOOR_TRANSITION:
            self.floor_transition_elapsed = 0.0
        elif new_state == GameState.WORKSHOP:
            self.workshop_system.open(self.last_completed_floor)
            self.workshop_notice = self.workshop_system.notice
        elif new_state == GameState.PLAYING and self.placeholder_run is not None:
            if self.placeholder_run.generated_floor is None or self.player is None or self.camera is None:
                self.prepare_generated_floor()

    def start_new_run(self) -> None:
        self.death_creature_id = None
        self.death_world_position = None
        self.last_completed_floor = None
        self.workshop_notice = "Workshop online"
        self.next_seed += 1
        self.placeholder_run = PlaceholderRun(seed=self.next_seed)
        self.run_exists = True
        self.prepare_generated_floor()
        self.transition_to(GameState.PLAYING)

    def restart_placeholder_run(self) -> None:
        self.death_creature_id = None
        self.death_world_position = None
        self.last_completed_floor = None
        self.workshop_notice = "Workshop online"
        if self.placeholder_run is None:
            self.placeholder_run = PlaceholderRun(seed=self.next_seed)
        else:
            self.placeholder_run = self.placeholder_run.reset_same_seed()
        self.run_exists = True
        self.prepare_generated_floor()
        self.transition_to(GameState.PLAYING)

    def retry_same_seed(self) -> None:
        self.restart_placeholder_run()

    def end_placeholder_run(self) -> None:
        self.run_exists = False
        self.placeholder_run = None
        self.player = None
        self.camera = None
        self.doors = []
        self.dynamic_blockers.replace_doors([])
        self.floor_content = None
        self.floor_objectives = None
        self.material_pickups = []
        self.elevator_entity = None
        self.creatures = []
        self.creatures_rng = None
        self.death_creature_id = None
        self.death_world_position = None
        self.floor_power_available = True
        self.floor_world_surface = None
        self.floor_preview_surface = None
        self.floor_preview_rect = pygame.Rect(0, 0, 0, 0)
        self.generation_error = None
        self.last_completed_floor = None
        self.workshop_notice = "Workshop online"
        self.scan_system.reset()
        self.threat_events.reset()
        self.snapshot_system.reset()
        self.world_renderer.clear()

    def request_quit(self) -> None:
        self.running = False

    def prepare_generated_floor(self) -> None:
        self.scan_system.reset()
        self.threat_events.reset()
        self.snapshot_system.reset()
        self.floor_objectives = None
        if self.placeholder_run is None:
            return
        try:
            generated_floor = self.floor_generator.generate(
                seed=self.placeholder_run.seed,
                floor_number=self.placeholder_run.floor,
            )
        except GenerationError as exc:
            self.generation_error = str(exc)
            self.placeholder_run.generated_floor = None
            self.player = None
            self.camera = None
            self.doors = []
            self.dynamic_blockers.replace_doors([])
            self.floor_content = None
            self.floor_objectives = None
            self.material_pickups = []
            self.elevator_entity = None
            self.creatures = []
            self.creatures_rng = None
            self.floor_world_surface = None
            self.floor_preview_surface = None
            self.threat_events.reset()
            return

        self.generation_error = None
        self.floor_power_available = generated_floor.floor_number != 1
        self.placeholder_run.generated_floor = generated_floor
        self.floor_world_surface = self.world_renderer.build_for_floor(generated_floor)
        self.floor_preview_surface = None
        self.floor_preview_rect = pygame.Rect(0, 0, 0, 0)
        self.player = Player(generated_floor.player_spawn, self.assets, settings.TILE_SIZE)
        self.camera = Camera(settings.WINDOW_SIZE, generated_floor.world_size_pixels(settings.TILE_SIZE))
        self.camera.update(self.player.world_position)
        door_result = create_doors_for_floor(
            generated_floor,
            self.assets,
            settings.TILE_SIZE,
            floor_powered=self.floor_power_available,
        )
        self.doors = door_result.doors
        self.dynamic_blockers = door_result.blockers
        self.floor_content = create_floor_content(generated_floor, self.assets, settings.TILE_SIZE)
        self.material_pickups = self.floor_content.materials
        self.elevator_entity = self.floor_content.elevator
        if generated_floor.floor_number == 1:
            objective_reserved = {pickup.tile for pickup in self.material_pickups}
            objective_reserved.update(door.tile for door in self.doors)
            objective_reserved.update(generated_floor.candidate_creature_spawns)
            self.floor_objectives = Floor1ObjectiveSystem.create_for_floor(
                generated_floor,
                self.assets,
                settings.TILE_SIZE,
                self.dynamic_blockers,
                reserved_tiles=objective_reserved,
            )
        elif generated_floor.floor_number == 2:
            objective_reserved = {pickup.tile for pickup in self.material_pickups}
            objective_reserved.update(door.tile for door in self.doors)
            objective_reserved.update(generated_floor.candidate_creature_spawns)
            self.floor_objectives = Floor2ObjectiveSystem.create_for_floor(
                generated_floor,
                self.assets,
                settings.TILE_SIZE,
                self.doors,
                reserved_tiles=objective_reserved,
            )
        elif generated_floor.floor_number == 3:
            objective_reserved = {pickup.tile for pickup in self.material_pickups}
            objective_reserved.update(door.tile for door in self.doors)
            objective_reserved.update(generated_floor.candidate_creature_spawns)
            self.floor_objectives = Floor3ObjectiveSystem.create_for_floor(
                generated_floor,
                self.assets,
                settings.TILE_SIZE,
                self.doors,
                reserved_tiles=objective_reserved,
            )
        else:
            self.floor_objectives = None
        
        # Create deterministic creatures from validated spawn candidates.
        reserved_tiles = {generated_floor.player_spawn, generated_floor.elevator_tile}
        reserved_tiles.update(pickup.tile for pickup in self.material_pickups)
        reserved_tiles.update(door.tile for door in self.doors)
        if self.floor_objectives is not None:
            for entity in self.floor_objectives.active_entities:
                tile = getattr(entity, "tile", None)
                if tile is not None:
                    reserved_tiles.add(tile)
        valid_spawns = [
            tile
            for tile in generated_floor.candidate_creature_spawns
            if tile not in reserved_tiles
        ]
        desired_count = 1 if generated_floor.floor_number == 1 else 2
        self.creatures = []
        for index, spawn_tile in enumerate(valid_spawns[:desired_count]):
            creature_seed = (
                generated_floor.attempt_seed
                + generated_floor.floor_number * 1_000_003
                + index * 97_409
            )
            creature_rng = random.Random(creature_seed)
            creature = Creature(
                f"f{generated_floor.floor_number}-a{generated_floor.generation_attempt}-creature-{index:02d}",
                spawn_tile,
                self.assets,
                settings.TILE_SIZE,
                creature_rng,
            )
            ai_seed = creature_seed + 51_337
            creature.ai = CreatureAI(
                creature,
                random.Random(ai_seed),
                floor_number=generated_floor.floor_number,
                creature_index=index,
            )
            self.creatures.append(creature)
        self.creatures_rng = random.Random(generated_floor.attempt_seed)

        self.scan_system.reset()
        self.threat_events.reset()
        self.snapshot_system.reset()

    def complete_floor_one(self) -> None:
        if self.placeholder_run is None:
            return
        self.last_completed_floor = 1
        self.placeholder_run.completed_floor_count = max(self.placeholder_run.completed_floor_count, 1)
        self.placeholder_run.floor_completion_summaries[1] = {
            "floor": 1,
            "power_restored": True,
            "score": self.placeholder_run.score,
            "materials": dict(self.placeholder_run.material_counts),
            "elapsed_time": self.placeholder_run.elapsed_time,
            "modules": self.placeholder_run.module_loadout.snapshot(),
        }
        self.workshop_notice = "Workshop online"
        self._clear_floor_runtime()
        self.transition_to(GameState.WORKSHOP)

    def complete_floor_two(self) -> None:
        if self.placeholder_run is None:
            return
        summary = {
            "floor": 2,
            "keycard_recovered": True,
            "relay_a_active": True,
            "relay_b_active": True,
            "security_override_completed": True,
            "score": self.placeholder_run.score,
            "materials": dict(self.placeholder_run.material_counts),
            "elapsed_time": self.placeholder_run.elapsed_time,
            "modules": self.placeholder_run.module_loadout.snapshot(),
        }
        self.last_completed_floor = 2
        self.placeholder_run.completed_floor_count = max(self.placeholder_run.completed_floor_count, 2)
        self.placeholder_run.floor_completion_summaries[2] = summary
        self.workshop_notice = "Workshop online"
        self._clear_floor_runtime()
        self.transition_to(GameState.WORKSHOP)


    def complete_floor_three(self) -> None:
        if self.placeholder_run is None:
            return
        summary = {
            "floor": 3,
            "containment_component_recovered": True,
            "containment_control_active": True,
            "echo_core_recovered": True,
            "extraction_completed": True,
            "score": self.placeholder_run.score,
            "materials": dict(self.placeholder_run.material_counts),
            "elapsed_time": self.placeholder_run.elapsed_time,
            "modules": self.placeholder_run.module_loadout.snapshot(),
        }
        self.last_completed_floor = 3
        self.placeholder_run.completed_floor_count = max(self.placeholder_run.completed_floor_count, 3)
        self.placeholder_run.floor_completion_summaries[3] = summary
        self._clear_floor_runtime()
        self.transition_to(GameState.VICTORY)

    def _start_extraction_phase(self) -> None:
        if self.placeholder_run is None or self.placeholder_run.generated_floor is None:
            return
        if not isinstance(self.floor_objectives, Floor3ObjectiveSystem):
            return
        if self.floor_objectives.state.extraction_creature_spawned:
            return
        for creature in self.creatures:
            creature.speed *= settings.EXTRACTION_CREATURE_SPEED_MULTIPLIER

        floor = self.placeholder_run.generated_floor
        occupied = {creature.spawn_tile for creature in self.creatures}
        reserved = {floor.player_spawn, floor.elevator_tile}
        reserved.update(pickup.tile for pickup in self.material_pickups)
        reserved.update(door.tile for door in self.doors)
        reserved.update(
            getattr(entity, "tile", (-1, -1))
            for entity in self.floor_objectives.active_entities
        )
        spawn_tile = next(
            (tile for tile in floor.candidate_creature_spawns if tile not in occupied and tile not in reserved),
            None,
        )
        if spawn_tile is not None:
            index = len(self.creatures)
            creature_seed = floor.attempt_seed + floor.floor_number * 1_000_003 + index * 97_409
            creature = Creature(
                f"f3-a{floor.generation_attempt}-creature-{index:02d}",
                spawn_tile,
                self.assets,
                settings.TILE_SIZE,
                random.Random(creature_seed),
                speed=settings.CREATURE_SPEED * settings.EXTRACTION_CREATURE_SPEED_MULTIPLIER,
            )
            creature.ai = CreatureAI(
                creature,
                random.Random(creature_seed + 51_337),
                floor_number=3,
                creature_index=index,
            )
            self.creatures.append(creature)
        self.floor_objectives.mark_extraction_creature_spawned()

    def _clear_floor_runtime(self) -> None:
        self.player = None
        self.camera = None
        self.doors = []
        self.dynamic_blockers.replace_doors([])
        self.floor_content = None
        self.floor_objectives = None
        self.material_pickups = []
        self.elevator_entity = None
        self.creatures = []
        self.creatures_rng = None
        self.floor_power_available = False
        self.placeholder_run.generated_floor = None
        self.floor_world_surface = None
        self.floor_preview_surface = None
        self.floor_preview_rect = pygame.Rect(0, 0, 0, 0)
        self.scan_system.reset()
        self.threat_events.reset()
        self.snapshot_system.reset()
        self.world_renderer.clear()

    def nearest_door(self, door_type: DoorType | None = None) -> DynamicDoor | None:
        if self.player is None:
            return None
        candidates = [door for door in self.doors if door_type is None or door.door_type is door_type]
        if not candidates:
            return None
        return min(candidates, key=lambda door: door.world_center.distance_squared_to(self.player.world_position))

    def debug_toggle_nearest_door(self) -> None:
        door = self.nearest_door()
        if door is not None:
            door.debug_toggle_open_closed()

    def debug_toggle_nearest_security_door(self) -> None:
        door = self.nearest_door(DoorType.SECURITY)
        if door is None:
            door = self.nearest_door(DoorType.CONTAINMENT)
        if door is None:
            return
        if door.is_locked:
            door.unlock()
        else:
            door.lock()

    def shutdown(self) -> None:
        if self._shutdown_complete:
            return
        self.running = False
        pygame.quit()
        self._shutdown_complete = True

    def render(self) -> None:
        if self.state == GameState.SPLASH:
            self.render_splash()
        elif self.state == GameState.MAIN_MENU:
            self.render_main_menu()
        elif self.state == GameState.HOW_TO_PLAY:
            self.render_how_to_play()
        elif self.state == GameState.PLAYING:
            self.render_playing()
        elif self.state == GameState.PAUSED:
            self.render_paused()
        elif self.state == GameState.WORKSHOP:
            self.render_workshop()
        elif self.state == GameState.FLOOR_TRANSITION:
            self.render_floor_transition()
        elif self.state == GameState.DEATH:
            self.render_death()
        elif self.state == GameState.VICTORY:
            self.render_victory()

    def render_splash(self) -> None:
        self.draw_background()
        core = self.visual_assets["echo_core"]
        assert isinstance(core, pygame.Surface)
        core_rect = core.get_rect(center=(settings.WINDOW_WIDTH // 2, 215))
        self.screen.blit(core, core_rect)
        self.draw_centered_text("Echoes Below", "title", settings.COLOR_TEXT, 300)
        self.draw_centered_text("A descent into the unseen", "subtitle", settings.COLOR_ACCENT, 378)
        self.draw_centered_text("Press Enter, Space or Escape to skip", "small", settings.COLOR_TEXT_MUTED, 620)

    def render_main_menu(self) -> None:
        self.draw_background()
        module_icons = self.visual_assets["module_icons"]
        assert isinstance(module_icons, dict)
        core = self.visual_assets["echo_core"]
        assert isinstance(core, pygame.Surface)
        self.screen.blit(core, core.get_rect(center=(settings.WINDOW_WIDTH // 2, 112)))
        for index, icon_name in enumerate(("shock_pulse_ready", "decoy_beacon_ready", "door_wedge_ready", "scan_projector_ready")):
            icon = module_icons[icon_name]
            assert isinstance(icon, pygame.Surface)
            self.screen.blit(icon, (460 + index * 72, 545))
        self.draw_centered_text("Echoes Below", "title", settings.COLOR_TEXT, 170)
        self.draw_centered_text("A descent into the unseen", "body", settings.COLOR_ACCENT, 230)
        self.draw_button_group(GameState.MAIN_MENU)

    def render_how_to_play(self) -> None:
        self.draw_background()
        self.draw_centered_text("How to Play", "subtitle", settings.COLOR_TEXT, 70)

        lines = [
            "WASD or arrow keys: move",
            "Space: scan",
            "F: interact",
            "Q: module slot 1",
            "E: module slot 2",
            "Escape: pause",
            "F2: debug view",
            "F3: performance overlay",
            "",
            "The environment is hidden in darkness.",
            "The scan reveals only reachable surfaces.",
            "Walls and closed doors block the scan.",
            "Creature images are fading snapshots of previous detected positions.",
            "Touching a creature ends the run.",
            "Complete the floor objective and reach the elevator.",
            "Modules are crafted between floors.",
            "",
            "Escape or Backspace returns to the main menu.",
        ]
        module_icons = self.visual_assets["module_icons"]
        assert isinstance(module_icons, dict)
        icon_names = ["floor", "scan_ready", "score", "shock_pulse_ready", "decoy_beacon_ready", "door_wedge_ready", "scan_projector_ready"]
        for index, icon_name in enumerate(icon_names):
            icon = module_icons[icon_name]
            assert isinstance(icon, pygame.Surface)
            self.screen.blit(icon, (880, 130 + index * 58))
        self.draw_text_lines(lines, 160, 118, line_height=29)
        self.draw_button_group(GameState.HOW_TO_PLAY)

    def render_playing(self) -> None:
        if (
            self.placeholder_run is None
            or self.placeholder_run.generated_floor is None
            or self.player is None
            or self.camera is None
        ):
            self.draw_background()
            self.render_generated_floor_preview()
            if self.generation_error is None:
                self.draw_centered_text("Preparing playable floor...", "subtitle", settings.COLOR_TEXT, 50)
            return

        generated_floor = self.placeholder_run.generated_floor
        self.world_renderer.render_view(self.screen, generated_floor, self.camera)
        draw_doors(self.screen, self.doors, self.camera)
        if self.debug_world_view and self.floor_content is not None:
            draw_floor_content_debug(self.screen, self.floor_content, self.camera, self.fonts["small"])
        if self.debug_world_view and self.floor_objectives is not None:
            self.draw_floor1_objective_debug()

        player_screen_rect = self.camera.world_rect_to_screen(self.player.visual_rect)
        if not self.debug_world_view:
            apply_darkness(
                self.screen,
                self.darkness_surface,
                self.local_glow_surface,
                player_screen_rect.center,
            )
            self.scan_renderer.render(self.screen, self.scan_system, self.camera)
            self.snapshot_renderer.render(self.screen, self.snapshot_system.snapshots, self.camera)
            draw_material_contact_hints(
                self.screen,
                self.material_pickups,
                self.player.world_position,
                self.camera,
            )
            self.draw_objective_contact_hints()
            self.screen.blit(self.player.image, player_screen_rect)
        else:
            self.scan_renderer.render(self.screen, self.scan_system, self.camera)
            self.snapshot_renderer.render(self.screen, self.snapshot_system.snapshots, self.camera)
            self.screen.blit(self.player.image, player_screen_rect)
            
            # Real creatures are visible only in F2 debug mode.
            active_scan_id = self.scan_system.active_wave.scan_id if self.scan_system.active_wave else None
            processed_ids = (
                self.snapshot_system.processed_ids_for_scan(active_scan_id)
                if active_scan_id is not None
                else frozenset()
            )
            for creature in self.creatures:
                creature_screen_rect = self.camera.world_rect_to_screen(creature.visual_rect)
                self.screen.blit(creature.image, creature_screen_rect)
                pygame.draw.rect(
                    self.screen,
                    (255, 0, 255),
                    self.camera.world_rect_to_screen(creature.collision_rect),
                    1,
                )
                ai = creature.ai
                path_tiles = ai.current_path if ai is not None else creature.current_path
                for tile in path_tiles[:60]:
                    tile_rect = pygame.Rect(
                        tile[0] * settings.TILE_SIZE + settings.TILE_SIZE // 3,
                        tile[1] * settings.TILE_SIZE + settings.TILE_SIZE // 3,
                        settings.TILE_SIZE // 3,
                        settings.TILE_SIZE // 3,
                    )
                    pygame.draw.rect(
                        self.screen,
                        (255, 170, 40),
                        self.camera.world_rect_to_screen(tile_rect),
                        1,
                    )
                if ai is not None and ai.current_target_tile is not None:
                    target_world = pygame.Vector2(
                        (ai.current_target_tile[0] + 0.5) * settings.TILE_SIZE,
                        (ai.current_target_tile[1] + 0.5) * settings.TILE_SIZE,
                    )
                    pygame.draw.circle(
                        self.screen,
                        (255, 220, 80),
                        self.camera.world_to_screen(target_world),
                        6,
                        1,
                    )
                if ai is not None and ai.last_known_player_position is not None:
                    pygame.draw.circle(
                        self.screen,
                        (255, 80, 80),
                        self.camera.world_to_screen(ai.last_known_player_position),
                        8,
                        1,
                    )
                if creature.patrol_target is not None:
                    target_world = pygame.Vector2(
                        (creature.patrol_target[0] + 0.5) * settings.TILE_SIZE,
                        (creature.patrol_target[1] + 0.5) * settings.TILE_SIZE,
                    )
                    pygame.draw.line(
                        self.screen,
                        (255, 170, 40),
                        creature_screen_rect.center,
                        self.camera.world_to_screen(target_world),
                        1,
                    )
                if ai is None:
                    labels = [
                        f"{creature.unique_id} tile={creature.current_tile} target={creature.patrol_target}",
                    ]
                else:
                    labels = [
                        (
                            f"{creature.unique_id} {ai.state.name} prev={ai.previous_state.name} "
                            f"reason={ai.transition_reason}"
                        ),
                        (
                            f"tile={creature.current_tile} target={ai.current_target_tile} "
                            f"path={len(ai.current_path)} threat={ai.selected_threat_event_id}"
                        ),
                        (
                            f"patrol={ai.current_patrol_target} investigate={ai.investigation_target_tile} "
                            f"search={ai.search_centre_tile}"
                        ),
                        (
                            f"last_player={ai.last_known_player_tile} stun={ai.stun_timer:0.1f} "
                            f"LOS={ai.last_los_result} range={settings.CREATURE_DETECTION_DISTANCE / settings.TILE_SIZE:0.1f}t"
                        ),
                        f"processed={creature.unique_id in processed_ids}",
                    ]
                for line_index, text in enumerate(labels):
                    label = self.fonts["small"].render(text, True, (255, 170, 40))
                    self.screen.blit(label, (creature_screen_rect.left, creature_screen_rect.top - 18 - line_index * 18))
            
            draw_camera_debug_overlay(
                self.screen,
                generated_floor,
                self.camera,
                settings.TILE_SIZE,
                self.fonts["small"],
                self.player,
            )
            draw_door_debug_overlay(self.screen, self.doors, self.camera, self.fonts["small"])
            self.scan_renderer.render_debug(self.screen, self.scan_system, self.camera, font=self.fonts["small"])
            self.snapshot_renderer.render_debug(
                self.screen, self.snapshot_system.snapshots, self.camera, self.fonts["small"]
            )
            report = generated_floor.validation_report
            if report is not None:
                debug_lines = [
                    f"Attempt {generated_floor.generation_attempt} | Attempt seed {generated_floor.attempt_seed}",
                    f"Validation {'OK' if report.is_valid else 'FAILED'} | Cycle rank {report.graph_cycle_rank}",
                    f"Connectivity {report.connectivity_ratio:0.3f} | Doors {len(self.doors)} | Power {self.floor_power_available}",
                    f"Materials {len([p for p in self.material_pickups if p.scan_active])} | Creatures {len(self.creatures)} | Echo snapshots {len(self.snapshot_system.snapshots)}",
                    "F6 nearest door | F7 nearest locked door | F8 power",
                ]
                if self.floor_objectives is not None:
                    state = self.floor_objectives.state
                    placement = self.floor_objectives.placement
                    if state.floor_number == 1:
                        debug_lines.extend(
                            [
                                (
                                    f"Floor1 objective: {state.current_objective_text} | "
                                    f"components {state.components_collected}/2"
                                ),
                                (
                                    f"Rooms A:{placement.component_a_room_id} B:{placement.component_b_room_id} "
                                    f"G:{placement.generator_room_id} | target {state.interaction_target_id}"
                                ),
                                (
                                    f"Generator {self.floor_objectives.generator.state.name} "
                                    f"repair {state.generator_repair_progress:0.2f}/{settings.GENERATOR_REPAIR_DURATION:0.2f} "
                                    f"threat {state.generator_threat_event_id}"
                                ),
                                (
                                    f"Power {state.floor_power_active} | elevator unlocked {state.elevator_unlocked} "
                                    f"complete {state.floor_complete}"
                                ),
                            ]
                        )
                    elif state.floor_number == 2:
                        debug_lines.extend(
                            [
                                (
                                    f"Floor2 objective: {state.current_objective_text} | "
                                    f"keycard {state.keycard_collected} relays {state.relays_active_count}/2"
                                ),
                                (
                                    f"Gate {placement.security_gate_edge} | public {list(placement.public_side_room_ids)} "
                                    f"secure {list(placement.secure_side_room_ids)}"
                                ),
                                (
                                    f"Security {placement.security_door_id} {self.floor_objectives.security_door.state.name} "
                                    f"tile {placement.security_door_tile}"
                                ),
                                (
                                    f"Keycard r{placement.keycard_room_id} {placement.keycard_tile} | "
                                    f"Relay A r{placement.relay_a_room_id} {placement.relay_a_tile} | "
                                    f"Relay B r{placement.relay_b_room_id} {placement.relay_b_tile}"
                                ),
                                (
                                    f"Relay progress A {state.relay_a_progress:0.2f} B {state.relay_b_progress:0.2f} | "
                                    f"threats {state.relay_a_threat_event_id},{state.relay_b_threat_event_id}"
                                ),
                            ]
                        )
                    elif state.floor_number == 3:
                        debug_lines.extend(
                            [
                                (
                                    f"Floor3 objective: {state.current_objective_text} | "
                                    f"component {state.component_collected} control {state.control_active} core {state.echo_core_collected}"
                                ),
                                (
                                    f"Gate {placement.containment_gate_edge} | public {list(placement.public_side_room_ids)} "
                                    f"containment {list(placement.containment_side_room_ids)}"
                                ),
                                (
                                    f"Containment {placement.containment_door_id} "
                                    f"{self.floor_objectives.containment_door.state.name} tile {placement.containment_door_tile}"
                                ),
                                (
                                    f"Component r{placement.component_room_id} {placement.component_tile} | "
                                    f"Control r{placement.control_room_id} {placement.control_tile} | "
                                    f"Core r{placement.core_room_id} {placement.core_tile}"
                                ),
                                (
                                    f"Install {state.control_progress:0.2f}/{settings.CONTAINMENT_INSTALL_DURATION:0.2f} | "
                                    f"threats {state.containment_threat_event_id},{state.echo_core_threat_event_id} | "
                                    f"extraction {state.extraction_active}"
                                ),
                            ]
                        )
                self.draw_text_lines(debug_lines, 16, 112, 24)

        self.draw_gameplay_hud()
        if self.performance_overlay:
            self.draw_performance_overlay()

    def render_paused(self) -> None:
        self.render_playing()
        self.draw_overlay()
        self.draw_centered_text("Paused", "subtitle", settings.COLOR_TEXT, 240)
        self.draw_button_group(GameState.PAUSED)

    def render_workshop(self) -> None:
        self.draw_background()
        run = self.placeholder_run
        if run is None:
            self.draw_centered_text("Workshop unavailable", "subtitle", settings.COLOR_WARNING, 260)
            return

        loadout = run.module_loadout
        materials = run.material_counts
        if self.last_completed_floor == 2:
            title = "Floor 2 Complete"
            status = "Security override complete"
        else:
            title = "Floor 1 Complete"
            status = "Power restored"

        self.draw_centered_text(title, "subtitle", settings.COLOR_TEXT, 48)
        self.draw_centered_text(status, "small", settings.COLOR_ACCENT, 88)
        self.draw_centered_text(
            f"Score {run.score}   Materials  S:{materials.get('scrap', 0)} "
            f"C:{materials.get('circuit', 0)} P:{materials.get('power_cell', 0)}",
            "small",
            settings.COLOR_TEXT_MUTED,
            118,
        )

        module_icons = self.visual_assets["module_icons"]
        assert isinstance(module_icons, dict)
        card_width = 540
        card_height = 112
        positions = ((70, 150), (670, 150), (70, 280), (670, 280))
        small_font = self.fonts["small"]
        body_font = self.fonts["body"]
        for index, definition in enumerate(MODULE_DEFINITIONS):
            x, y = positions[index]
            selected = self.workshop_system.selected_index == index
            crafted = loadout.is_crafted(definition.module_type)
            affordable = loadout.can_afford(definition.module_type, materials)
            fill = settings.COLOR_PANEL_SELECTED if selected else settings.COLOR_PANEL
            border = settings.COLOR_ACCENT if selected else settings.COLOR_ACCENT_DIM
            rect = pygame.Rect(x, y, card_width, card_height)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, width=2 if selected else 1, border_radius=8)

            icon = module_icons[definition.icon_key]
            assert isinstance(icon, pygame.Surface)
            self.screen.blit(icon, icon.get_rect(center=(x + 55, y + 56)))
            name_image = body_font.render(definition.display_name, True, settings.COLOR_TEXT)
            self.screen.blit(name_image, (x + 102, y + 12))
            description = small_font.render(definition.description, True, settings.COLOR_TEXT_MUTED)
            self.screen.blit(description, (x + 102, y + 46))
            recipe_text = "  ".join(f"{name[0].upper()}:{amount}" for name, amount in definition.recipe.items())
            status_text = "CRAFTED" if crafted else ("AVAILABLE" if affordable else "MISSING MATERIALS")
            status_color = settings.COLOR_SUCCESS if crafted else (settings.COLOR_ACCENT if affordable else settings.COLOR_WARNING)
            recipe_image = small_font.render(f"Recipe {recipe_text}", True, settings.COLOR_TEXT_MUTED)
            status_image = small_font.render(status_text, True, status_color)
            self.screen.blit(recipe_image, (x + 102, y + 76))
            self.screen.blit(status_image, (x + 365, y + 76))
            equipped_slot = loadout.equipped_slot_for(definition.module_type)
            if equipped_slot is not None:
                badge = small_font.render(f"SLOT {equipped_slot + 1}", True, settings.COLOR_BACKGROUND)
                badge_rect = badge.get_rect()
                badge_rect.inflate_ip(14, 8)
                badge_rect.topright = (rect.right - 10, rect.top + 10)
                pygame.draw.rect(self.screen, settings.COLOR_SUCCESS, badge_rect, border_radius=5)
                self.screen.blit(badge, badge.get_rect(center=badge_rect.center))

        slot_y = 426
        self.draw_centered_text("Equipment slots", "small", settings.COLOR_TEXT_MUTED, slot_y - 20)
        for slot_index in range(2):
            x = 310 + slot_index * 350
            rect = pygame.Rect(x, slot_y, 310, 64)
            target = self.workshop_system.target_slot == slot_index
            pygame.draw.rect(
                self.screen,
                settings.COLOR_PANEL_SELECTED if target else settings.COLOR_PANEL,
                rect,
                border_radius=7,
            )
            pygame.draw.rect(
                self.screen,
                settings.COLOR_ACCENT if target else settings.COLOR_ACCENT_DIM,
                rect,
                width=2 if target else 1,
                border_radius=7,
            )
            value = loadout.equipped_slots[slot_index]
            module_name = MODULE_BY_VALUE[value].display_name if value in MODULE_BY_VALUE else "Empty"
            label = small_font.render(f"{'Q' if slot_index == 0 else 'E'} / Slot {slot_index + 1}: {module_name}", True, settings.COLOR_TEXT)
            self.screen.blit(label, label.get_rect(center=rect.center))

        action_y = 526
        action_label = self.workshop_system.action_label(loadout, materials)
        self.draw_centered_text(action_label, "small", settings.COLOR_ACCENT, action_y)
        self.draw_centered_text(self.workshop_notice, "small", settings.COLOR_TEXT_MUTED, action_y + 28)

        footer_entries = (("Continue", self.workshop_system.CONTINUE_INDEX), ("Main Menu", self.workshop_system.MAIN_MENU_INDEX))
        for offset, (label_text, selection_index) in enumerate(footer_entries):
            x = 390 + offset * 330
            rect = pygame.Rect(x, 600, 280, 52)
            selected = self.workshop_system.selected_index == selection_index
            pygame.draw.rect(self.screen, settings.COLOR_PANEL_SELECTED if selected else settings.COLOR_PANEL, rect, border_radius=7)
            pygame.draw.rect(self.screen, settings.COLOR_ACCENT if selected else settings.COLOR_ACCENT_DIM, rect, width=2 if selected else 1, border_radius=7)
            label = self.fonts["button"].render(label_text, True, settings.COLOR_TEXT)
            self.screen.blit(label, label.get_rect(center=rect.center))

        self.draw_centered_text(
            "Up/Down select | Left/Right or Q/E choose slot | Enter craft/equip",
            "small",
            settings.COLOR_TEXT_MUTED,
            682,
        )

    def render_floor_transition(self) -> None:
        self.draw_background()
        floor = self.placeholder_run.floor if self.placeholder_run is not None else 1
        self.draw_centered_text(f"Descending to Floor {floor}", "subtitle", settings.COLOR_TEXT, 280)
        self.draw_centered_text(f"Next floor: {floor}", "body", settings.COLOR_ACCENT, 345)
        self.draw_centered_text("Press Enter or Space to skip", "small", settings.COLOR_TEXT_MUTED, 620)

    def render_death(self) -> None:
        self.draw_background()
        run = self.placeholder_run
        floor = run.floor if run is not None else 1
        score = run.score if run is not None else 0
        seed = run.seed if run is not None else self.next_seed
        elapsed = run.elapsed_time if run is not None else 0.0
        self.draw_centered_text("SIGNAL LOST", "title", settings.COLOR_WARNING, 160)
        self.draw_centered_text(
            f"Floor {floor} | Time {elapsed:0.1f}s | Score {score} | Seed {seed}",
            "body",
            settings.COLOR_TEXT_MUTED,
            245,
        )
        if self.death_creature_id:
            self.draw_centered_text(
                f"Contact: {self.death_creature_id}",
                "small",
                settings.COLOR_WARNING,
                292,
            )
        self.draw_button_group(GameState.DEATH)

    def render_victory(self) -> None:
        self.draw_background()
        run = self.placeholder_run
        final_time = run.elapsed_time if run is not None else 0.0
        score = run.score if run is not None else 0
        seed = run.seed if run is not None else self.next_seed
        floors = run.completed_floor_count if run is not None else 0
        materials = run.material_counts if run is not None else {}
        self.draw_centered_text("ECHO RECOVERED", "title", settings.COLOR_SUCCESS, 150)
        self.draw_centered_text("Extraction successful", "subtitle", settings.COLOR_ACCENT, 235)
        self.draw_centered_text(
            f"Time {final_time:0.1f}s | Score {score} | Seed {seed}",
            "body", settings.COLOR_TEXT_MUTED, 295
        )
        self.draw_centered_text(
            f"Floors {floors}/3 | Materials S:{materials.get('scrap', 0)} "
            f"C:{materials.get('circuit', 0)} P:{materials.get('power_cell', 0)}",
            "small", settings.COLOR_TEXT_MUTED, 335
        )
        self.draw_button_group(GameState.VICTORY)

    def draw_background(self) -> None:
        self.screen.fill(settings.COLOR_BACKGROUND)
        tiles = self.visual_assets.get("tiles") if hasattr(self, "visual_assets") else None
        if isinstance(tiles, list) and tiles:
            for x in range(34, settings.WINDOW_WIDTH - 34, 48):
                for y in range(34, settings.WINDOW_HEIGHT - 34, 48):
                    tile_index = 0 if (x // 48 + y // 48) % 5 else 1
                    tile = tiles[tile_index]
                    if isinstance(tile, pygame.Surface):
                        self.screen.blit(tile, (x, y))
            darkness = pygame.Surface(settings.WINDOW_SIZE, pygame.SRCALPHA)
            darkness.fill((0, 0, 0, 176))
            self.screen.blit(darkness, (0, 0))
        for x in range(0, settings.WINDOW_WIDTH, 80):
            pygame.draw.line(self.screen, settings.COLOR_BACKGROUND_ALT, (x, 0), (x, settings.WINDOW_HEIGHT))
        for y in range(0, settings.WINDOW_HEIGHT, 80):
            pygame.draw.line(self.screen, settings.COLOR_BACKGROUND_ALT, (0, y), (settings.WINDOW_WIDTH, y))
        pygame.draw.rect(
            self.screen,
            settings.COLOR_ACCENT_DIM,
            pygame.Rect(34, 34, settings.WINDOW_WIDTH - 68, settings.WINDOW_HEIGHT - 68),
            width=1,
            border_radius=6,
        )

    def draw_overlay(self) -> None:
        self.overlay_surface.fill(settings.COLOR_OVERLAY)
        self.screen.blit(self.overlay_surface, (0, 0))

    def draw_centered_text(self, text: str, font_key: str, color: tuple[int, int, int], y: int) -> None:
        font = self.fonts[font_key]
        image = font.render(text, True, color)
        rect = image.get_rect(center=(settings.WINDOW_WIDTH // 2, y))
        self.screen.blit(image, rect)

    def draw_text_lines(self, lines: list[str], x: int, y: int, line_height: int) -> None:
        font = self.fonts["small"]
        for offset, line in enumerate(lines):
            if not line:
                continue
            image = font.render(line, True, settings.COLOR_TEXT if offset < 8 else settings.COLOR_TEXT_MUTED)
            self.screen.blit(image, (x, y + offset * line_height))

    def draw_gameplay_hud(self) -> None:
        if self.placeholder_run is None or self.player is None:
            return
        objective_lines: list[str] = []
        prompt_line = ""
        if self.floor_objectives is not None:
            state = self.floor_objectives.state
            if state.floor_number == 3:
                heading = "ECHO CORE EXTRACTION"
            elif state.floor_number == 2:
                heading = "SECURITY OVERRIDE"
            else:
                heading = "RESTORE POWER"
            objective_lines = [
                heading,
                state.current_objective_text,
            ]
            if state.current_prompt:
                prompt_line = state.current_prompt
        hud_lines = [
            f"Floor {self.placeholder_run.floor}",
            f"Seed {self.placeholder_run.seed}",
            f"World ({self.player.world_position.x:0.1f}, {self.player.world_position.y:0.1f})",
            f"Tile {self.player.current_tile}",
            f"Doors {len(self.doors)} | Power {'ON' if self.floor_power_available else 'OFF'}",
            *objective_lines,
            (
                f"Materials S:{self.placeholder_run.material_counts.get('scrap', 0)} "
                f"C:{self.placeholder_run.material_counts.get('circuit', 0)} "
                f"P:{self.placeholder_run.material_counts.get('power_cell', 0)} | Score {self.placeholder_run.score}"
            ),
            (
                f"Q {MODULE_BY_VALUE[self.placeholder_run.module_loadout.equipped_slots[0]].short_name if self.placeholder_run.module_loadout.equipped_slots[0] in MODULE_BY_VALUE else 'EMPTY'} | "
                f"E {MODULE_BY_VALUE[self.placeholder_run.module_loadout.equipped_slots[1]].short_name if self.placeholder_run.module_loadout.equipped_slots[1] in MODULE_BY_VALUE else 'EMPTY'}"
            ),
            prompt_line,
            "SCAN READY" if self.scan_system.ready else f"SCAN {self.scan_system.cooldown_remaining:0.1f}s",
            f"F2 Debug {'ON' if self.debug_world_view else 'OFF'} | F3 Perf {'ON' if self.performance_overlay else 'OFF'}",
            "Space Scan | F Interact | Esc Pause",
        ]
        hud_lines = [line for line in hud_lines if line]
        font = self.fonts["small"]
        width = 356
        height = 18 + len(hud_lines) * 24
        panel = pygame.Rect(12, 12, width, height)
        self.overlay_surface.fill((0, 0, 0, 0))
        pygame.draw.rect(self.overlay_surface, (6, 10, 14, 182), panel, border_radius=6)
        pygame.draw.rect(self.overlay_surface, settings.COLOR_ACCENT_DIM, panel, width=1, border_radius=6)
        self.screen.blit(self.overlay_surface, (0, 0))
        for index, line in enumerate(hud_lines):
            color = settings.COLOR_ACCENT if line in ("RESTORE POWER", "SECURITY OVERRIDE", "ECHO CORE EXTRACTION") else (
                settings.COLOR_TEXT if index < 4 else settings.COLOR_TEXT_MUTED
            )
            self.screen.blit(font.render(line, True, color), (24, 24 + index * 24))
        self.draw_interaction_progress()
        self.draw_context_messages()

    def draw_interaction_progress(self) -> None:
        if self.floor_objectives is None:
            return
        state = self.floor_objectives.state
        if state.interaction_progress <= 0.0:
            return
        if state.floor_number == 1:
            if state.generator_repaired:
                return
            duration = settings.GENERATOR_REPAIR_DURATION
            label_text = f"Repairing generator {min(100.0, state.interaction_progress / duration * 100):0.0f}%"
        elif state.floor_number == 2:
            duration = settings.RELAY_ACTIVATION_DURATION
            relay_label = "relay"
            relay = getattr(self.floor_objectives, "_relay_by_id", lambda _: None)(state.active_relay_id)
            if relay is not None:
                relay_label = f"Relay {relay.label}"
            label_text = f"Activating {relay_label} {min(100.0, state.interaction_progress / duration * 100):0.0f}%"
        else:
            if state.control_active:
                return
            duration = settings.CONTAINMENT_INSTALL_DURATION
            label_text = f"Installing component {min(100.0, state.interaction_progress / duration * 100):0.0f}%"
        fraction = max(0.0, min(1.0, state.interaction_progress / duration))
        panel = pygame.Rect(settings.WINDOW_WIDTH // 2 - 180, settings.WINDOW_HEIGHT - 88, 360, 42)
        fill_rect = pygame.Rect(panel.left + 10, panel.bottom - 18, int((panel.width - 20) * fraction), 8)
        self.overlay_surface.fill((0, 0, 0, 0))
        pygame.draw.rect(self.overlay_surface, (6, 10, 14, 210), panel, border_radius=6)
        pygame.draw.rect(self.overlay_surface, settings.COLOR_ACCENT_DIM, panel, width=1, border_radius=6)
        pygame.draw.rect(self.overlay_surface, settings.COLOR_ACCENT, fill_rect, border_radius=3)
        self.screen.blit(self.overlay_surface, (0, 0))
        label = self.fonts["small"].render(label_text, True, settings.COLOR_TEXT)
        self.screen.blit(label, (panel.left + 10, panel.top + 7))

    def draw_context_messages(self) -> None:
        if self.floor_objectives is None or not self.floor_objectives.messages:
            return
        font = self.fonts["small"]
        visible = self.floor_objectives.messages[-3:]
        y = settings.WINDOW_HEIGHT - 160 - (len(visible) - 1) * 24
        for message in visible:
            image = font.render(message.text, True, settings.COLOR_ACCENT)
            rect = image.get_rect(midtop=(settings.WINDOW_WIDTH // 2, y))
            self.screen.blit(image, rect)
            y += 24

    def draw_objective_contact_hints(self) -> None:
        if self.floor_objectives is None or self.player is None or self.camera is None:
            return
        screen_rect = self.screen.get_rect()
        for entity in self.floor_objectives.active_entities:
            world_position = getattr(entity, "world_position", getattr(entity, "world_center", None))
            if world_position is None:
                continue
            distance = world_position.distance_to(self.player.world_position)
            if distance > settings.OBJECTIVE_CONTACT_HINT_RADIUS:
                continue
            position = tuple(round(value) for value in self.camera.world_to_screen(world_position))
            if not screen_rect.collidepoint(position):
                continue
            category = getattr(entity, "scan_category", "")
            if category.startswith("relay"):
                color = settings.COLOR_SUCCESS
            elif category.startswith("door"):
                color = settings.COLOR_WARNING
            elif entity is getattr(self.floor_objectives, "generator", None):
                color = settings.COLOR_ACCENT
            else:
                color = (255, 220, 80)
            pygame.draw.circle(self.screen, color, position, 3)

    def draw_floor1_objective_debug(self) -> None:
        if self.floor_objectives is None or self.camera is None:
            return
        screen_rect = self.screen.get_rect()
        font = self.fonts["small"]
        for entity in self.floor_objectives.active_entities:
            rect = self.camera.world_rect_to_screen(entity.visual_rect)
            if not screen_rect.colliderect(rect):
                continue
            self.screen.blit(entity.image, rect)
            if entity is getattr(self.floor_objectives, "generator", None):
                color = settings.COLOR_SUCCESS
            elif getattr(entity, "scan_category", "").startswith("relay"):
                color = settings.COLOR_ACCENT
            elif getattr(entity, "scan_category", "").startswith("door"):
                color = settings.COLOR_WARNING
            else:
                color = (255, 220, 80)
            pygame.draw.rect(self.screen, color, rect, 1)
            collision_rect = getattr(entity, "collision_rect", None)
            if collision_rect is not None:
                pygame.draw.rect(self.screen, color, self.camera.world_rect_to_screen(collision_rect), 1)
            if entity is getattr(self.floor_objectives, "generator", None):
                pygame.draw.rect(
                    self.screen,
                    settings.COLOR_ACCENT,
                    self.camera.world_rect_to_screen(entity.interaction_rect),
                    1,
                )
                label_text = (
                    f"{entity.unique_id} room={entity.room_id} {entity.state.name} "
                    f"repair={entity.repair_progress:0.2f}"
                )
            else:
                room_id = getattr(entity, "room_id", "-")
                tile = getattr(entity, "tile", "-")
                state_name = getattr(getattr(entity, "state", None), "name", "")
                label_text = f"{entity.unique_id} room={room_id} tile={tile} {state_name}"
                interaction_rect = getattr(entity, "interaction_rect", None)
                if interaction_rect is not None:
                    pygame.draw.rect(self.screen, color, self.camera.world_rect_to_screen(interaction_rect), 1)
            label = font.render(label_text, True, color)
            self.screen.blit(label, (rect.left, max(0, rect.top - 18)))

    def draw_performance_overlay(self) -> None:
        wave = self.scan_system.active_wave
        diagnostics = self.scan_system.diagnostics
        ai_stats = self.ai_diagnostics()
        fps = self.clock.get_fps()
        lines = [
            f"FPS {fps:0.1f} | frame {self.last_frame_dt * 1000.0:0.2f} ms",
            f"scan {'active' if wave is not None else 'idle'} | radius {wave.current_radius:0.1f}" if wave else "scan idle",
            f"rays {settings.SCAN_RAY_COUNT} | raw {diagnostics.raw_hit_count} | hits {diagnostics.deduplicated_hit_count}",
            f"traces {len(self.scan_system.traces)} | segments {diagnostics.segments_drawn}",
            f"object echoes {len(self.snapshot_system.snapshots)} | evaluated {self.snapshot_system.diagnostics.evaluated_entities}",
            f"raycast {diagnostics.last_raycast_ms:0.2f} ms | max {diagnostics.max_raycast_ms:0.2f} ms",
            f"dynamic doors {diagnostics.last_dynamic_door_count}",
            (
                f"creatures {len(self.creatures)} | creature echoes "
                f"{self.snapshot_system.snapshot_count_for_category('creature')}"
            ),
            (
                f"processed current scan "
                f"{len(self.snapshot_system.processed_ids_for_scan(wave.scan_id)) if wave else 0}"
            ),
            (
                f"AI states {ai_stats['state_counts']} | threats {ai_stats['active_threats']} "
                f"{ai_stats['threat_source_counts']}"
            ),
            (
                f"A* calls {ai_stats['pathfinding_calls']} "
                f"({ai_stats['pathfinding_calls_per_second']:0.2f}/s) | nodes {ai_stats['active_path_nodes']}"
            ),
            (
                f"A* last {ai_stats['last_pathfinding_ms']:0.3f} ms max {ai_stats['max_pathfinding_ms']:0.3f} ms | "
                f"perception {ai_stats['perception_checks_per_second']:0.2f}/s"
            ),
            f"stunned {ai_stats['stunned_creatures']} | active path target count {ai_stats['creatures_with_paths']}",
        ]
        if self.floor_objectives is not None:
            state = self.floor_objectives.state
            if state.floor_number == 1:
                lines.extend(
                    [
                        (
                            f"F1 objective {state.current_objective_text} | "
                            f"components {state.components_collected}/2"
                        ),
                        (
                            f"repair {state.generator_repair_progress:0.2f}/{settings.GENERATOR_REPAIR_DURATION:0.2f} "
                            f"powered {state.floor_power_active} elevator {state.elevator_unlocked}"
                        ),
                        (
                            f"objective entities {len(self.floor_objectives.active_entities)} | "
                            f"generator events {state.generator_activation_event_count}"
                        ),
                    ]
                )
            elif state.floor_number == 2:
                lines.extend(
                    [
                        (
                            f"F2 objective {state.current_objective_text} | "
                            f"keycard {state.keycard_collected} relays {state.relays_active_count}/2"
                        ),
                        (
                            f"relay progress A {state.relay_a_progress:0.2f}/{settings.RELAY_ACTIVATION_DURATION:0.2f} "
                            f"B {state.relay_b_progress:0.2f}/{settings.RELAY_ACTIVATION_DURATION:0.2f}"
                        ),
                        (
                            f"powered {state.floor_power_active} elevator {state.elevator_unlocked} | "
                            f"objective entities {len(self.floor_objectives.active_entities)} | "
                            f"relay events {state.relay_activation_event_count}"
                        ),
                    ]
                )
            elif state.floor_number == 3:
                lines.extend(
                    [
                        (
                            f"F3 objective {state.current_objective_text} | component {state.component_collected} "
                            f"control {state.control_active} core {state.echo_core_collected}"
                        ),
                        (
                            f"install {state.control_progress:0.2f}/{settings.CONTAINMENT_INSTALL_DURATION:0.2f} | "
                            f"extraction {state.extraction_active} elevator {state.elevator_unlocked}"
                        ),
                        (
                            f"objective entities {len(self.floor_objectives.active_entities)} | "
                            f"containment events {state.containment_event_count} core events {state.echo_core_event_count}"
                        ),
                    ]
                )
        font = self.fonts["small"]
        width = 390
        height = 18 + len(lines) * 23
        panel = pygame.Rect(settings.WINDOW_WIDTH - width - 12, 12, width, height)
        self.overlay_surface.fill((0, 0, 0, 0))
        pygame.draw.rect(self.overlay_surface, (6, 10, 14, 205), panel, border_radius=6)
        pygame.draw.rect(self.overlay_surface, settings.COLOR_ACCENT_DIM, panel, width=1, border_radius=6)
        self.screen.blit(self.overlay_surface, (0, 0))
        for index, line in enumerate(lines):
            self.screen.blit(font.render(line, True, settings.COLOR_TEXT_MUTED), (panel.left + 12, panel.top + 10 + index * 23))

    def ai_diagnostics(self) -> dict[str, object]:
        elapsed = 1.0
        if self.placeholder_run is not None:
            elapsed = max(1.0, self.placeholder_run.elapsed_time)
        state_counts = {state.name: 0 for state in CreatureState}
        pathfinding_calls = 0
        perception_checks = 0
        active_path_nodes = 0
        stunned_creatures = 0
        creatures_with_paths = 0
        last_pathfinding_ms = 0.0
        max_pathfinding_ms = 0.0
        for creature in self.creatures:
            ai = creature.ai
            if ai is None:
                continue
            state_counts[ai.state.name] += 1
            pathfinding_calls += ai.pathfinding_call_count
            perception_checks += ai.perception_check_count
            active_path_nodes += len(ai.current_path)
            if ai.current_path:
                creatures_with_paths += 1
            if ai.state is CreatureState.STUNNED:
                stunned_creatures += 1
            last_pathfinding_ms = max(last_pathfinding_ms, ai.last_pathfinding_ms)
            max_pathfinding_ms = max(max_pathfinding_ms, ai.max_pathfinding_ms)
        return {
            "state_counts": {key: value for key, value in state_counts.items() if value},
            "active_threats": len(self.threat_events.active_events),
            "threat_source_counts": self.threat_events.source_counts(),
            "pathfinding_calls": pathfinding_calls,
            "pathfinding_calls_per_second": pathfinding_calls / elapsed,
            "last_pathfinding_ms": last_pathfinding_ms,
            "max_pathfinding_ms": max_pathfinding_ms,
            "perception_checks_per_second": perception_checks / elapsed,
            "active_path_nodes": active_path_nodes,
            "stunned_creatures": stunned_creatures,
            "creatures_with_paths": creatures_with_paths,
        }

    def draw_button_group(self, state: GameState) -> None:
        group = self.buttons.get(state, [])
        selected_index = self.selected_indices.get(state, 0)
        for index, button in enumerate(group):
            button.draw(self.screen, self.fonts["button"], selected=index == selected_index)

    def render_generated_floor_preview(self) -> None:
        if self.generation_error is not None:
            self.draw_centered_text(f"Generation error: {self.generation_error}", "small", settings.COLOR_WARNING, 420)
            return

        if (
            self.placeholder_run is None
            or self.placeholder_run.generated_floor is None
            or self.floor_preview_surface is None
        ):
            self.draw_placeholder_asset_scene()
            return

        self.screen.blit(self.floor_preview_surface, self.floor_preview_rect)
        pygame.draw.rect(self.screen, settings.COLOR_ACCENT_DIM, self.floor_preview_rect, width=2, border_radius=4)

        if self.debug_world_view:
            draw_debug_overlay(
                self.screen,
                self.placeholder_run.generated_floor,
                self.floor_preview_rect,
                self.fonts["small"],
            )
            report = self.placeholder_run.generated_floor.validation_report
            if report is not None:
                debug_lines = [
                    f"Attempt {self.placeholder_run.generated_floor.generation_attempt} | "
                    f"Attempt seed {self.placeholder_run.generated_floor.attempt_seed}",
                    f"Validation {'OK' if report.is_valid else 'FAILED'} | "
                    f"Cycle rank {report.graph_cycle_rank} | "
                    f"Connectivity {report.connectivity_ratio:0.3f}",
                    f"Creature candidates {len(self.placeholder_run.generated_floor.candidate_creature_spawns)} | "
                    f"Objective rooms {len(self.placeholder_run.generated_floor.candidate_objective_rooms)} | "
                    f"Gate candidates {len(self.placeholder_run.generated_floor.gate_candidates)}",
                ]
                self.draw_text_lines(debug_lines, 54, 140, 24)

    def draw_placeholder_asset_scene(self) -> None:
        tiles = self.visual_assets["tiles"]
        assert isinstance(tiles, list)
        origin_x = settings.WINDOW_WIDTH // 2 - 168
        origin_y = 450
        pattern = [0, 1, 10, 0, 2, 7, 0, 8, 9, 1, 0, 5, 6, 0]
        for index, tile_index in enumerate(pattern):
            x = origin_x + (index % 7) * 48
            y = origin_y + (index // 7) * 48
            tile = tiles[tile_index]
            assert isinstance(tile, pygame.Surface)
            self.screen.blit(tile, (x, y))

        player = self.visual_assets["player_idle"]
        player_outline = self.visual_assets["player_outline"]
        creature_outline = self.visual_assets["creature_outline"]
        elevator = self.visual_assets["elevator"]
        assert isinstance(player, pygame.Surface)
        assert isinstance(player_outline, pygame.Surface)
        assert isinstance(creature_outline, pygame.Surface)
        assert isinstance(elevator, pygame.Surface)

        self.screen.blit(elevator, elevator.get_rect(center=(origin_x + 312, origin_y + 48)))
        self.screen.blit(player_outline, player_outline.get_rect(center=(origin_x + 120, origin_y + 56)))
        self.screen.blit(player, player.get_rect(center=(origin_x + 120, origin_y + 56)))
        self.screen.blit(creature_outline, creature_outline.get_rect(center=(origin_x + 245, origin_y + 58)))
