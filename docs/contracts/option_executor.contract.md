# Option Executor Contract

The option executor must:

- Receive a tactical option and game state
- Return a legal engine action
- Never choose a tactical option
- Never access reward signals

Heuristics may use:
- Geometry
- Pathfinding
- Unit statistics
- Doctrinal rules