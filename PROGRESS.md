# Echoes Below Progress

Last updated: 2026-06-12

## Phase Checklist

- [x] Phase 0: Planning documentation, requirements file and repository bootstrap.
- [x] Phase 1: Minimal Pygame shell, splash screen, automatic menu transition and Play button.
- [x] Phase 2: Asset manager, spritesheets, tiles, animations and visible score HUD.
- [ ] Phase 3: Seeded room-and-corridor procedural generation with validation.
- [ ] Phase 4: Player movement, keyboard input, collisions, doors and objective interactions.
- [ ] Phase 5: Fixed-origin scan with occlusion, expansion and fading traces.
- [ ] Phase 6: Creature movement, collision death and scan snapshots.
- [ ] Phase 7: Three-floor run flow, floor transitions, death options and victory.
- [ ] Phase 8: Workshop, materials and active modules.
- [ ] Phase 9: Performance overlay, debug world view, polish and final requirement pass.

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
