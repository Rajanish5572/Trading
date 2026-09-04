// Option chain tab: filterable by underlying + expiry, ATM-highlighted,
// with a PCR summary. Builds its own DOM into #tab-optionchain since the
// shell only ships a bare <section> for it.
const OptionChainTab = (() => {
  const root = () => document.getElementById("tab-optionchain");
  let symbolMap = {};

  function render() {
    root().innerHTML = `
      <div class="filter-row">
        <select id="ocUnderlying"></select>
        <select id="ocExpiry"></select>
        <select id="ocExchange" style="width:80px">
          <option value="NFO">NFO</option>
          <option value="BFO">BFO</option>
        </select>
        <input id="ocCount" type="number" value="10" style="width:70px" title="Strikes each side of ATM" />
        <button id="ocLoadBtn">Load</button>
      </div>
      <div class="summary-row">
        <div class="summary-card"><div class="label">Spot</div><div class="value" id="ocSpot">-</div></div>
        <div class="summary-card"><div class="label">ATM strike</div><div class="value" id="ocAtm">-</div></div>
        <div class="summary-card"><div class="label">PCR</div><div class="value" id="ocPcr">-</div></div>
        <div class="summary-card"><div class="label">Total CE OI</div><div class="value" id="ocCeOi">-</div></div>
        <div class="summary-card"><div class="label">Total PE OI</div><div class="value" id="ocPeOi">-</div></div>
      </div>
      <table>
        <thead><tr>
          <th>CE OI</th><th>CE LTP</th><th>Strike</th><th>PE LTP</th><th>PE OI</th>
        </tr></thead>
        <tbody id="ocBody"></tbody>
      </table>`;

    document.getElementById("ocLoadBtn").addEventListener("click", loadChain);
    document.getElementById("ocUnderlying").addEventListener("change", onUnderlyingChange);
    loadSymbols();
  }

  async function loadSymbols() {
    try {
      symbolMap = await Api.get("/api/option-chain/symbols");
    } catch (e) {
      console.warn("Could not load underlying/expiry map, falling back to manual entry", e);
      symbolMap = { NIFTY: [], BANKNIFTY: [], FINNIFTY: [], SENSEX: [] };
    }
    const underlyingSel = document.getElementById("ocUnderlying");
    underlyingSel.innerHTML = Object.keys(symbolMap).map((u) => `<option value="${u}">${u}</option>`).join("");
    onUnderlyingChange();
  }

  function onUnderlyingChange() {
    const u = document.getElementById("ocUnderlying").value;
    const expirySel = document.getElementById("ocExpiry");
    const expiries = symbolMap[u] || [];
    expirySel.innerHTML = expiries.length
      ? expiries.map((e) => `<option value="${e}">${e}</option>`).join("")
      : `<option value="">enter manually via load</option>`;
  }

  async function loadChain() {
    const underlying = document.getElementById("ocUnderlying").value;
    const expiry = document.getElementById("ocExpiry").value;
    const exchange = document.getElementById("ocExchange").value;
    const count = document.getElementById("ocCount").value;
    let data;
    try {
      data = await Api.get(`/api/option-chain?underlying=${underlying}&exchange=${exchange}&expiry=${expiry}&count=${count}`);
    } catch (e) {
      document.getElementById("ocBody").innerHTML = `<tr><td colspan="5">${e.message}</td></tr>`;
      return;
    }

    document.getElementById("ocSpot").textContent = data.spot != null ? data.spot.toFixed(2) : "-";
    document.getElementById("ocAtm").textContent = data.atm_strike ?? "-";
    document.getElementById("ocPcr").textContent = data.pcr ?? "-";
    document.getElementById("ocCeOi").textContent = data.total_ce_oi?.toLocaleString() ?? "-";
    document.getElementById("ocPeOi").textContent = data.total_pe_oi?.toLocaleString() ?? "-";

    const byStrike = {};
    for (const leg of data.legs) {
      const s = byStrike[leg.strikePrice] || (byStrike[leg.strikePrice] = { strike: leg.strikePrice, is_atm: leg.is_atm });
      if (leg.optionType === "CE") s.ce = leg; else if (leg.optionType === "PE") s.pe = leg;
    }
    const rows = Object.values(byStrike).sort((a, b) => a.strike - b.strike);
    document.getElementById("ocBody").innerHTML = rows.map((r) => `
      <tr class="${r.is_atm ? "atm-row" : ""}">
        <td class="ce-cell">${r.ce?.openingOI?.toLocaleString() ?? "-"}</td>
        <td class="ce-cell">${r.ce?.ltp ?? "-"}</td>
        <td>${r.strike}</td>
        <td class="pe-cell">${r.pe?.ltp ?? "-"}</td>
        <td class="pe-cell">${r.pe?.openingOI?.toLocaleString() ?? "-"}</td>
      </tr>`).join("");
  }

  return { render };
})();
