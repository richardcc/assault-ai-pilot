param(
  [string]$Repo = "C:\repos\python\assault"
)

$ErrorActionPreference = "Stop"

Push-Location $Repo
try {
  if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
  }

  Write-Host "== ptest combat tables smoke =="
  python -m pytest -q `
    assault_sim/tests/test_state_encoder_lote_a_features.py `
    assault_sim/tests/test_state_encoder_lote_b_features.py `
    assault_sim/tests/test_state_encoder_lote_c_features.py `
    assault_sim/tests/test_state_encoder_lote_d_features.py `
    assault_sim/tests/test_state_encoder_lote_e_features.py `
    assault_sim/tests/test_option_executor_plan_tags.py `
    assault_sim/tests/test_trace_plan_fields.py
}
finally {
  Pop-Location
}
