# Echoes Below Progress

Last updated: 2026-06-12

## Phase Checklist

- [x] Phase 0: Planning documentation, requirements file and repository bootstrap.
- [x] Phase 1: Minimal Pygame shell, splash screen, automatic menu transition and Play button.
- [x] Phase 2: Asset manager, spritesheets, tiles and animation support.
- [x] Phase 3: Seeded room-and-corridor procedural generation.
- [x] Phase 4: Generator validation, graph loops and safe content candidates.
- [x] Phase 5: Player movement, camera, world rendering and tile collisions.
- [x] Phase 6: Dynamic doors and shared blocker interfaces.
- [x] Phase 7: Fixed-origin scan, DDA occlusion and fading static traces.
- [x] Phase 8: Generic object echoes, material pickups and elevator scan states.
- [x] Phase 9: Moving invisible creature, dynamic creature snapshots, death and restart.
- [x] Phase 10: Creature AI, threat events and pathfinding.
- [x] Phase 11: Floor 1 objective and workshop transition.
- [x] Phase 12: Floor 2 security objective.
- [x] Phase 13: Floor 3 Echo Core extraction and victory.
- [x] Phase 14: Workshop crafting, recipes and persistent two-slot module loadout.
- [ ] Phase 15: Shock Pulse and Decoy Beacon.
- [ ] Phase 16: Door Wedge and Scan Projector.
- [ ] Phase 17: Final HUD, scoring and presentation effects.
- [ ] Phase 18: Performance audit and stress testing.
- [ ] Phase 19: Complete QA and regression repair.
- [ ] Phase 20: Final documentation, presentation and submission package.

## Phase 0 Notes

- Created the project rules, design document, implementation plan, progress checklist, requirements file and README.
- No `main.py`, gameplay code, source folders or assets were added in this phase.
- `workshop26.zip` is treated as existing workshop/reference material and is not part of the initial Echoes Below checkpoint.

## Phase 1 Notes

- Baseline before Phase 1: no existing `tests/` directory or automated tests were present.
- Implemented `main.py`, the `game/` package, reusable buttons, placeholder state screens, unit tests, a headless smoke test, and `.gitignore`.
- Added the central Pygame application shell with clean shutdown, optional mixer initialisation, cached fonts, fixed window settings, clamped delta time and Event -> Update -> Render loop.
- Implemented states: `SPLASH`, `MAIN_MENU`, `HOW_TO_PLAY`, `PLAYING`, `PAUSED`, `WORKSHOP`, `FLOOR_TRANSITION`, `DEATH` and `VICTORY`.
- Current limitations: no procedural generation, player movement, scan, creatures, objectives, crafting, assets or final gameplay systems yet.

## Phase 1 Test Results

- `python -m unittest discover -s tests`: passed, 11 tests.
- `python tools/smoke_test.py`: passed.
- `python -m py_compile main.py`: passed.
- `python -c "import main; print('main import ok')"`: passed.

## Phase 2 Notes

- Implemented `game/assets.py` with central spritesheet metadata, path-safe asset loading, image/frame/scale/outline/flip caching, visible image fallbacks and no-op missing audio.
- Implemented `game/animation.py` with reusable delta-time animation playback, looping, non-looping completion and reset support.
- Added deterministic placeholder generation in `tools/generate_placeholder_assets.py`.
- Added `tools/asset_preview.py` with a headless preview export to `artifacts/asset_preview.png`.
- Generated and integrated placeholder tiles, player frames, creature frames, door sheets, objective objects, materials, module icons, UI icons and effect graphics.
- Updated the Phase 1 screens to use preloaded generated assets for splash/menu decoration, How to Play icons, workshop material icons and a non-interactive gameplay placeholder scene.
- Current limitations: artwork is placeholder quality, generated audio files are not included, and procedural generation, player movement, scan raycasting, creatures, objectives and crafting logic are still future phases.

## Phase 2 Generated Files

- Asset directories: `assets/tiles/`, `assets/sprites/`, `assets/objects/`, `assets/ui/`, `assets/effects/` and `assets/audio/`.
- Key spritesheets: `industrial_tileset.png`, `player_sheet.png`, `creature_sheet.png`, door sheets, objective sheets, `materials_sheet.png` and `scan_origin_pulse_sheet.png`.
- UI/effect PNGs: module ready/cooldown icons, scan/material/score/floor icons and replaceable effect graphics.

## Phase 2 Test Results

- `python tools/generate_placeholder_assets.py`: passed.
- `python -m unittest discover -s tests`: passed, 26 tests.
- `python tools/smoke_test.py`: passed.
- `python tools/asset_preview.py --headless`: passed.
- `python -m py_compile main.py`: passed.
- Preview confirmed at `artifacts/asset_preview.png`.

## Phase 3 Notes

- Implemented `game/world/` with central tile definitions, room rectangles, generated floor data, deterministic room-and-corridor generation and temporary overview rendering helpers.
- Added seeded local-RNG generation for room placement, graph edges, L-shaped corridors, wall shells, restrained floor/wall variants, basic obstacles, player spawn, elevator floor, doorway candidates and candidate rooms/spawns for later phases.
- Integrated the generated Floor 1 preview into the `PLAYING` placeholder after New Run. The preview is pre-rendered into a cached surface and uses the Phase 2 industrial tileset.
- Added F2 debug overlays for room rectangles, IDs, centres, graph edges, player spawn, elevator, doorway candidates and creature-spawn candidates.
- Added `tools/generation_preview.py` and `tools/generation_sweep.py`.
- Current limitations reserved for later phases: no player movement, camera, dynamic doors, final objectives, materials placement, scan raycasting, creature AI, combat-like systems, or full Phase 4 connectivity stress validation.

## Phase 3 Created Files

- `game/world/__init__.py`
- `game/world/tiles.py`
- `game/world/room.py`
- `game/world/floor.py`
- `game/world/generator.py`
- `game/world/rendering.py`
- `tests/test_generator.py`
- `tools/generation_preview.py`
- `tools/generation_sweep.py`

## Phase 3 Test Results

- Baseline before editing: `python tools/generate_placeholder_assets.py`, `python -m unittest discover -s tests`, `python tools/smoke_test.py` and `python -m py_compile main.py` all passed.
- `python -m unittest discover -s tests`: passed, 49 tests.
- `python tools/smoke_test.py`: passed.
- `python tools/generation_sweep.py`: passed for 50 Floor 1 seeds.
- `python tools/generation_preview.py --seed 12345 --floor 1 --headless`: passed.
- `python -m py_compile main.py`: passed.
- Preview confirmed at `artifacts/generation_preview_12345_floor1.png`.

## Phase 4 Notes

- Added `game/world/validation.py` with reusable flood fill, path reconstruction, graph checks, cycle rank, spawn/elevator safety, doorway safety, obstacle connectivity checks, corridor diagnostics and structured validation reports.
- Formalised deterministic retries with derived attempt seeds recorded on each generated floor.
- Added explicit Floor 1, Floor 2 and Floor 3 profiles for room counts, required/preferred cycles, obstacle density and candidate minimums.
- Strengthened generation acceptance so final maps require graph connectivity, walkable connectivity, safe player spawn, safe elevator approach, reachable candidates, valid doorways and later-floor cycle rank.
- Expanded generated floor metadata with attempt seed, elevator approach tiles, doorway orientation data, grouped objective-room candidates, scored material rooms, gate-edge candidates and containment-room candidates.
- Updated debug rendering and preview output with validation status, cycle rank, connectivity ratio, candidate groups, gate candidates and containment candidates.
- Added `tools/generation_test.py` for a 450-floor stress test across all three floors.
- Current limitations reserved for later phases: no player movement, camera, dynamic door entities, scan raycasting, creatures, AI, final objectives, material pickups, crafting or modules.

## Phase 4 Created Or Updated Files

- `game/world/validation.py`
- `game/world/generator.py`
- `game/world/floor.py`
- `game/world/rendering.py`
- `tests/test_validation.py`
- `tools/generation_test.py`
- `tools/generation_preview.py`
- `README.md`
- `PROGRESS.md`

## Phase 4 Test Results

- Baseline before editing: `python -m unittest discover -s tests`, `python tools/smoke_test.py`, `python tools/generation_sweep.py`, `python tools/generation_preview.py --seed 12345 --floor 1 --headless` and `python -m py_compile main.py` all passed.
- `python tools/generate_placeholder_assets.py`: passed.
- `python -m unittest discover -s tests`: passed, 72 tests.
- `python tools/smoke_test.py`: passed.
- `python tools/generation_test.py`: passed for 450 generated floors.
- Stress statistics: retries used 104, maximum attempt index 4, average attempt index 1.313, average room count 11.816, cycle rank distribution `{1: 150, 2: 300}`, average connectivity ratio 1.000.
- `python tools/generation_preview.py --seed 12345 --floor 1 --headless`: passed.
- `python tools/generation_preview.py --seed 12345 --floor 2 --headless`: passed.
- `python tools/generation_preview.py --seed 12345 --floor 3 --headless`: passed.
- `python -m py_compile main.py`: passed.
- Previews confirmed at `artifacts/generation_preview_12345_floor1.png`, `artifacts/generation_preview_12345_floor2.png` and `artifacts/generation_preview_12345_floor3.png`.

## Phase 5 Notes

- Added a physical `Player` entity with float world position, cached idle/walk animations, facing state, smaller lower-body collision rect, feet/current-tile helpers and bounded movement substeps.
- Added a `Camera` that centers on the player, clamps to generated world bounds and exposes world/screen conversion helpers.
- Added reusable static-world collision helpers for world-to-tile conversion, blocking tile lookup, nearby overlap queries and axis-separated collision resolution.
- Replaced the PLAYING scaled overview with a full-size 48 px tile world view rendered through a player-centered camera.
- Added a cached static floor renderer that rebuilds only when the generated floor render key changes. Future tile mutation should explicitly clear or rebuild this static cache.
- Added temporary local darkness and a cached player glow. This is only a Phase 5 visibility stand-in, not the final scan.
- Updated F2 to draw camera-space diagnostics over the real viewport, including room boundaries, IDs, graph edges, candidates, spawn/elevator markers, player visual rect, collision rect and current tile.
- Updated pause/restart flow so movement, animation and camera stop while paused, and restart recreates the generated Floor 1 session, player and camera.
- Current limitations reserved for later phases: no dynamic doors, fixed-origin scan, scan occlusion, creatures, AI, floor objectives, materials, crafting, modules, final score or victory logic.

## Phase 5 Created Or Updated Files

- `game/camera.py`
- `game/entities/__init__.py`
- `game/entities/player.py`
- `game/world/collision.py`
- `game/world/rendering.py`
- `game/app.py`
- `game/settings.py`
- `tests/test_camera.py`
- `tests/test_collision.py`
- `tests/test_player.py`
- `tests/test_world_rendering.py`
- `tools/smoke_test.py`
- `tools/player_preview.py`
- `README.md`
- `PROGRESS.md`

## Phase 5 Test Results

- Baseline before editing: `python tools/generate_placeholder_assets.py`, `python -m unittest discover -s tests`, `python tools/smoke_test.py`, `python tools/generation_test.py`, `python tools/generation_preview.py --seed 12345 --floor 1 --headless` and `python -m py_compile main.py` all passed.
- `python tools/generate_placeholder_assets.py`: passed.
- `python -m unittest discover -s tests`: passed, 109 tests.
- `python tools/smoke_test.py`: passed.
- `python tools/generation_test.py`: passed for 450 generated floors.
- `python tools/player_preview.py --seed 12345 --headless`: passed.
- `python -m py_compile main.py`: passed.
- `python -c "import main; print('main import ok')"`: passed.
- Player previews confirmed at `artifacts/player_preview_12345_start.png` and `artifacts/player_preview_12345_moved.png`.

## Phase 5 Manual Checklist

- Run `python main.py`.
- Start New Run.
- Move with WASD and arrow keys.
- Verify diagonal movement is not faster than straight movement.
- Walk into walls, damaged walls, obstacles and pillars.
- Verify sliding along a free axis when one axis is blocked.
- Walk to each camera edge and confirm the camera clamps to the map.
- Toggle F2 and confirm debug overlays follow the camera and player.
- Pause and resume.
- Restart the run from pause and confirm the player returns to the regenerated Floor 1 session.

## Phase 6 Notes

- Added dynamic door entities with one shared implementation for powered, security and containment doors.
- Added the central `DoorState` enum with `LOCKED`, `CLOSED`, `OPENING`, `OPEN`, `CLOSING`, `WEDGED_OPEN` and `WEDGED_CLOSED`.
- Added cached door animation usage, orientation-aware door sprites, approach rectangles, collision rectangles, interaction rectangles and stable door IDs.
- Added automatic powered-door opening and safe delayed closing. Doors do not close while the player occupies the approach area or doorway.
- Added explicit security and containment unlock APIs. Security and containment doors start locked; after unlock they behave like powered automatic doors.
- Added wedge-ready APIs for direct tests. Door Wedge gameplay, inventory, cooldown and module activation remain future work.
- Added a dynamic blocker registry for movement, future creature movement, future scan and future line-of-sight queries.
- Integrated dynamic door blockers into player collision without modifying the static tile grid.
- Added deterministic door generation from validated doorway metadata. Floor 1 uses only powered doors for current preview playability. Floor 2 selects one deterministic security-door candidate. Floor 3 selects one deterministic containment-door candidate.
- Added F2 debug door rendering with door ID, type, state, orientation, approach rect, collision rect, movement blocking, scan blocking, power and lock status.
- Added debug-only F6/F7/F8 controls while F2 is active: nearest door toggle, nearest locked-door toggle and temporary floor-power toggle.
- Current limitations reserved for later phases: no scan raycasting, creatures, AI, final objectives, materials, crafting, modules, score expansion or Door Wedge gameplay.

## Phase 6 Created Or Updated Files

- `game/entities/door.py`
- `game/entities/__init__.py`
- `game/world/blockers.py`
- `game/world/navigation.py`
- `game/world/door_generation.py`
- `game/world/collision.py`
- `game/world/rendering.py`
- `game/entities/player.py`
- `game/assets.py`
- `game/app.py`
- `game/settings.py`
- `tests/test_doors.py`
- `tests/test_dynamic_blockers.py`
- `tests/test_door_generation.py`
- `tools/smoke_test.py`
- `tools/door_preview.py`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `PROGRESS.md`

## Phase 6 Test Results

- Baseline before editing: `python tools/generate_placeholder_assets.py`, `python -m unittest discover -s tests`, `python tools/smoke_test.py`, `python tools/generation_test.py`, `python tools/player_preview.py --seed 12345 --headless` and `python -m py_compile main.py` all passed.
- `python tools/generate_placeholder_assets.py`: passed.
- `python -m unittest discover -s tests`: passed, 161 tests.
- `python tools/smoke_test.py`: passed.
- `python tools/generation_test.py`: passed for 450 generated floors.
- `python tools/player_preview.py --seed 12345 --headless`: passed.
- `python tools/door_preview.py --seed 12345 --floor 2 --headless`: passed.
- `python -m py_compile main.py`: passed.
- `python -c "import main; print('main import ok')"`: passed.
- Door previews confirmed at `artifacts/door_preview_12345_floor2_closed.png` and `artifacts/door_preview_12345_floor2_open.png`.

## Phase 6 Manual Checklist

- Run `python main.py`.
- Start New Run.
- Walk toward a powered door.
- Verify it opens.
- Stand in the doorway.
- Verify it does not close.
- Leave the doorway.
- Verify it closes.
- Walk into the closed door.
- Verify collision blocks movement.
- Toggle F2.
- Inspect door type, state and blocker values.
- Pause during animation.
- Resume and verify animation continues correctly.
- Restart and verify new door instances exist.

## Phase 7 Notes

- Added a fixed-origin normal scan triggered with Space.
- Added configurable 720-ray tile-grid DDA raycasting that is calculated once per scan rather than once per frame.
- Rays stop at the first wall, damaged wall, obstacle, pillar, map boundary or scan-blocking dynamic door.
- Added exact dynamic-door rectangle intersection through the existing blocker registry. Closed, locked and wedged-closed doors block; open and wedged-open doors allow rays through.
- Added conservative diagonal-corner handling so a zero-width gap between touching blockers does not reveal geometry behind the corner.
- Added reusable point-to-point line of sight with the same static and dynamic blocker rules for future creature snapshots and AI.
- Added expanding scan-front timing, fixed world-space origins, distance-based trace reveal, smooth trace fading, trace cleanup and bounded threat-event hooks.
- Added trace deduplication and conservative contour connection rules that reject gaps, depth jumps, doorway bridges and corner bridges.
- Added a cached viewport scan renderer, nearly black normal gameplay, corrected small player-local glow, F2 sampled ray debugging and F3 performance diagnostics.
- Door state is snapshotted at scan activation: a door closed at activation blocks that historical scan even if it opens later.
- Current limitations reserved for later phases: no moving creatures, dynamic creature snapshots, AI reactions, objective items, floor progression, materials, crafting or modules.

## Phase 7 Created Or Updated Files

- `game/systems/__init__.py`
- `game/systems/raycasting.py`
- `game/systems/scan.py`
- `game/settings.py`
- `game/app.py`
- `game/world/rendering.py`
- `tests/test_raycasting.py`
- `tests/test_scan.py`
- `tests/test_scan_app.py`
- `tools/smoke_test.py`
- `tools/scan_preview.py`
- `tools/scan_benchmark.py`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `PROGRESS.md`

## Phase 7 Test Results

- `python tools/generate_placeholder_assets.py`: passed.
- `python -m unittest discover -s tests`: passed, 196 tests.
- `python tools/smoke_test.py`: passed, including fixed origin, reveal, pause freeze, F3 and restart cleanup checks.
- `python tools/generation_test.py`: passed for 450 floors, 0 failures, maximum attempt index 4, average attempt index 1.313 and connectivity ratio 1.000.
- `python tools/player_preview.py --seed 12345 --headless`: passed.
- `python tools/door_preview.py --seed 12345 --floor 2 --headless`: passed.
- `python tools/scan_preview.py --seed 12345 --floor 2 --headless`: passed; 707 raw hits, 506 deduplicated hits and approximately 13.2 ms raycast time in that run.
- `python tools/scan_benchmark.py`: passed for 27 scans of 720 rays; average 14.419 ms, median 14.143 ms and maximum 17.618 ms in the container environment.
- `python -m py_compile main.py`: passed.
- `python -c "import main; print('main import ok')"`: passed.
- Scan previews confirmed at `artifacts/scan_preview_12345_floor2_early.png`, `artifacts/scan_preview_12345_floor2_late.png` and `artifacts/scan_preview_12345_floor2_camera_shift.png`.

## Phase 7 Manual Checklist

- Run `python main.py` and start New Run.
- Verify the distant map is almost entirely black.
- Press Space and verify the circular front expands from the original world position.
- Move while the wave expands and verify its origin remains behind.
- Confirm nearby wall contours appear only when reached by the wave.
- Confirm the first wall hides everything behind it and corners do not leak visibility.
- Scan a closed powered door, then open it and confirm the old scan remains blocked.
- Trigger a new scan through the open door and confirm it reaches the space behind it.
- Move the camera while traces fade and confirm traces remain fixed in world space.
- Toggle F2 and inspect sampled rays, hit categories and blocker IDs.
- Toggle F3 and inspect raycast timing and trace counts.
- Pause during an active wave and confirm radius, traces and cooldown freeze until resume.
## Phase 8 Notes

- Added a generic `ScanDetectable` contract and `EchoSnapshotSystem` for fixed world-space object echoes.
- Object detection occurs only when the expanding wave front overtakes the entity's current distance from the fixed scan origin.
- Every entity is evaluated at most once per scan. A current line-of-sight test uses the same walls, obstacles and dynamic doors as static DDA raycasting.
- Captured outlines are copied at detection time, remain stationary, fade independently and are cleaned after expiry. The framework already tracks moving entity distances for the future creature phase.
- Added deterministic material placement in validated optional rooms: scrap, circuit and power cells. Floor 1 contains three materials, Floor 2 four and Floor 3 five.
- Material pickups animate internally, remain hidden in normal darkness except for scan echoes and a tiny close-contact hint, collect only once, add +5 score and update per-run material counters.
- Added a scan-detectable elevator entity with locked, unlocked and active states, state-coloured outlines and an interaction region derived from validated elevator approach tiles.
- Added F2 full-object diagnostics, F3 object-echo counters, snapshot reset on floor/run cleanup and a dedicated headless preview tool.
- Current limitations reserved for later phases: no moving creature, creature collision death, objective items, floor progression, crafting or modules.

## Phase 9 Notes

- Added deterministic creature creation from validated spawn candidates. Floor 1 creates one creature; later floors create two when candidates are available. Creature IDs and per-creature RNG seeds are stable for a run seed and generation attempt.
- Added `game/entities/creature.py` with cached sprite/outline frames, delta-time animation, collision Rects, bounded movement substeps and a simple deterministic BFS patrol. Paths are recalculated only after target changes or the creature becomes stuck; full threat-aware AI remains Phase 10.
- Real creature sprites continue moving in darkness and are omitted from normal rendering. F2 shows their actual position, collision Rect, ID, tile, patrol target and current-scan processed state.
- Extended the generic snapshot system with robust moving-front intersection logic. It detects both a wave overtaking a creature and a creature crossing outward through the wave between frames. Detection still requires current line of sight through the same wall, corner and door rules as DDA raycasting.
- Creature echoes copy the exact current outline frame, facing and world position, remain stationary while the real creature continues moving, and fade after 1.5 seconds. One creature is evaluated at most once per scan; later scans may create a new echo.
- Player contact now transitions to `DEATH` in the same gameplay update, including contact caused by player movement. The death screen shows actual floor, elapsed time, score, seed and the creature ID.
- New Run, Retry Same Seed, Main Menu and floor cleanup discard creatures, scans, traces and snapshots. Retry Same Seed reproduces the same floor and creature spawn. Pause freezes creature movement, animation and snapshot lifetime because gameplay updates are not executed outside PLAYING.
- Powered doors receive creature collision Rects during updates, so doors do not close through creatures.
- Added F3 diagnostics for creature count, active creature echoes and IDs processed by the active scan.
- Added deterministic headless creature preview screenshots for debug position, pre-scan darkness, detected snapshot, moved real creature with fixed snapshot and death screen.
- Phase 10 still owns PATROL/INVESTIGATE/SEARCH/CHASE/STUNNED threat-aware AI, A* target pursuit and scan/noise reactions.

## Phase 9 Created Or Updated Files

- `game/entities/creature.py`
- `game/systems/snapshots.py`
- `game/settings.py`
- `game/app.py`
- `tests/test_creature.py`
- `tests/test_creature_movement.py`
- `tests/test_creature_snapshots.py`
- `tests/test_death_restart.py`
- `tools/creature_preview.py`
- `tools/smoke_test.py`
- `.gitignore`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `PROGRESS.md`

## Phase 9 Test Results

- `python -m unittest discover -s tests`: passed with 248 tests.
- `python tools/smoke_test.py`: passed, including creature echo capture, stationary snapshot, immediate contact death and same-seed retry cleanup.
- `python tools/creature_preview.py --seed 12345 --floor 1 --headless`: passed and generated five deterministic screenshots under `artifacts/`.
- `python tools/snapshot_preview.py --seed 12345 --floor 1 --headless`: passed.
- `python tools/scan_benchmark.py`: passed for 27 scans of 720 rays; average 21.384 ms, median 20.320 ms and maximum 30.387 ms in this container run.
- `python -m py_compile main.py` and `python -c "import main; print('main import ok')"`: passed.
- The 450-floor `tools/generation_test.py` is unchanged by Phase 9 and should be rerun on the target Windows machine before commit.

## Phase 10 Baseline Before Editing

- `python -m unittest discover -s tests`: passed with 248 tests.
- `python tools/smoke_test.py`: passed.
- `python tools/generation_test.py`: passed for 450 generated floors, 0 failures, retries used 104, maximum attempt index 4, average attempt index 1.313, average room count 11.816, cycle rank distribution `{1: 150, 2: 300}`, average connectivity ratio 1.000 and total execution time 62.501s.
- `python tools/scan_benchmark.py`: passed for 27 scans of 720 rays; average raycast 36.596 ms, median 33.627 ms and maximum 69.450 ms in this run.
- `python tools/creature_preview.py --seed 12345 --floor 1 --headless`: passed and wrote debug, before-scan, snapshot, moved and death previews under `artifacts/`.
- `python -m py_compile main.py`: passed.

## Phase 10 Notes

- Added `game/systems/threat_events.py` with stable event IDs, source types, age/lifetime handling, pause-safe updates, bounded active storage, reset cleanup, source counts and relevance selection.
- Added `game/systems/creature_ai.py` with the authoritative `CreatureState` enum: `PATROL`, `INVESTIGATE`, `SEARCH`, `CHASE` and `STUNNED`.
- Added deterministic four-directional A* utilities to `game/world/navigation.py`, including Manhattan heuristic, neighbour filtering, path reconstruction, path validity checks and nearest reachable fallback.
- `Creature` remains the physical body for sprite frames, collision Rects, movement and scan snapshots. Attached `CreatureAI` objects own decisions, targets, timers, perception, path memory, stun state and diagnostics.
- `Game` owns one shared `ThreatEventSystem`. A successful Space scan creates exactly one `PLAYER_SCAN` event at the fixed scan origin while the existing static DDA scan, traces and moving-creature snapshots stay separate.
- AI perception uses the existing `has_line_of_sight` implementation and the shared dynamic door blocker registry. Closed, locked and wedged-closed doors block movement, navigation and visibility; open and wedged-open doors allow them.
- Pathfinding is throttled per state. Repathing happens on state entry, target change, invalid path, stuck movement or limited chase refresh, not every frame.
- F2 debug now draws AI state, previous state, transition reason, path tiles, target marker, selected threat, search centre, last known player marker, stun timer and recent LOS result.
- F3 diagnostics now include state counts, active threat counts, threat source counts, pathfinding calls, calls per second, path timing, active path nodes, perception checks per second and stunned creature count.
- Added deterministic `tools/ai_preview.py` with headless screenshots for PATROL, INVESTIGATE, SEARCH, CHASE and STUNNED.
- Extended `tools/smoke_test.py` to cover PATROL, scan threat creation, INVESTIGATE, SEARCH, CHASE, last-known-player memory, direct stun, pause freeze, stun expiry, contact death and retry cleanup.
- Current limitations: floor objectives, generator repair, relay activation, Echo Core extraction, crafting, active modules, Shock Pulse input, Decoy Beacon gameplay, Door Wedge gameplay, Scan Projector gameplay, final HUD and score balancing remain future phases.

## Phase 10 Created Or Updated Files

- `game/systems/threat_events.py`
- `game/systems/creature_ai.py`
- `game/world/navigation.py`
- `game/entities/creature.py`
- `game/systems/__init__.py`
- `game/settings.py`
- `game/app.py`
- `tests/test_threat_events.py`
- `tests/test_navigation.py`
- `tests/test_creature_ai.py`
- `tools/ai_preview.py`
- `tools/smoke_test.py`
- `README.md`
- `PROGRESS.md`

## Phase 10 Test Results

- `python -m unittest discover -s tests`: passed with 302 tests in 20.112s.
- `python tools/smoke_test.py`: passed.
- `python tools/generation_test.py`: passed for 450 generated floors, 0 failures, retries used 104, maximum attempt index 4, average attempt index 1.313, average room count 11.816, cycle rank distribution `{1: 150, 2: 300}`, average connectivity ratio 1.000 and total execution time 51.565s.
- `python tools/scan_benchmark.py`: passed for 27 scans of 720 rays; average raycast 29.510 ms, median 26.872 ms, maximum 44.052 ms, average raw hits 712.4, average deduplicated hits 562.0 and total seconds 2.631.
- `python tools/snapshot_preview.py --seed 12345 --floor 1 --headless`: passed and wrote `artifacts/snapshot_preview_12345_floor1_detected.png`, `artifacts/snapshot_preview_12345_floor1_collected.png`, `artifacts/snapshot_preview_12345_floor1_fading.png` and `artifacts/snapshot_preview_12345_floor1_expired.png`; material count was `{'scrap': 0, 'circuit': 0, 'power_cell': 1}`, score was 5 and active snapshots ended at 0.
- `python tools/creature_preview.py --seed 12345 --floor 1 --headless`: passed and wrote `artifacts/creature_preview_12345_floor1_debug.png`, `artifacts/creature_preview_12345_floor1_before_scan.png`, `artifacts/creature_preview_12345_floor1_snapshot.png`, `artifacts/creature_preview_12345_floor1_moved.png` and `artifacts/creature_preview_12345_floor1_death.png`; creature spawn `(18, 41)`, moved tile `(19, 41)`, snapshot count 1 and snapshot stationary `True`.
- `python tools/ai_preview.py --seed 12345 --floor 1 --headless`: passed and wrote `artifacts/ai_preview_12345_floor1_patrol.png`, `artifacts/ai_preview_12345_floor1_investigate.png`, `artifacts/ai_preview_12345_floor1_search.png`, `artifacts/ai_preview_12345_floor1_chase.png` and `artifacts/ai_preview_12345_floor1_stunned.png`; transition sequence `PATROL -> INVESTIGATE -> SEARCH -> CHASE -> STUNNED`, threat event IDs `[1]`, pathfinding calls 3, path lengths `{'investigate': 2, 'search': 0, 'chase': 2}`, last known player position `(840.0, 1896.0)`, A* throttled `True` and reset cleaned AI state `True`.
- `python -m py_compile main.py`: passed.
- `python -c "import main; print('main import ok')"`: passed with output `main import ok`.
- `python -m compileall -q main.py game tests tools`: passed.

## Phase 11 Baseline Before Editing

- `python -m unittest discover -s tests`: passed with 302 tests in 21.827s.
- `python tools/smoke_test.py`: passed.
- `python tools/generation_test.py`: passed for 450 generated floors, 0 failures, retries used 104, maximum attempt index 4, average attempt index 1.313, average room count 11.816, cycle rank distribution `{1: 150, 2: 300}`, average connectivity ratio 1.000 and total execution time 57.990s.
- `python tools/scan_benchmark.py`: passed for 27 scans of 720 rays; average raycast 30.128 ms, median 29.256 ms, maximum 46.336 ms, average raw hits 712.4, average deduplicated hits 562.0 and total seconds 2.872.
- `python tools/ai_preview.py --seed 12345 --floor 1 --headless`: passed; transition sequence `PATROL -> INVESTIGATE -> SEARCH -> CHASE -> STUNNED`, threat event IDs `[1]`, pathfinding calls 3, path lengths `{'investigate': 2, 'search': 0, 'chase': 2}`, last known player position `(840.0, 1896.0)`, A* throttled `True` and reset cleaned AI state `True`.
- `python -m py_compile main.py`: passed.

## Phase 11 Notes

- Added Floor 1 objective content with two deterministic generator components and one generator placed from validated room metadata after materials, doors, creature candidates, player spawn and elevator tiles are reserved.
- Floor 1 now starts unpowered. Powered doors remain closed until the generator is repaired; security and containment doors remain reserved for later floors.
- Added `Floor1ObjectiveState` as the authoritative state for component IDs, collection flags, generator progress, repairable/repaired flags, floor power, elevator unlock, completion, prompts, interaction target, contextual messages and generator threat-event ID.
- Generator components are scan-detectable animated pickups. Collision collection is idempotent, adds +50 score each, updates objective text and preserves already captured historical snapshots until they expire.
- Generator repair requires both components and continuous held F inside the interaction Rect for 1.5 seconds. Releasing F, leaving range or death resets progress; pause freezes progress because gameplay updates stop outside PLAYING.
- Generator activation sets the generator to POWERED, sets floor power active, adds +150 score, emits exactly one strong `GENERATOR` threat event, updates powered doors, unlocks the existing elevator entity and updates HUD/objective text.
- The elevator starts locked and offline. After generator repair, holding F inside the elevator interaction range adds +300 score, clears active Floor 1 runtime objects, scans, snapshots and threat events, and transitions to the WORKSHOP placeholder.
- The WORKSHOP placeholder now shows `Floor 1 Complete`, `Power restored`, current score, material counts and `Crafting will be enabled in a later phase`. Continue intentionally remains controlled placeholder behaviour and does not generate Floor 2.
- F2 debug mode includes objective room IDs, positions, generator state/progress, interaction Rect, power/elevator state and threat ID. F3 includes objective stage, components collected, progress, power/elevator state, objective-entity count and generator activation count.

## Phase 11 Placement Diagnostics

- Seed `12345`, Floor 1: Component A `f1-a1-component-a-61-24`, room 3, tile `(61, 24)`.
- Seed `12345`, Floor 1: Component B `f1-a1-component-b-61-11`, room 5, tile `(61, 11)`.
- Seed `12345`, Floor 1: Generator `f1-a1-generator-37-36`, room 2, tile `(37, 36)`.
- Placement validation errors: `[]`.
- Repair duration: `1.50`.
- Generator threat event ID during preview: `1`; Floor 1 completion cleanup left 0 generator threat events active in WORKSHOP.

## Phase 11 Created Or Updated Files

- `game/entities/objectives.py`
- `game/systems/floor_objectives.py`
- `tests/test_floor1_objectives.py`
- `tools/floor1_preview.py`
- `game/app.py`
- `game/settings.py`
- `game/entities/__init__.py`
- `game/systems/__init__.py`
- `tools/smoke_test.py`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `PROGRESS.md`

## Phase 11 Test Results

- `python -m unittest discover -s tests`: passed with 327 tests in 40.134s.
- `python tools/smoke_test.py`: passed.
- `python tools/generation_test.py`: passed for 450 generated floors, 0 failures, retries used 104, maximum attempt index 4, average attempt index 1.313, average room count 11.816, cycle rank distribution `{1: 150, 2: 300}`, average connectivity ratio 1.000 and total execution time 70.898s.
- `python tools/scan_benchmark.py`: passed for 27 scans of 720 rays; average raycast 26.107 ms, median 24.854 ms, maximum 39.565 ms, average raw hits 712.4, average deduplicated hits 562.0 and total seconds 2.691.
- `python tools/snapshot_preview.py --seed 12345 --floor 1 --headless`: passed and wrote detected, collected, fading and expired previews; pickup `f1-a1-material-00-power_cell-17-40`, material counts `{'scrap': 0, 'circuit': 0, 'power_cell': 1}`, score 5 and active snapshots ended at 0.
- `python tools/creature_preview.py --seed 12345 --floor 1 --headless`: passed and wrote debug, before-scan, snapshot, moved and death previews; creature spawn `(18, 41)`, moved tile `(19, 41)`, snapshot position `(888.0, 1992.0)`, creature position `(936.0, 1992.0)`, scan ID 1, snapshot count 1 and snapshot stationary `True`.
- `python tools/ai_preview.py --seed 12345 --floor 1 --headless`: passed and wrote PATROL, INVESTIGATE, SEARCH, CHASE and STUNNED previews; transition sequence `PATROL -> INVESTIGATE -> SEARCH -> CHASE -> STUNNED`, threat event IDs `[1]`, pathfinding calls 3, path lengths `{'investigate': 2, 'search': 0, 'chase': 2}`, last known player position `(840.0, 1896.0)`, A* throttled `True` and reset cleaned AI state `True`.
- `python tools/floor1_preview.py --seed 12345 --headless`: passed and wrote `artifacts/floor1_preview_12345_initial.png`, `artifacts/floor1_preview_12345_component1.png`, `artifacts/floor1_preview_12345_components_complete.png`, `artifacts/floor1_preview_12345_repairing.png`, `artifacts/floor1_preview_12345_powered.png`, `artifacts/floor1_preview_12345_elevator.png` and `artifacts/floor1_preview_12345_workshop.png`; summary score 550, completed floor count 1, materials `{'scrap': 0, 'circuit': 0, 'power_cell': 0}` and game state `WORKSHOP`.
- Final workshop runtime cleanup diagnostics from `tools/floor1_preview.py --seed 12345 --headless`: `runtime_generated_floor_present=False`, `runtime_floor_objectives_present=False`, `runtime_floor_power_active=False`, `runtime_elevator_entity_present=False`, `runtime_generator_entity_present=False`, `runtime_player_present=False`, `runtime_doors_count=0`, `runtime_creatures_count=0`, `runtime_material_entities_count=0`, `runtime_threat_events_count=0`, `runtime_generator_threats_count=0`, `runtime_scan_wave_active=False`, `runtime_scan_traces_count=0` and `runtime_snapshots_count=0`.
- `python -m py_compile main.py`: passed.
- `python -c "import main; print('main import ok')"`: passed with output `main import ok`.
- `python -m compileall -q main.py game tests tools`: passed.

## Phase 11 Known Limitations

- Historical Phase 11 limitation: workshop crafting remained a placeholder and Continue did not generate Floor 2 yet. Phase 12 supersedes the Floor 2 part of this note.
- Historical Phase 11 limitation: Floor 2 security/keycard/relay objectives were still future work. Phase 12 implements them; Floor 3 containment/Echo Core extraction, active modules and final victory remain future phases.
- No separate particle pickup-effect system exists yet, so Phase 11 uses contextual messages, scan echoes and close-contact hints for objective feedback.
- Score values are centralised and functional but not final-balanced.

## Phase 12 Baseline Before Editing

- `python -m unittest discover -s tests`: passed with 327 tests in 40.440s.
- `python tools/smoke_test.py`: passed.
- `python tools/generation_test.py`: passed for 450 generated floors, 0 failures, retries used 104, maximum attempt index 4, average attempt index 1.313, average room count 11.816, cycle rank distribution `{1: 150, 2: 300}`, average connectivity ratio 1.000 and total execution time 62.386s.
- `python tools/scan_benchmark.py`: passed for 27 scans of 720 rays; average raycast 38.701 ms, median 36.683 ms, maximum 67.934 ms, average raw hits 712.4, average deduplicated hits 562.0 and total seconds 3.269.
- `python tools/floor1_preview.py --seed 12345 --headless`: passed and ended in WORKSHOP with Floor 1 summary preserved and active runtime cleared.
- `python tools/ai_preview.py --seed 12345 --floor 1 --headless`: passed; transition sequence `PATROL -> INVESTIGATE -> SEARCH -> CHASE -> STUNNED`, threat event IDs `[1]`, pathfinding calls 3, path lengths `{'investigate': 2, 'search': 0, 'chase': 2}`, last known player position `(840.0, 1896.0)`, A* throttled `True` and reset cleaned AI state `True`.
- `python -m py_compile main.py`: passed.

## Phase 12 Notes

- Added Floor 1 workshop progression into Floor 2 through `FLOOR_TRANSITION`, preserving run seed, score, elapsed time, material counts, restart count and completed-floor summaries while keeping Floor 1 runtime cleared.
- Floor 2 begins with explicit runtime power active. Normal powered doors can operate, while the selected security door and elevator start locked.
- Added `Floor2ObjectiveState` and `Floor2ObjectiveSystem` for the authoritative keycard, security door, relay, elevator and contextual-message state.
- Floor 2 generation now rejects otherwise-valid maps with no gate candidate through the existing bounded deterministic retry loop. Seed `1001` verifies this path by accepting attempt 2.
- Floor 2 selects one generated security gate, keeps the start/elevator/keycard side public, and places Relay A and Relay B in distinct secure-side rooms.
- Added the scan-detectable `SecurityKeycardPickup` and `RelayEntity` classes. Keycard collection is collision-based and idempotent; relay activation uses continuous held F, resets on release/range changes and freezes while gameplay is paused.
- Each relay activation awards score once and emits exactly one strong `RELAY` threat event through the existing threat system.
- Two creatures are created on Floor 2 and keep the existing AI, pathfinding, line-of-sight, snapshot and death behaviour.
- Floor 2 completion archives a summary, preserves score/materials, clears Floor 2 runtime entities, scan traces, snapshots and threat events, then returns to WORKSHOP.
- The one-life rule remains unchanged: a Floor 2 death ends the full run, and Retry Same Seed restarts deterministically from Floor 1.
- Continue after Floor 2 remains a controlled placeholder notice and does not generate Floor 3.

## Phase 12 Placement Diagnostics

- Seed `12345`, Floor 2: selected gate edge `(7, 8)`.
- Public-side rooms: `(0, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12)`.
- Secure-side rooms: `(1, 7)`.
- Security keycard `f2-a1-keycard-6-38`, room 11, tile `(6, 38)`.
- Security door `f2-a1-00-security-23-18`, tile `(23, 18)`.
- Relay A `f2-a1-relay-a-50-8`, room 1, tile `(50, 8)`.
- Relay B `f2-a1-relay-b-33-9`, room 7, tile `(33, 9)`.
- Relay activation duration: `2.00`.
- Relay threat event IDs during preview: `[1, 2]`; strengths `[2.4, 2.4]`.
- Floor 2 placement validation errors: `[]`.

## Phase 12 Created Or Updated Files

- Created `tests/test_floor2_objectives.py`.
- Created `tools/floor2_preview.py`.
- Updated `game/app.py`.
- Updated `game/settings.py`.
- Updated `game/states.py`.
- Updated `game/entities/objectives.py`.
- Updated `game/entities/door.py`.
- Updated `game/entities/__init__.py`.
- Updated `game/systems/floor_objectives.py`.
- Updated `game/systems/__init__.py`.
- Updated `game/world/generator.py`.
- Updated `tools/smoke_test.py`.
- Updated `README.md`.
- Updated `IMPLEMENTATION_PLAN.md`.
- Updated `PROGRESS.md`.

## Phase 12 Test Results

- `python -m unittest discover -s tests`: passed with 347 tests in 54.270s.
- `python tools/smoke_test.py`: passed.
- `python tools/generation_test.py`: passed for 450 generated floors, 0 failures, retries used 109, maximum attempt index 5, average attempt index 1.331, average room count 11.829, cycle rank distribution `{1: 150, 2: 300}`, average connectivity ratio 1.000 and total execution time 66.242s.
- `python tools/scan_benchmark.py`: passed for 27 scans of 720 rays; average raycast 27.551 ms, median 26.703 ms, maximum 43.293 ms, average raw hits 712.9, average deduplicated hits 556.6 and total seconds 2.758.
- `python tools/floor1_preview.py --seed 12345 --headless`: passed and wrote the existing Floor 1 preview screenshots; final cleanup diagnostics show no generated floor, objectives, power, elevator, generator, player, doors, creatures, materials, threats, scan wave, traces or snapshots active in WORKSHOP.
- `python tools/floor2_preview.py --seed 12345 --headless`: passed and wrote the Floor 2 preview screenshots listed below.
- `python tools/ai_preview.py --seed 12345 --floor 2 --headless`: passed; transition sequence `PATROL -> INVESTIGATE -> SEARCH -> CHASE -> STUNNED`, threat event IDs `[1]`, pathfinding calls 3, path lengths `{'investigate': 2, 'search': 0, 'chase': 2}`, last known player position `(312.0, 1848.0)`, A* throttled `True` and reset cleaned AI state `True`.
- `python -m py_compile main.py`: passed.
- `python -c "import main; print('main import ok')"`: passed with output `main import ok`.
- `python -m compileall -q main.py game tests tools`: passed.

## Phase 12 Preview Outputs

- `artifacts/floor2_preview_12345_initial.png`
- `artifacts/floor2_preview_12345_keycard.png`
- `artifacts/floor2_preview_12345_keycard_collected.png`
- `artifacts/floor2_preview_12345_door_unlocked.png`
- `artifacts/floor2_preview_12345_relay_a_progress.png`
- `artifacts/floor2_preview_12345_relay_a_active.png`
- `artifacts/floor2_preview_12345_relay_b_progress.png`
- `artifacts/floor2_preview_12345_relays_complete.png`
- `artifacts/floor2_preview_12345_elevator.png`
- `artifacts/floor2_preview_12345_workshop.png`
- `artifacts/ai_preview_12345_floor2_patrol.png`
- `artifacts/ai_preview_12345_floor2_investigate.png`
- `artifacts/ai_preview_12345_floor2_search.png`
- `artifacts/ai_preview_12345_floor2_chase.png`
- `artifacts/ai_preview_12345_floor2_stunned.png`

## Phase 12 Cleanup Diagnostics

- Preserved run summary after Floor 2 preview: last completed floor `2`, completed floor count `2`, score `1100`, materials `{'scrap': 0, 'circuit': 0, 'power_cell': 0}` and Floor 2 summary `{'floor': 2, 'keycard_recovered': True, 'relay_a_active': True, 'relay_b_active': True, 'security_override_completed': True, 'score': 1100, 'materials': {'scrap': 0, 'circuit': 0, 'power_cell': 0}, 'elapsed_time': 0.0}`.
- Archived pre-cleanup Floor 2 runtime state: keycard collected `True`, security door unlocked `True`, security door state `CLOSED`, Relay A active `True`, Relay B active `True`, elevator unlocked `True`, elevator state `UNLOCKED`, relay threat event IDs `[1, 2]`, relay threat strengths `[2.4, 2.4]` and creature count `2`.
- Cleared active runtime after Floor 2 preview: generated floor present `False`, floor objectives present `False`, floor power active `False`, elevator entity present `False`, player present `False`, doors count `0`, creatures count `0`, material entity count `0`, threat events count `0`, scan wave active `False`, scan traces count `0`, snapshots count `0` and game state `WORKSHOP`.

## Phase 12 Known Limitations

- Floor 3 containment, Echo Core extraction and victory remain future work.
- Workshop crafting and active modules remain placeholders.
- Continue after Floor 2 shows a Floor 3 placeholder notice rather than generating Floor 3.
- Score values are centralised and functional but not final-balanced.

## Phase 8 Created Or Updated Files

- `game/entities/scan_objects.py`
- `game/systems/snapshots.py`
- `game/world/content_generation.py`
- `game/systems/scan.py`
- `game/states.py`
- `game/settings.py`
- `game/app.py`
- `game/world/rendering.py`
- `tests/test_snapshots.py`
- `tests/test_content.py`
- `tools/smoke_test.py`
- `tools/snapshot_preview.py`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `PROGRESS.md`

## Phase 8 Test Results

- `python -m unittest discover -s tests`: passed, 216 tests.
- `python tools/smoke_test.py`: passed, including content creation, object snapshot capture, collection, counters, score and restart cleanup.
- `python tools/snapshot_preview.py --seed 12345 --floor 1 --headless`: passed.
- Preview outputs: detected, collected, fading and expired object-echo screenshots under `artifacts/`.
- Equivalent 450-floor generation stress sweep: passed with 0 failures, maximum attempt index 4, average attempt index 1.313 and connectivity ratio 1.000.
- Existing player, door and scan headless previews: passed.
- `python tools/scan_benchmark.py`: passed for 27 scans of 720 rays; average 15.390 ms, median 14.976 ms and maximum 20.859 ms in this container run.
- `python -m py_compile ...` and `python -c "import main"`: passed.



## Phase 14 Completed

- Added `game/systems/modules.py` with four authoritative module definitions, material recipes, run-level ownership and exactly two equipment slots.
- Added `game/systems/crafting.py` with deterministic workshop selection, target-slot control, crafting, equip/unequip, insufficient-material feedback and Continue/Main Menu actions.
- Extended `PlaceholderRun` with `ModuleLoadout`; crafted/equipped modules persist between floors and reset on Retry Same Seed or New Run.
- Replaced the placeholder workshop with a two-by-two recipe card UI, material counters, target-slot highlights, owned/equipped badges, action hints and keyboard controls.
- Added Q/E loadout display to the gameplay HUD. Active module effects intentionally remain Phase 15/16.
- Floor completion summaries now archive the current crafted/equipped loadout without coupling workshop state to floor runtime.
- Updated the end-to-end smoke test to craft Shock Pulse and Decoy Beacon after Floor 1, equip both slots and verify preservation into Floors 2 and 3.
- Added `tests/test_modules.py`, `tests/test_workshop.py` and `tools/workshop_preview.py`.

## Phase 14 Verification

- `python -m unittest discover -s tests`: passed, 412 tests.
- `python tools/smoke_test.py`: passed through all three floors and victory with the crafted loadout preserved.
- `python tools/workshop_preview.py --seed 12345 --headless`: passed and generated five workshop screenshots.
- `python -m compileall -q main.py game tests tools`: passed.
- The workshop preview confirmed crafting does not change score, materials are deducted exactly, three modules can remain owned while only two are equipped, replacing a slot preserves ownership, and the loadout survives the Floor 1-to-Floor 2 workshop transition.

## Phase 14 Known Limitations

- Q and E show equipped modules during gameplay, but active effects and cooldowns are not implemented yet.
- Shock Pulse and Decoy Beacon are planned for Phase 15.
- Door Wedge and Scan Projector are planned for Phase 16.
- Workshop mouse-card selection is not implemented; the workshop is fully usable with keyboard controls.
