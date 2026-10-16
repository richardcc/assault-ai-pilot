from __future__ import annotations


def model_viewer_css() -> str:
    return """
    html, body { height: 100%; }
    body { font-family: Arial, sans-serif; margin: 0; background: #0f172a; color: #e2e8f0; }
    .wrap { box-sizing: border-box; padding: 12px; width: 100vw; height: 100vh; display: flex; flex-direction: column; gap: 10px; }
    .panel { border: 1px solid #334155; border-radius: 8px; background: #111827; padding: 10px; }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
    .kpi { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px; }
    .muted { color: #94a3b8; font-size: 12px; }
    .ok-chip { display:inline-block; padding:1px 6px; border:1px solid #14532d; border-radius:999px; color:#86efac; background:#052e16; font-size:11px; font-weight:600; }
    .degraded-chip { display:inline-block; padding:1px 6px; border:1px solid #7c2d12; border-radius:999px; color:#fdba74; background:#431407; font-size:11px; font-weight:600; }
    .ok-text { color:#86efac; font-weight:600; }
    .degraded-text { color:#fdba74; font-weight:600; }
    .na-text { color:#94a3b8; font-style:italic; }
    .main { flex: 1; min-height: 0; display: grid; grid-template-columns: 320px minmax(0,1fr); gap: 10px; }
    .main.train-collapsed { grid-template-columns: 44px minmax(0,1fr); }
    .collapsed-body { display: none; }
    .main.train-collapsed .collapsed-body { display: none !important; }
    .main.train-collapsed #trainPanelTitle { display: none; }
    .main.train-collapsed #trainList { display: none; }
    .main.train-collapsed #collapseTrainBtn { width: 100%; padding: 10px 0; }
    .list { overflow: auto; min-height: 0; display: flex; flex-direction: column; gap: 6px; }
    .item { background: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 8px; cursor: pointer; }
    .item.active { border-color: #22d3ee; }
    .tabs { display:flex; gap:8px; margin-top:10px; }
    .tab-btn { cursor:pointer; background:#1e293b; border:1px solid #475569; color:#e2e8f0; border-radius:6px; padding:6px 10px; }
    .tab-btn.active { background:#0ea5e9; color:#0f172a; border-color:#0ea5e9; font-weight:700; }
    .tab-pane { display:none; min-height:0; }
    .tab-pane.active { display:flex; flex-direction:column; min-height:0; }
    .analysis-toolbar { display:flex; align-items:flex-start; gap:10px; flex-wrap:wrap; margin-bottom:6px; }
    .tab-group { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
    .tab-level-label { font-size:11px; color:#93c5fd; border:1px solid #334155; background:#0b1220; border-radius:999px; padding:2px 8px; text-transform:uppercase; letter-spacing:.04em; }
    .toolbar-sep { width:1px; align-self:stretch; background:#334155; opacity:.9; min-height:30px; }
    .toolbar-filters { margin-left:auto; min-width:280px; flex:1 1 320px; }
    .replay-top { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:8px; }
    .replay-input, .replay-select { background:#1f2532; color:#e2e8f0; border:1px solid #334155; border-radius:8px; padding:6px 8px; }
    .replay-panel { margin-top:8px; background:#0f172a; border:1px solid #334155; border-radius:8px; padding:10px; }
    .replay-panel h3 { margin:0 0 8px 0; font-size:13px; }
    .replay-kv { display:grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap:8px; }
    .replay-kv .kpi { background:#111827; }
    .replay-canvas { width:100%; max-width:100%; height:auto; max-height:560px; aspect-ratio:16/9; background:#0b0f18; border:1px solid #334155; border-radius:8px; display:block; }
    .replay-hover-legend { display:flex; gap:12px; align-items:center; margin-top:8px; font-size:12px; color:#cbd5e1; }
    .replay-hover-legend-chip { display:inline-block; width:10px; height:10px; border-radius:999px; margin-right:6px; border:1px solid #334155; vertical-align:middle; }
    .replay-hover-legend-move { background:rgba(34,197,94,0.34); border-color:#22c55e; }
    .replay-hover-legend-attack { background:rgba(239,68,68,0.34); border-color:#ef4444; }
    .replay-grid { display:grid; grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.8fr) minmax(280px, 0.75fr); gap:10px; }
    .replay-side-col { display:grid; gap:10px; min-height:0; max-height:760px; overflow:auto; overscroll-behavior: contain; padding-right:2px; }
    .replay-details-grid { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:10px; }
    .replay-details-grid .replay-panel { margin-top:0; }
    @media (max-width: 1400px) { .replay-grid { grid-template-columns: minmax(0, 1fr); } }
    @media (max-width: 900px) { .replay-details-grid { grid-template-columns: minmax(0, 1fr); } }
    .replay-log { white-space: pre-wrap; word-break: break-word; background:#0b1220; border:1px solid #334155; border-radius:6px; padding:8px; font-size:12px; line-height:1.35; overflow:auto; max-height:520px; min-height:280px; }
    .replay-candidate-table-wrap { max-height: 320px; overflow-y: auto; border: 1px solid #334155; border-radius: 6px; }
    .replay-candidate-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .replay-candidate-sort-btn { background: transparent; border: 0; color: #cbd5e1; cursor: pointer; font-size: 12px; font-weight: 600; padding: 0; text-align: left; }
    .replay-candidate-sort-btn:hover { color: #7dd3fc; }
    .dash-wrap { margin-top:10px; display:grid; grid-template-columns: 1fr; gap:10px; }
    .dash-section { border:1px solid #334155; border-radius:8px; background:#0b1220; padding:10px; }
    .dash-title { margin:0 0 8px 0; font-size:13px; color:#cbd5e1; }
    .dash-cards { display:grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap:8px; }
    .dash-card { border:1px solid #334155; border-radius:8px; background:#0f172a; padding:8px; }
    .dash-k { font-size:11px; color:#94a3b8; margin-bottom:4px; }
    .dash-v { font-size:12px; color:#e2e8f0; font-weight:700; word-break:break-word; }
    @media (max-width: 1600px) { .dash-cards { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
    @media (max-width: 1100px) { .dash-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
    .objective-reward-grid { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:10px; grid-auto-flow:dense; align-items:start; min-width:0; }
    .objective-reward-section { background:#0f172a; border:1px solid #334155; border-radius:8px; padding:8px; min-width:0; }
    .objective-reward-section--wide { grid-column: 1 / -1; }
    .objective-reward-section h3 { margin:0 0 8px 0; font-size:13px; }
    .objective-reward-table-wrap { width:100%; min-width:0; overflow-x:auto; }
    .objective-reward-table { border-collapse:collapse; width:100%; min-width:420px; font-size:12px; }
    @media (max-width: 1100px) {
      .objective-reward-grid { grid-template-columns: minmax(0, 1fr); }
      .objective-reward-section--wide { grid-column:auto; }
    }
    h1 { margin: 0; font-size: 18px; }
    h2 { margin: 0 0 8px 0; font-size: 14px; }
    pre { white-space: pre-wrap; word-break: break-word; background: #0b1220; border: 1px solid #334155; border-radius: 6px; padding: 8px; }
"""
