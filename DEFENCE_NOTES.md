# Echoes Below — Architecture Defence Notes

## Core design choices

- **Deterministic generation:** A run seed and floor number produce reproducible rooms, graph edges, objective placement, doors and creature spawns. Bounded retries reject invalid maps instead of risking infinite generation.
- **One authoritative blocker model:** Static tiles and `DynamicBlockerRegistry` are reused by player collision, creature navigation, DDA scan and line of sight. A closed door cannot be passable to one system and blocking to another.
- **Historical scan model:** Static rays are calculated once at activation. Dynamic entities are evaluated when the expanding front crosses their current distance, then copied into stationary fading snapshots.
- **Separated creature body and AI:** `Creature` owns position, collision and animation. `CreatureAI` owns PATROL, INVESTIGATE, SEARCH, CHASE and STUNNED decisions. This makes movement and decision tests independent.
- **Threat events instead of omniscient AI:** Scans, objectives, decoys and projectors create temporary world-space events. Creatures evaluate strength, age and distance but enter CHASE only with direct line of sight.
- **Run-level versus floor-level state:** Score, materials, crafted modules, equipment and cooldowns survive between floors. Doors, creatures, deployed devices, traces and objectives are destroyed during floor cleanup.

## Active modules

- **Shock Pulse:** reuses existing LOS and stun APIs. It can save the player but also creates noise.
- **Decoy Beacon:** creates repeated false threat events at a fixed location, giving the player route-control choices.
- **Door Wedge:** reuses authoritative door states. Open wedges preserve routes; closed wedges deny them.
- **Scan Projector:** reuses the same DDA scan from a remote fixed origin and does not consume the player's normal scan cooldown.

## Performance decisions

- Static scan raycasting happens only on activation, never every frame.
- A* pathfinding is throttled and state-driven.
- Images, outlines, flips and scaled surfaces are cached.
- Module rendering reuses one transparent viewport surface.
- Threat lists, snapshots, traces and context messages are bounded or expire.
- Procedural generation and objective graph partitioning happen once per floor.

## Failure safety

- Missing images use visible fallback surfaces; missing audio uses silent objects.
- Generation has bounded retries and explicit validation errors.
- Retry Same Seed reconstructs the entire run from Floor 1; New Run changes the seed.
- Floor completion clears runtime references before workshop or victory, preventing stale AI, scans or power state from leaking forward.

## Demonstration order

1. Start a run and show darkness plus fixed-origin scan.
2. Show a creature moving after its snapshot remains behind.
3. Complete Floor 1 and craft two modules.
4. Use Shock Pulse and Decoy Beacon on Floor 2.
5. Re-equip Door Wedge and Scan Projector in the workshop.
6. Use both on Floor 3 and extract the Echo Core.
7. Toggle F2/F3 to explain shared blockers, AI state, paths and performance counters.
