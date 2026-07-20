param(
  [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

& $PythonExe -m pytest `
  "agents/efficientzero_v2/tests/test_mcts_q_normalization.py" `
  "agents/efficientzero_v2/tests/test_mcts_selection_battery.py" `
  "agents/muzero/tests/test_mcts_contract.py" `
  -o addopts= `
  -ra `
  --maxfail=1
