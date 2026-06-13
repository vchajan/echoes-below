from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame

from game import settings
from game.app import Game
from game.assets import AssetManager
from game.entities.door import DoorState, DoorType, DynamicDoor
from game.states import GameState, PlaceholderRun
from game.systems.module_effects import ModuleEffectSystem
from game.systems.modules import MODULE_DEFINITIONS, ModuleRuntimeState, ModuleType
from game.systems.scan import ScanConfig, ScanSystem
from game.systems.snapshots import EchoSnapshotSystem
from game.systems.threat_events import ThreatEventSystem, ThreatSourceType
from game.world.blockers import DynamicBlockerRegistry
from game.world.floor import DoorwayCandidate
from game.world.tiles import TileType


class FakeFloor:
    def __init__(self, width: int = 9, height: int = 9) -> None:
        self.width = width
        self.height = height
        self.tiles = np.full((height, width), int(TileType.FLOOR), dtype=np.int16)
        self.tiles[0, :] = int(TileType.WALL)
        self.tiles[-1, :] = int(TileType.WALL)
        self.tiles[:, 0] = int(TileType.WALL)
        self.tiles[:, -1] = int(TileType.WALL)

    def tile_at(self, x: int, y: int) -> TileType:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError((x, y))
        return TileType(int(self.tiles[y, x]))


class FakeCreature:
    def __init__(self, position: tuple[float, float]) -> None:
        self.world_position = pygame.Vector2(position)
        self.stun_durations: list[float] = []

    def stun(self, duration: float) -> None:
        self.stun_durations.append(duration)


class ModuleRuntimeTests(unittest.TestCase):
    def test_runtime_contains_every_module(self) -> None:
        runtime = ModuleRuntimeState()
        self.assertEqual(set(runtime.cooldown_remaining), {d.module_type.value for d in MODULE_DEFINITIONS})

    def test_cooldown_starts_and_counts_down(self) -> None:
        runtime = ModuleRuntimeState()
        runtime.start_cooldown(ModuleType.SHOCK_PULSE)
        self.assertFalse(runtime.is_ready(ModuleType.SHOCK_PULSE))
        runtime.update(2.0)
        self.assertAlmostEqual(runtime.remaining(ModuleType.SHOCK_PULSE), 6.0)
        runtime.update(10.0)
        self.assertTrue(runtime.is_ready(ModuleType.SHOCK_PULSE))
        self.assertEqual(runtime.activation_counts[ModuleType.SHOCK_PULSE.value], 1)

    def test_retry_creates_fresh_runtime(self) -> None:
        run = PlaceholderRun(seed=9)
        run.module_runtime.start_cooldown(ModuleType.DECOY_BEACON)
        restarted = run.reset_same_seed()
        self.assertTrue(restarted.module_runtime.is_ready(ModuleType.DECOY_BEACON))
        self.assertEqual(restarted.module_runtime.activation_counts[ModuleType.DECOY_BEACON.value], 0)


class ModuleEffectSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.assets = AssetManager(audio_available=False)

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def setUp(self) -> None:
        images = {
            "beacon_pulse": pygame.Surface((32, 32), pygame.SRCALPHA),
            "projector_activation": pygame.Surface((32, 32), pygame.SRCALPHA),
        }
        outlines = {key: value.copy() for key, value in images.items()}
        self.effects = ModuleEffectSystem(images, outlines)
        self.runtime = ModuleRuntimeState()
        self.floor = FakeFloor()
        self.blockers = DynamicBlockerRegistry([], settings.TILE_SIZE)
        self.threats = ThreatEventSystem()
        self.scan = ScanSystem(ScanConfig(ray_count=32, max_radius=240.0, wave_speed=600.0))
        self.origin = pygame.Vector2(4.5 * settings.TILE_SIZE, 4.5 * settings.TILE_SIZE)

    def activate(self, module: ModuleType, *, creatures=(), doors=()):
        return self.effects.activate(
            module,
            runtime=self.runtime,
            player_position=self.origin,
            floor=self.floor,
            blockers=self.blockers,
            doors=doors,
            creatures=creatures,
            scan_system=self.scan,
            threat_events=self.threats,
            session_time=3.0,
            floor_number=1,
        )

    def test_shock_stuns_visible_creature(self) -> None:
        creature = FakeCreature((self.origin.x + settings.TILE_SIZE * 2, self.origin.y))
        result = self.activate(ModuleType.SHOCK_PULSE, creatures=[creature])
        self.assertTrue(result.success)
        self.assertEqual(result.affected_count, 1)
        self.assertEqual(creature.stun_durations, [settings.SHOCK_PULSE_STUN_DURATION])
        self.assertEqual(self.threats.active_events[0].source_type, ThreatSourceType.SHOCK_PULSE)
        self.assertFalse(self.runtime.is_ready(ModuleType.SHOCK_PULSE))

    def test_shock_does_not_stun_through_wall(self) -> None:
        self.floor.tiles[4, 5] = int(TileType.WALL)
        creature = FakeCreature((self.origin.x + settings.TILE_SIZE * 2, self.origin.y))
        result = self.activate(ModuleType.SHOCK_PULSE, creatures=[creature])
        self.assertTrue(result.success)
        self.assertEqual(result.affected_count, 0)
        self.assertEqual(creature.stun_durations, [])

    def test_cooldown_rejects_repeat_without_new_effect(self) -> None:
        self.activate(ModuleType.SHOCK_PULSE)
        pulse_count = len(self.effects.pulse_visuals)
        result = self.activate(ModuleType.SHOCK_PULSE)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "cooldown")
        self.assertEqual(len(self.effects.pulse_visuals), pulse_count)

    def test_decoy_emits_repeated_events_and_expires(self) -> None:
        result = self.activate(ModuleType.DECOY_BEACON)
        self.assertTrue(result.success)
        self.assertEqual(len(self.effects.decoys), 1)
        self.assertEqual(self.effects.decoys[0].pulse_count, 1)
        initial = len(self.threats.active_events)
        self.effects.update(
            settings.DECOY_BEACON_PULSE_INTERVAL + 0.01,
            floor=self.floor,
            blockers=self.blockers,
            scan_system=self.scan,
            threat_events=self.threats,
            session_time=5.0,
            floor_number=1,
        )
        self.assertGreater(len(self.threats.active_events), initial)
        self.assertTrue(all(e.source_type is ThreatSourceType.DECOY_BEACON for e in self.threats.active_events))
        self.effects.update(
            settings.DECOY_BEACON_LIFETIME,
            floor=self.floor,
            blockers=self.blockers,
            scan_system=self.scan,
            threat_events=self.threats,
            session_time=20.0,
            floor_number=1,
        )
        self.assertEqual(self.effects.decoys, [])

    def test_second_decoy_is_rejected_while_first_active(self) -> None:
        self.activate(ModuleType.DECOY_BEACON)
        self.runtime.cooldown_remaining[ModuleType.DECOY_BEACON.value] = 0.0
        result = self.activate(ModuleType.DECOY_BEACON)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "already_active")

    def make_door(self, state: DoorState = DoorState.CLOSED) -> DynamicDoor:
        doorway = DoorwayCandidate(tile=(4, 4), room_id=0, connected_room_id=1, orientation="vertical_door_plane")
        door = DynamicDoor("wedge-door", DoorType.POWERED, doorway, self.assets, settings.TILE_SIZE)
        if state is DoorState.OPEN:
            door.force_open()
        return door

    def test_wedge_applies_to_near_closed_door(self) -> None:
        door = self.make_door()
        result = self.activate(ModuleType.DOOR_WEDGE, doors=[door])
        self.assertTrue(result.success)
        self.assertEqual(door.state, DoorState.WEDGED_CLOSED)
        self.assertAlmostEqual(door.wedge_remaining, settings.DOOR_WEDGE_DURATION)

    def test_wedge_applies_to_near_open_door_and_keeps_passable(self) -> None:
        door = self.make_door(DoorState.OPEN)
        result = self.activate(ModuleType.DOOR_WEDGE, doors=[door])
        self.assertTrue(result.success)
        self.assertEqual(door.state, DoorState.WEDGED_OPEN)
        self.assertFalse(door.blocks_player)

    def test_wedge_rejects_locked_or_distant_door(self) -> None:
        doorway = DoorwayCandidate(tile=(4, 4), room_id=0, connected_room_id=1, orientation="vertical_door_plane")
        locked = DynamicDoor("locked", DoorType.SECURITY, doorway, self.assets, settings.TILE_SIZE)
        result = self.activate(ModuleType.DOOR_WEDGE, doors=[locked])
        self.assertFalse(result.success)
        locked.world_center += pygame.Vector2(settings.DOOR_WEDGE_RANGE * 4, 0)
        self.assertFalse(self.activate(ModuleType.DOOR_WEDGE, doors=[locked]).success)

    def test_timed_wedge_removes_itself(self) -> None:
        door = self.make_door()
        door.wedge(0.2)
        door.update(0.21, floor_powered=True)
        self.assertEqual(door.state, DoorState.CLOSED)
        self.assertIsNone(door.wedge_remaining)

    def test_projector_emits_remote_scan_without_player_cooldown(self) -> None:
        result = self.activate(ModuleType.SCAN_PROJECTOR)
        self.assertTrue(result.success)
        self.assertEqual(len(self.effects.projectors), 1)
        self.assertTrue(self.scan.ready)
        self.effects.update(
            settings.SCAN_PROJECTOR_ACTIVATION_DELAY + 0.01,
            floor=self.floor,
            blockers=self.blockers,
            scan_system=self.scan,
            threat_events=self.threats,
            session_time=5.0,
            floor_number=1,
        )
        self.assertIsNotNone(self.scan.active_wave)
        self.assertTrue(self.scan.ready)
        self.assertEqual(self.effects.projectors[0].pulse_count, 1)
        projector_events = [e for e in self.threats.active_events if e.source_type is ThreatSourceType.SCAN_PROJECTOR]
        self.assertEqual(len(projector_events), 1)

    def test_projector_waits_for_active_wave(self) -> None:
        self.activate(ModuleType.SCAN_PROJECTOR)
        self.scan.trigger(self.origin, self.floor, self.blockers, settings.TILE_SIZE)
        self.effects.update(
            settings.SCAN_PROJECTOR_ACTIVATION_DELAY + 0.1,
            floor=self.floor,
            blockers=self.blockers,
            scan_system=self.scan,
            threat_events=self.threats,
            session_time=5.0,
            floor_number=1,
        )
        self.assertEqual(self.effects.projectors[0].pulse_count, 0)

    def test_devices_are_scan_detectable_and_floor_reset_clears_them(self) -> None:
        self.activate(ModuleType.DECOY_BEACON)
        self.runtime.cooldown_remaining[ModuleType.DECOY_BEACON.value] = 0.0
        self.activate(ModuleType.SCAN_PROJECTOR)
        self.assertEqual(len(self.effects.scan_entities), 2)
        self.effects.reset_floor()
        self.assertEqual(self.effects.scan_entities, [])
        self.assertEqual(self.effects.active_device_count, 0)

    def test_deployed_decoy_can_be_captured_as_historical_snapshot(self) -> None:
        self.activate(ModuleType.DECOY_BEACON)
        device = self.effects.decoys[0]
        snapshots = EchoSnapshotSystem()
        external_origin = device.world_position - pygame.Vector2(settings.TILE_SIZE, 0.0)
        external_scan = ScanSystem(ScanConfig(ray_count=32, max_radius=240.0, wave_speed=600.0))
        self.assertTrue(external_scan.trigger(external_origin, self.floor, self.blockers, settings.TILE_SIZE))
        external_scan.update(0.2)
        snapshots.update(
            0.0,
            external_scan.last_wave_step,
            self.effects.scan_entities,
            self.floor,
            self.blockers,
            settings.TILE_SIZE,
        )
        captured = snapshots.snapshots_for_source(device.unique_id)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].category, "module:decoy_beacon")
        self.assertEqual(captured[0].world_position, device.world_position)

    def test_device_snapshot_survives_source_expiry(self) -> None:
        self.activate(ModuleType.DECOY_BEACON)
        device = self.effects.decoys[0]
        snapshots = EchoSnapshotSystem()
        external_origin = device.world_position - pygame.Vector2(settings.TILE_SIZE, 0.0)
        external_scan = ScanSystem(ScanConfig(ray_count=32, max_radius=240.0, wave_speed=600.0))
        external_scan.trigger(external_origin, self.floor, self.blockers, settings.TILE_SIZE)
        external_scan.update(0.2)
        snapshots.update(
            0.0,
            external_scan.last_wave_step,
            self.effects.scan_entities,
            self.floor,
            self.blockers,
            settings.TILE_SIZE,
        )
        self.effects.update(
            settings.DECOY_BEACON_LIFETIME + 0.1,
            floor=self.floor,
            blockers=self.blockers,
            scan_system=self.scan,
            threat_events=self.threats,
            session_time=20.0,
            floor_number=1,
        )
        snapshots.update(0.1, None, (), self.floor, self.blockers, settings.TILE_SIZE)
        self.assertEqual(self.effects.decoys, [])
        self.assertEqual(len(snapshots.snapshots_for_source(device.unique_id)), 1)

    def test_decoy_threat_outranks_player_scan_at_same_position(self) -> None:
        self.threats.add_player_scan(self.origin, creation_time=1.0, floor_number=1)
        self.activate(ModuleType.DECOY_BEACON)
        selected = self.threats.select_relevant_event(
            self.origin,
            floor_number=1,
            minimum_relevance=0.0,
        )
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertIs(selected.source_type, ThreatSourceType.DECOY_BEACON)


class ModuleGameIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def setUp(self) -> None:
        self.game = Game()
        self.game.start_new_run()
        assert self.game.placeholder_run is not None
        self.game.placeholder_run.material_counts = {"scrap": 20, "circuit": 20, "power_cell": 20}
        for definition in MODULE_DEFINITIONS:
            self.game.placeholder_run.module_loadout.craft(definition.module_type, self.game.placeholder_run.material_counts)
        self.game.placeholder_run.module_loadout.equip(ModuleType.SHOCK_PULSE, 0)
        self.game.placeholder_run.module_loadout.equip(ModuleType.DECOY_BEACON, 1)

    def tearDown(self) -> None:
        self.game.shutdown()

    def test_q_and_e_activate_equipped_modules(self) -> None:
        self.game.handle_keydown(pygame.K_q)
        self.game.handle_keydown(pygame.K_e)
        runtime = self.game.placeholder_run.module_runtime
        self.assertFalse(runtime.is_ready(ModuleType.SHOCK_PULSE))
        self.assertFalse(runtime.is_ready(ModuleType.DECOY_BEACON))
        self.assertEqual(len(self.game.module_effects.decoys), 1)

    def test_pause_freezes_module_cooldowns_and_devices(self) -> None:
        self.game.handle_keydown(pygame.K_e)
        runtime = self.game.placeholder_run.module_runtime
        before_cooldown = runtime.remaining(ModuleType.DECOY_BEACON)
        before_age = self.game.module_effects.decoys[0].age
        self.game.transition_to(GameState.PAUSED)
        self.game.update(2.0)
        self.assertEqual(runtime.remaining(ModuleType.DECOY_BEACON), before_cooldown)
        self.assertEqual(self.game.module_effects.decoys[0].age, before_age)

    def test_floor_cleanup_preserves_cooldown_but_clears_devices(self) -> None:
        self.game.handle_keydown(pygame.K_e)
        runtime = self.game.placeholder_run.module_runtime
        before = runtime.remaining(ModuleType.DECOY_BEACON)
        self.game._clear_floor_runtime()
        self.assertEqual(runtime.remaining(ModuleType.DECOY_BEACON), before)
        self.assertEqual(self.game.module_effects.active_device_count, 0)

    def test_retry_same_seed_resets_module_runtime_and_effects(self) -> None:
        self.game.handle_keydown(pygame.K_e)
        self.game.retry_same_seed()
        self.assertTrue(self.game.placeholder_run.module_runtime.is_ready(ModuleType.DECOY_BEACON))
        self.assertEqual(self.game.placeholder_run.module_loadout.crafted_modules, set())
        self.assertEqual(self.game.module_effects.active_device_count, 0)

    def test_empty_slot_does_not_start_cooldown(self) -> None:
        self.game.placeholder_run.module_loadout.equipped_slots[0] = None
        self.assertFalse(self.game.activate_module_slot(0))
        self.assertTrue(self.game.placeholder_run.module_runtime.is_ready(ModuleType.SHOCK_PULSE))


if __name__ == "__main__":
    unittest.main()
