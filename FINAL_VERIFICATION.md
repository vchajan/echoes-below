# Echoes Below — Final Verification

Final functional checkpoint: 2026-06-13.

## Automated results

- Unit and integration suite: **435 tests passed**.
- End-to-end smoke test: passed through Floor 1, both workshops, Floor 2, Floor 3 and Victory while activating all four modules.
- Generation stress test: **450 floors**, 0 failures, maximum attempt index 5, average attempt index 1.331, connectivity ratio 1.000.
- DDA scan benchmark: 27 scans × 720 rays; average 10.971 ms, median 11.075 ms, maximum 13.317 ms in SDL dummy mode.
- Active-module update audit: 360 frames; average 0.221 ms, median 0.118 ms, maximum 13.088 ms, including three projector scans and four decoy pulses.
- Snapshot, creature, AI, Floor 1, Floor 2, Floor 3, workshop and module previews: passed.
- `py_compile`, `main` import and `compileall`: passed.

## Final local verification commands

Run from the project root with the virtual environment active:

```powershell
python -m unittest discover -s tests
python tools/smoke_test.py
python tools/generation_test.py
python tools/scan_benchmark.py
python tools/performance_audit.py
python tools/module_preview.py --seed 12345 --headless
python tools/floor3_preview.py --seed 12345 --headless
python -m py_compile main.py
python -c "import main; print('main import ok')"
python -m compileall -q main.py game tests tools
```

## Manual presentation-machine checks

1. Run `python main.py` and complete basic movement and scan input.
2. Confirm Q/E module activations match the equipped workshop slots.
3. Confirm pause freezes cooldowns, devices, AI and scan progression.
4. Confirm normal mode remains dark and F2/F3 remain developer-only overlays.
5. Play at least one full run to evaluate difficulty, message readability and audio fallback behaviour.

## Submission limitations

- Pixel art is deterministic placeholder art and can be replaced without changing code paths.
- Optional audio may be absent; silent fallbacks prevent crashes.
- SDL dummy benchmarks validate computation, not guaranteed rendered FPS on every machine.
- Workshop recipe cards are keyboard-first; standard menu buttons still support mouse input.
