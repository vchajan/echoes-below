# Echoes Below Progress

Last updated: 2026-06-12

## Phase Checklist

- [x] Phase 0: Planning documentation, requirements file and repository bootstrap.
- [x] Phase 1: Minimal Pygame shell, splash screen, automatic menu transition and Play button.
- [x] Phase 2: Asset manager, spritesheets, tiles, animations and visible score HUD.
- [x] Phase 3: Seeded room-and-corridor procedural generation with validation.
- [x] Phase 4: Procedural generator validation, graph loops and safe content placement.
- [x] Phase 5: Player movement, camera, real-size world rendering and tile collisions.
- [x] Phase 6: Dynamic doors, blocker interfaces, door collision and door previews.
- [ ] Phase 7: Fixed-origin scan with occlusion, expansion and fading traces.
- [ ] Phase 8: Creature movement, collision death and scan snapshots.
- [ ] Phase 9: Three-floor run flow, floor transitions, death options and victory.
- [ ] Phase 10: Workshop, materials and active modules.
- [ ] Phase 11: Performance overlay, debug world view, polish and final requirement pass.

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
