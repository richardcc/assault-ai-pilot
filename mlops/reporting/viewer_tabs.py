from __future__ import annotations


def tabs_controller_js() -> str:
    return """
    function switchSection(section) {
      activeSection = section;
      const secTrain = el("sectionTrainBtn");
      const secEval = el("sectionEvalBtn");
      const secMeta = el("sectionMetaBtn");
      if (secTrain) secTrain.classList.toggle("active", section === "train");
      if (secEval) secEval.classList.toggle("active", section === "eval");
      if (secMeta) secMeta.classList.toggle("active", section === "meta");
      ["tabTrainDetailBtn", "tabTrainHeadDiagnosticsBtn", "tabObjectiveRewardConfigBtn", "tabMuzeroVpsBtn", "tabHeadDiagnosticsBtn", "tabEvalMetricsBtn", "tabEvalDecisionsBtn", "tabReplayBtn", "tabOverviewBtn"].forEach(id => {
        const n = el(id);
        if (!n) return;
        const sec = n.getAttribute("data-section");
        n.style.display = (sec === section) ? "" : "none";
      });
      const filtersHost = el("analysisFiltersHost");
      if (filtersHost) filtersHost.style.display = (section === "eval") ? "block" : "none";
      if (section === "train" && activeTab !== "train-detail" && activeTab !== "train-head-diagnostics" && activeTab !== "objective-reward-config") switchTab("train-detail");
      if (section === "eval" && activeTab !== "vps" && activeTab !== "head-diagnostics" && activeTab !== "eval-metrics" && activeTab !== "eval-decisions" && activeTab !== "replay") switchTab("vps");
      if (section === "meta" && activeTab !== "overview") switchTab("overview");
    }

    function switchTab(tab) {
      activeTab = tab;
      const tOverviewBtn = el("tabOverviewBtn");
      const tVpsBtn = el("tabMuzeroVpsBtn");
      const tHeadDiagBtn = el("tabHeadDiagnosticsBtn");
      const tEvalMetricsBtn = el("tabEvalMetricsBtn");
      const tDecisionsBtn = el("tabEvalDecisionsBtn");
      const tReplayBtn = el("tabReplayBtn");
      const tTrainDetailBtn = el("tabTrainDetailBtn");
      const tTrainHeadDiagBtn = el("tabTrainHeadDiagnosticsBtn");
      const tObjectiveRewardConfigBtn = el("tabObjectiveRewardConfigBtn");
      const pOverview = el("tabOverview");
      const pVps = el("tabMuzeroVps");
      const pHeadDiag = el("tabHeadDiagnostics");
      const pEvalMetrics = el("tabEvalMetrics");
      const pDecisions = el("tabEvalDecisions");
      const pReplay = el("tabReplay");
      const pTrainDetail = el("tabTrainDetail");
      const pTrainHeadDiag = el("tabTrainHeadDiagnostics");
      const pObjectiveRewardConfig = el("tabObjectiveRewardConfig");
      if (tOverviewBtn) tOverviewBtn.classList.toggle("active", tab === "overview");
      if (tVpsBtn) tVpsBtn.classList.toggle("active", tab === "vps");
      if (tHeadDiagBtn) tHeadDiagBtn.classList.toggle("active", tab === "head-diagnostics");
      if (tEvalMetricsBtn) tEvalMetricsBtn.classList.toggle("active", tab === "eval-metrics");
      if (tDecisionsBtn) tDecisionsBtn.classList.toggle("active", tab === "eval-decisions");
      if (tReplayBtn) tReplayBtn.classList.toggle("active", tab === "replay");
      if (tTrainDetailBtn) tTrainDetailBtn.classList.toggle("active", tab === "train-detail");
      if (tTrainHeadDiagBtn) tTrainHeadDiagBtn.classList.toggle("active", tab === "train-head-diagnostics");
      if (tObjectiveRewardConfigBtn) tObjectiveRewardConfigBtn.classList.toggle("active", tab === "objective-reward-config");
      if (pOverview) pOverview.classList.toggle("active", tab === "overview");
      if (pVps) pVps.classList.toggle("active", tab === "vps");
      if (pHeadDiag) pHeadDiag.classList.toggle("active", tab === "head-diagnostics");
      if (pEvalMetrics) pEvalMetrics.classList.toggle("active", tab === "eval-metrics");
      if (pDecisions) pDecisions.classList.toggle("active", tab === "eval-decisions");
      if (pReplay) pReplay.classList.toggle("active", tab === "replay");
      if (pTrainDetail) pTrainDetail.classList.toggle("active", tab === "train-detail");
      if (pTrainHeadDiag) pTrainHeadDiag.classList.toggle("active", tab === "train-head-diagnostics");
      if (pObjectiveRewardConfig) pObjectiveRewardConfig.classList.toggle("active", tab === "objective-reward-config");
      if (tab === "objective-reward-config") {
        renderObjectiveRewardConfig();
      }
      if (tab === "replay") {
        setTimeout(() => { try { window.dispatchEvent(new Event("resize")); } catch (_e) {} }, 0);
        setTimeout(() => { try { window.dispatchEvent(new Event("resize")); } catch (_e) {} }, 80);
      }
    }

    function setTrainCollapsed(next) {
      trainCollapsed = !!next;
      const main = document.querySelector(".main");
      if (!main) return;
      main.classList.toggle("train-collapsed", trainCollapsed);
      const btn = el("collapseTrainBtn");
      if (btn) btn.textContent = trainCollapsed ? "⟩" : "⟨";
    }

    const nSectionTrain = el("sectionTrainBtn");
    const nSectionEval = el("sectionEvalBtn");
    const nSectionMeta = el("sectionMetaBtn");
    const nTabTrainDetail = el("tabTrainDetailBtn");
    const nTabTrainHeadDiag = el("tabTrainHeadDiagnosticsBtn");
    const nTabObjectiveRewardConfig = el("tabObjectiveRewardConfigBtn");
    const nTabOverview = el("tabOverviewBtn");
    const nTabVps = el("tabMuzeroVpsBtn");
    const nTabHeadDiag = el("tabHeadDiagnosticsBtn");
    const nTabEvalMetrics = el("tabEvalMetricsBtn");
    const nTabDecisions = el("tabEvalDecisionsBtn");
    const nTabReplay = el("tabReplayBtn");
    if (nSectionTrain) nSectionTrain.onclick = () => switchSection("train");
    if (nSectionEval) nSectionEval.onclick = () => switchSection("eval");
    if (nSectionMeta) nSectionMeta.onclick = () => switchSection("meta");
    if (nTabTrainDetail) nTabTrainDetail.onclick = () => switchTab("train-detail");
    if (nTabTrainHeadDiag) nTabTrainHeadDiag.onclick = () => switchTab("train-head-diagnostics");
    if (nTabObjectiveRewardConfig) nTabObjectiveRewardConfig.onclick = () => switchTab("objective-reward-config");
    if (nTabOverview) nTabOverview.onclick = () => switchTab("overview");
    if (nTabVps) nTabVps.onclick = () => switchTab("vps");
    if (nTabHeadDiag) nTabHeadDiag.onclick = () => switchTab("head-diagnostics");
    if (nTabEvalMetrics) nTabEvalMetrics.onclick = () => switchTab("eval-metrics");
    if (nTabDecisions) nTabDecisions.onclick = () => switchTab("eval-decisions");
    if (nTabReplay) nTabReplay.onclick = () => switchTab("replay");
    el("collapseTrainBtn").onclick = () => setTrainCollapsed(!trainCollapsed);
    switchSection("eval");
    const requestedInitialTab = String((window && window.__INITIAL_MODEL_TAB__) || "").trim();
    const validInitialTab = new Set([
      "vps",
      "head-diagnostics",
      "eval-metrics",
      "eval-decisions",
      "replay",
      "overview",
      "train-detail",
      "train-head-diagnostics",
      "objective-reward-config",
    ]);
    switchTab(validInitialTab.has(requestedInitialTab) ? requestedInitialTab : "vps");
"""
