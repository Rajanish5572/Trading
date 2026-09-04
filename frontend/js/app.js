// Bootstraps the terminal: tab navigation + one-time render of each tab's
// content, then connects the websockets.
(function () {
  const rendered = { chart: true }; // chart tab's DOM is already in index.html

  function renderTabIfNeeded(name) {
    if (rendered[name]) return;
    rendered[name] = true;
    if (name === "optionchain") OptionChainTab.render();
    if (name === "analytics") AnalyticsTab.render();
    if (name === "strategy") StrategyTab.render();
    if (name === "positions") PositionsTab.render();
  }

  function switchTab(name) {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
    document.querySelectorAll(".tabpanel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
    renderTabIfNeeded(name);
  }

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  window.addEventListener("DOMContentLoaded", async () => {
    try {
      const health = await Api.get("/api/health");
      const badge = document.getElementById("paperBadge");
      badge.textContent = health.paper_mode ? "paper mode" : "LIVE trading";
      badge.className = health.paper_mode ? "pill pill-warning" : "pill pill-ok";
    } catch (e) {
      console.warn("Health check failed", e);
    }

    TerminalWS.init();
    ChartTab.init();
  });
})();
