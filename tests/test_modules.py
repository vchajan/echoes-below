from __future__ import annotations

import unittest

from game.states import PlaceholderRun
from game.systems.modules import (
    MODULE_BY_VALUE,
    MODULE_DEFINITIONS,
    ModuleLoadout,
    ModuleType,
)


class ModuleDefinitionTests(unittest.TestCase):
    def test_four_unique_module_definitions_exist(self) -> None:
        self.assertEqual(len(MODULE_DEFINITIONS), 4)
        self.assertEqual(len({definition.module_type for definition in MODULE_DEFINITIONS}), 4)

    def test_every_recipe_uses_known_positive_material_costs(self) -> None:
        for definition in MODULE_DEFINITIONS:
            self.assertTrue(definition.recipe)
            self.assertTrue(set(definition.recipe).issubset({"scrap", "circuit", "power_cell"}))
            self.assertTrue(all(amount > 0 for amount in definition.recipe.values()))

    def test_definition_lookup_accepts_enum_and_value(self) -> None:
        loadout = ModuleLoadout()
        for definition in MODULE_DEFINITIONS:
            self.assertIs(loadout.definition(definition.module_type), definition)
            self.assertIs(loadout.definition(definition.module_type.value), definition)

    def test_unknown_definition_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ModuleLoadout().definition("unknown")


class ModuleCraftingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loadout = ModuleLoadout()
        self.materials = {"scrap": 5, "circuit": 5, "power_cell": 5}

    def test_affordability_uses_recipe_only(self) -> None:
        self.assertTrue(self.loadout.can_afford(ModuleType.SHOCK_PULSE, self.materials))
        self.materials["power_cell"] = 0
        self.assertFalse(self.loadout.can_afford(ModuleType.SHOCK_PULSE, self.materials))

    def test_missing_materials_reports_only_shortfall(self) -> None:
        materials = {"scrap": 0, "circuit": 0, "power_cell": 9}
        missing = self.loadout.missing_materials(ModuleType.DECOY_BEACON, materials)
        self.assertEqual(missing, {"scrap": 1, "circuit": 1})

    def test_craft_subtracts_exact_recipe(self) -> None:
        before = dict(self.materials)
        result = self.loadout.craft(ModuleType.SCAN_PROJECTOR, self.materials)
        self.assertTrue(result.success)
        recipe = MODULE_BY_VALUE[ModuleType.SCAN_PROJECTOR.value].recipe
        for name in before:
            self.assertEqual(self.materials[name], before[name] - recipe.get(name, 0))

    def test_craft_marks_module_owned(self) -> None:
        self.loadout.craft(ModuleType.DOOR_WEDGE, self.materials)
        self.assertTrue(self.loadout.is_crafted(ModuleType.DOOR_WEDGE))

    def test_craft_rejects_insufficient_materials_without_mutation(self) -> None:
        materials = {"scrap": 0, "circuit": 0, "power_cell": 0}
        result = self.loadout.craft(ModuleType.SHOCK_PULSE, materials)
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "insufficient_materials")
        self.assertEqual(materials, {"scrap": 0, "circuit": 0, "power_cell": 0})
        self.assertFalse(self.loadout.is_crafted(ModuleType.SHOCK_PULSE))

    def test_module_cannot_be_crafted_twice(self) -> None:
        first = self.loadout.craft(ModuleType.DECOY_BEACON, self.materials)
        remaining = dict(self.materials)
        second = self.loadout.craft(ModuleType.DECOY_BEACON, self.materials)
        self.assertTrue(first.success)
        self.assertFalse(second.success)
        self.assertEqual(second.reason, "already_crafted")
        self.assertEqual(self.materials, remaining)

    def test_crafting_does_not_use_score(self) -> None:
        run = PlaceholderRun(seed=7, score=123)
        run.material_counts = dict(self.materials)
        run.module_loadout.craft(ModuleType.SHOCK_PULSE, run.material_counts)
        self.assertEqual(run.score, 123)


class ModuleEquipmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loadout = ModuleLoadout()
        materials = {"scrap": 20, "circuit": 20, "power_cell": 20}
        for definition in MODULE_DEFINITIONS:
            self.loadout.craft(definition.module_type, materials)

    def test_two_slots_start_empty(self) -> None:
        self.assertEqual(ModuleLoadout().equipped_slots, [None, None])

    def test_uncrafted_module_cannot_be_equipped(self) -> None:
        fresh = ModuleLoadout()
        self.assertFalse(fresh.equip(ModuleType.SHOCK_PULSE, 0))
        self.assertEqual(fresh.equipped_slots, [None, None])

    def test_module_can_be_equipped_in_each_slot(self) -> None:
        self.assertTrue(self.loadout.equip(ModuleType.SHOCK_PULSE, 0))
        self.assertTrue(self.loadout.equip(ModuleType.DECOY_BEACON, 1))
        self.assertEqual(
            self.loadout.equipped_slots,
            [ModuleType.SHOCK_PULSE.value, ModuleType.DECOY_BEACON.value],
        )

    def test_same_module_cannot_occupy_both_slots(self) -> None:
        self.loadout.equip(ModuleType.SHOCK_PULSE, 0)
        self.loadout.equip(ModuleType.SHOCK_PULSE, 1)
        self.assertEqual(self.loadout.equipped_slots, [None, ModuleType.SHOCK_PULSE.value])

    def test_replacing_slot_does_not_destroy_owned_module(self) -> None:
        self.loadout.equip(ModuleType.SHOCK_PULSE, 0)
        self.loadout.equip(ModuleType.DOOR_WEDGE, 0)
        self.assertTrue(self.loadout.is_crafted(ModuleType.SHOCK_PULSE))
        self.assertTrue(self.loadout.is_crafted(ModuleType.DOOR_WEDGE))
        self.assertEqual(self.loadout.equipped_slots[0], ModuleType.DOOR_WEDGE.value)

    def test_toggle_equips_and_unequips_target_slot(self) -> None:
        self.assertEqual(self.loadout.toggle_equip(ModuleType.SCAN_PROJECTOR, 1), "equipped")
        self.assertEqual(self.loadout.toggle_equip(ModuleType.SCAN_PROJECTOR, 1), "unequipped")
        self.assertIsNone(self.loadout.equipped_slots[1])

    def test_unequip_returns_previous_module(self) -> None:
        self.loadout.equip(ModuleType.DECOY_BEACON, 0)
        self.assertEqual(self.loadout.unequip(0), ModuleType.DECOY_BEACON.value)
        self.assertIsNone(self.loadout.equipped_slots[0])

    def test_invalid_slot_index_is_rejected(self) -> None:
        with self.assertRaises(IndexError):
            self.loadout.equip(ModuleType.SHOCK_PULSE, 2)
        with self.assertRaises(IndexError):
            self.loadout.unequip(-1)

    def test_snapshot_is_detached_from_loadout(self) -> None:
        self.loadout.equip(ModuleType.SHOCK_PULSE, 0)
        snapshot = self.loadout.snapshot()
        snapshot["slots"][0] = None
        self.assertEqual(self.loadout.equipped_slots[0], ModuleType.SHOCK_PULSE.value)

    def test_same_seed_retry_resets_crafted_and_equipped_modules(self) -> None:
        run = PlaceholderRun(seed=44)
        run.module_loadout = self.loadout
        run.module_loadout.equip(ModuleType.SHOCK_PULSE, 0)
        restarted = run.reset_same_seed()
        self.assertEqual(restarted.module_loadout.crafted_modules, set())
        self.assertEqual(restarted.module_loadout.equipped_slots, [None, None])
        self.assertEqual(restarted.seed, run.seed)


if __name__ == "__main__":
    unittest.main()
