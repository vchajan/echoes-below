from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import pygame

from game import settings
from game.entities.door import DoorState, DynamicDoor
from game.systems.modules import ModuleRuntimeState, ModuleType
from game.systems.raycasting import TileFloor, has_line_of_sight
from game.systems.scan import ScanSystem
from game.systems.threat_events import ThreatEventSystem, ThreatSourceType
from game.world.blockers import DynamicBlockerRegistry


@dataclass(frozen=True)
class ModuleActivationResult:
    success: bool
    module_type: ModuleType
    reason: str
    message: str
    affected_count: int = 0
    target_id: str | None = None


@dataclass
class PulseVisual:
    world_position: pygame.Vector2
    max_radius: float
    lifetime: float
    color: tuple[int, int, int]
    age: float = 0.0

    @property
    def expired(self) -> bool:
        return self.age >= self.lifetime

    @property
    def fraction(self) -> float:
        if self.lifetime <= 0.0:
            return 1.0
        return max(0.0, min(1.0, self.age / self.lifetime))

    @property
    def radius(self) -> float:
        return self.max_radius * self.fraction

    @property
    def alpha(self) -> int:
        return round(220 * (1.0 - self.fraction))


@dataclass
class DeployedModuleDevice:
    unique_id: str
    module_type: ModuleType
    world_position: pygame.Vector2
    image: pygame.Surface
    outline_image: pygame.Surface
    lifetime: float
    pulse_interval: float
    next_pulse: float
    age: float = 0.0
    pulse_count: int = 0
    snapshot_lifetime: float = settings.OBJECT_SNAPSHOT_LIFETIME
    scan_active: bool = True
    facing: str = "down"

    def __post_init__(self) -> None:
        self.world_position = pygame.Vector2(self.world_position)
        self.scan_position = self.world_position
        self.scan_category = f"module:{self.module_type.value}"
        self.collision_rect = pygame.Rect(0, 0, settings.MODULE_DEVICE_COLLISION_SIZE, settings.MODULE_DEVICE_COLLISION_SIZE)
        self.collision_rect.center = (round(self.world_position.x), round(self.world_position.y))
        self.visual_rect = self.image.get_rect(center=self.collision_rect.center)
        self.rect = self.visual_rect

    @property
    def expired(self) -> bool:
        return self.age >= self.lifetime

    def capture_scan_outline(self) -> pygame.Surface:
        return self.outline_image

    def update_age(self, dt: float) -> None:
        self.age += max(0.0, dt)
        if self.expired:
            self.scan_active = False


@dataclass
class ModuleEffectDiagnostics:
    shock_pulses: int = 0
    creatures_stunned: int = 0
    decoy_pulses: int = 0
    projector_scans: int = 0
    doors_wedged: int = 0
    failed_activations: int = 0


class ModuleEffectSystem:
    """Floor-local active module effects.

    Ownership, equipment and cooldowns are run-level. Deployed devices and
    transient visuals are cleared whenever a floor ends.
    """

    def __init__(
        self,
        device_images: dict[str, pygame.Surface],
        device_outlines: dict[str, pygame.Surface],
    ) -> None:
        self.device_images = device_images
        self.device_outlines = device_outlines
        self.decoys: list[DeployedModuleDevice] = []
        self.projectors: list[DeployedModuleDevice] = []
        self.pulse_visuals: list[PulseVisual] = []
        self._next_device_id = 1
        self._effect_surface: pygame.Surface | None = None
        self.diagnostics = ModuleEffectDiagnostics()

    @property
    def scan_entities(self) -> list[DeployedModuleDevice]:
        return [device for device in (*self.decoys, *self.projectors) if device.scan_active]

    @property
    def active_device_count(self) -> int:
        return len(self.decoys) + len(self.projectors)

    def activate(
        self,
        module_type: ModuleType,
        *,
        runtime: ModuleRuntimeState,
        player_position: pygame.Vector2,
        floor: TileFloor,
        blockers: DynamicBlockerRegistry,
        doors: Iterable[DynamicDoor],
        creatures: Iterable[object],
        scan_system: ScanSystem,
        threat_events: ThreatEventSystem,
        session_time: float,
        floor_number: int,
    ) -> ModuleActivationResult:
        if not runtime.is_ready(module_type):
            self.diagnostics.failed_activations += 1
            remaining = runtime.remaining(module_type)
            return ModuleActivationResult(
                False,
                module_type,
                "cooldown",
                f"Module cooling down: {remaining:0.1f}s",
            )

        if module_type is ModuleType.SHOCK_PULSE:
            result = self._activate_shock(
                player_position,
                floor,
                blockers,
                creatures,
                threat_events,
                session_time,
                floor_number,
            )
        elif module_type is ModuleType.DECOY_BEACON:
            result = self._activate_decoy(
                player_position,
                threat_events,
                session_time,
                floor_number,
            )
        elif module_type is ModuleType.DOOR_WEDGE:
            result = self._activate_wedge(player_position, doors)
        else:
            result = self._activate_projector(player_position)

        if result.success:
            runtime.start_cooldown(module_type)
        else:
            self.diagnostics.failed_activations += 1
        return result

    def _activate_shock(
        self,
        origin: pygame.Vector2,
        floor: TileFloor,
        blockers: DynamicBlockerRegistry,
        creatures: Iterable[object],
        threat_events: ThreatEventSystem,
        session_time: float,
        floor_number: int,
    ) -> ModuleActivationResult:
        stunned = 0
        for creature in creatures:
            position = pygame.Vector2(getattr(creature, "world_position"))
            if origin.distance_to(position) > settings.SHOCK_PULSE_RADIUS:
                continue
            if not has_line_of_sight(origin, position, floor, blockers, settings.TILE_SIZE):
                continue
            stun = getattr(creature, "stun", None)
            if callable(stun):
                stun(settings.SHOCK_PULSE_STUN_DURATION)
                stunned += 1
        threat_events.add_event(
            origin,
            ThreatSourceType.SHOCK_PULSE,
            strength=settings.SHOCK_PULSE_THREAT_STRENGTH,
            lifetime=settings.SHOCK_PULSE_THREAT_LIFETIME,
            creation_time=session_time,
            floor_number=floor_number,
        )
        self.pulse_visuals.append(
            PulseVisual(
                pygame.Vector2(origin),
                settings.SHOCK_PULSE_RADIUS,
                settings.SHOCK_PULSE_VISUAL_LIFETIME,
                (90, 235, 255),
            )
        )
        self.diagnostics.shock_pulses += 1
        self.diagnostics.creatures_stunned += stunned
        return ModuleActivationResult(
            True,
            ModuleType.SHOCK_PULSE,
            "activated",
            f"Shock Pulse: {stunned} creature{'s' if stunned != 1 else ''} stunned",
            affected_count=stunned,
        )

    def _activate_decoy(
        self,
        origin: pygame.Vector2,
        threat_events: ThreatEventSystem,
        session_time: float,
        floor_number: int,
    ) -> ModuleActivationResult:
        if self.decoys:
            return ModuleActivationResult(False, ModuleType.DECOY_BEACON, "already_active", "Decoy already active")
        device = self._new_device(
            ModuleType.DECOY_BEACON,
            origin,
            "beacon_pulse",
            settings.DECOY_BEACON_LIFETIME,
            settings.DECOY_BEACON_PULSE_INTERVAL,
            settings.DECOY_BEACON_PULSE_INTERVAL,
        )
        self.decoys.append(device)
        event = threat_events.add_event(
            origin,
            ThreatSourceType.DECOY_BEACON,
            strength=settings.DECOY_BEACON_THREAT_STRENGTH,
            lifetime=settings.DECOY_BEACON_THREAT_LIFETIME,
            creation_time=session_time,
            source_entity_id=device.unique_id,
            floor_number=floor_number,
        )
        device.pulse_count = 1
        self.diagnostics.decoy_pulses += 1
        self.pulse_visuals.append(PulseVisual(pygame.Vector2(origin), settings.TILE_SIZE * 2.2, 0.6, (100, 255, 170)))
        return ModuleActivationResult(True, ModuleType.DECOY_BEACON, "deployed", "Decoy Beacon deployed", 1, event.source_entity_id)

    def _activate_wedge(
        self,
        origin: pygame.Vector2,
        doors: Iterable[DynamicDoor],
    ) -> ModuleActivationResult:
        candidates = [
            door
            for door in doors
            if origin.distance_to(door.world_center) <= settings.DOOR_WEDGE_RANGE
            and door.state in (DoorState.OPEN, DoorState.CLOSED)
        ]
        if not candidates:
            return ModuleActivationResult(False, ModuleType.DOOR_WEDGE, "no_door", "No eligible door in range")
        door = min(candidates, key=lambda candidate: origin.distance_squared_to(candidate.world_center))
        if not door.wedge(settings.DOOR_WEDGE_DURATION):
            return ModuleActivationResult(False, ModuleType.DOOR_WEDGE, "door_rejected", "Door cannot be wedged")
        self.diagnostics.doors_wedged += 1
        self.pulse_visuals.append(PulseVisual(door.world_center.copy(), settings.TILE_SIZE, 0.45, (255, 210, 90)))
        return ModuleActivationResult(True, ModuleType.DOOR_WEDGE, "wedged", f"Door wedged {door.state.value}", 1, door.door_id)

    def _activate_projector(self, origin: pygame.Vector2) -> ModuleActivationResult:
        if self.projectors:
            return ModuleActivationResult(False, ModuleType.SCAN_PROJECTOR, "already_active", "Scan Projector already active")
        device = self._new_device(
            ModuleType.SCAN_PROJECTOR,
            origin,
            "projector_activation",
            settings.SCAN_PROJECTOR_LIFETIME,
            settings.SCAN_PROJECTOR_INTERVAL,
            settings.SCAN_PROJECTOR_ACTIVATION_DELAY,
        )
        self.projectors.append(device)
        self.pulse_visuals.append(PulseVisual(pygame.Vector2(origin), settings.TILE_SIZE * 1.4, 0.55, (110, 220, 255)))
        return ModuleActivationResult(True, ModuleType.SCAN_PROJECTOR, "deployed", "Scan Projector deployed", 1, device.unique_id)

    def _new_device(
        self,
        module_type: ModuleType,
        origin: pygame.Vector2,
        image_key: str,
        lifetime: float,
        interval: float,
        first_pulse: float,
    ) -> DeployedModuleDevice:
        unique_id = f"module-{module_type.value}-{self._next_device_id:03d}"
        self._next_device_id += 1
        return DeployedModuleDevice(
            unique_id=unique_id,
            module_type=module_type,
            world_position=pygame.Vector2(origin),
            image=self.device_images[image_key],
            outline_image=self.device_outlines[image_key],
            lifetime=lifetime,
            pulse_interval=interval,
            next_pulse=first_pulse,
        )

    def update(
        self,
        dt: float,
        *,
        floor: TileFloor,
        blockers: DynamicBlockerRegistry,
        scan_system: ScanSystem,
        threat_events: ThreatEventSystem,
        session_time: float,
        floor_number: int,
    ) -> None:
        dt = max(0.0, dt)
        for visual in self.pulse_visuals:
            visual.age += dt
        self.pulse_visuals = [visual for visual in self.pulse_visuals if not visual.expired]

        for device in self.decoys:
            device.update_age(dt)
            device.next_pulse -= dt
            while not device.expired and device.next_pulse <= 0.0:
                threat_events.add_event(
                    device.world_position,
                    ThreatSourceType.DECOY_BEACON,
                    strength=settings.DECOY_BEACON_THREAT_STRENGTH,
                    lifetime=settings.DECOY_BEACON_THREAT_LIFETIME,
                    creation_time=session_time,
                    source_entity_id=device.unique_id,
                    floor_number=floor_number,
                )
                device.pulse_count += 1
                device.next_pulse += device.pulse_interval
                self.diagnostics.decoy_pulses += 1
                self.pulse_visuals.append(PulseVisual(device.world_position.copy(), settings.TILE_SIZE * 2.2, 0.6, (100, 255, 170)))
        self.decoys = [device for device in self.decoys if not device.expired]

        for device in self.projectors:
            device.update_age(dt)
            device.next_pulse -= dt
            if not device.expired and device.next_pulse <= 0.0 and scan_system.active_wave is None:
                triggered = scan_system.trigger_remote(
                    device.world_position,
                    floor,
                    blockers,
                    settings.TILE_SIZE,
                    session_time=session_time,
                    source_type="scan_projector",
                )
                if triggered:
                    threat_events.add_event(
                        device.world_position,
                        ThreatSourceType.SCAN_PROJECTOR,
                        strength=settings.SCAN_PROJECTOR_THREAT_STRENGTH,
                        lifetime=settings.SCAN_PROJECTOR_THREAT_LIFETIME,
                        creation_time=session_time,
                        source_entity_id=device.unique_id,
                        floor_number=floor_number,
                        scan_id=scan_system.active_wave.scan_id if scan_system.active_wave else None,
                    )
                    device.pulse_count += 1
                    device.next_pulse += device.pulse_interval
                    self.diagnostics.projector_scans += 1
                    self.pulse_visuals.append(PulseVisual(device.world_position.copy(), settings.SCAN_MAX_RADIUS, 0.8, (90, 225, 255)))
        self.projectors = [device for device in self.projectors if not device.expired]

    def reset_floor(self) -> None:
        self.decoys.clear()
        self.projectors.clear()
        self.pulse_visuals.clear()
        self._next_device_id = 1

    def render_devices(self, target: pygame.Surface, camera: object) -> None:
        screen_rect = target.get_rect()
        for device in (*self.decoys, *self.projectors):
            rect = camera.world_rect_to_screen(device.visual_rect)
            if screen_rect.colliderect(rect):
                target.blit(device.image, rect)

    def render_effects(self, target: pygame.Surface, camera: object) -> None:
        if self._effect_surface is None or self._effect_surface.get_size() != target.get_size():
            self._effect_surface = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        self._effect_surface.fill((0, 0, 0, 0))
        for visual in self.pulse_visuals:
            center = tuple(round(value) for value in camera.world_to_screen(visual.world_position))
            radius = max(1, round(visual.radius))
            pygame.draw.circle(self._effect_surface, (*visual.color, visual.alpha), center, radius, 2)
        target.blit(self._effect_surface, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
