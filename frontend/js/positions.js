// Positions tab: open positions, closed positions for the current expiry
// (even if closed on an earlier day), and an orders view split into
// open / filled / cancelled, with modify+cancel on open orders.
const PositionsTab = (() => {
  const root = () => document.getElementById("tab-positions");

  function render() {
    root().innerHTML = `
      <div class="positions-tabs">
        <button class="subtab-btn active" data-sub="pos">Positions</button>
        <button class="subtab-btn" data-sub="orders">Orders</button>
      </div>

      <div id="sub-pos">
        <div class="summary-row" id="limitsSummary"></div>
        <div class="panel-title">Open positions</div>
        <table><thead><tr>
          <th>Symbol</th><th>Product</th><th>Qty</th><th>Avg price</th><th>LTP</th><th>Unrealized</th><th>Realized</th>
        </tr></thead><tbody id="openPosBody"></tbody></table>

        <div class="panel-title" style="margin-top:16px">Closed positions -- same expiry</div>
        <table><thead><tr>
          <th>Symbol</th><th>Expiry</th><th>Qty</th><th>Avg buy</th><th>Avg sell</th><th>Realized P&amp;L</th>
        </tr></thead><tbody id="closedPosBody"></tbody></table>
      </div>

      <div id="sub-orders" class="hidden">
        <div class="panel-title">Open orders</div>
        <table><thead><tr>
          <th>Order ID</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Type</th><th>Price</th><th>Status</th><th></th>
        </tr></thead><tbody id="openOrdBody"></tbody></table>

        <div class="panel-title" style="margin-top:16px">Filled orders</div>
        <table><thead><tr><th>Order ID</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Fill price</th></tr></thead><tbody id="filledOrdBody"></tbody></table>

        <div class="panel-title" style="margin-top:16px">Cancelled / rejected</div>
        <table><thead><tr><th>Order ID</th><th>Symbol</th><th>Side</th><th>Status</th></tr></thead><tbody id="cancelledOrdBody"></tbody></table>
      </div>`;

    document.querySelectorAll(".positions-tabs .subtab-btn").forEach((btn) =>
      btn.addEventListener("click", () => switchSub(btn.dataset.sub)));

    TerminalWS.onOrders(() => refresh()); // any order/fill event -> just reload both tables
    refresh();
  }

  function switchSub(name) {
    document.querySelectorAll(".positions-tabs .subtab-btn").forEach((b) => b.classList.toggle("active", b.dataset.sub === name));
    document.getElementById("sub-pos").classList.toggle("hidden", name !== "pos");
    document.getElementById("sub-orders").classList.toggle("hidden", name !== "orders");
  }

  async function refresh() {
    await Promise.all([loadPositions(), loadLimits(), loadOrders()]);
  }

  async function loadLimits() {
    try {
      const l = await Api.get("/api/positions/limits");
      document.getElementById("limitsSummary").innerHTML = Object.entries(l).map(([k, v]) => `
        <div class="summary-card"><div class="label">${k}</div><div class="value">${v}</div></div>`).join("");
    } catch (e) {
      document.getElementById("limitsSummary").textContent = e.message;
    }
  }

  async function loadPositions() {
    let data;
    try { data = await Api.get("/api/positions"); }
    catch (e) { document.getElementById("openPosBody").innerHTML = `<tr><td colspan="7">${e.message}</td></tr>`; return; }

    document.getElementById("openPosBody").innerHTML = data.open.map((p) => `
      <tr>
        <td>${p.symbol}</td><td>${p.product}</td><td>${p.quantity}</td><td>${p.avg_price}</td><td>${p.ltp}</td>
        <td class="${p.unrealized_pnl >= 0 ? "pnl-pos" : "pnl-neg"}">${p.unrealized_pnl}</td>
        <td class="${p.realized_pnl >= 0 ? "pnl-pos" : "pnl-neg"}">${p.realized_pnl}</td>
      </tr>`).join("") || `<tr><td colspan="7" class="hint">No open positions</td></tr>`;

    document.getElementById("closedPosBody").innerHTML = data.closed_same_expiry.map((p) => `
      <tr>
        <td>${p.symbol}</td><td>${p.expiry ?? "-"}</td><td>${p.quantity}</td>
        <td>${p.avg_buy_price}</td><td>${p.avg_sell_price}</td>
        <td class="${p.realized_pnl >= 0 ? "pnl-pos" : "pnl-neg"}">${p.realized_pnl}</td>
      </tr>`).join("") || `<tr><td colspan="6" class="hint">Nothing closed yet this expiry</td></tr>`;
  }

  async function loadOrders() {
    let data;
    try { data = await Api.get("/api/positions/orders"); }
    catch (e) { document.getElementById("openOrdBody").innerHTML = `<tr><td colspan="8">${e.message}</td></tr>`; return; }

    document.getElementById("openOrdBody").innerHTML = data.open.map((o) => `
      <tr>
        <td>${o.order_id}</td><td>${o.symbol}</td><td>${o.transaction_type}</td><td>${o.quantity}</td>
        <td>${o.order_type}</td><td>${o.price}</td><td>${o.status}</td>
        <td><button data-id="${o.order_id}" class="cancelOrdBtn">Cancel</button></td>
      </tr>`).join("") || `<tr><td colspan="8" class="hint">No open orders</td></tr>`;

    document.getElementById("filledOrdBody").innerHTML = data.filled.map((o) => `
      <tr><td>${o.order_id}</td><td>${o.symbol}</td><td>${o.transaction_type}</td><td>${o.quantity}</td><td>${o.filled_price ?? "-"}</td></tr>
    `).join("") || `<tr><td colspan="5" class="hint">No fills yet</td></tr>`;

    document.getElementById("cancelledOrdBody").innerHTML = data.cancelled_or_rejected.map((o) => `
      <tr><td>${o.order_id}</td><td>${o.symbol}</td><td>${o.transaction_type}</td><td>${o.status}</td></tr>
    `).join("") || `<tr><td colspan="4" class="hint">None</td></tr>`;

    document.querySelectorAll(".cancelOrdBtn").forEach((b) => b.addEventListener("click", () => cancelOrder(b.dataset.id)));
  }

  async function cancelOrder(orderId) {
    try { await Api.del(`/api/positions/orders/${orderId}`); refresh(); }
    catch (e) { alert(`Cancel failed: ${e.message}`); }
  }

  return { render };
})();
