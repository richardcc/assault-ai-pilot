# VOEC Runbook

## Run tests

```bash
pytest voec_sim/tests -q
```

## Initial validation checklist

1. Unit catalog loads from existing assets.
2. Scenario list is non-empty and contains baseline scenario.
3. Two fresh simulator instances produce equal initial snapshots for same scenario.
4. Legal action API returns non-empty string action IDs.
