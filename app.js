const SYMBOLS = [
  { symbol: "BTCUSDT", label: "BTC/USDT", name: "比特币现货" },
  { symbol: "ETHUSDT", label: "ETH/USDT", name: "以太坊现货" },
  { symbol: "BNBUSDT", label: "BNB/USDT", name: "BNB现货" },
  { symbol: "SOLUSDT", label: "SOL/USDT", name: "索拉纳现货" },
  { symbol: "XRPUSDT", label: "XRP/USDT", name: "瑞波币现货" }
];

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"];
const INTERVAL_LABELS = {
  "1m": "1分钟",
  "5m": "5分钟",
  "15m": "15分钟",
  "1h": "1小时",
  "4h": "4小时",
  "1d": "1天"
};
const API_BASES = [
  "https://data-api.binance.vision/api/v3",
  "https://api.binance.com/api/v3"
];

const state = {
  symbol: "BTCUSDT",
  interval: "1m",
  candles: [],
  ticker: null,
  book: { bids: [], asks: [] },
  trades: [],
  markets: new Map(),
  apiBase: API_BASES[0],
  ws: null,
  candleWidth: 7,
  enabledMa: new Set([7, 25]),
  demoMode: false,
  crosshair: null
};

const els = {
  symbolSelect: document.querySelector("#symbolSelect"),
  intervalButtons: document.querySelector("#intervalButtons"),
  marketList: document.querySelector("#marketList"),
  marketFilter: document.querySelector("#marketFilter"),
  refreshButton: document.querySelector("#refreshButton"),
  connectionState: document.querySelector("#connectionState"),
  lastPrice: document.querySelector("#lastPrice"),
  priceChange: document.querySelector("#priceChange"),
  high24: document.querySelector("#high24"),
  low24: document.querySelector("#low24"),
  quoteVolume: document.querySelector("#quoteVolume"),
  priceCanvas: document.querySelector("#priceCanvas"),
  depthCanvas: document.querySelector("#depthCanvas"),
  crosshairTip: document.querySelector("#crosshairTip"),
  asks: document.querySelector("#asks"),
  bids: document.querySelector("#bids"),
  spreadRow: document.querySelector("#spreadRow"),
  tradeTape: document.querySelector("#tradeTape"),
  candleSummary: document.querySelector("#candleSummary"),
  simPrice: document.querySelector("#simPrice"),
  simQty: document.querySelector("#simQty"),
  simTotal: document.querySelector("#simTotal"),
  themeToggle: document.querySelector("#themeToggle")
};

function init() {
  renderIntervals();
  renderMarkets();
  bindEvents();
  resizeCanvas(els.priceCanvas);
  resizeCanvas(els.depthCanvas);
  loadAll();
  window.setInterval(refreshTickerOnly, 15_000);
}

function bindEvents() {
  els.symbolSelect.addEventListener("change", () => {
    state.symbol = els.symbolSelect.value;
    loadAll();
  });

  els.marketFilter.addEventListener("input", renderMarkets);
  els.refreshButton.addEventListener("click", loadAll);
  els.themeToggle.addEventListener("click", () => {
    document.documentElement.classList.toggle("light-detail");
  });

  document.querySelectorAll("[data-ma]").forEach((button) => {
    button.addEventListener("click", () => {
      const period = Number(button.dataset.ma);
      if (state.enabledMa.has(period)) {
        state.enabledMa.delete(period);
        button.classList.remove("active");
      } else {
        state.enabledMa.add(period);
        button.classList.add("active");
      }
      drawPriceChart();
    });
  });

  document.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-tab]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      document.querySelector("#bookView").classList.toggle("hidden", button.dataset.tab !== "book");
      document.querySelector("#tradesView").classList.toggle("hidden", button.dataset.tab !== "trades");
    });
  });

  els.priceCanvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const direction = Math.sign(event.deltaY);
    state.candleWidth = clamp(state.candleWidth - direction, 4, 14);
    drawPriceChart();
  }, { passive: false });

  els.priceCanvas.addEventListener("mousemove", (event) => {
    const rect = els.priceCanvas.getBoundingClientRect();
    state.crosshair = {
      x: (event.clientX - rect.left) * window.devicePixelRatio,
      y: (event.clientY - rect.top) * window.devicePixelRatio,
      clientX: event.clientX - rect.left,
      clientY: event.clientY - rect.top
    };
    drawPriceChart();
  });

  els.priceCanvas.addEventListener("mouseleave", () => {
    state.crosshair = null;
    els.crosshairTip.hidden = true;
    drawPriceChart();
  });

  els.simPrice.addEventListener("input", updateSimulation);
  els.simQty.addEventListener("input", updateSimulation);

  window.addEventListener("resize", () => {
    resizeCanvas(els.priceCanvas);
    resizeCanvas(els.depthCanvas);
    drawAll();
  });
}

function renderIntervals() {
  els.intervalButtons.replaceChildren();
  INTERVALS.forEach((interval) => {
    const button = document.createElement("button");
    button.className = `interval-button${interval === state.interval ? " active" : ""}`;
    button.textContent = INTERVAL_LABELS[interval] || interval;
    button.addEventListener("click", () => {
      state.interval = interval;
      document.querySelectorAll(".interval-button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      loadAll();
    });
    els.intervalButtons.append(button);
  });
}

async function loadAll() {
  setConnection("加载中");
  closeWebSocket();
  try {
    const [candles, ticker, book, trades, markets] = await Promise.all([
      apiGet("/klines", { symbol: state.symbol, interval: state.interval, limit: "260" }),
      apiGet("/ticker/24hr", { symbol: state.symbol }),
      apiGet("/depth", { symbol: state.symbol, limit: "20" }),
      apiGet("/trades", { symbol: state.symbol, limit: "40" }),
      apiGet("/ticker/24hr", {})
    ]);
    state.demoMode = false;
    state.candles = candles.map(parseCandle);
    state.ticker = ticker;
    state.book = parseBook(book);
    state.trades = trades.map(parseTrade).reverse();
    cacheMarkets(markets);
    setConnection("实时");
    openWebSocket();
  } catch (error) {
    console.warn("Market data request failed, using local demo data.", error);
    loadDemoData();
    setConnection("演示");
  }
  syncInputs();
  renderMarkets();
  drawAll();
}

async function refreshTickerOnly() {
  if (state.demoMode) {
    advanceDemo();
    return;
  }
  try {
    state.ticker = await apiGet("/ticker/24hr", { symbol: state.symbol });
    updateHeader();
  } catch {
    setConnection("延迟");
  }
}

async function apiGet(path, params) {
  const query = new URLSearchParams(params).toString();
  const errors = [];
  for (const base of API_BASES) {
    try {
      const url = `${base}${path}${query ? `?${query}` : ""}`;
      const response = await fetchWithTimeout(url, 7000);
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      state.apiBase = base;
      return response.json();
    } catch (error) {
      errors.push(`${base}: ${error.message}`);
    }
  }
  throw new Error(errors.join("; "));
}

function fetchWithTimeout(url, timeoutMs) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  return fetch(url, { signal: controller.signal, cache: "no-store" })
    .finally(() => window.clearTimeout(timeout));
}

function openWebSocket() {
  const symbol = state.symbol.toLowerCase();
  const streams = [
    `${symbol}@kline_${state.interval}`,
    `${symbol}@depth20@100ms`,
    `${symbol}@trade`
  ].join("/");
  const url = `wss://stream.binance.com:9443/stream?streams=${streams}`;

  try {
    state.ws = new WebSocket(url);
    state.ws.onopen = () => setConnection("实时");
    state.ws.onmessage = (event) => handleStream(JSON.parse(event.data));
    state.ws.onerror = () => setConnection("延迟");
    state.ws.onclose = () => {
      if (!state.demoMode) setConnection("轮询");
    };
  } catch {
    setConnection("轮询");
  }
}

function closeWebSocket() {
  if (state.ws) {
    state.ws.close();
    state.ws = null;
  }
}

function handleStream(message) {
  const data = message.data;
  if (!data) return;
  if (data.e === "kline") {
    upsertCandle({
      time: data.k.t,
      open: Number(data.k.o),
      high: Number(data.k.h),
      low: Number(data.k.l),
      close: Number(data.k.c),
      volume: Number(data.k.v)
    });
    state.ticker = {
      ...state.ticker,
      lastPrice: data.k.c
    };
    syncInputs();
    drawPriceChart();
    updateHeader();
  }
  if (data.e === "depthUpdate" && data.b && data.a) {
    state.book = {
      bids: data.b.slice(0, 20).map(([price, qty]) => ({ price: Number(price), qty: Number(qty) })),
      asks: data.a.slice(0, 20).map(([price, qty]) => ({ price: Number(price), qty: Number(qty) }))
    };
    renderBook();
    drawDepthChart();
  }
  if (data.e === "trade") {
    state.trades.unshift({
      price: Number(data.p),
      qty: Number(data.q),
      time: data.T,
      side: data.m ? "sell" : "buy"
    });
    state.trades = state.trades.slice(0, 80);
    renderTrades();
  }
}

function parseCandle(row) {
  return {
    time: Number(row[0]),
    open: Number(row[1]),
    high: Number(row[2]),
    low: Number(row[3]),
    close: Number(row[4]),
    volume: Number(row[5])
  };
}

function parseBook(book) {
  return {
    bids: book.bids.map(([price, qty]) => ({ price: Number(price), qty: Number(qty) })),
    asks: book.asks.map(([price, qty]) => ({ price: Number(price), qty: Number(qty) }))
  };
}

function parseTrade(trade) {
  return {
    price: Number(trade.price),
    qty: Number(trade.qty),
    time: trade.time,
    side: trade.isBuyerMaker ? "sell" : "buy"
  };
}

function cacheMarkets(markets) {
  if (!Array.isArray(markets)) return;
  SYMBOLS.forEach(({ symbol }) => {
    const ticker = markets.find((item) => item.symbol === symbol);
    if (ticker) state.markets.set(symbol, ticker);
  });
}

function upsertCandle(candle) {
  const last = state.candles[state.candles.length - 1];
  if (last && last.time === candle.time) {
    state.candles[state.candles.length - 1] = candle;
  } else {
    state.candles.push(candle);
    state.candles = state.candles.slice(-300);
  }
}

function loadDemoData() {
  const base = state.symbol.startsWith("ETH") ? 3200 : state.symbol.startsWith("SOL") ? 170 : 64000;
  const now = Date.now();
  const step = intervalMs(state.interval);
  const candles = [];
  let close = base;
  for (let index = 260; index > 0; index -= 1) {
    const open = close;
    const wave = Math.sin(index / 9) * base * 0.002;
    const drift = (Math.random() - 0.48) * base * 0.003;
    close = Math.max(base * 0.7, open + wave + drift);
    const high = Math.max(open, close) + Math.random() * base * 0.002;
    const low = Math.min(open, close) - Math.random() * base * 0.002;
    candles.push({
      time: now - index * step,
      open,
      high,
      low,
      close,
      volume: 30 + Math.random() * 120
    });
  }
  state.candles = candles;
  const last = candles[candles.length - 1];
  state.ticker = {
    symbol: state.symbol,
    lastPrice: String(last.close),
    priceChangePercent: "1.28",
    highPrice: String(last.high * 1.012),
    lowPrice: String(last.low * 0.988),
    quoteVolume: String(last.close * 23800)
  };
  state.book = makeDemoBook(last.close);
  state.trades = makeDemoTrades(last.close);
  SYMBOLS.forEach((item, index) => {
    state.markets.set(item.symbol, {
      symbol: item.symbol,
      lastPrice: String(base * (1 + index * 0.07)),
      priceChangePercent: String((Math.sin(index + 1) * 2.4).toFixed(2)),
      quoteVolume: String(base * (10000 + index * 2000))
    });
  });
}

function advanceDemo() {
  const last = state.candles[state.candles.length - 1];
  if (!last) return;
  const close = last.close * (1 + (Math.random() - 0.5) * 0.002);
  const candle = {
    time: Date.now(),
    open: last.close,
    high: Math.max(last.close, close) * 1.001,
    low: Math.min(last.close, close) * 0.999,
    close,
    volume: 20 + Math.random() * 80
  };
  upsertCandle(candle);
  state.ticker = {
    ...state.ticker,
    lastPrice: String(close)
  };
  state.book = makeDemoBook(close);
  state.trades.unshift(...makeDemoTrades(close).slice(0, 2));
  state.trades = state.trades.slice(0, 80);
  syncInputs();
  drawAll();
}

function makeDemoBook(mid) {
  const bids = [];
  const asks = [];
  for (let index = 1; index <= 20; index += 1) {
    bids.push({ price: mid * (1 - index * 0.00025), qty: 0.15 + Math.random() * 3 });
    asks.push({ price: mid * (1 + index * 0.00025), qty: 0.15 + Math.random() * 3 });
  }
  return { bids, asks };
}

function makeDemoTrades(mid) {
  return Array.from({ length: 40 }, (_, index) => ({
    price: mid * (1 + (Math.random() - 0.5) * 0.002),
    qty: 0.005 + Math.random() * 0.24,
    time: Date.now() - index * 2200,
    side: Math.random() > 0.5 ? "buy" : "sell"
  }));
}

function intervalMs(interval) {
  const map = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000
  };
  return map[interval] || 60_000;
}

function drawAll() {
  updateHeader();
  renderBook();
  renderTrades();
  drawPriceChart();
  drawDepthChart();
  updateSimulation();
}

function syncInputs() {
  const last = lastPrice();
  if (Number.isFinite(last)) {
    els.simPrice.value = formatPrice(last);
  }
}

function updateHeader() {
  const ticker = state.ticker || {};
  const last = Number(ticker.lastPrice);
  const change = Number(ticker.priceChangePercent);
  els.lastPrice.textContent = Number.isFinite(last) ? formatPrice(last) : "--";
  els.lastPrice.className = `last-price ${change < 0 ? "negative" : "positive"}`;
  els.priceChange.textContent = Number.isFinite(change) ? `${change >= 0 ? "+" : ""}${change.toFixed(2)}%` : "--";
  els.priceChange.className = change < 0 ? "negative" : "positive";
  els.high24.textContent = formatOptionalPrice(ticker.highPrice);
  els.low24.textContent = formatOptionalPrice(ticker.lowPrice);
  els.quoteVolume.textContent = formatCompact(ticker.quoteVolume);

  const latest = state.candles[state.candles.length - 1];
  if (latest) {
    els.candleSummary.textContent =
      `开盘 ${formatPrice(latest.open)}  最高 ${formatPrice(latest.high)}  最低 ${formatPrice(latest.low)}  收盘 ${formatPrice(latest.close)}`;
  }
}

function renderMarkets() {
  const filter = els.marketFilter.value.trim().toLowerCase();
  els.marketList.replaceChildren();
  SYMBOLS
    .filter((item) => !filter || item.symbol.toLowerCase().includes(filter) || item.name.toLowerCase().includes(filter))
    .forEach((item) => {
      const ticker = state.markets.get(item.symbol);
      const change = Number(ticker?.priceChangePercent || 0);
      const row = document.createElement("button");
      row.className = `market-row${item.symbol === state.symbol ? " active" : ""}`;
      const left = document.createElement("span");
      const symbol = document.createElement("span");
      symbol.className = "market-symbol";
      symbol.textContent = item.label;
      const name = document.createElement("span");
      name.className = "market-name";
      name.textContent = item.name;
      left.append(symbol, name);

      const right = document.createElement("span");
      right.className = "market-price";
      const price = document.createElement("span");
      price.textContent = formatOptionalPrice(ticker?.lastPrice);
      const changeNode = document.createElement("span");
      changeNode.className = `market-change ${change < 0 ? "negative" : "positive"}`;
      changeNode.textContent = Number.isFinite(change) ? `${change >= 0 ? "+" : ""}${change.toFixed(2)}%` : "--";
      right.append(price, changeNode);

      row.append(left, right);
      row.addEventListener("click", () => {
        state.symbol = item.symbol;
        els.symbolSelect.value = item.symbol;
        loadAll();
      });
      els.marketList.append(row);
    });
}

function renderBook() {
  renderBookSide(els.asks, [...state.book.asks].reverse(), "ask");
  renderBookSide(els.bids, state.book.bids, "bid");
  const bestAsk = state.book.asks[0]?.price;
  const bestBid = state.book.bids[0]?.price;
  if (bestAsk && bestBid) {
    const spread = bestAsk - bestBid;
    els.spreadRow.textContent = `价差 ${formatPrice(spread)} (${((spread / bestBid) * 100).toFixed(3)}%)`;
  } else {
    els.spreadRow.textContent = "--";
  }
}

function renderBookSide(container, rows, side) {
  const totals = [];
  rows.reduce((sum, row, index) => {
    totals[index] = sum + row.qty;
    return totals[index];
  }, 0);
  const maxTotal = Math.max(...totals, 1);
  container.replaceChildren();
  rows.slice(0, 14).forEach((row, index) => {
    const div = document.createElement("div");
    div.className = "book-row";
    div.style.setProperty("--depth-width", `${(totals[index] / maxTotal) * 100}%`);
    const price = document.createElement("span");
    price.className = side === "ask" ? "negative" : "positive";
    price.textContent = formatPrice(row.price);
    const qty = document.createElement("span");
    qty.textContent = formatQty(row.qty);
    const total = document.createElement("span");
    total.textContent = formatQty(totals[index]);
    div.append(price, qty, total);
    container.append(div);
  });
}

function renderTrades() {
  els.tradeTape.replaceChildren();
  state.trades.slice(0, 34).forEach((trade) => {
    const row = document.createElement("div");
    row.className = "trade-row";
    const price = document.createElement("span");
    price.className = trade.side === "sell" ? "negative" : "positive";
    price.textContent = formatPrice(trade.price);
    const qty = document.createElement("span");
    qty.textContent = formatQty(trade.qty);
    const time = document.createElement("span");
    time.textContent = formatTime(trade.time);
    row.append(price, qty, time);
    els.tradeTape.append(row);
  });
}

function drawPriceChart() {
  resizeCanvas(els.priceCanvas);
  const canvas = els.priceCanvas;
  const ctx = canvas.getContext("2d");
  const { width, height } = canvas;
  const scale = window.devicePixelRatio || 1;
  ctx.clearRect(0, 0, width, height);
  drawPanelBackground(ctx, width, height);

  const candles = visibleCandles(width);
  if (candles.length < 2) return;

  const volumeHeight = Math.max(74 * scale, height * 0.18);
  const chartHeight = height - volumeHeight - 28 * scale;
  const left = 14 * scale;
  const right = (canvas.clientWidth < 520 ? 128 : 92) * scale;
  const top = 16 * scale;
  const bottom = top + chartHeight;
  const plotWidth = width - left - right;
  const priceRange = priceBounds(candles);
  const maxVolume = Math.max(...candles.map((item) => item.volume), 1);
  const xStep = plotWidth / candles.length;

  drawGrid(ctx, left, top, plotWidth, chartHeight, priceRange);
  drawMaLines(ctx, candles, left, top, plotWidth, chartHeight, priceRange);

  candles.forEach((candle, index) => {
    const x = left + index * xStep + xStep / 2;
    const openY = priceToY(candle.open, top, chartHeight, priceRange);
    const closeY = priceToY(candle.close, top, chartHeight, priceRange);
    const highY = priceToY(candle.high, top, chartHeight, priceRange);
    const lowY = priceToY(candle.low, top, chartHeight, priceRange);
    const up = candle.close >= candle.open;
    const color = up ? "#13b981" : "#ef5f67";
    const bodyWidth = clamp(xStep * 0.62, 2, 10);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, highY);
    ctx.lineTo(x, lowY);
    ctx.stroke();
    ctx.fillRect(x - bodyWidth / 2, Math.min(openY, closeY), bodyWidth, Math.max(1.5, Math.abs(closeY - openY)));

    const volumeTop = height - volumeHeight + 18;
    const volumeBar = (candle.volume / maxVolume) * (volumeHeight - 30);
    ctx.globalAlpha = 0.45;
    ctx.fillRect(x - bodyWidth / 2, height - 12 - volumeBar, bodyWidth, volumeBar);
    ctx.globalAlpha = 1;
  });

  drawAxes(ctx, candles, left, top, plotWidth, chartHeight, priceRange, bottom, height);
  drawCrosshair(ctx, candles, left, top, plotWidth, chartHeight, priceRange);
}

function drawDepthChart() {
  resizeCanvas(els.depthCanvas);
  const canvas = els.depthCanvas;
  const ctx = canvas.getContext("2d");
  const { width, height } = canvas;
  ctx.clearRect(0, 0, width, height);
  drawPanelBackground(ctx, width, height);

  const bids = cumulativeDepth([...state.book.bids].reverse());
  const asks = cumulativeDepth(state.book.asks);
  const rows = [...bids, ...asks];
  if (!rows.length) return;

  const maxTotal = Math.max(...rows.map((item) => item.total), 1);
  const midX = width / 2;
  const top = 20;
  const bottom = height - 24;

  drawDepthSide(ctx, bids, 14, midX - 10, top, bottom, maxTotal, "bid");
  drawDepthSide(ctx, asks, midX + 10, width - 14, top, bottom, maxTotal, "ask");

  ctx.strokeStyle = "#262a33";
  ctx.beginPath();
  ctx.moveTo(midX, top);
  ctx.lineTo(midX, bottom);
  ctx.stroke();

  ctx.fillStyle = "#8b95a7";
  ctx.font = `${12 * window.devicePixelRatio}px system-ui`;
  ctx.fillText("深度", 14, 15 * window.devicePixelRatio);
}

function drawDepthSide(ctx, rows, startX, endX, top, bottom, maxTotal, side) {
  if (!rows.length) return;
  const color = side === "bid" ? "rgba(19, 185, 129, 0.28)" : "rgba(239, 95, 103, 0.28)";
  const line = side === "bid" ? "#13b981" : "#ef5f67";
  const width = endX - startX;
  ctx.beginPath();
  rows.forEach((row, index) => {
    const x = startX + (index / Math.max(rows.length - 1, 1)) * width;
    const y = bottom - (row.total / maxTotal) * (bottom - top);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineTo(endX, bottom);
  ctx.lineTo(startX, bottom);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = line;
  ctx.stroke();
}

function cumulativeDepth(rows) {
  let total = 0;
  return rows.map((row) => {
    total += row.qty;
    return { ...row, total };
  });
}

function visibleCandles(width) {
  const count = Math.floor((width - 86) / state.candleWidth);
  return state.candles.slice(-clamp(count, 40, 260));
}

function priceBounds(candles) {
  const high = Math.max(...candles.map((item) => item.high));
  const low = Math.min(...candles.map((item) => item.low));
  const pad = (high - low) * 0.08 || high * 0.01;
  return { min: low - pad, max: high + pad };
}

function priceToY(price, top, height, bounds) {
  return top + ((bounds.max - price) / (bounds.max - bounds.min)) * height;
}

function yToPrice(y, top, height, bounds) {
  return bounds.max - ((y - top) / height) * (bounds.max - bounds.min);
}

function drawPanelBackground(ctx, width, height) {
  ctx.fillStyle = "#111318";
  ctx.fillRect(0, 0, width, height);
}

function drawGrid(ctx, left, top, width, height, bounds) {
  ctx.strokeStyle = "#262a33";
  ctx.lineWidth = 1;
  ctx.font = `${11 * window.devicePixelRatio}px system-ui`;
  ctx.fillStyle = "#8b95a7";
  for (let index = 0; index <= 5; index += 1) {
    const y = top + (height / 5) * index;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + width, y);
    ctx.stroke();
    const price = bounds.max - ((bounds.max - bounds.min) / 5) * index;
    ctx.fillText(formatPrice(price), left + width + 10, y + 4);
  }
  for (let index = 0; index <= 6; index += 1) {
    const x = left + (width / 6) * index;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, top + height);
    ctx.stroke();
  }
}

function drawAxes(ctx, candles, left, top, width, height, bounds, bottom, canvasHeight) {
  ctx.strokeStyle = "#343946";
  ctx.beginPath();
  ctx.moveTo(left, top);
  ctx.lineTo(left, top + height);
  ctx.lineTo(left + width, top + height);
  ctx.stroke();

  ctx.fillStyle = "#8b95a7";
  ctx.font = `${11 * window.devicePixelRatio}px system-ui`;
  for (let index = 0; index <= 4; index += 1) {
    const candle = candles[Math.floor((candles.length - 1) * (index / 4))];
    if (!candle) continue;
    const x = left + width * (index / 4);
    ctx.fillText(formatDate(candle.time), x, canvasHeight - 8);
  }

  const latest = candles[candles.length - 1];
  const y = priceToY(latest.close, top, height, bounds);
  ctx.fillStyle = latest.close >= latest.open ? "#13b981" : "#ef5f67";
  ctx.fillRect(left + width + 6, y - 10, 64, 20);
  ctx.fillStyle = "#ffffff";
  ctx.fillText(formatPrice(latest.close), left + width + 10, y + 4);
}

function drawMaLines(ctx, candles, left, top, width, height, bounds) {
  const colors = {
    7: "#e8ad2d",
    25: "#5aa7ff",
    99: "#d26dff"
  };
  [...state.enabledMa].forEach((period) => {
    const values = movingAverage(candles, period);
    ctx.strokeStyle = colors[period];
    ctx.lineWidth = 1.2 * window.devicePixelRatio;
    ctx.beginPath();
    values.forEach((value, index) => {
      if (value == null) return;
      const x = left + (index / Math.max(candles.length - 1, 1)) * width;
      const y = priceToY(value, top, height, bounds);
      if (index === period - 1) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
}

function movingAverage(candles, period) {
  const result = [];
  let sum = 0;
  candles.forEach((candle, index) => {
    sum += candle.close;
    if (index >= period) sum -= candles[index - period].close;
    result.push(index >= period - 1 ? sum / period : null);
  });
  return result;
}

function drawCrosshair(ctx, candles, left, top, width, height, bounds) {
  if (!state.crosshair) return;
  const { x, y, clientX, clientY } = state.crosshair;
  const inChart = x >= left && x <= left + width && y >= top && y <= top + height;
  if (!inChart) {
    els.crosshairTip.hidden = true;
    return;
  }
  const index = clamp(Math.round(((x - left) / width) * (candles.length - 1)), 0, candles.length - 1);
  const candle = candles[index];
  const candleX = left + (index / Math.max(candles.length - 1, 1)) * width;
  const price = yToPrice(y, top, height, bounds);

  ctx.strokeStyle = "rgba(232, 237, 246, 0.38)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(candleX, top);
  ctx.lineTo(candleX, top + height);
  ctx.moveTo(left, y);
  ctx.lineTo(left + width, y);
  ctx.stroke();
  ctx.setLineDash([]);

  els.crosshairTip.hidden = false;
  els.crosshairTip.style.left = `${Math.min(clientX + 18, els.priceCanvas.clientWidth - 238)}px`;
  els.crosshairTip.style.top = `${Math.max(12, clientY - 78)}px`;
  const lines = [
    `${formatDateTime(candle.time)} · ${formatPrice(price)}`,
    `开盘 ${formatPrice(candle.open)} 最高 ${formatPrice(candle.high)}`,
    `最低 ${formatPrice(candle.low)} 收盘 ${formatPrice(candle.close)}`,
    `成交量 ${formatQty(candle.volume)}`
  ].map((text) => {
    const line = document.createElement("div");
    line.textContent = text;
    return line;
  });
  els.crosshairTip.replaceChildren(...lines);
}

function updateSimulation() {
  const price = Number(els.simPrice.value);
  const qty = Number(els.simQty.value);
  if (!Number.isFinite(price) || !Number.isFinite(qty)) {
    els.simTotal.textContent = "-- USDT";
    return;
  }
  els.simTotal.textContent = `${formatPrice(price * qty)} USDT`;
}

function lastPrice() {
  const tickerPrice = Number(state.ticker?.lastPrice);
  if (Number.isFinite(tickerPrice)) return tickerPrice;
  return state.candles[state.candles.length - 1]?.close;
}

function setConnection(label) {
  els.connectionState.textContent = label;
}

function resizeCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(rect.width * ratio));
  const height = Math.max(1, Math.floor(rect.height * ratio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function formatPrice(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  if (number >= 1000) return number.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (number >= 1) return number.toLocaleString("en-US", { maximumFractionDigits: 4 });
  return number.toLocaleString("en-US", { maximumFractionDigits: 6 });
}

function formatOptionalPrice(value) {
  return value == null ? "--" : formatPrice(value);
}

function formatQty(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  if (number >= 1000) return number.toLocaleString("en-US", { maximumFractionDigits: 0 });
  return number.toLocaleString("en-US", { maximumFractionDigits: 5 });
}

function formatCompact(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  if (Math.abs(number) >= 100_000_000) {
    return `${(number / 100_000_000).toFixed(2)}亿`;
  }
  if (Math.abs(number) >= 10_000) {
    return `${(number / 10_000).toFixed(2)}万`;
  }
  return number.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function formatTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString("zh-CN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function formatDate(timestamp) {
  const date = new Date(timestamp);
  if (state.interval.endsWith("d")) {
    return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
  }
  return date.toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit" });
}

function formatDateTime(timestamp) {
  return new Date(timestamp).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });
}

init();
