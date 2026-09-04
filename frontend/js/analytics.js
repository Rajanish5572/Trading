// Analytics tab: OI change / buildup classification per near strike, ATM
// straddle price chart, and IV percentile. Same underlying/expiry filter
// pattern as the option chain tab.
const AnalyticsTab = (() => {
  const root = () => document.getElementById("tab-analytics");
  let symbolMap = {};
  let straddleChart, straddleSeries;

  function render() {
    root().innerHTML = `
      <div class="filter-row">
        <select id="anUnderlying"></select>
        <select id="anExpiry"></select>
        <select id="anExchange" style="width:80px"><option value="NFO">NFO</option><option value="BFO">BFO</option></select>
        <input id="anCount" type="number" value="10" style="width:70px" title="Strikes each side of ATM" />
        <button id="anLoadBtn">Load OI buildup</button>
      </div>

      <table>
        <thead><tr>
          <th>Symbol</th><th>Strike</th><th>Type</th><th>LTP</th><th>Price chg %</th>
          <th>Current OI</th><th>OI chg</th><th>OI chg %</th><th>Buildup</th><th>Reading</th>
        </tr></thead>
        <tbody id="anBody"></tbody>
      </table>

      <div class="panel" style="margin-top:16px">
        <div class="panel-title">ATM straddle price (intraday)</div>
        <div class="filter-row">
          <input id="stStrike" type="number" placeholder="Strike" style="width:100px" />
          <button id="stLoadBtn">Plot straddle</button>
        </div>
        <div id="straddleChart" style="height:220px"></div>
      </div>

      <div class="panel" style="margin-top:16px;max-width:320px">
        <div class="panel-title">IV percentile (ATM)</div>
        <button id="ivLoadBtn">Fetch IV percentile</button>
        <div id="ivResult" class="hint"></div>
      </div>`;

    straddleChart = LightweightCharts.createChart(document.getElementById("straddleChart"), {
      layout: { background: { color: "#151a23" }, textColor: "#7c8494" },
      grid: { vertLines: { color: "#1e2430" }, horzLines: { color: "#1e2430" } },
      rightPriceScale: { borderColor: "#262c38" },
      timeScale: { borderColor: "#262c38", timeVisible: true },
    });
    straddleSeries = straddleChart.addLineSeries({ color: "#378add", lineWidth: 2 });

    document.getElementById("anLoadBtn").addEventListener("click", loadBuildup);
    document.getElementById("stLoadBtn").addEventListener("click", loadStraddle);
    document.getElementById("ivLoadBtn").addEventListener("click", loadIvPercentile);
    document.getElementById("anUnderlying").addEventListener("change", onUnderlyingChange);
    loadSymbols();
  }

  async function loadSymbols() {
    try { symbolMap = await Api.get("/api/option-chain/symbols"); }
    catch { symbolMap = { NIFTY: [], BANKNIFTY: [] }; }
    const sel = document.getElementById("anUnderlying");
    sel.innerHTML = Object.keys(symbolMap).map((u) => `<option value="${u}">${u}</option>`).join("");
    onUnderlyingChange();
  }

  function onUnderlyingChange() {
    const u = document.getElementById("anUnderlying").value;
    const expirySel = document.getElementById("anExpiry");
    const expiries = symbolMap[u] || [];
    expirySel.innerHTML = expiries.length ? expiries.map((e) => `<option value="${e}">${e}</option>`).join("") : `<option value="">enter manually</option>`;
  }

  const buildupClass = {
    "Long buildup": "buildup-long", "Short buildup": "buildup-short",
    "Short covering": "buildup-covering", "Long unwinding": "buildup-unwinding",
  };

  async function loadBuildup() {
    const underlying = document.getElementById("anUnderlying").value;
    const expiry = document.getElementById("anExpiry").value;
    const exchange = document.getElementById("anExchange").value;
    const count = document.getElementById("anCount").value;
    let data;
    try {
      data = await Api.get(`/api/analytics/oi-buildup?underlying=${underlying}&exchange=${exchange}&expiry=${expiry}&count=${count}`);
    } catch (e) {
      document.getElementById("anBody").innerHTML = `<tr><td colspan="10">${e.message}</td></tr>`;
      return;
    }
    document.getElementById("anBody").innerHTML = data.strikes.map((r) => `
      <tr>
        <td>${r.symbol}</td><td>${r.strike}</td><td>${r.option_type}</td><td>${r.ltp}</td>
        <td>${r.price_change_pct}%</td><td>${r.current_oi?.toLocaleString()}</td>
        <td>${r.oi_change?.toLocaleString()}</td><td>${r.oi_change_pct}%</td>
        <td class="${buildupClass[r.buildup] || ""}">${r.buildup}</td>
        <td style="font-size:11px;color:var(--text-muted)">${r.interpretation}</td>
      </tr>`).join("");
  }

  async function loadStraddle() {
    const underlying = document.getElementById("anUnderlying").value;
    const expiry = document.getElementById("anExpiry").value;
    const exchange = document.getElementById("anExchange").value;
    const strike = parseFloat(document.getElementById("stStrike").value);
    if (!strike) { alert("Enter a strike first (use the ATM strike from the option chain tab)."); return; }

    const to = new Date();
    const from = new Date(to);
    from.setHours(9, 15, 0, 0);
    const fmt = (d) => d.toISOString().slice(0, 19);

    let data;
    try {
      data = await Api.get(
        `/api/analytics/straddle?underlying=${underlying}&exchange=${exchange}&expiry=${expiry}&strike=${strike}` +
        `&interval=5min&from_dt=${fmt(from)}&to_dt=${fmt(to)}`
      );
    } catch (e) {
      alert(`Straddle load failed: ${e.message}`);
      return;
    }
    straddleSeries.setData(data.series.map((p) => ({ time: Math.floor(new Date(p.ts).getTime() / 1000), value: p.straddle })));
  }

  async function loadIvPercentile() {
    const underlying = document.getElementById("anUnderlying").value;
    const expiry = document.getElementById("anExpiry").value;
    const exchange = document.getElementById("anExchange").value;
    const el = document.getElementById("ivResult");
    try {
      const data = await Api.get(`/api/analytics/iv-percentile?underlying=${underlying}&exchange=${exchange}&expiry=${expiry}`);
      el.innerHTML = `IV ${data.current_iv}% &middot; percentile ${data.percentile} &middot; ${data.sample_count} samples` +
        (data.note ? `<br><span style="color:var(--amber)">${data.note}</span>` : "");
    } catch (e) {
      el.textContent = e.message;
    }
  }

  return { render };
})();
