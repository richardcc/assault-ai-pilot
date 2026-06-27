Write-Host "== ptest rag copilot endpoints =="
python -m pytest assault_backend/tests/test_rag_copilot_endpoints.py -q
