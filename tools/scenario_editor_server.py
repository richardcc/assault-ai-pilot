"""
tools/scenario_editor_server.py

Unified Scenario & Unit Editor runner.
Aliases ScenarioEditorHandler to the unified UnitEditorHandler in tools/unit_editor_server.py.
"""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
from tools.unit_editor_server import UnitEditorHandler, run_server as run_editor_server

# Compatibility alias for scenario tests and standalone scripts
ScenarioEditorHandler = UnitEditorHandler

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assault Tactical Scenario, Unit & Formation Editor")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8780, help="Port to listen on (default: 8780)")
    args = parser.parse_args()

    run_editor_server(args.port)
