# Echoes Below Game Design

## Concept

Echoes Below is a 2D top-down stealth exploration roguelite for Pygame. The player descends through three procedurally generated underground floors hidden mostly in darkness. The main tool is a scan that briefly reveals reachable surfaces and creates fading snapshots of creatures that were visible at the moment the scan reached them.

The game must visibly include a splash screen, automatic transition to a menu, a menu with a Play button, several sprite types, spritesheets, tiles, animations, keyboard input, collisions, reactions to collisions, visible point counting, victory and game-over states.

## Core Gameplay Loop

1. Start at the splash screen, then transition automatically to the main menu.
2. Begin a run from the Play button.
3. Explore a dark procedural floor using movement, interaction and scans.
4. Find floor objectives while avoiding invisible moving creatures.
5. Return to the elevator after each floor objective is complete.
6. Use the workshop between floors to craft or equip active modules.
7. Win by extracting the Echo Core on Floor 3 and returning to the elevator.

The player has one life. Contact with a creature immediately ends the run. After death, the player can start a new run with a new seed, retry the same seed, or return to the main menu.

## States And Controls

Game states:

- `SPLASH`
- `MAIN_MENU`
- `HOW_TO_PLAY`
- `PLAYING`
- `PAUSED`
- `WORKSHOP`
- `FLOOR_TRANSITION`
- `DEATH`
- `VICTORY`

Controls:

- WASD or arrow keys: move
- Space: normal scan
- F: interact
- Q: module slot 1
- E: module slot 2
- Escape: pause
- F2: debug world view
- F3: performance overlay

## Floors

Floor 1, Restore Power:

- Find two generator components.
- Reach the generator.
- Hold the interaction key to repair it.
- Survive the noise event.
- Return to the unlocked elevator.

Floor 2, Security Override:

- Find a keycard.
- Open a security door.
- Activate two relay terminals.
- Each relay produces a strong threat event.
- Return to the elevator.

Floor 3, Echo Core Extraction:

- Find a containment component.
- Install it at the containment control.
- Open the containment section.
- Take the Echo Core.
- Enter an extraction phase with more aggressive creatures.
- Return to the elevator to win.

## Scan

The scan begins from a fixed origin and expands visually over time. It reveals only directly reachable surfaces. Walls, obstacles and closed doors block the scan. Nothing behind a wall, obstacle or corner may be revealed.

The planned implementation uses tile-grid DDA raycasting or an equivalently efficient algorithm with about 720 configurable rays. Static raycasting happens once per scan, not every frame. Each ray stops at the first blocking wall, obstacle or closed door. Static scan traces fade after about 3.5 to 4 seconds.

When an expanding scan reaches a creature and there is direct line of sight, the game creates a fading snapshot at the creature's exact position and animation frame at that moment. The snapshot remains stationary. The real creature keeps moving invisibly. Creature snapshots fade after about 1.3 to 1.6 seconds.

User-facing text should call this mechanic only a scan.

## Creature Behaviour

Creatures move continuously in darkness. They are not killed by modules or the player. They react to threat events, decoys, projectors and objective noise. Touching a creature causes immediate death. Some modules can redirect or temporarily stun creatures, but no system should turn the game into combat.

## Procedural Generation

Each run uses seeded room-and-corridor generation. The same seed must produce the same floor layout and placements.

The generator must create connected maps, several rooms and corridors, at least one additional loop on later floors, valid objective ordering, safe player and creature spawns, and controlled retries for invalid maps. It must avoid placing a required key behind its own locked door.

Suggested room and creature counts:

- Floor 1: 8 to 10 meaningful rooms and one creature.
- Floor 2: 11 to 13 meaningful rooms and two creatures.
- Floor 3: 13 to 16 meaningful rooms and two creatures, optionally a third after extraction.

## Crafting And Modules

Workshops open between Floors 1 and 2 and between Floors 2 and 3. Materials are scrap, circuit and power_cell. The player has two active module slots: Q for slot 1 and E for slot 2. Normal scan uses Space and does not occupy a slot.

Mandatory modules:

- Shock Pulse: short-range pulse around the player. It stuns visible nearby creatures for about 2 seconds, cannot pass through walls, produces a threat event and has a cooldown.
- Decoy Beacon: deploys at the player position, emits repeated false signals for about 7 to 9 seconds, draws creatures to investigate it, allows only one active beacon and has a cooldown.
- Door Wedge: interacts with the nearest valid door and temporarily locks it in its current open or closed state. A closed wedged door blocks movement and scan. An open wedged door blocks neither. It expires after about 7 to 10 seconds.
- Scan Projector: places about two tiles ahead on valid floor. After a short delay, it performs a scan from its own position using the same occlusion rules as the normal scan. Creatures investigate its position. Only one active projector may exist and it has a cooldown.

## Score, Victory And Game Over

Score exists only to satisfy the assignment requirement for visible point counting. It must not control crafting, progression or difficulty. Victory occurs after the player takes the Echo Core, survives extraction and returns to the elevator on Floor 3. Game over occurs immediately on creature contact.
