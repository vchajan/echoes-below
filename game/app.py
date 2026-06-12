from __future__ import annotations

import pygame

from game.assets import EFFECT_IMAGE_PATHS, MODULE_ICON_PATHS, AssetManager
from game.camera import Camera
from game.entities.door import DoorType, DynamicDoor
from game.entities.scan_objects import ElevatorEntity, MaterialPickup
from game.entities.player import Player, movement_direction_from_bools
from game import settings
from game.systems.scan import ScanRenderer, ScanSystem
from game.systems.snapshots import EchoSnapshotRenderer, EchoSnapshotSystem
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
        self.material_pickups: list[MaterialPickup] = []
        self.elevator_entity: ElevatorEntity | None = None
        self.dynamic_blockers = DynamicBlockerRegistry([], settings.TILE_SIZE)
        self.floor_world_surface: pygame.Surface | None = None
        self.floor_preview_surface: pygame.Surface | None = None
        self.floor_preview_rect = pygame.Rect(0, 0, 0, 0)
        self.generation_error: str | None = None

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
            GameState.WORKSHOP: [
                Button.centered("Continue", "continue_floor", (center_x, 430)),
                Button.centered("Main Menu", "main_menu", (center_x, 500)),
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
            if self.placeholder_run is not None:
                self.placeholder_run.floor += 1
                self.placeholder_run.generated_floor = None
                self.player = None
                self.camera = None
                self.doors = []
                self.dynamic_blockers.replace_doors([])
                self.floor_content = None
                self.material_pickups = []
                self.elevator_entity = None
                self.snapshot_system.reset()
                self.floor_world_surface = None
                self.floor_preview_surface = None
                self.scan_system.reset()
            self.transition_to(GameState.FLOOR_TRANSITION)
        elif action == "retry_seed":
            self.retry_same_seed()

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
    ) -> None:
        if (
            self.placeholder_run is None
            or self.placeholder_run.generated_floor is None
            or self.player is None
            or self.camera is None
        ):
            return

        if movement_direction is None:
            keys = pygame.key.get_pressed()
            movement_direction = movement_direction_from_bools(
                keys[pygame.K_w] or keys[pygame.K_UP],
                keys[pygame.K_s] or keys[pygame.K_DOWN],
                keys[pygame.K_a] or keys[pygame.K_LEFT],
                keys[pygame.K_d] or keys[pygame.K_RIGHT],
            )
        direction = pygame.Vector2(movement_direction)
        if direction.length_squared() > 1:
            direction = direction.normalize()

        for door in self.doors:
            door.update(dt, self.player.collision_rect, floor_powered=self.floor_power_available)
        if self.floor_content is not None:
            self.floor_content.update(dt)

        self.player.update(direction, dt, self.placeholder_run.generated_floor, self.dynamic_blockers)
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
        self.collect_material_pickups()

    def scan_detectable_entities(self) -> list[object]:
        if self.floor_content is None:
            return []
        return self.floor_content.scan_entities

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
        return self.scan_system.trigger(
            self.player.world_position,
            self.placeholder_run.generated_floor,
            self.dynamic_blockers,
            settings.TILE_SIZE,
            session_time=self.placeholder_run.elapsed_time,
        )

    def transition_to(self, new_state: GameState) -> None:
        self.previous_state = self.state
        self.state = new_state

        if new_state in self.selected_indices:
            self.selected_indices[new_state] = 0
        if new_state == GameState.SPLASH:
            self.splash_elapsed = 0.0
        elif new_state == GameState.FLOOR_TRANSITION:
            self.floor_transition_elapsed = 0.0
        elif new_state == GameState.PLAYING and self.placeholder_run is not None:
            if self.placeholder_run.generated_floor is None or self.player is None or self.camera is None:
                self.prepare_generated_floor()

    def start_new_run(self) -> None:
        self.next_seed += 1
        self.placeholder_run = PlaceholderRun(seed=self.next_seed)
        self.run_exists = True
        self.prepare_generated_floor()
        self.transition_to(GameState.PLAYING)

    def restart_placeholder_run(self) -> None:
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
        self.material_pickups = []
        self.elevator_entity = None
        self.floor_power_available = True
        self.floor_world_surface = None
        self.floor_preview_surface = None
        self.floor_preview_rect = pygame.Rect(0, 0, 0, 0)
        self.generation_error = None
        self.scan_system.reset()
        self.snapshot_system.reset()
        self.world_renderer.clear()

    def request_quit(self) -> None:
        self.running = False

    def prepare_generated_floor(self) -> None:
        self.scan_system.reset()
        self.snapshot_system.reset()
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
            self.material_pickups = []
            self.elevator_entity = None
            self.floor_world_surface = None
            self.floor_preview_surface = None
            return

        self.generation_error = None
        self.floor_power_available = True
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
        self.scan_system.reset()
        self.snapshot_system.reset()

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
            self.screen.blit(self.player.image, player_screen_rect)
        else:
            self.scan_renderer.render(self.screen, self.scan_system, self.camera)
            self.snapshot_renderer.render(self.screen, self.snapshot_system.snapshots, self.camera)
            self.screen.blit(self.player.image, player_screen_rect)
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
                    f"Materials {len([p for p in self.material_pickups if p.scan_active])} | Echo snapshots {len(self.snapshot_system.snapshots)}",
                    "F6 nearest door | F7 nearest locked door | F8 power",
                ]
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
        module_icons = self.visual_assets["module_icons"]
        assert isinstance(module_icons, dict)
        for index, icon_name in enumerate(("scrap", "circuit", "power_cell")):
            icon = module_icons[icon_name]
            assert isinstance(icon, pygame.Surface)
            self.screen.blit(icon, (settings.WINDOW_WIDTH // 2 - 92 + index * 68, 330))
        self.draw_centered_text("Elevator Workshop", "subtitle", settings.COLOR_TEXT, 210)
        self.draw_centered_text("Crafting will be added in a later phase.", "body", settings.COLOR_TEXT_MUTED, 280)
        self.draw_button_group(GameState.WORKSHOP)

    def render_floor_transition(self) -> None:
        self.draw_background()
        floor = self.placeholder_run.floor if self.placeholder_run is not None else 1
        self.draw_centered_text("Descending...", "subtitle", settings.COLOR_TEXT, 280)
        self.draw_centered_text(f"Next floor: {floor}", "body", settings.COLOR_ACCENT, 345)
        self.draw_centered_text("Press Enter or Space to skip", "small", settings.COLOR_TEXT_MUTED, 620)

    def render_death(self) -> None:
        self.draw_background()
        run = self.placeholder_run
        floor = run.floor if run is not None else 1
        score = run.score if run is not None else 0
        seed = run.seed if run is not None else self.next_seed
        self.draw_centered_text("SIGNAL LOST", "title", settings.COLOR_WARNING, 160)
        self.draw_centered_text(f"Floor {floor} | Score {score} | Seed {seed}", "body", settings.COLOR_TEXT_MUTED, 245)
        self.draw_button_group(GameState.DEATH)

    def render_victory(self) -> None:
        self.draw_background()
        run = self.placeholder_run
        final_time = run.elapsed_time if run is not None else 0.0
        score = run.score if run is not None else 0
        self.draw_centered_text("ECHO RECOVERED", "title", settings.COLOR_SUCCESS, 180)
        self.draw_centered_text(f"Final time {final_time:0.1f}s | Score {score}", "body", settings.COLOR_TEXT_MUTED, 275)
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
        hud_lines = [
            f"Floor {self.placeholder_run.floor}",
            f"Seed {self.placeholder_run.seed}",
            f"World ({self.player.world_position.x:0.1f}, {self.player.world_position.y:0.1f})",
            f"Tile {self.player.current_tile}",
            f"Doors {len(self.doors)} | Power {'ON' if self.floor_power_available else 'OFF'}",
            (
                f"Materials S:{self.placeholder_run.material_counts.get('scrap', 0)} "
                f"C:{self.placeholder_run.material_counts.get('circuit', 0)} "
                f"P:{self.placeholder_run.material_counts.get('power_cell', 0)} | Score {self.placeholder_run.score}"
            ),
            "SCAN READY" if self.scan_system.ready else f"SCAN {self.scan_system.cooldown_remaining:0.1f}s",
            f"F2 Debug {'ON' if self.debug_world_view else 'OFF'} | F3 Perf {'ON' if self.performance_overlay else 'OFF'}",
            "Space Scan | Esc Pause",
        ]
        font = self.fonts["small"]
        width = 288
        height = 18 + len(hud_lines) * 24
        panel = pygame.Rect(12, 12, width, height)
        self.overlay_surface.fill((0, 0, 0, 0))
        pygame.draw.rect(self.overlay_surface, (6, 10, 14, 182), panel, border_radius=6)
        pygame.draw.rect(self.overlay_surface, settings.COLOR_ACCENT_DIM, panel, width=1, border_radius=6)
        self.screen.blit(self.overlay_surface, (0, 0))
        for index, line in enumerate(hud_lines):
            color = settings.COLOR_TEXT if index < 4 else settings.COLOR_TEXT_MUTED
            self.screen.blit(font.render(line, True, color), (24, 24 + index * 24))

    def draw_performance_overlay(self) -> None:
        wave = self.scan_system.active_wave
        diagnostics = self.scan_system.diagnostics
        fps = self.clock.get_fps()
        lines = [
            f"FPS {fps:0.1f} | frame {self.last_frame_dt * 1000.0:0.2f} ms",
            f"scan {'active' if wave is not None else 'idle'} | radius {wave.current_radius:0.1f}" if wave else "scan idle",
            f"rays {settings.SCAN_RAY_COUNT} | raw {diagnostics.raw_hit_count} | hits {diagnostics.deduplicated_hit_count}",
            f"traces {len(self.scan_system.traces)} | segments {diagnostics.segments_drawn}",
            f"object echoes {len(self.snapshot_system.snapshots)} | evaluated {self.snapshot_system.diagnostics.evaluated_entities}",
            f"raycast {diagnostics.last_raycast_ms:0.2f} ms | max {diagnostics.max_raycast_ms:0.2f} ms",
            f"dynamic doors {diagnostics.last_dynamic_door_count}",
        ]
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
