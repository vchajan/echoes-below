from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, MutableMapping


class ModuleType(Enum):
    SHOCK_PULSE = "shock_pulse"
    DECOY_BEACON = "decoy_beacon"
    DOOR_WEDGE = "door_wedge"
    SCAN_PROJECTOR = "scan_projector"


@dataclass(frozen=True)
class ModuleDefinition:
    module_type: ModuleType
    display_name: str
    short_name: str
    description: str
    recipe: Mapping[str, int]
    icon_key: str


MODULE_DEFINITIONS: tuple[ModuleDefinition, ...] = (
    ModuleDefinition(
        ModuleType.SHOCK_PULSE,
        "Shock Pulse",
        "PULSE",
        "Stuns nearby visible creatures.",
        {"circuit": 1, "power_cell": 1},
        "shock_pulse_ready",
    ),
    ModuleDefinition(
        ModuleType.DECOY_BEACON,
        "Decoy Beacon",
        "DECOY",
        "Creates a temporary false signal.",
        {"scrap": 1, "circuit": 1},
        "decoy_beacon_ready",
    ),
    ModuleDefinition(
        ModuleType.DOOR_WEDGE,
        "Door Wedge",
        "WEDGE",
        "Temporarily locks a door in place.",
        {"scrap": 2},
        "door_wedge_ready",
    ),
    ModuleDefinition(
        ModuleType.SCAN_PROJECTOR,
        "Scan Projector",
        "PROJECTOR",
        "Deploys a delayed remote scan.",
        {"scrap": 1, "circuit": 1, "power_cell": 1},
        "scan_projector_ready",
    ),
)

MODULE_BY_TYPE = {definition.module_type: definition for definition in MODULE_DEFINITIONS}
MODULE_BY_VALUE = {definition.module_type.value: definition for definition in MODULE_DEFINITIONS}


@dataclass(frozen=True)
class CraftResult:
    success: bool
    reason: str
    module_type: ModuleType
    spent: dict[str, int] = field(default_factory=dict)


@dataclass
class ModuleLoadout:
    """Run-level ownership and two-slot equipment state.

    Active effects and cooldowns intentionally belong to later phases. This object
    only owns persistent crafting/equipment choices between floors.
    """

    crafted_modules: set[str] = field(default_factory=set)
    equipped_slots: list[str | None] = field(default_factory=lambda: [None, None])

    def __post_init__(self) -> None:
        if len(self.equipped_slots) != 2:
            raise ValueError("Exactly two module slots are required.")
        self._sanitize()

    def is_crafted(self, module_type: ModuleType | str) -> bool:
        return self._value(module_type) in self.crafted_modules

    def can_afford(
        self,
        module_type: ModuleType | str,
        materials: Mapping[str, int],
    ) -> bool:
        definition = self.definition(module_type)
        return all(materials.get(name, 0) >= amount for name, amount in definition.recipe.items())

    def missing_materials(
        self,
        module_type: ModuleType | str,
        materials: Mapping[str, int],
    ) -> dict[str, int]:
        definition = self.definition(module_type)
        return {
            name: amount - materials.get(name, 0)
            for name, amount in definition.recipe.items()
            if materials.get(name, 0) < amount
        }

    def craft(
        self,
        module_type: ModuleType | str,
        materials: MutableMapping[str, int],
    ) -> CraftResult:
        definition = self.definition(module_type)
        value = definition.module_type.value
        if value in self.crafted_modules:
            return CraftResult(False, "already_crafted", definition.module_type)
        if not self.can_afford(definition.module_type, materials):
            return CraftResult(False, "insufficient_materials", definition.module_type)
        spent: dict[str, int] = {}
        for name, amount in definition.recipe.items():
            materials[name] = materials.get(name, 0) - amount
            spent[name] = amount
        self.crafted_modules.add(value)
        return CraftResult(True, "crafted", definition.module_type, spent)

    def equip(self, module_type: ModuleType | str, slot_index: int) -> bool:
        if slot_index not in (0, 1):
            raise IndexError("Module slot index must be 0 or 1.")
        value = self._value(module_type)
        if value not in self.crafted_modules:
            return False
        for index, equipped in enumerate(self.equipped_slots):
            if equipped == value:
                self.equipped_slots[index] = None
        self.equipped_slots[slot_index] = value
        return True

    def unequip(self, slot_index: int) -> str | None:
        if slot_index not in (0, 1):
            raise IndexError("Module slot index must be 0 or 1.")
        previous = self.equipped_slots[slot_index]
        self.equipped_slots[slot_index] = None
        return previous

    def toggle_equip(self, module_type: ModuleType | str, slot_index: int) -> str:
        value = self._value(module_type)
        if value not in self.crafted_modules:
            return "not_crafted"
        if self.equipped_slots[slot_index] == value:
            self.unequip(slot_index)
            return "unequipped"
        self.equip(value, slot_index)
        return "equipped"

    def equipped_slot_for(self, module_type: ModuleType | str) -> int | None:
        value = self._value(module_type)
        try:
            return self.equipped_slots.index(value)
        except ValueError:
            return None

    def definition(self, module_type: ModuleType | str) -> ModuleDefinition:
        if isinstance(module_type, ModuleType):
            return MODULE_BY_TYPE[module_type]
        try:
            return MODULE_BY_VALUE[module_type]
        except KeyError as exc:
            raise ValueError(f"Unknown module type: {module_type}") from exc

    def snapshot(self) -> dict[str, object]:
        return {
            "crafted": sorted(self.crafted_modules),
            "slots": list(self.equipped_slots),
        }

    @staticmethod
    def _value(module_type: ModuleType | str) -> str:
        if isinstance(module_type, ModuleType):
            return module_type.value
        if module_type not in MODULE_BY_VALUE:
            raise ValueError(f"Unknown module type: {module_type}")
        return module_type

    def _sanitize(self) -> None:
        self.crafted_modules.intersection_update(MODULE_BY_VALUE)
        seen: set[str] = set()
        for index, value in enumerate(self.equipped_slots):
            if value is None:
                continue
            if value not in self.crafted_modules or value not in MODULE_BY_VALUE or value in seen:
                self.equipped_slots[index] = None
                continue
            seen.add(value)
