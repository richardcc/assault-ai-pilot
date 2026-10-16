from __future__ import annotations


def analysis_toolbar_html() -> str:
    return """
        <div class="analysis-toolbar">
          <div class="tab-group">
            <span class="tab-level-label">Nivel 1</span>
            <div class="tabs" style="margin:0;">
              <button id="sectionTrainBtn" class="tab-btn">Train Metrics</button>
              <button id="sectionEvalBtn" class="tab-btn active">Eval Metrics</button>
              <button id="sectionMetaBtn" class="tab-btn">Meta</button>
            </div>
          </div>
          <div class="toolbar-sep"></div>
          <div class="tab-group">
            <span class="tab-level-label">Nivel 2</span>
            <div class="tabs" style="margin:0;">
              <button id="tabTrainDetailBtn" class="tab-btn" data-section="train">Train Detail</button>
              <button id="tabTrainHeadDiagnosticsBtn" class="tab-btn" data-section="train">Train Head Diagnostics</button>
              <button id="tabObjectiveRewardConfigBtn" class="tab-btn" data-section="train">Objective/Reward Config</button>
              <button id="tabMuzeroVpsBtn" class="tab-btn active" data-section="eval">VP Summary</button>
              <button id="tabHeadDiagnosticsBtn" class="tab-btn" data-section="eval">Eval Head Diagnostics</button>
              <button id="tabEvalMetricsBtn" class="tab-btn" data-section="eval">Eval Metrics</button>
              <button id="tabEvalDecisionsBtn" class="tab-btn" data-section="eval">Eval KBI Decisions</button>
              <button id="tabReplayBtn" class="tab-btn" data-section="eval">Match Replay</button>
              <button id="tabOverviewBtn" class="tab-btn" data-section="meta">Overview</button>
            </div>
          </div>
          <div class="toolbar-sep"></div>
          <div id="analysisFiltersHost" class="toolbar-filters"></div>
          <span id="viewerBuildMarker" class="muted" style="margin-left:auto;font-size:11px;"></span>
        </div>
"""


def analysis_tab_panes_html() -> str:
    return """
        <div id="tabTrainDetail" class="tab-pane">
          <h2 style="margin-top:8px;">Selected Train Metrics</h2>
          <div id="trainDashboard" class="dash-wrap" style="margin-bottom:8px;"></div>
          <div id="trainArchitectureHost" style="margin-bottom:8px;"></div>
          <pre id="trainMetricsPre">{}</pre>
        </div>
        <div id="tabTrainHeadDiagnostics" class="tab-pane">
          <h2 style="margin-top:8px;">Train Head Diagnostics</h2>
          <div id="trainHeadDiagnosticsRoot" class="list"></div>
        </div>
        <div id="tabObjectiveRewardConfig" class="tab-pane">
          <h2 style="margin-top:8px;">Objective/Reward Config</h2>
          <div id="objectiveRewardConfigRoot" class="list"></div>
        </div>
        <div id="tabOverview" class="tab-pane">
          <h2 style="margin-top:8px;">Evals for Selected Train</h2>
          <div id="evalList" class="list"></div>
        </div>
        <div id="tabMuzeroVps" class="tab-pane active">
          <h2 style="margin-top:8px;">VP Summary</h2>
          <div id="muzeroVpsRoot" class="list"></div>
        </div>
        <div id="tabHeadDiagnostics" class="tab-pane">
          <h2 style="margin-top:8px;">Eval Head Diagnostics</h2>
          <div id="headDiagnosticsRoot" class="list"></div>
        </div>
        <div id="tabEvalMetrics" class="tab-pane">
          <h2 style="margin-top:8px;">Eval Metrics</h2>
          <div id="evalMetricsRoot" class="list"></div>
        </div>
        <div id="tabEvalDecisions" class="tab-pane">
          <h2 style="margin-top:8px;">Eval KBI Decisions</h2>
          <div id="evalDecisionsRoot" class="list"></div>
        </div>
        <div id="tabReplay" class="tab-pane">
          <h2 style="margin-top:8px;">Match Replay</h2>
          <div id="replayRoot" class="list"></div>
        </div>
"""
