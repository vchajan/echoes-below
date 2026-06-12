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
12. Phase 11: Floor 1 restore-power objective, generator repair, power activation, elevator completion and controlled workshop transition.
13. Phases 12-13: Floor 2 security objective, Floor 3 extraction and victory.
14. Phases 14-16: workshop, recipes and four active modules.
15. Phases 17-20: HUD/effects, performance, QA and submission documentation.

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
- Phase 10 layers threat events and AI states over this stable movement/snapshot foundation rather than replacing it.

## Phase 10 Creature AI Architecture Notes

- `game/systems/threat_events.py` owns temporary sound/disturbance events. It supports all planned source types; active gameplay events currently come from `PLAYER_SCAN` and Phase 11 `GENERATOR` activation.
- `game/systems/creature_ai.py` owns the `CreatureState` enum, state transitions, timers, selected threat, patrol/investigation/search/chase targets, last-known player memory, stun state, perception cadence and pathfinding diagnostics.
- `game/world/navigation.py` now contains deterministic four-directional A* helpers that respect static floor walkability and `DynamicBlockerRegistry` door semantics.
- `Creature` remains responsible for physical position, animation, collision Rects, bounded movement and scan outlines. It delegates decision-making only when an AI object is attached.
- `Game` owns one shared `ThreatEventSystem`, creates per-creature deterministic AI instances during floor preparation, emits exactly one `PLAYER_SCAN` event after a successful fixed-origin scan, and clears AI/threat state on retry, new run, main menu and floor cleanup.
- F2 and F3 read existing AI diagnostics. They do not perform extra pathfinding or alter gameplay state.

## Phase 11 Floor Objective Architecture Notes

- `game/entities/objectives.py` defines the scan-detectable generator components and generator entity. These own stable IDs, room/tile metadata, cached animations, collision/interaction Rects and outline capture without knowing about run state.
- `game/systems/floor_objectives.py` owns `Floor1ObjectiveState`, deterministic placement, validation metadata, component collection, hold-F repair progress, contextual messages, generator activation and elevator completion results.
- `Game.prepare_generated_floor` creates Floor 1 objective content once after static content and doors exist. It reserves material, door, creature, spawn and elevator tiles so objectives do not overlap existing content.
- Objective placement uses existing generated room-distance groups and deterministic candidate ordering. Reachability checks use `navigation.astar_path` with `BlockerPurpose.MOVEMENT`, so components and the generator must be reachable while Floor 1 powered doors are still closed.
- `Game.update_gameplay` passes continuous F-state into the objective system after scan snapshots are evaluated, preserving historical component echoes before collision pickup removes the source entity.
- Generator repair emits exactly one strong `GENERATOR` threat event through `ThreatEventSystem`, sets Floor 1 power active, updates powered doors, unlocks the existing elevator entity and leaves security/containment doors for later phases.
- Floor completion clears floor runtime objects, scans, snapshots, objectives, doors, creatures and threat events while preserving run-level seed, score, elapsed time, restart count and material counters for the WORKSHOP placeholder.
