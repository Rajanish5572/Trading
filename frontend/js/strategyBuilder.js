// Strategy builder tab: multi-leg builder + payoff diagram + margin, plus a
// Backtest sub-tab that reuses the exact same legs.
const StrategyTab = (() => {
  const root = () => document.getElementById("tab-strategy");
  let legs = [];
  let payoffChart, payoffSeries, zeroSeries;

  function render() {
    root().innerHTML = `
      <div class="subtabs">
        <button class="subtab-btn active" data-sub="builder">Builder</button>
        <button class="subtab-btn" data-sub="backtest">Backtest</button>
      </div>

      <div id="sub-builder" class="strategy-layout">
        <div class="leg-builder">
          <div class="panel">
            <div class="panel-title">Add leg</div>
            <form id="legForm">
              <div class="leg-row"><input name="symbol" placeholder="Symbol" required style="flex:2" /></div>
              <div class="leg-row">
                <input name="token" type="number" placeholder="Token (for backtest)" style="flex:1" />
                <input name="strike" type="number" placeholder="Strike" required style="flex:1" />
              </div>
              <div class="leg-row">
                <select name="option_type"><option>CE</option><option>PE</option><option>FUT</option></select>
                <select name="transaction_type"><option>BUY</option><option>SELL</option></select>
              </div>
              <div class="leg-row">
                <input name="quantity" type="number" placeholder="Lots" value="1" required style="flex:1" />
                <input name="lot_size" type="number" placeholder="Lot size" value="50" required style="flex:1" />
              </div>
              <div class="leg-row"><input name="premium" type="number" step="0.05" placeholder="Premium / entry price" required /></div>
              <button type="submit" style="width:100%;margin-top:4px">Add leg</button>
            </form>
          </div>
          <div class="panel" style="margin-top:10px">
            <div class="panel-title">Legs</div>
            <table><tbody id="legsBody"></tbody></table>
          </div>
          <div class="panel" style="margin-top:10px">
            <div class="panel-title">Spot &amp; range</div>
            <div class="leg-row"><input id="stratSpot" type="number" placeholder="Spot price" /></div>
            <div class="leg-row"><input id="stratRange" type="number" value="10" style="width:70px" /> <span style="align-self:center;color:var(--text-muted)">% range</span></div>
            <div class="leg-row">
              <button id="calcPayoffBtn" style="flex:1">Calculate payoff</button>
              <button id="calcMarginBtn" style="flex:1">Margin</button>
            </div>
            <div id="marginResult" class="hint"></div>
          </div>
        </div>
        <div class="payoff-area">
          <div class="panel">
            <div class="panel-title">Payoff at expiry</div>
            <div id="payoffChart"></div>
            <div id="payoffStats" class="hint" style="margin-top:8px"></div>
          </div>
        </div>
      </div>

      <div id="sub-backtest" class="strategy-layout hidden">
        <div class="leg-builder">
          <div class="panel">
            <div class="panel-title">Backtest window (uses legs above)</div>
            <div class="leg-row"><input id="btUnderlying" placeholder="Underlying e.g. NIFTY" /></div>
            <div class="leg-row"><input id="btFrom" type="date" /></div>
            <div class="leg-row"><input id="btTo" type="date" /></div>
            <div class="leg-row"><input id="btEntry" type="time" value="09:20" /><input id="btExit" type="time" value="15:15" /></div>
            <button id="btRunBtn" style="width:100%;margin-top:4px">Run backtest</button>
          </div>
        </div>
        <div class="payoff-area">
          <div class="panel">
            <div class="panel-title">Results</div>
            <div id="btSummary" class="hint" style="margin-bottom:8px"></div>
            <table><thead><tr><th>Date</th><th>P&amp;L</th><th>Cumulative</th></tr></thead><tbody id="btBody"></tbody></table>
          </div>
        </div>
      </div>`;

    payoffChart = LightweightCharts.createChart(document.getElementById("payoffChart"), {
      layout: { background: { color: "#151a23" }, textColor: "#7c8494" },
      grid: { vertLines: { color: "#1e2430" }, horzLines: { color: "#1e2430" } },
      rightPriceScale: { borderColor: "#262c38" },
      timeScale: { visible: false },
    });
    payoffSeries = payoffChart.addLineSeries({ color: "#378add", lineWidth: 2 });
    zeroSeries = payoffChart.addLineSeries({ color: "#7c8494", lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed });

    document.querySelectorAll(".subtab-btn").forEach((btn) => btn.addEventListener("click", () => switchSub(btn.dataset.sub)));
    document.getElementById("legForm").addEventListener("submit", addLeg);
    document.getElementById("calcPayoffBtn").addEventListener("click", calcPayoff);
    document.getElementById("calcMarginBtn").addEventListener("click", calcMargin);
    document.getElementById("btRunBtn").addEventListener("click", runBacktest);
  }

  function switchSub(name) {
    document.querySelectorAll(".subtab-btn").forEach((b) => b.classList.toggle("active", b.dataset.sub === name));
    document.getElementById("sub-builder").classList.toggle("hidden", name !== "builder");
    document.getElementById("sub-backtest").classList.toggle("hidden", name !== "backtest");
  }

  function addLeg(evt) {
    evt.preventDefault();
    const fd = new FormData(evt.target);
    legs.push({
      symbol: fd.get("symbol"), token: parseInt(fd.get("token"), 10) || 0,
      strike: parseFloat(fd.get("strike")), option_type: fd.get("option_type"),
      transaction_type: fd.get("transaction_type"), quantity: parseInt(fd.get("quantity"), 10),
      lot_size: parseInt(fd.get("lot_size"), 10), premium: parseFloat(fd.get("premium")),
    });
    evt.target.reset();
    renderLegs();
  }

  function renderLegs() {
    document.getElementById("legsBody").innerHTML = legs.map((l, i) => `
      <tr>
        <td>${l.transaction_type} ${l.quantity}x${l.symbol} ${l.strike}${l.option_type} @ ${l.premium}</td>
        <td><button data-i="${i}" class="removeLegBtn">x</button></td>
      </tr>`).join("");
    document.querySelectorAll(".removeLegBtn").forEach((b) => b.addEventListener("click", () => {
      legs.splice(parseInt(b.dataset.i, 10), 1);
      renderLegs();
    }));
  }

  async function calcPayoff() {
    const spot = parseFloat(document.getElementById("stratSpot").value);
    const rangePct = parseFloat(document.getElementById("stratRange").value) / 100;
    if (!spot || !legs.length) { alert("Set a spot price and add at least one leg."); return; }
    let data;
    try {
      data = await Api.post("/api/strategy/payoff", { underlying: "STRATEGY", spot, legs, price_range_pct: rangePct });
    } catch (e) {
      document.getElementById("payoffStats").textContent = e.message;
      return;
    }
    payoffSeries.setData(data.curve.map((p, i) => ({ time: i, value: p.pnl })));
    zeroSeries.setData(data.curve.map((p, i) => ({ time: i, value: 0 })));
    document.getElementById("payoffStats").innerHTML =
      `Max profit: <b>${data.max_profit_uncapped ? "uncapped" : data.max_profit}</b> &middot; ` +
      `Max loss: <b>${data.max_loss_uncapped ? "uncapped" : data.max_loss}</b> &middot; ` +
      `Breakevens: ${data.breakevens.join(", ") || "none"}`;
  }

  async function calcMargin() {
    const spot = parseFloat(document.getElementById("stratSpot").value) || 0;
    const el = document.getElementById("marginResult");
    if (!legs.length) { el.textContent = "Add at least one leg first."; return; }
    try {
      const data = await Api.post("/api/strategy/margin", { underlying: "STRATEGY", spot, legs, price_range_pct: 0.1 });
      el.textContent = JSON.stringify(data);
    } catch (e) {
      el.textContent = e.message;
    }
  }

  async function runBacktest() {
    const underlying = document.getElementById("btUnderlying").value;
    const from_date = document.getElementById("btFrom").value;
    const to_date = document.getElementById("btTo").value;
    const entry_time = document.getElementById("btEntry").value;
    const exit_time = document.getElementById("btExit").value;
    if (!legs.length || !from_date || !to_date) { alert("Add legs and pick a date range first."); return; }
    if (legs.some((l) => !l.token)) { alert("Every leg needs an instrument token for backtesting -- add it in the leg form."); return; }

    let data;
    try {
      data = await Api.post("/api/strategy/backtest", { underlying, from_date, to_date, legs, entry_time, exit_time });
    } catch (e) {
      document.getElementById("btSummary").textContent = e.message;
      return;
    }
    document.getElementById("btSummary").innerHTML =
      `Total P&amp;L: <b class="${data.total_pnl >= 0 ? "pnl-pos" : "pnl-neg"}">${data.total_pnl}</b> &middot; ` +
      `Win days: ${data.win_days} &middot; Loss days: ${data.loss_days} &middot; No data: ${data.days_with_no_data}`;
    document.getElementById("btBody").innerHTML = data.daily_results.map((r) => `
      <tr>
        <td>${r.date}</td>
        <td class="${(r.pnl ?? 0) >= 0 ? "pnl-pos" : "pnl-neg"}">${r.pnl ?? r.note}</td>
        <td>${r.cumulative_pnl ?? ""}</td>
      </tr>`).join("");
  }

  return { render };
})();
