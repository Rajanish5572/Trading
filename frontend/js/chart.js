// Chart tab: candlesticks + volume + toggleable indicators, live depth panel,
// and the order ticket. Built on TradingView's lightweight-charts.
const ChartTab = (() => {
  let priceChart, candleSeries, volumeSeries;
  let rsiChart, rsiSeries;
  let macdChart, macdLineSeries, macdSignalSeries, macdHistSeries;
  const overlaySeries = {}; // indicator id -> [series,...] so we can remove/re-add on toggle
  const activeIndicators = new Set();
  let lastCandles = [];
  let currentSymbolMeta = null;

  function makeChart(container) {
    return LightweightCharts.createChart(container, {
      layout: { background: { color: "#151a23" }, textColor: "#7c8494" },
      grid: { vertLines: { color: "#1e2430" }, horzLines: { color: "#1e2430" } },
      rightPriceScale: { borderColor: "#262c38" },
      timeScale: { borderColor: "#262c38", timeVisible: true, secondsVisible: false },
      crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    });
  }

  function init() {
    priceChart = makeChart(document.getElementById("priceChart"));
    candleSeries = priceChart.addCandlestickSeries({
      upColor: "#1d9e75", downColor: "#d85a30", borderVisible: false,
      wickUpColor: "#1d9e75", wickDownColor: "#d85a30",
    });
    volumeSeries = priceChart.addHistogramSeries({
      color: "#378add", priceFormat: { type: "volume" },
      priceScaleId: "vol", scaleMargins: { top: 0.85, bottom: 0 },
    });

    rsiChart = makeChart(document.getElementById("rsiChart"));
    rsiSeries = rsiChart.addLineSeries({ color: "#7f77dd", lineWidth: 1 });

    macdChart = makeChart(document.getElementById("macdChart"));
    macdLineSeries = macdChart.addLineSeries({ color: "#378add", lineWidth: 1 });
    macdSignalSeries = macdChart.addLineSeries({ color: "#ef9f27", lineWidth: 1 });
    macdHistSeries = macdChart.addHistogramSeries({ color: "#639922" });

    document.getElementById("chartLoadBtn").addEventListener("click", load);
    document.querySelectorAll(".chip[data-ind]").forEach((btn) => {
      btn.addEventListener("click", () => toggleIndicator(btn));
    });
    document.getElementById("orderTicketForm").addEventListener("submit", submitOrder);

    TerminalWS.onMarket(onTick);
    load();
  }

  function toggleIndicator(btn) {
    const id = btn.dataset.ind;
    btn.classList.toggle("active");
    if (btn.classList.contains("active")) activeIndicators.add(id);
    else activeIndicators.delete(id);

    document.getElementById("rsiChart").classList.toggle("hidden", !activeIndicators.has("rsi"));
    document.getElementById("macdChart").classList.toggle("hidden", !activeIndicators.has("macd"));
    load();
  }

  function isoRangeFor(interval) {
    const to = new Date();
    const from = new Date(to);
    if (interval === "day") from.setDate(from.getDate() - 365);
    else if (interval === "hour" || interval === "2hours" || interval === "3hours" || interval === "4hours")
      from.setDate(from.getDate() - 30);
    else from.setDate(from.getDate() - 5);
    const fmt = (d) => d.toISOString().slice(0, 19);
    return { from_dt: fmt(from), to_dt: fmt(to) };
  }

  function clearOverlays() {
    Object.values(overlaySeries).flat().forEach((s) => {
      try { priceChart.removeSeries(s); } catch (e) {}
    });
    for (const k in overlaySeries) delete overlaySeries[k];
  }

  async function load() {
    const token = parseInt(document.getElementById("chartToken").value, 10);
    const exchange = document.getElementById("chartExchange").value;
    const symbol = document.getElementById("chartUnderlying").value;
    const interval = document.getElementById("chartInterval").value;
    if (!token) {
      document.getElementById("orderTicketResult").textContent = "Enter an instrument token to load a chart.";
      return;
    }

    const range = isoRangeFor(interval);
    const indicatorConfigs = [];
    if (activeIndicators.has("ma")) indicatorConfigs.push({ id: "ma", params: { configs: [
      { type: "SMA", period: 9 }, { type: "SMA", period: 21 }, { type: "SMA", period: 50 } ] } });
    if (activeIndicators.has("supertrend")) indicatorConfigs.push({ id: "supertrend", params: {} });
    if (activeIndicators.has("volume_profile")) indicatorConfigs.push({ id: "volume_profile", params: {} });
    if (activeIndicators.has("rsi")) indicatorConfigs.push({ id: "rsi", params: {} });
    if (activeIndicators.has("macd")) indicatorConfigs.push({ id: "macd", params: {} });

    let data;
    try {
      data = await Api.post("/api/chart/candles", {
        exchange, token, symbol, interval, ...range, indicators: indicatorConfigs,
      });
    } catch (e) {
      document.getElementById("orderTicketResult").textContent = `Chart load failed: ${e.message}`;
      return;
    }

    currentSymbolMeta = { token, exchange, symbol };
    lastCandles = data.candles;
    renderCandles(data.candles);
    clearOverlays();
    if (data.indicators.ma) renderMA(data.candles, data.indicators.ma);
    if (data.indicators.supertrend) renderSupertrend(data.candles, data.indicators.supertrend);
    if (data.indicators.rsi) renderRSI(data.candles, data.indicators.rsi);
    if (data.indicators.macd) renderMACD(data.candles, data.indicators.macd);
    if (activeIndicators.has("cpr")) loadCPR(exchange, token, symbol, range);

    subscribeLiveTick(token, symbol);
  }

  function toTime(ts) {
    // backend ts is ISO datetime; lightweight-charts wants unix seconds for intraday
    return Math.floor(new Date(ts).getTime() / 1000);
  }

  function renderCandles(candles) {
    candleSeries.setData(candles.map((c) => ({ time: toTime(c.ts), open: c.open, high: c.high, low: c.low, close: c.close })));
    volumeSeries.setData(candles.map((c) => ({ time: toTime(c.ts), value: c.volume, color: c.close >= c.open ? "rgba(29,158,117,0.5)" : "rgba(216,90,48,0.5)" })));
  }

  function renderMA(candles, maData) {
    const colors = ["#378add", "#ef9f27", "#7f77dd", "#d4537e"];
    let i = 0;
    overlaySeries.ma = [];
    for (const [label, values] of Object.entries(maData)) {
      const s = priceChart.addLineSeries({ color: colors[i % colors.length], lineWidth: 1, title: label });
      s.setData(candles.map((c, idx) => ({ time: toTime(c.ts), value: values[idx] })).filter((p) => p.value != null));
      overlaySeries.ma.push(s);
      i++;
    }
  }

  function renderSupertrend(candles, st) {
    const up = priceChart.addLineSeries({ color: "#1d9e75", lineWidth: 2, title: "Supertrend" });
    const down = priceChart.addLineSeries({ color: "#d85a30", lineWidth: 2, title: "Supertrend" });
    const upData = [], downData = [];
    candles.forEach((c, idx) => {
      const v = st.value[idx];
      if (v == null) return;
      const point = { time: toTime(c.ts), value: v };
      if (st.direction[idx] === 1) upData.push(point);
      else downData.push(point);
    });
    up.setData(upData);
    down.setData(downData);
    overlaySeries.supertrend = [up, down];
  }

  function renderRSI(candles, values) {
    rsiSeries.setData(candles.map((c, idx) => ({ time: toTime(c.ts), value: values[idx] })).filter((p) => p.value != null));
  }

  function renderMACD(candles, macd) {
    macdLineSeries.setData(candles.map((c, idx) => ({ time: toTime(c.ts), value: macd.macd[idx] })).filter((p) => p.value != null));
    macdSignalSeries.setData(candles.map((c, idx) => ({ time: toTime(c.ts), value: macd.signal[idx] })).filter((p) => p.value != null));
    macdHistSeries.setData(candles.map((c, idx) => ({
      time: toTime(c.ts), value: macd.histogram[idx],
      color: (macd.histogram[idx] || 0) >= 0 ? "#639922" : "#e24b4a",
    })).filter((p) => p.value != null));
  }

  async function loadCPR(exchange, token, symbol, range) {
    try {
      const cpr = await Api.post("/api/chart/cpr", { exchange, token, symbol, interval: "day", ...range, indicators: [] });
      const pivot = priceChart.addLineSeries({ color: "#888780", lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, title: "CPR pivot" });
      const lastVal = cpr.pivot.filter((v) => v != null).slice(-1)[0];
      if (lastVal != null && lastCandles.length) {
        pivot.setData([
          { time: toTime(lastCandles[0].ts), value: lastVal },
          { time: toTime(lastCandles[lastCandles.length - 1].ts), value: lastVal },
        ]);
      }
      overlaySeries.cpr = [pivot];
    } catch (e) {
      console.warn("CPR load failed", e);
    }
  }

  function subscribeLiveTick(token, symbol) {
    Api.post("/api/chart/subscribe", { mode: "FULL", instruments: { [token]: symbol } }).catch(() => {});
  }

  function onTick(msg) {
    if (!currentSymbolMeta || msg.symbol !== currentSymbolMeta.symbol) return;
    if (msg.ltp != null && lastCandles.length) {
      candleSeries.update({ time: toTime(new Date().toISOString()), open: lastCandles.at(-1).close, high: msg.ltp, low: msg.ltp, close: msg.ltp });
    }
    if (msg.bids && msg.asks) renderDepth(msg.bids, msg.asks);
  }

  function renderDepth(bids, asks) {
    const tbody = document.querySelector("#depthTable tbody");
    tbody.innerHTML = "";
    for (let i = 0; i < Math.max(bids.length, asks.length); i++) {
      const b = bids[i] || {}, a = asks[i] || {};
      const tr = document.createElement("tr");
      tr.innerHTML = `<td class="bid">${b.quantity ?? ""}</td><td>${b.price ?? a.price ?? ""}</td><td class="ask">${a.quantity ?? ""}</td>`;
      tbody.appendChild(tr);
    }
  }

  async function submitOrder(evt) {
    evt.preventDefault();
    const submitter = evt.submitter;
    const side = submitter ? submitter.dataset.side : "BUY";
    const form = evt.target;
    const fd = new FormData(form);
    const body = {
      exchange: fd.get("exchange"),
      symbol: fd.get("symbol"),
      quantity: parseInt(fd.get("quantity"), 10),
      product: fd.get("product"),
      order_type: fd.get("order_type"),
      transaction_type: side,
      price: parseFloat(fd.get("price")) || 0,
    };
    const resultEl = document.getElementById("orderTicketResult");
    try {
      const res = await Api.post("/api/positions/orders", body);
      resultEl.textContent = `Order placed: ${res.order_id} (${res.paper_mode ? "paper" : "live"})`;
    } catch (e) {
      resultEl.textContent = `Order failed: ${e.message}`;
    }
  }

  return { init };
})();
