from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from game.app import Game
from game.states import GameState, PlaceholderRun
from game.systems.crafting import WorkshopAction, WorkshopSystem
from game.systems.modules import MODULE_DEFINITIONS, ModuleLoadout, ModuleType


class WorkshopSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workshop = WorkshopSystem()
        self.loadout = ModuleLoadout()
        self.materials = {"scrap": 6, "circuit": 6, "power_cell": 6}
        self.workshop.open(1)

    def test_open_resets_selection_slot_and_notice(self) -> None:
        self.workshop.selected_index = 4
        self.workshop.target_slot = 1
        self.workshop.open(2)
        self.assertEqual(self.workshop.selected_index, 0)
        self.assertEqual(self.workshop.target_slot, 0)
        self.assertEqual(self.workshop.last_completed_floor, 2)

    def test_selection_wraps_over_modules_and_footer(self) -> None:
        self.workshop.move_selection(-1)
        self.assertEqual(self.workshop.selected_index, self.workshop.MAIN_MENU_INDEX)
        self.workshop.move_selection(1)
        self.assertEqual(self.workshop.selected_index, 0)

    def test_target_slot_changes_only_for_module_rows(self) -> None:
        self.workshop.change_target_slot(1)
        self.assertEqual(self.workshop.target_slot, 1)
        self.workshop.selected_index = self.workshop.CONTINUE_INDEX
        self.workshop.change_target_slot(1)
        self.assertEqual(self.workshop.target_slot, 1)

    def test_crafting_auto_equips_selected_slot(self) -> None:
        self.workshop.select_slot(1)
        result = self.workshop.activate(self.loadout, self.materials)
        self.assertTrue(result.changed)
        self.assertTrue(self.loadout.is_crafted(ModuleType.SHOCK_PULSE))
        self.assertEqual(self.loadout.equipped_slots[1], ModuleType.SHOCK_PULSE.value)

    def test_insufficient_crafting_changes_nothing(self) -> None:
        materials = {"scrap": 0, "circuit": 0, "power_cell": 0}
        result = self.workshop.activate(self.loadout, materials)
        self.assertFalse(result.changed)
        self.assertEqual(self.loadout.crafted_modules, set())
        self.assertIn("Missing materials", result.message)

    def test_owned_module_activation_toggles_equipment(self) -> None:
        self.loadout.craft(ModuleType.SHOCK_PULSE, self.materials)
        first = self.workshop.activate(self.loadout, self.materials)
        second = self.workshop.activate(self.loadout, self.materials)
        self.assertTrue(first.changed)
        self.assertTrue(second.changed)
        self.assertIsNone(self.loadout.equipped_slots[0])

    def test_replacing_slot_preserves_both_crafted_modules(self) -> None:
        self.workshop.activate(self.loadout, self.materials)
        self.workshop.selected_index = 1
        self.workshop.activate(self.loadout, self.materials)
        self.assertTrue(self.loadout.is_crafted(ModuleType.SHOCK_PULSE))
        self.assertTrue(self.loadout.is_crafted(ModuleType.DECOY_BEACON))
        self.assertEqual(self.loadout.equipped_slots[0], ModuleType.DECOY_BEACON.value)

    def test_continue_and_main_menu_return_actions(self) -> None:
        self.workshop.selected_index = self.workshop.CONTINUE_INDEX
        self.assertIs(self.workshop.activate(self.loadout, self.materials).action, WorkshopAction.CONTINUE)
        self.workshop.selected_index = self.workshop.MAIN_MENU_INDEX
        self.assertIs(self.workshop.activate(self.loadout, self.materials).action, WorkshopAction.MAIN_MENU)

    def test_action_label_reflects_craft_and_equip_state(self) -> None:
        self.assertIn("craft", self.workshop.action_label(self.loadout, self.materials).lower())
        self.workshop.activate(self.loadout, self.materials)
        self.assertIn("unequip", self.workshop.action_label(self.loadout, self.materials).lower())


class WorkshopGameIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def setUp(self) -> None:
        self.game = Game()
        self.game.placeholder_run = PlaceholderRun(seed=12345, score=550, completed_floor_count=1)
        self.game.placeholder_run.material_counts = {"scrap": 4, "circuit": 4, "power_cell": 4}
        self.game.last_completed_floor = 1
        self.game.run_exists = True
        self.game.transition_to(GameState.WORKSHOP)

    def tearDown(self) -> None:
        self.game.shutdown()

    def test_workshop_enter_key_crafts_selected_module(self) -> None:
        self.game.handle_keydown(pygame.K_RETURN)
        self.assertTrue(self.game.placeholder_run.module_loadout.is_crafted(ModuleType.SHOCK_PULSE))
        self.assertEqual(self.game.placeholder_run.module_loadout.equipped_slots[0], ModuleType.SHOCK_PULSE.value)

    def test_q_and_e_select_target_slots(self) -> None:
        self.game.handle_keydown(pygame.K_e)
        self.assertEqual(self.game.workshop_system.target_slot, 1)
        self.game.handle_keydown(pygame.K_q)
        self.assertEqual(self.game.workshop_system.target_slot, 0)

    def test_keyboard_can_craft_two_modules_into_two_slots(self) -> None:
        self.game.handle_keydown(pygame.K_RETURN)
        self.game.handle_keydown(pygame.K_DOWN)
        self.game.handle_keydown(pygame.K_e)
        self.game.handle_keydown(pygame.K_RETURN)
        slots = self.game.placeholder_run.module_loadout.equipped_slots
        self.assertEqual(slots, [ModuleType.SHOCK_PULSE.value, ModuleType.DECOY_BEACON.value])

    def test_workshop_render_is_safe_with_crafted_loadout(self) -> None:
        self.game.handle_keydown(pygame.K_RETURN)
        self.game.render_workshop()
        self.assertEqual(self.game.state, GameState.WORKSHOP)

    def test_continue_preserves_loadout_into_floor_transition(self) -> None:
        self.game.handle_keydown(pygame.K_RETURN)
        expected = self.game.placeholder_run.module_loadout.snapshot()
        self.game.workshop_system.selected_index = self.game.workshop_system.CONTINUE_INDEX
        self.game.activate_workshop_selection()
        self.assertEqual(self.game.state, GameState.FLOOR_TRANSITION)
        self.assertEqual(self.game.placeholder_run.floor, 2)
        self.assertEqual(self.game.placeholder_run.module_loadout.snapshot(), expected)

    def test_floor_two_workshop_preserves_floor_one_modules(self) -> None:
        self.game.handle_keydown(pygame.K_RETURN)
        self.game.placeholder_run.floor = 2
        self.game.complete_floor_two()
        self.assertEqual(self.game.state, GameState.WORKSHOP)
        self.assertTrue(self.game.placeholder_run.module_loadout.is_crafted(ModuleType.SHOCK_PULSE))
        self.assertEqual(
            self.game.placeholder_run.floor_completion_summaries[2]["modules"],
            self.game.placeholder_run.module_loadout.snapshot(),
        )

    def test_restart_same_seed_clears_modules(self) -> None:
        self.game.handle_keydown(pygame.K_RETURN)
        self.game.restart_placeholder_run()
        self.assertEqual(self.game.placeholder_run.module_loadout.crafted_modules, set())
        self.assertEqual(self.game.placeholder_run.module_loadout.equipped_slots, [None, None])

    def test_new_run_starts_with_empty_loadout(self) -> None:
        self.game.handle_keydown(pygame.K_RETURN)
        self.game.start_new_run()
        self.assertEqual(self.game.placeholder_run.module_loadout.crafted_modules, set())
        self.assertEqual(self.game.placeholder_run.module_loadout.equipped_slots, [None, None])

    def test_main_menu_discards_run_loadout(self) -> None:
        self.game.handle_keydown(pygame.K_RETURN)
        self.game.workshop_system.selected_index = self.game.workshop_system.MAIN_MENU_INDEX
        self.game.activate_workshop_selection()
        self.assertEqual(self.game.state, GameState.MAIN_MENU)
        self.assertIsNone(self.game.placeholder_run)

    def test_crafting_never_changes_score(self) -> None:
        score = self.game.placeholder_run.score
        self.game.handle_keydown(pygame.K_RETURN)
        self.assertEqual(self.game.placeholder_run.score, score)

    def test_every_module_can_be_selected_and_crafted_via_system(self) -> None:
        self.game.placeholder_run.material_counts = {"scrap": 20, "circuit": 20, "power_cell": 20}
        for index, definition in enumerate(MODULE_DEFINITIONS):
            self.game.workshop_system.selected_index = index
            self.game.activate_workshop_selection()
            self.assertTrue(self.game.placeholder_run.module_loadout.is_crafted(definition.module_type))


if __name__ == "__main__":
    unittest.main()
