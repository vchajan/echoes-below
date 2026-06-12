from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from game.systems.modules import MODULE_DEFINITIONS, ModuleLoadout, ModuleType


class WorkshopAction(Enum):
    NONE = "none"
    CONTINUE = "continue"
    MAIN_MENU = "main_menu"


@dataclass(frozen=True)
class WorkshopActivation:
    action: WorkshopAction = WorkshopAction.NONE
    changed: bool = False
    message: str = ""


class WorkshopSystem:
    MODULE_COUNT = len(MODULE_DEFINITIONS)
    CONTINUE_INDEX = MODULE_COUNT
    MAIN_MENU_INDEX = MODULE_COUNT + 1
    ENTRY_COUNT = MODULE_COUNT + 2

    def __init__(self) -> None:
        self.selected_index = 0
        self.target_slot = 0
        self.notice = "Select a recipe. Left/Right chooses the equipment slot."
        self.last_completed_floor: int | None = None

    def open(self, last_completed_floor: int | None) -> None:
        self.selected_index = 0
        self.target_slot = 0
        self.last_completed_floor = last_completed_floor
        self.notice = "Select a recipe. Left/Right chooses the equipment slot."

    @property
    def selected_module(self) -> ModuleType | None:
        if 0 <= self.selected_index < self.MODULE_COUNT:
            return MODULE_DEFINITIONS[self.selected_index].module_type
        return None

    def move_selection(self, direction: int) -> None:
        self.selected_index = (self.selected_index + direction) % self.ENTRY_COUNT

    def change_target_slot(self, direction: int) -> None:
        if self.selected_module is None:
            return
        self.target_slot = (self.target_slot + direction) % 2

    def select_slot(self, slot_index: int) -> None:
        if slot_index not in (0, 1):
            raise IndexError("Workshop slot must be 0 or 1.")
        self.target_slot = slot_index

    def activate(self, loadout: ModuleLoadout, materials: dict[str, int]) -> WorkshopActivation:
        if self.selected_index == self.CONTINUE_INDEX:
            return WorkshopActivation(WorkshopAction.CONTINUE, message="Continue")
        if self.selected_index == self.MAIN_MENU_INDEX:
            return WorkshopActivation(WorkshopAction.MAIN_MENU, message="Main Menu")

        module_type = self.selected_module
        assert module_type is not None
        definition = loadout.definition(module_type)
        if not loadout.is_crafted(module_type):
            result = loadout.craft(module_type, materials)
            if not result.success:
                missing = loadout.missing_materials(module_type, materials)
                missing_text = ", ".join(f"{name} {amount}" for name, amount in missing.items())
                self.notice = f"Missing materials: {missing_text}"
                return WorkshopActivation(message=self.notice)
            loadout.equip(module_type, self.target_slot)
            self.notice = f"Crafted {definition.display_name}; equipped in slot {self.target_slot + 1}."
            return WorkshopActivation(changed=True, message=self.notice)

        outcome = loadout.toggle_equip(module_type, self.target_slot)
        if outcome == "unequipped":
            self.notice = f"Unequipped {definition.display_name} from slot {self.target_slot + 1}."
        else:
            self.notice = f"Equipped {definition.display_name} in slot {self.target_slot + 1}."
        return WorkshopActivation(changed=True, message=self.notice)

    def action_label(self, loadout: ModuleLoadout, materials: dict[str, int]) -> str:
        module_type = self.selected_module
        if module_type is None:
            return "Enter: select"
        definition = loadout.definition(module_type)
        if not loadout.is_crafted(module_type):
            return "Enter: craft and equip" if loadout.can_afford(module_type, materials) else "Insufficient materials"
        if loadout.equipped_slots[self.target_slot] == module_type.value:
            return f"Enter: unequip from slot {self.target_slot + 1}"
        return f"Enter: equip in slot {self.target_slot + 1}"
