# Echoes Below

Echoes Below is planned as a school Pygame project: a 2D top-down stealth exploration roguelite about navigating dark underground floors with a scan mechanic.

This repository is currently in Phase 2. It contains the application shell, state system, asset manager, generated placeholder spritesheets, placeholder screens, tests and a headless smoke test. Full gameplay systems are planned for later phases.

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
- Escape: skip splash, pause from the playing placeholder, resume from pause or return from How to Play
- Backspace: return from How to Play

Planned gameplay controls:

- WASD or arrow keys: move
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
python -m py_compile main.py
python -c "import main; print('main import ok')"
```

Gameplay systems such as movement, procedural generation, scanning, creatures, objectives and crafting are implemented in later phases.

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

## Documentation

- `AGENTS.md`: permanent project rules.
- `GAME_DESIGN.md`: game concept, mechanics, floors and player flow.
- `IMPLEMENTATION_PLAN.md`: planned architecture, phases, tests and risks.
- `PROGRESS.md`: implementation checklist.
