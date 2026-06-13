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
    cooldown: float


MODULE_DEFINITIONS: tuple[ModuleDefinition, ...] = (
    ModuleDefinition(
        ModuleType.SHOCK_PULSE,
        "Shock Pulse",
        "PULSE",
        "Stuns nearby creatures with direct line of sight.",
        {"circuit": 1, "power_cell": 1},
        "shock_pulse_ready",
        8.0,
    ),
    ModuleDefinition(
        ModuleType.DECOY_BEACON,
        "Decoy Beacon",
        "DECOY",
        "Creates a temporary false signal that attracts creatures.",
        {"scrap": 1, "circuit": 1},
        "decoy_beacon_ready",
        12.0,
    ),
    ModuleDefinition(
        ModuleType.DOOR_WEDGE,
        "Door Wedge",
        "WEDGE",
        "Temporarily locks the nearest open or closed door in place.",
        {"scrap": 2},
        "door_wedge_ready",
        10.0,
    ),
    ModuleDefinition(
        ModuleType.SCAN_PROJECTOR,
        "Scan Projector",
        "PROJECTOR",
        "Deploys a remote device that emits repeated scans.",
        {"scrap": 1, "circuit": 1, "power_cell": 1},
        "scan_projector_ready",
        15.0,
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
class ModuleRuntimeState:
    """Run-level module cooldown state.

    Cooldowns intentionally survive floor transitions and workshop visits. A new
    run or Retry Same Seed creates a fresh instance, clearing all cooldowns.
    Deployed world objects live in ModuleEffectSystem and are floor-specific.
    """

    cooldown_remaining: dict[str, float] = field(
        default_factory=lambda: {definition.module_type.value: 0.0 for definition in MODULE_DEFINITIONS}
    )
    activation_counts: dict[str, int] = field(
        default_factory=lambda: {definition.module_type.value: 0 for definition in MODULE_DEFINITIONS}
    )

    def update(self, dt: float) -> None:
        dt = max(0.0, float(dt))
        for key in tuple(self.cooldown_remaining):
            self.cooldown_remaining[key] = max(0.0, self.cooldown_remaining[key] - dt)

    def is_ready(self, module_type: ModuleType | str) -> bool:
        return self.remaining(module_type) <= 0.0

    def remaining(self, module_type: ModuleType | str) -> float:
        value = self._value(module_type)
        return max(0.0, float(self.cooldown_remaining.get(value, 0.0)))

    def cooldown_fraction(self, module_type: ModuleType | str) -> float:
        value = self._value(module_type)
        total = MODULE_BY_VALUE[value].cooldown
        if total <= 0.0:
            return 0.0
        return max(0.0, min(1.0, self.remaining(value) / total))

    def start_cooldown(self, module_type: ModuleType | str) -> None:
        value = self._value(module_type)
        self.cooldown_remaining[value] = MODULE_BY_VALUE[value].cooldown
        self.activation_counts[value] = self.activation_counts.get(value, 0) + 1

    def clear(self) -> None:
        for value in MODULE_BY_VALUE:
            self.cooldown_remaining[value] = 0.0
            self.activation_counts[value] = 0

    def snapshot(self) -> dict[str, object]:
        return {
            "cooldowns": dict(self.cooldown_remaining),
            "activations": dict(self.activation_counts),
        }

    @staticmethod
    def _value(module_type: ModuleType | str) -> str:
        if isinstance(module_type, ModuleType):
            return module_type.value
        if module_type not in MODULE_BY_VALUE:
            raise ValueError(f"Unknown module type: {module_type}")
        return module_type


@dataclass
class ModuleLoadout:
    """Run-level ownership and two-slot equipment state."""

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
