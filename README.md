# Echoes Below

Echoes Below is planned as a school Pygame project: a 2D top-down stealth exploration roguelite about navigating dark underground floors with a scan mechanic.

This repository is currently in Phase 1. It contains the application shell, state system, placeholder screens, tests and a headless smoke test. Full gameplay systems are planned for later phases.

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
python -m unittest discover -s tests
python tools/smoke_test.py
python -m py_compile main.py
python -c "import main; print('main import ok')"
```

Gameplay systems such as movement, procedural generation, scanning, creatures, objectives and crafting are implemented in later phases.

## Documentation

- `AGENTS.md`: permanent project rules.
- `GAME_DESIGN.md`: game concept, mechanics, floors and player flow.
- `IMPLEMENTATION_PLAN.md`: planned architecture, phases, tests and risks.
- `PROGRESS.md`: implementation checklist.
