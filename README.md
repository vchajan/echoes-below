# Echoes Below

Echoes Below is planned as a school Pygame project: a 2D top-down stealth exploration roguelite about navigating dark underground floors with a scan mechanic.

This repository is currently complete through Phase 10. It contains the application shell, state system, cached asset pipeline, seeded and validated procedural floors, player movement, camera and collisions, dynamic doors, fixed-origin DDA scan occlusion, fading static traces, generic object echoes, moving invisible creatures, threat-aware creature AI, deterministic material pickups, elevator scan states, death/restart flow, score/material counters, tests and headless preview tools. Objectives, crafting and active modules are later phases.

## Setup

Use Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

Start the current application shell with:

```powershell
python main.py
```

## Current Controls

- Up and Down: move menu selection
- Enter or Space: confirm selected menu item
- Mouse: hover and click buttons
- WASD or arrow keys: move the player during PLAYING
- Escape: skip splash, pause during PLAYING, resume from pause or return from How to Play
- Backspace: return from How to Play
- F2: toggle the camera-space debug overlay during PLAYING
- F3: toggle scan, snapshot and AI diagnostics during PLAYING
- F6/F7/F8: door debug controls, only while F2 debug mode is active

Planned gameplay controls:

- Space: scan
- F: interact
- Q: module slot 1
- E: module slot 2
- Escape: pause
- F2: debug view
- F3: performance overlay

## Tests

```powershell
python tools/generate_placeholder_assets.py
python -m unittest discover -s tests
python tools/smoke_test.py
python tools/asset_preview.py --headless
python tools/generation_sweep.py
python tools/generation_test.py
python tools/generation_preview.py --seed 12345 --floor 1 --headless
python tools/generation_preview.py --seed 12345 --floor 2 --headless
python tools/generation_preview.py --seed 12345 --floor 3 --headless
python tools/player_preview.py --seed 12345 --headless
python tools/door_preview.py --seed 12345 --floor 2 --headless
python tools/snapshot_preview.py --seed 12345 --floor 1 --headless
python tools/creature_preview.py --seed 12345 --floor 1 --headless
python tools/ai_preview.py --seed 12345 --floor 1 --headless
python -m py_compile main.py
python -c "import main; print('main import ok')"
```

Floor objectives, crafting, active modules and final HUD scoring remain later phases.

## Assets

Placeholder art is generated with Pygame only:

```powershell
python tools/generate_placeholder_assets.py
```

Generated assets live under:

```text
assets/
|-- audio/
|-- effects/
|-- objects/
|-- sprites/
|-- tiles/
|-- ui/
```

The placeholders are committed because the current application shell uses them for visual verification. They can be replaced later with final PNG files as long as the same paths and documented spritesheet grids are preserved.

Spritesheet metadata is centralised in `game/assets.py`. The current grids are:

- `assets/tiles/industrial_tileset.png`: 48 x 48 tiles in a regular 6-column grid.
- `assets/sprites/player_sheet.png`: 48 x 64 frames, 4 direction rows, 5 frames per row.
- `assets/sprites/creature_sheet.png`: 64 x 64 movement frames.
- Door, objective, material and effect sheets use regular grids documented in the metadata.

`AssetManager` derives paths from the project root, caches loaded images, spritesheet frames, scaled images, flipped frames and outline frames, and uses visible fallback surfaces for missing images. Missing sounds return a no-op sound object, so absent audio files or unavailable mixer support do not crash the game.

Create a developer preview with:

```powershell
python tools/asset_preview.py --headless
```

The preview is saved to `artifacts/asset_preview.png`.

## Procedural Generation And Playable View

Phase 4 uses a deterministic room-and-corridor floor generator with bounded retries. It uses local `random.Random` instances only. A supplied base seed, floor number and generator configuration produce the same successful attempt index, derived attempt seed, room rectangles, graph edges, corridors, tile grid, player spawn, elevator tile and candidate lists.

New Run now generates Floor 1 and creates a physical player at the validated spawn tile. The map is rendered at full size with 48 px tiles, and the screen shows a camera viewport centered on the player and clamped to the generated world bounds.

The player uses the Phase 2 spritesheet animations for idle and walking in all four directions. Movement uses delta time, normalizes diagonal input and resolves against a smaller lower-body collision rectangle so the sprite can be taller than its floor footprint.

Movement collision uses the central tile metadata in `game/world/tiles.py`. `VOID`, `WALL`, `DAMAGED_WALL`, `OBSTACLE` and `PILLAR` block movement; floor variants, doorways and elevator floor tiles are walkable. Out-of-bounds map space is always blocking. Axis-separated resolution allows sliding along free axes and uses bounded substeps to avoid tunnelling on slower frames.

Normal PLAYING mode is intentionally dark as a temporary Phase 5 visibility stand-in. A cached local glow around the player reveals only the immediate area. This is not the final scan mechanic; fixed-origin scan traces and occlusion are still future work.

F2 debug mode disables the heavy darkness and draws camera-space diagnostics: tile grid, room boundaries and IDs, graph links, doorway candidates, creature candidates, objective candidates, spawn/elevator markers, player visual rect, player collision rect and current tile.

## Dynamic Doors

Phase 6 creates dynamic door entities from validated doorway metadata without changing the static tile grid. Doors render separately from the cached floor surface and supply temporary blockers for movement, future scan raycasting, line of sight and future creature navigation.

Door types:

- Powered doors are automatic doors. They open when the player enters the approach area while floor power is available, stay open while the approach or doorway is occupied, and close after a delay when clear.
- Security doors start locked, block movement and future scan, and expose an unlock API. Once unlocked, they behave like powered automatic doors.
- Containment doors start locked, remain distinct from security doors, expose a containment unlock API, and then behave as heavier powered doors.

Temporary Phase 6 behavior: Floor 1 uses powered doors only so the current playable preview remains traversable. Floor 2 exposes a deterministic security-door candidate, and Floor 3 exposes a containment-door candidate for later objective phases.

Closed, locked, opening, closing and wedged-closed doors block player movement, future scan, future line of sight and future creature navigation. Open and wedged-open doors block none of those purposes. Closing begins only after the doorway is clear, so doors do not push or trap the player.

Debug controls are active only in F2 mode:

- F6: toggle the nearest door open or closed.
- F7: toggle the nearest security or containment door locked or unlocked.
- F8: toggle temporary floor power.

Validation now checks walkable connectivity, elevator reachability, graph connectivity, graph cycle rank, safe player/elevator placement, obstacle connectivity, doorway validity, corridor continuity and future content candidates. Floor 2 and Floor 3 require at least one graph cycle. Floor 3 prefers two loops when room count allows it.

Current floor profiles:

- Floor 1: 8 to 10 rooms, one preferred loop, lighter obstacles and at least one creature candidate.
- Floor 2: 11 to 13 rooms, required loop, more candidates for security-door/keycard/relay planning and at least two creature candidates.
- Floor 3: 13 to 16 rooms, required loop, two preferred loops, containment candidates and at least two creature candidates.

Tile types are centralised in `game/world/tiles.py`:

- `VOID`
- `FLOOR`
- `FLOOR_ALT`
- `DAMAGED_FLOOR`
- `WALL`
- `DAMAGED_WALL`
- `OBSTACLE`
- `PILLAR`
- `DOORWAY`
- `ELEVATOR_FLOOR`

Each tile definition exposes walkability, movement blocking, scan blocking and tileset asset index.

Create a headless generation preview with:

```powershell
python tools/generation_preview.py --seed 12345 --floor 1 --headless
python tools/generation_preview.py --seed 12345 --floor 2 --headless
python tools/generation_preview.py --seed 12345 --floor 3 --headless
```

The previews are saved to `artifacts/generation_preview_12345_floor1.png`, `artifacts/generation_preview_12345_floor2.png` and `artifacts/generation_preview_12345_floor3.png`.

Preview player movement and camera behavior with:

```powershell
python tools/player_preview.py --seed 12345
python tools/player_preview.py --seed 12345 --headless
```

Headless mode saves `artifacts/player_preview_12345_start.png` and `artifacts/player_preview_12345_moved.png`.

Preview door animation, collision and debug information with:

```powershell
python tools/door_preview.py --seed 12345 --floor 2
python tools/door_preview.py --seed 12345 --floor 2 --headless
```

Headless mode saves `artifacts/door_preview_12345_floor2_closed.png` and `artifacts/door_preview_12345_floor2_open.png`.

Run the Phase 4 stress test with:

```powershell
python tools/generation_test.py
```

It generates 150 seeds for each of Floors 1, 2 and 3, validates each floor, and checks deterministic regeneration on a subset.

## Documentation

- `AGENTS.md`: permanent project rules.
- `GAME_DESIGN.md`: game concept, mechanics, floors and player flow.
- `IMPLEMENTATION_PLAN.md`: planned architecture, phases, tests and risks.
- `PROGRESS.md`: implementation checklist.

## Fixed-Origin Scan And Occlusion

Phase 7 implements the central scan mechanic. Press **Space** during PLAYING to emit a scan from the player's exact world position at that moment. The origin remains fixed even if the player and camera move while the wave expands.

The scan performs one 360-degree tile-grid DDA raycast at activation time using 720 configurable rays. Each ray stops at the first static blocker (`VOID`, walls, damaged walls, machinery obstacles or pillars) or a dynamic closed/locked door. Open and wedged-open doors allow the ray to continue. Door state is sampled when the scan starts, so opening a door later does not change an already calculated historical scan.

The circular wave is only a visual front. Geometry appears when the front reaches each stored hit distance. Revealed cyan points and safe neighbouring outline segments remain in world coordinates, follow the camera correctly and fade after approximately 3.8 seconds. The distant tile map is almost completely black in normal play; only the small local player glow and scan traces provide information. F2 keeps the bright developer view and displays sampled ray paths, hit categories and blocker IDs.

The scan has a short cooldown but no battery or charges. F3 toggles a diagnostics panel showing FPS, frame time, ray count, raw/deduplicated hit counts, active traces, segment count and raycast timing.

Preview and benchmark commands:

```powershell
python tools/scan_preview.py --seed 12345 --floor 2
python tools/scan_preview.py --seed 12345 --floor 2 --headless
python tools/scan_benchmark.py
```

Headless preview output:

- `artifacts/scan_preview_12345_floor2_early.png`
- `artifacts/scan_preview_12345_floor2_late.png`
- `artifacts/scan_preview_12345_floor2_camera_shift.png`

The benchmark measures only static scan computation. It does not claim graphical 60 FPS; interactive rendering still requires manual verification on the target computer.
## Scan-Detectable Objects, Materials And Elevator

Phase 8 adds a generic echo-snapshot layer for objects that exist in the world but are hidden during normal darkness. The scan wave evaluates an object only when the front reaches its current distance from the fixed origin. It then performs the same line-of-sight test used by raycasting. A visible object produces one copied outline frame for that scan; the echo stays at the captured world position, fades independently and does not follow the source object.

Procedural floors now receive deterministic optional materials:

- `scrap`
- `circuit`
- `power_cell`

They are placed on validated walkable tiles away from the spawn, elevator and doorways. Collection is collision-based, idempotent, adds five points and updates the run counters shown in the HUD. Their normal sprites remain hidden outside F2 debug mode; a tiny contact hint appears only at very close range.

The elevator is a scan-detectable entity with locked, unlocked and active states. Its state controls the captured outline colour and animation frame. Final floor-transition interaction is implemented in later objective phases.

Create deterministic object-echo screenshots with:

```powershell
python tools/snapshot_preview.py --seed 12345 --floor 1 --headless
```

Create deterministic creature echo screenshots with:

```powershell
python tools/creature_preview.py --seed 12345 --floor 1 --headless
```

The tools save detected, collected, fading and expired snapshots under `artifacts/`, so these systems can be checked without searching manually through a random floor.


## Invisible Creatures And Dynamic Echoes

Phase 9 added moving creatures that are physically present and lethal but are never rendered during normal play. Walls, obstacles and closed doors block their movement. Phase 10 replaces the simple patrol-only behaviour in active runs with a threat-aware AI state machine while preserving the same physical creature body, collision and snapshot contract.

A creature is not part of the static 720-ray result. During every active scan, the dynamic echo system compares the previous/current wave radius with the creature's previous/current radial distance. When the moving creature and the expanding front intersect, the game performs the same line-of-sight check used by scan raycasting. Walls, pillars, corners and closed doors prevent capture.

A successful detection creates a copied cyan outline at the exact position, facing and animation frame from that instant. The echo remains stationary for about 1.5 seconds while the real creature continues moving invisibly. Each creature can create at most one echo per scan; a later scan may reveal its new position.

Touching a creature immediately ends the one-life run. The death screen displays floor, elapsed time, score and seed. `Retry Same Seed` reconstructs the same procedural floor and deterministic creature spawn, while `New Run` chooses a new seed. Both routes clear old creatures, scan fronts, traces and snapshots.

Debug and preview:

```powershell
python tools/creature_preview.py --seed 12345 --floor 1
python tools/creature_preview.py --seed 12345 --floor 1 --headless
```

F2 reveals the real creature, its collision Rect and AI target/path information. F3 adds creature, creature-echo and AI counters. Headless preview output includes debug, before-scan, snapshot, moved-creature and death screenshots in `artifacts/`.

## Creature AI, Threat Events And Pathfinding

Phase 10 adds the authoritative creature states `PATROL`, `INVESTIGATE`, `SEARCH`, `CHASE` and `STUNNED` in `game/systems/creature_ai.py`.

- `PATROL`: default invisible movement. Each creature chooses deterministic reachable patrol targets and reuses paths instead of recalculating every frame.
- `INVESTIGATE`: entered when a relevant shared threat event is selected. A player scan creates exactly one `PLAYER_SCAN` threat at the fixed scan origin, not one event per ray or trace.
- `SEARCH`: uncertainty around an investigated point or last known player position. The creature samples nearby valid search points for a limited duration, then returns to patrol.
- `CHASE`: entered only through direct perception: the player must be within detection range and line of sight must pass through the same wall, corner and dynamic-door blocker rules as scan raycasting. If sight is lost, the creature follows the last known player position briefly, then searches.
- `STUNNED`: implemented as an API preparation state for later Shock Pulse gameplay. Direct calls such as `creature.stun(duration)` stop movement and preserve collision danger, but no module input or inventory is implemented yet.

Threat events are stored in `ThreatEventSystem`. The source types are `PLAYER_SCAN`, `GENERATOR`, `RELAY`, `ECHO_CORE`, `SHOCK_PULSE`, `DECOY_BEACON` and `SCAN_PROJECTOR`; only `PLAYER_SCAN` currently creates gameplay events. Relevance uses a simple strength, age-decay and distance formula with hearing-radius filtering and hysteresis so creatures do not switch targets for tiny differences.

Tile navigation lives in `game/world/navigation.py` and uses deterministic four-way A*. It respects map bounds, walls, obstacles, pillars and the existing dynamic door blocker registry. Closed, locked and wedged-closed doors block paths and line of sight; open and wedged-open doors allow them. Each AI stores pathfinding timers and counters so A* is not run every frame.

Debug and preview:

```powershell
python tools/ai_preview.py --seed 12345 --floor 1
python tools/ai_preview.py --seed 12345 --floor 1 --headless
```

Headless AI preview saves:

- `artifacts/ai_preview_12345_floor1_patrol.png`
- `artifacts/ai_preview_12345_floor1_investigate.png`
- `artifacts/ai_preview_12345_floor1_search.png`
- `artifacts/ai_preview_12345_floor1_chase.png`
- `artifacts/ai_preview_12345_floor1_stunned.png`

F2 now draws creature state, previous state, transition reason, current target, path tiles, selected threat, search centre, last known player marker and recent line-of-sight result. F3 reports state counts, active threat counts, threat source counts, pathfinding calls per second, path timing, active path nodes, perception checks per second and stunned creature count.
