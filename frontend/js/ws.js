// Pub/sub over the two backend websockets. Any tab can do
// TerminalWS.onMarket(fn) / TerminalWS.onOrders(fn) without needing to know
// about reconnection, JSON parsing, etc.
const TerminalWS = (() => {
  const marketListeners = [];
  const orderListeners = [];
  let marketSocket, orderSocket;
  let connected = { market: false, orders: false };

  function updateStatusPill() {
    const el = document.getElementById("connStatus");
    if (!el) return;
    if (connected.market && connected.orders) {
      el.textContent = "live";
      el.className = "pill pill-ok";
    } else if (connected.market || connected.orders) {
      el.textContent = "partial";
      el.className = "pill pill-warning";
    } else {
      el.textContent = "disconnected";
      el.className = "pill pill-muted";
    }
  }

  function connectSocket(path, onMessage, key) {
    const url = `ws://${location.host}${path}`;
    const sock = new WebSocket(url);
    sock.onopen = () => { connected[key] = true; updateStatusPill(); };
    sock.onclose = () => {
      connected[key] = false;
      updateStatusPill();
      setTimeout(() => connectSocket(path, onMessage, key), 3000); // simple backoff-free retry
    };
    sock.onerror = () => sock.close();
    sock.onmessage = (evt) => {
      try {
        onMessage(JSON.parse(evt.data));
      } catch (e) {
        console.warn("Bad WS payload", e);
      }
    };
    return sock;
  }

  function init() {
    marketSocket = connectSocket("/ws/market", (msg) => marketListeners.forEach((fn) => fn(msg)), "market");
    orderSocket = connectSocket("/ws/orders", (msg) => orderListeners.forEach((fn) => fn(msg)), "orders");
  }

  return {
    init,
    onMarket(fn) { marketListeners.push(fn); },
    onOrders(fn) { orderListeners.push(fn); },
  };
})();
