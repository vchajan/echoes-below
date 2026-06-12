# Echoes Below

Echoes Below is planned as a school Pygame project: a 2D top-down stealth exploration roguelite about navigating dark underground floors with a scan mechanic.

This repository is currently in Phase 5. It contains the application shell, state system, asset manager, generated placeholder spritesheets, seeded procedural floor generation, stronger generator validation, player movement, a camera-driven playable world view, tile collisions, tests and headless verification tools. Scan raycasting, creatures, objectives, materials, crafting, modules and scoring are planned for later phases.

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
python -m py_compile main.py
python -c "import main; print('main import ok')"
```

Gameplay systems such as scan raycasting, creatures, objectives, materials and crafting are implemented in later phases.

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
