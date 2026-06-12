# Echoes Below Agent Rules

These rules are permanent for this project.

## Runtime And Dependencies

- Use Python 3.11 or newer.
- The only permitted non-standard libraries are `pygame` and `numpy`.
- The game must run with `python main.py`.
- All asset paths must be relative to the project location.

## Game Loop And Timing

- Use a standard Event -> Update -> Render game loop.
- Use delta time for movement, animation, timers, scan expansion, cooldowns and fades.
- Clamp unexpectedly large delta time values.
- Target 60 FPS.

## Asset And Performance Rules

- Never load images, sounds or fonts inside the game loop.
- Never generate masks, outlines, rotations or scaled images every frame when they can be cached.
- Missing visual or audio assets must not crash the game.
- If `pygame.mixer` fails, continue without audio.

## Architecture Rules

- Keep the architecture understandable for a student oral defence.
- Prefer clear classes and data structures over excessive abstraction.
- Do not add external frameworks, databases, networking or web services.
- Work only inside the repository.
- Never use destructive Git commands.

## Gameplay Boundaries

- Do not add guns, combat, creature killing, XP levelling, a Vampire Survivors system, a large inventory or permanent meta-progression.
- Do not change the central scan behaviour.
- Score is present only to satisfy the assignment. It must not control crafting, progression or difficulty.

## Development Process

- Test every completed phase.
- Preserve working systems.
- Update `PROGRESS.md` after each implementation phase.
- Make a Git checkpoint commit after each successful phase if Git author information is available.
