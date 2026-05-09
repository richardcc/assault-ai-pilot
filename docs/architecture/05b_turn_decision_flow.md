# Turn Decision Flow

1. Unit is activated
2. HRL controller checks current tactical option
3. If no option or option expired:
   - RL selects a new option
4. Option executor runs one step
5. Engine resolves the action
6. Reward accumulates
7. Option continues or finishes

This decouples decisions from execution.