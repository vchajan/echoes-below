# Echoes Below Implementation Plan

## Proposed Folder Structure

The project root will eventually contain `main.py`, this documentation, `requirements.txt`, and a small `src/` package. No gameplay files are created during Phase 0.

Planned structure:

```text
.
|-- main.py
|-- src/
|   |-- game.py
|   |-- states.py
|   |-- settings.py
|   |-- assets.py
|   |-- world/
|   |   |-- generation.py
|   |   |-- tilemap.py
|   |   |-- objectives.py
|   |-- entities/
|   |   |-- player.py
|   |   |-- creature.py
|   |   |-- snapshots.py
|   |-- systems/
|   |   |-- scan.py
|   |   |-- collision.py
|   |   |-- modules.py
|   |   |-- crafting.py
|   |   |-- scoring.py
|   |-- ui/
|   |   |-- screens.py
|   |   |-- hud.py
|   |-- tests/
|       |-- test_generation.py
|       |-- test_scan.py
|       |-- test_objectives.py
|-- assets/
|   |-- images/
|   |-- audio/
|   |-- fonts/
```

## Core Classes And Data Flow

- `Game`: owns Pygame setup, state switching, the Event -> Update -> Render loop, delta time clamping and global services.
- `State` classes: splash, menu, how-to-play, playing, pause, workshop, floor transition, death and victory screens.
- `AssetManager`: loads images, spritesheets, fonts and sounds before gameplay use; returns safe placeholders or silent fallbacks when assets are missing.
- `RunManager`: owns seed, floor index, materials, score, active module slots, objective progress and retry/new-run decisions.
- `WorldGenerator`: creates deterministic room-and-corridor maps, validates connectivity and objective ordering, and retries invalid layouts in a controlled way.
- `TileMap`: stores floor, wall, obstacle, door and objective tiles; answers movement and scan blocking queries.
- `Player`: handles movement input, interaction hold progress, module activation and collision bounds.
- `Creature`: moves continuously in darkness, reacts to threat targets, decoys and projectors, and triggers death on contact.
- `ScanSystem`: stores scan origins, static ray traces, visual scan fronts, occlusion results and creature snapshots.
- `ModuleSystem`: implements Shock Pulse, Decoy Beacon, Door Wedge and Scan Projector as active actions with cooldowns.
- `HUD` and screen UI classes: render score, objectives, module cooldowns, workshop choices, pause, death and victory choices.

Data flows from input events into the current state, then into player/module actions, world/objective updates, creature updates, collision checks, score updates and rendering. Rendering reads state only; it does not load assets or perform expensive generation.

## Current Architecture Notes

The implemented project uses the `game/` package rather than the early `src/` placeholder tree. Phase 6 door and blocker code lives in:

- `game/entities/door.py`: dynamic door type, state, animation, timers, collision and lock/wedge APIs.
- `game/world/blockers.py`: dynamic blocker registry for movement, future scan, future line of sight and future creature navigation queries.
- `game/world/door_generation.py`: deterministic conversion from validated doorway metadata to dynamic doors.
- `game/world/navigation.py`: small future-facing navigation helpers.

Doors are rendered separately from the cached static floor surface. The static tile grid remains walkable at doorway tiles; closed or locked doors provide temporary dynamic blockers instead of rewriting tile data.

## Implementation Order

1. Phase 0: create planning docs, requirements and Git checkpoint.
2. Phase 1: minimal Pygame shell with splash, automatic menu transition, Play button, state manager, pause, death and victory placeholders.
3. Phase 2: asset manager, placeholder-safe loading, spritesheet animation support, tiles and basic HUD with visible score.
4. Phase 3: deterministic room-and-corridor generation with validation tests and debug world view.
5. Phase 4: player movement, camera, tile collisions, doors, interactions and floor objectives.
6. Phase 5: scan system with fixed origin, cached static raycasting, visual expansion, fade traces and no reveal through blockers.
7. Phase 6: dynamic doors and shared blocker interfaces.
8. Phase 7: fixed-origin DDA scan and static traces.
9. Phase 8: generic object echoes, materials and elevator scan states.
10. Phase 9: moving invisible creature, dynamic creature echoes, death and restart.
11. Phase 10: threat-aware creature AI and pathfinding.
12. Phases 11-13: three floor objectives, extraction and victory.
13. Phases 14-16: workshop, recipes and four active modules.
14. Phases 17-20: HUD/effects, performance, QA and submission documentation.

## Automated Tests

- Generation determinism: same seed and floor produce the same map and placements.
- Generation validity: maps are connected, contain required rooms, include later-floor loops and place objectives in valid order.
- Locked-door safety: required keys are not placed behind their own locked doors.
- Spawn safety: player and creature spawns are on valid walkable tiles and not too close.
- Scan occlusion: rays stop at walls, obstacles and closed doors; hidden areas behind corners are not revealed.
- Module behaviour: cooldowns, one-active limits, line-of-sight restrictions and expiry timers work.
- State flow: splash to menu, play to run, pause resume, death retry/new seed/menu and victory.

Manual checks remain important for feel: movement, scan readability, creature tension, workshop clarity and oral-defence simplicity.

## Performance Risks

- Scan raycasting can become expensive if recalculated every frame. Static traces must be calculated once per scan and then rendered/faded cheaply.
- Sprite transforms, outlines, masks and scaled images must be cached instead of regenerated every frame.
- Procedural generation must have a bounded retry count and a simple fallback plan.
- Debug overlays must be optional and inexpensive when hidden.
- Asset and audio failures must use placeholders or silence instead of crashing.

## Fallback Priorities

If time becomes limited, preserve the central scan, stealth, three-floor objective flow, death/victory states and school-visible features first. Simplify art, creature variety, workshop presentation and balance before cutting core scan occlusion, deterministic generation, collisions, animations or state flow.

## Phase 7 Scan Architecture Notes

The implemented scan architecture lives in `game/systems/`:

- `raycasting.py` contains reusable tile-grid DDA ray traversal, exact first-hit data, dynamic-door rectangle intersection, conservative zero-width corner handling and point-to-point line of sight.
- `scan.py` contains the fixed-origin wave, cooldown, historical static hits, fading world-space traces, safe contour connection rules, bounded scan threat-event hooks, diagnostics and a cached viewport renderer.

Static geometry is raycast once when Space is pressed, never every frame. The active wave only compares its previous and current radius against sorted hit distances. Dynamic doors use the existing `DynamicBlockerRegistry`, so movement, scan and line-of-sight passability share the same authoritative door state. Future moving-creature detection will use the reusable line-of-sight function at the moment the wave crosses each creature rather than precomputing creature positions.
## Phase 8 Object Echo Architecture Notes

- `game/entities/scan_objects.py` defines animated scan-detectable materials and the elevator entity. It exposes fixed IDs, world positions and cached current outline frames without coupling entities to the main application.
- `game/systems/snapshots.py` owns entity-front crossing checks, one-evaluation-per-scan tracking, line-of-sight validation, copied fixed-position echoes, fade/expiry and rendering.
- `game/world/content_generation.py` deterministically places materials into validated candidate rooms and creates the elevator from generated-floor metadata.
- `ScanSystem.last_wave_step` exposes the previous/current wave annulus for one update, allowing object and future creature detection without recalculating static rays.
- Run material counters remain simple dictionary data in `PlaceholderRun`; the later workshop can consume them without changing pickup behaviour.


## Phase 9 Creature Architecture Notes

- `game/entities/creature.py` owns deterministic patrol selection, cached animation/outline frames, bounded collision movement and simple BFS path generation. Pathfinding is event-driven rather than per-frame.
- `game/systems/snapshots.py` compares relative wave/target distance between updates, allowing both front-overtakes-target and target-crosses-front cases without adding creatures to static raycasts.
- Current line of sight always uses `game/systems/raycasting.py` and the authoritative `DynamicBlockerRegistry`.
- `Game.update_gameplay` updates doors with player and creature occupancy, moves creatures, moves the player, checks contact at safe points, then advances scans and captures echoes.
- Normal rendering excludes real creatures. F2 is the only world view that renders them directly; normal play receives copied snapshots only.
- Phase 10 will layer threat events and AI states over this stable movement/snapshot foundation rather than replacing it.
