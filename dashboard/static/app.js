/* Trader Dashboard - single page app. No dependencies. */
(function () {
  "use strict";
  const $ = (sel, el) => (el || document).querySelector(sel);
  const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
  const view = $("#view");
  const { fmt, fmtVol, sparkline, donut, PriceChart } = window.TChart;
  const PRO = window.ProCharts || null;
  const Price = PRO ? PRO.ProChart : PriceChart; // TradingView Lightweight Charts when available

  // ------------------------------------------------------------ helpers
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? esc(u) : "#");
  const dp = (x) => (x != null && Math.abs(x) < 2 ? 4 : 2);
  const money = (x, ccy) => {
    if (x == null) return "–";
    try { return new Intl.NumberFormat(undefined, { style: "currency", currency: ccy && ccy.length === 3 && ccy !== "GBp" ? ccy : "USD", maximumFractionDigits: Math.abs(x) < 2 ? 4 : 2 }).format(x).replace("US$", "$"); }
    catch (e) { return fmt(x, 2); }
  };
  const priceStr = (x, ccy) => (ccy === "GBp" || ccy === "GBX" ? fmt(x, 2) + "p" : money(x, ccy));
  const shares = (q) => (q == null ? "–" : Number(q).toLocaleString(undefined, { maximumFractionDigits: 4 }));
  const pct = (x, d) => (x == null ? "–" : x >= 1000 ? "×" + Math.round(1 + x / 100).toLocaleString() : (x > 0 ? "+" : "") + Number(x).toFixed(d == null ? (Math.abs(x) >= 10 ? 1 : 2) : d) + "%");
  const cls = (x) => (x == null ? "" : x >= 0 ? "up" : "down");
  const ago = (t) => {
    if (!t) return "";
    const s = Date.now() / 1000 - t;
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + "m ago";
    if (s < 86400) return Math.round(s / 3600) + "h ago";
    return Math.round(s / 86400) + "d ago";
  };
  const ratingBadge = (r) => r ? `<span class="badge b-${r.toLowerCase().replace(/\s/g, "")}">${esc(r)}</span>` : "";
  const entryClass = (st) => !st ? "e-none" : st.startsWith("Buy") ? "e-now" : st.startsWith("Wait") ? "e-wait" : st.startsWith("Watch") ? "e-watch" : st === "Avoid" ? "e-avoid" : "e-none";
  const entryBadge = (st) => st ? `<span class="badge ${entryClass(st)}">${esc(st)}</span>` : "";
  const meter = (score) => `<span class="meter" title="Signal score ${score}/100"><i><b class="${score >= 75 ? "hi" : score >= 50 ? "mid" : "lo"}" style="width:${score}%"></b></i><span class="num">${score}</span></span>`;
  const logo = (sym, size) => `<img class="logo" src="/logo/${encodeURIComponent(sym)}" alt="" width="${size || 28}" height="${size || 28}" loading="lazy" decoding="async">`;
  const isLT = () => (settings().mode || "lt") === "lt";
  const skeleton = (rows) => Array.from({ length: rows || 6 }, () => '<div class="skeleton"></div>').join("");
  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.hidden = false;
    clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), 3200);
  }

  let freshOn = false; // set while a refresh button runs: every request skips the server cache
  async function api(path, opts) {
    if (freshOn) path += (path.includes("?") ? "&" : "?") + "fresh=1";
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({ error: "Bad response from server" }));
    if (!res.ok) throw new Error(data.error || "Request failed (" + res.status + ")");
    return data;
  }
  const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.assign({}, body, freshOn ? { fresh: true } : {})) });

  // Refresh buttons: rf("key") renders "Updated hh:mm:ss  ↻"; RF[key] reloads that section with fresh data.
  let RF = {};
  const RF_NAMES = { market: "market signals", wl: "watchlist", hnews: "news", screener: "market table", signals: "signals", quote: "quote and plan", chart: "chart",
    perf: "performance", fund: "fundamentals", brief: "briefing", corr: "correlation", entry: "entry check", snews: "news", pos: "positions", hist: "performance history", journal: "trade journal", map: "market map", radar: "AI radar", news: "news", runners: "day runners" };
  const rf = (key) => `<span class="rf-wrap"><span class="upd" data-upd="${key}"></span><button type="button" class="rf" data-rf="${key}" title="Refresh with the latest data" aria-label="Refresh ${RF_NAMES[key] || "this section"}"><i data-lucide="rotate-cw"></i></button></span>`;
  const stamp = (key) => $$(`[data-upd="${key}"]`).forEach((el) => (el.textContent = "Updated " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })));
  async function runRefresh(key, btn) {
    if (!RF[key]) return;
    btn && (btn.disabled = true, btn.classList.add("spin"));
    freshOn = true;
    try { await RF[key](); stamp(key); const sr = $("#srStatus"); if (sr) sr.textContent = (RF_NAMES[key] || "Section") + " updated"; }
    catch (e) { toast("Refresh failed: " + e.message); }
    finally { freshOn = false; btn && (btn.disabled = false, btn.classList.remove("spin")); }
  }
  document.addEventListener("click", (e) => { const b = e.target.closest("[data-rf]"); if (b) { e.preventDefault(); e.stopPropagation(); runRefresh(b.dataset.rf, b); } });

  // ------------------------------------------------------------ local storage
  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem("td." + k)) ?? d; } catch (e) { return d; } },
    set(k, v) { localStorage.setItem("td." + k, JSON.stringify(v)); },
  };
  const watchlist = () => store.get("watchlist", ["AAPL", "NVDA", "MSFT", "TSLA", "SPY"]);
  const toggleWatch = (sym) => {
    const w = watchlist(); const i = w.indexOf(sym);
    i >= 0 ? w.splice(i, 1) : w.push(sym);
    store.set("watchlist", w); toast(i >= 0 ? sym + " removed from watchlist" : sym + " added to watchlist");
    return i < 0;
  };
  const settings = () => Object.assign({ riskPct: 1, account: 10000 }, store.get("settings", {}));
  const manual = () => store.get("manual", []);

  // ------------------------------------------------------------ shared data
  const state = { screener: null, screenerAt: 0, universe: null, t212: null, t212Status: null };
  async function getUniverse() { return state.universe || (state.universe = await api("/api/universe")); }
  async function getScreener(force) {
    force = force || freshOn;
    if (!force && state.screener && Date.now() - state.screenerAt < 120000) return state.screener;
    const rows = await api("/api/screener?list=all");
    const seen = new Set();
    state.screener = rows.filter((r) => !r.error && !seen.has(r.symbol + r.group) && seen.add(r.symbol + r.group));
    state.screenerAt = Date.now();
    return state.screener;
  }
  async function getRevolut(force) {
    if (state.revolut === undefined || force) state.revolut = await api("/api/revolut/portfolio").catch(() => null);
    return state.revolut && state.revolut.linked ? state.revolut : null;
  }
  // every broker position (Trading 212 + Revolut import), each tagged with its source
  function brokerPositions() {
    const t = state.t212 && !state.t212.error ? state.t212.positions.map((p) => Object.assign({ source: "Trading 212" }, p)) : [];
    const r = state.revolut && state.revolut.linked ? state.revolut.positions.map((p) => Object.assign({ source: state.revolut.broker || "Revolut" }, p)) : [];
    return t.concat(r);
  }
  async function getT212(force) {
    await getRevolut(force);
    if (!state.t212Status || force) state.t212Status = await api("/api/t212/status").catch(() => ({ linked: false }));
    if (!state.t212Status.linked) return null;
    try { state.t212 = await api("/api/t212/portfolio"); } catch (e) { state.t212 = { error: e.message }; }
    return state.t212;
  }

  // ------------------------------------------------------------ index strip
  async function loadStrip() {
    const u = await getUniverse();
    const rows = await api("/api/quotes?symbols=" + encodeURIComponent(u.indices.join(",")));
    const names = { "^VIX": "VIX", "BTC-USD": "Bitcoin", "EURUSD=X": "EUR/USD", SPY: "S&P 500 (SPY)", QQQ: "Nasdaq 100 (QQQ)", DIA: "Dow (DIA)", IWM: "Russell 2000 (IWM)", GLD: "Gold (GLD)" };
    $("#strip").innerHTML = `<a class="chip mood-chip" href="#/" id="moodChip" title="Market mood"></a>` + rows.filter((r) => !r.error).map((r) =>
      `<a class="chip" href="#/stock/${encodeURIComponent(r.symbol)}"><span class="s">${esc(names[r.symbol] || r.symbol)}</span>` +
      `<span class="num">${fmt(r.price, dp(r.price))}</span><span class="num ${cls(r.changePct)}">${pct(r.changePct)}</span></a>`).join("");
    if (window.Trade) window.Trade.regime($("#moodChip"), true);
  }

  document.addEventListener("click", (e) => { if (e.target.closest("#bell") && window.Trade) window.Trade.openAlerts(); });

  // ------------------------------------------------------------ search
  (function setupSearch() {
    const input = $("#searchInput"), list = $("#searchResults");
    let timer, items = [], sel = -1;
    const render = () => {
      list.innerHTML = items.map((x, i) => `<li><a href="#/stock/${encodeURIComponent(x.symbol)}" class="${i === sel ? "sel" : ""}">` +
        `<span><b>${esc(x.symbol)}</b> <span class="muted">${esc(x.name || "")}</span></span><span class="muted">${esc(x.type || "")} · ${esc(x.exchange || "")}</span></a></li>`).join("");
      list.hidden = !items.length;
    };
    input.addEventListener("input", () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (!q) { items = []; return render(); }
      timer = setTimeout(async () => { try { items = await api("/api/search?q=" + encodeURIComponent(q)); sel = -1; render(); } catch (e) { /* ignore */ } }, 250);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { sel = Math.min(items.length - 1, sel + 1); render(); e.preventDefault(); }
      if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); render(); e.preventDefault(); }
      if (e.key === "Escape") { items = []; render(); }
    });
    $("#search").addEventListener("submit", (e) => {
      e.preventDefault();
      const pick = items[sel] || items[0];
      const sym = pick ? pick.symbol : input.value.trim().toUpperCase();
      if (sym) location.hash = "#/stock/" + encodeURIComponent(sym);
      items = []; render(); input.value = ""; input.blur();
    });
    document.addEventListener("click", (e) => { if (!$("#search").contains(e.target)) { list.hidden = true; } });
    list.addEventListener("click", () => { items = []; render(); input.value = ""; });
  })();

  // ------------------------------------------------------------ tables
  function sortableTable(el, rows, cols, opts) {
    let key = opts.sort || cols[0].key, dir = opts.dir || -1;
    function paint() {
      const sorted = rows.slice().sort((a, b) => {
        const va = cols.find((c) => c.key === key).val(a), vb = cols.find((c) => c.key === key).val(b);
        if (va == null) return 1; if (vb == null) return -1;
        return (typeof va === "string" ? va.localeCompare(vb) : va - vb) * dir;
      });
      const sortable = cols.filter((c) => c.label);
      el.innerHTML = `<label class="sort-sm">Sort <select aria-label="Sort by">${sortable.map((c) => `<option value="${c.key}" ${c.key === key ? "selected" : ""}>${c.label}</option>`).join("")}</select>
          <button type="button" class="btn sm" aria-label="Reverse order">${dir > 0 ? "↑" : "↓"}</button></label>
        <div class="table-wrap"><table class="rt"><thead><tr>${cols.map((c) =>
        `<th class="${c.r ? "r" : ""} ${c.sm ? "hide-sm" : ""}" data-k="${c.key}" aria-sort="${c.key === key ? (dir > 0 ? "ascending" : "descending") : "none"}" scope="col">${c.label ? `<button type="button" class="th-btn">${c.label}</button>` : `<span class="sr-only">Watch</span>`}</th>`).join("")}</tr></thead>` +
        `<tbody>${sorted.map((r) => `<tr data-sym="${esc(r.symbol)}">${cols.map((c) => `<td class="${c.r ? "r num" : ""} ${c.sm ? "hide-sm" : ""} c-${c.key}">${c.html(r)}</td>`).join("")}</tr>`).join("") ||
        `<tr><td colspan="${cols.length}" class="empty">Nothing matches.</td></tr>`}</tbody></table></div>`;
      $$("th .th-btn", el).forEach((b) => b.addEventListener("click", () => { const k = b.parentElement.dataset.k; dir = k === key ? -dir : -1; key = k; paint(); }));
      $(".sort-sm select", el).addEventListener("change", (e) => { key = e.target.value; dir = -1; paint(); });
      $(".sort-sm button", el).addEventListener("click", () => { dir = -dir; paint(); });
      $$("tbody tr[data-sym]", el).forEach((tr) => tr.addEventListener("click", (e) => {
        if (e.target.closest("button,a")) return;
        location.hash = "#/stock/" + encodeURIComponent(tr.dataset.sym);
      }));
      $$(".star", el).forEach((b) => b.addEventListener("click", () => { b.classList.toggle("on", toggleWatch(b.dataset.sym)); }));
    }
    paint();
  }
  const symCell = (r) => `<span class="symwrap">${logo(r.symbol)}<span><a class="sym" href="#/stock/${encodeURIComponent(r.symbol)}">${esc(r.symbol)}</a><span class="nm">${esc(r.name || "")}</span></span></span>`;
  const star = (sym) => `<button class="star ${watchlist().includes(sym) ? "on" : ""}" data-sym="${esc(sym)}" aria-label="Toggle watchlist ${esc(sym)}" title="Watchlist">★</button>`;
  const ltOf = (r) => ("lt" in r ? r.lt || {} : r); // market rows carry .lt; long-term profiles are used directly
  const LTC = {
    score: { key: "lts", label: "Long-term score", val: (r) => ltOf(r).score, html: (r) => { const p = ltOf(r); return p.score == null ? `<span class="muted">…</span>` : `${meter(p.score)}<span class="nm">${esc(p.band || "")}</span>`; } },
    zone: { key: "zone", label: "Buy zone", val: (r) => ({ "Accumulate+": 4, Accumulate: 3, Stretched: 2, Speculative: 1 }[ltOf(r).zone] || 0), html: (r) => window.LT ? window.LT.zoneBadge(ltOf(r).zone) : "" },
    c5: { key: "c5", label: "5y a year", r: true, val: (r) => (ltOf(r).history || {}).cagr5, html: (r) => { const v = (ltOf(r).history || {}).cagr5; return `<span class="${cls(v)}">${pct(v, 1)}</span>`; } },
    ath: { key: "ath", label: "From high", r: true, sm: true, val: (r) => ltOf(r).fromATH, html: (r) => { const v = ltOf(r).fromATH; return `<span class="${cls(v)}">${pct(v, 0)}</span>`; } },
  };
  const COLS = {
    star: { key: "star", label: "", val: (r) => (watchlist().includes(r.symbol) ? 1 : 0), html: (r) => star(r.symbol) },
    sym: { key: "symbol", label: "Symbol", val: (r) => r.symbol, html: symCell },
    price: { key: "price", label: "Price", r: true, val: (r) => r.price, html: (r) => priceStr(r.price, r.currency) },
    chg: { key: "changePct", label: "Today", r: true, val: (r) => r.changePct, html: (r) => `<span class="${cls(r.changePct)}">${pct(r.changePct)}</span>` },
    m1: { key: "ret1m", label: "1M", r: true, sm: true, val: (r) => r.ret1m, html: (r) => `<span class="${cls(r.ret1m)}">${pct(r.ret1m, 1)}</span>` },
    m3: { key: "ret3m", label: "3M", r: true, sm: true, val: (r) => r.ret3m, html: (r) => `<span class="${cls(r.ret3m)}">${pct(r.ret3m, 1)}</span>` },
    y1: { key: "ret1y", label: "1Y", r: true, sm: true, val: (r) => r.ret1y, html: (r) => `<span class="${cls(r.ret1y)}">${pct(r.ret1y, 1)}</span>` },
    rsi: { key: "rsi", label: "RSI", r: true, sm: true, val: (r) => r.rsi, html: (r) => fmt(r.rsi, 0) },
    score: { key: "score", label: "Score", val: (r) => r.score, html: (r) => meter(r.score) },
    rating: { key: "rating", label: "Rating", val: (r) => r.score, html: (r) => ratingBadge(r.rating) },
    entry: { key: "entryStatus", label: "Entry", val: (r) => ({ "Buy now: breakout": 6, "Buy zone: pullback": 5, Watch: 4, "Watch: market weak": 3, "Wait: earnings": 3, "Wait: extended": 2, "No setup": 1, Avoid: 0 }[r.entryStatus] ?? 1), html: (r) => entryBadge(r.entryStatus) + (r.earnings && r.earnings.days <= 14 ? ` <span class="tag earn" title="Earnings ${esc(r.earnings.date)}">E ${r.earnings.days}d</span>` : "") },
    sector: { key: "sector", label: "Sector", sm: true, val: (r) => r.sector, html: (r) => `<span class="muted">${esc(r.sector || "")}</span>` },
  };

  function setMode(m) {
    store.set("settings", Object.assign(settings(), { mode: m }));
    toast(m === "lt" ? "Long-term investing mode" : "Swing trading mode");
    syncModeUI(); route();
  }
  function syncModeUI() {
    const lt = isLT();
    $$("#modeSeg button").forEach((b) => b.classList.toggle("on", b.dataset.m === (lt ? "lt" : "swing")));
    const sig = $('#tabs a[data-tab="signals"]');
    if (sig) sig.innerHTML = lt ? '<i data-lucide="gem"></i>Quality' : '<i data-lucide="flame"></i>Strong Buys';
  }
  document.addEventListener("click", (e) => { const b = e.target.closest("#modeSeg button"); if (b) setMode(b.dataset.m); });

  // ------------------------------------------------------------ live day-trend rows (quote board)
  const fmtChg = (x) => (x == null ? "–" : (x > 0 ? "+" : "") + fmt(x, Math.abs(x) < 0.1 ? 3 : 2));
  function liveRowsHtml(items, extra) {
    if (!items.length) return `<p class="empty">Nothing here yet.</p>`;
    return `<ul class="live-list">${items.map((q) => `<li><a href="#/stock/${encodeURIComponent(q.symbol)}" class="live-row">
      ${logo(q.symbol, 30)}
      <span class="lr-name"><b>${esc(q.symbol)}</b><span>${esc(q.name || "")}</span></span>
      <span class="lr-spark">${TChart.daySpark(q.spark, q.prev, 110, 34, q.change != null ? q.change >= 0 : null)}</span>
      <span class="lr-px">${q.price == null ? `<span class="muted">…</span>` : `<b class="num">${fmt(q.price, dp(q.price))}</b><span class="num ${cls(q.change)}">${fmtChg(q.change)} (${pct(q.changePct)})</span>`}</span>
      ${extra ? `<span class="lr-extra">${extra(q)}</span>` : ""}</a></li>`).join("")}</ul>`;
  }
  async function liveRows(el, symbols, extra) {
    if (!el) return;
    if (!symbols.length) { el.innerHTML = `<p class="empty">Nothing here yet.</p>`; return; }
    const rows = await api("/api/spark?symbols=" + encodeURIComponent(symbols.join(","))).catch(() => []);
    if (!el.isConnected) return;
    const by = Object.fromEntries(rows.map((r) => [r.symbol, r]));
    el.innerHTML = liveRowsHtml(symbols.map((s) => by[s]).filter(Boolean), extra);
    flash(el, rows);
  }
  // a short green/red pulse on rows whose price changed since the last refresh
  const lastPx = {};
  function flash(el, rows) {
    rows.forEach((r) => {
      const before = lastPx[r.symbol];
      lastPx[r.symbol] = r.price;
      if (before == null || r.price == null || before === r.price) return;
      const a = el.querySelector(`a[href="#/stock/${encodeURIComponent(r.symbol)}"] .lr-px`);
      if (a) { a.classList.remove("flash-up", "flash-down"); void a.offsetWidth; a.classList.add(r.price > before ? "flash-up" : "flash-down"); }
    });
  }

  // ------------------------------------------------------------ pages
  let current = null; // cleanup for the active page
  const stockMode = {}; // chart range picked per symbol
  let routeId = 0; // bumps on every page change, so late responses never draw over a newer page
  const pages = {};

  pages.home = async function () {
    const lt = isLT();
    view.innerHTML = `<h1>Market Dashboard</h1><p class="sub">${lt ? "Your long-term overview: quality businesses on sale, your watchlist, portfolio and the market mood." : "Live overview of the market, today's best setups, your watchlist and portfolio."}</p>
      <div id="moodBanner" style="margin-bottom:16px"></div>
      <div class="card brief-card" style="margin-bottom:16px"><div class="card-head" style="flex-wrap:wrap"><h2><i data-lucide="sunrise"></i>Your briefing</h2><span style="display:flex;gap:10px;align-items:center">${rf("brief")}<a href="#/news?tab=cal">Calendar →</a></span></div><div id="brief">${skeleton(4)}</div></div>
      <div class="grid g4" id="stats">${[1, 2, 3, 4].map(() => `<div class="card stat">${skeleton(2)}</div>`).join("")}</div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>${lt ? "Quality on sale" : "Top Strong Buys"}</h2><span style="display:flex;gap:10px;align-items:center">${rf("market")}<a href="#/signals">See all →</a></span></div><div id="top">${skeleton(8)}</div></div>
        <div class="card"><div class="card-head"><h2>${lt ? "Top quality (score 75+)" : "In the buy zone now"}</h2>${rf("market")}</div><div id="zone">${skeleton(6)}</div></div>
      </div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>Your watchlist</h2><span style="display:flex;gap:10px;align-items:center">${rf("wl")}<a href="#/markets">Add more →</a></span></div><div id="wl">${skeleton(5)}</div></div>
        <div class="card"><div class="card-head"><h2><i data-lucide="trending-up"></i>Trending tickers</h2>${rf("trend")}</div><div id="trend">${skeleton(5)}</div></div>
      </div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>Latest news</h2><span style="display:flex;gap:10px;align-items:center">${rf("hnews")}<a href="#/news">All news →</a></span></div><div id="hn" class="news-list news-compact">${skeleton(6)}</div></div>
      </div>`;

    RF.hnews = () => api("/api/news?symbols=" + encodeURIComponent(watchlist().slice(0, 8).join(","))).then((news) => {
      $("#hn") && ($("#hn").innerHTML = newsHtml(news.slice(0, 7), true));
    }).catch((e) => $("#hn") && ($("#hn").innerHTML = `<p class="error">${esc(e.message)}</p>`));
    RF.hnews().then(() => stamp("hnews"));
    RF.brief = async () => {
      await getT212().catch(() => null);
      const pos = brokerPositions().concat(manual().map((m) => Object.assign({ mv: m.qty * m.avgPrice }, m)));
      const w = {};
      pos.forEach((p) => { w[p.symbol] = (w[p.symbol] || 0) + (p.valueAcct || p.value || p.mv || 0); });
      const syms = Object.keys(w).sort((a, b) => w[b] - w[a]);
      if (window.Insights && $("#brief")) await window.Insights.briefing($("#brief"), syms.length ? syms : watchlist().slice(0, 15), w);
    };
    RF.brief().then(() => stamp("brief"));
    if (window.Trade) window.Trade.regime($("#moodBanner"));
    RF.market = async () => { await Promise.all([homeMarket(), loadStrip(), window.Trade ? window.Trade.regime($("#moodBanner")) : null]); };
    RF.wl = homeWatch;
    RF.trend = async () => { const t = await api("/api/trending").catch(() => []); const el = $("#trend"); if (el) { el.innerHTML = liveRowsHtml(t); flash(el, t); } };
    RF.trend().then(() => stamp("trend"));
    homeWatch().then(() => stamp("wl"));
    await homeMarket(); stamp("market");
    // live: prices and day charts refresh every minute while the dashboard is open
    const live = setInterval(() => { if (document.hidden) return; homeWatch(); RF.trend(); if (isLT()) homeSale(); }, 60000);
    const prev = current; current = () => { prev && prev(); clearInterval(live); };
  };
  async function homeMarket() {
    const [rows, t212] = await Promise.all([getScreener(), getT212().catch(() => null)]);
    if (!$("#stats")) return;
    const stocks = rows.filter((r) => r.group === "stocks");
    const strong = stocks.filter((r) => r.rating === "Strong Buy").sort((a, b) => b.score - a.score);
    const zone = rows.filter((r) => (r.entryStatus || "").startsWith("Buy")).sort((a, b) => b.score - a.score);
    const spy = rows.find((r) => r.symbol === "SPY") || {};
    const breadth = Math.round(100 * stocks.filter((r) => r.sma50 && r.price > r.sma50).length / (stocks.length || 1));
    const pf = portfolioSummary(t212, rows);
    $("#stats").innerHTML = `
      <div class="card stat"><div class="label"><i data-lucide="wallet"></i>My portfolio</div>${pf ? `<div class="value num" data-count="${pf.value}" data-fmt="money:${pf.ccy}">${money(pf.value, pf.ccy)}</div><div class="delta num ${cls(pf.ppl)}">${pf.ppl >= 0 ? "+" : ""}${money(pf.ppl, pf.ccy)} open P/L</div>` : `<div class="value" style="font-size:16px;margin-top:8px"><a href="#/portfolio">Link Trading 212 or Revolut →</a></div>`}</div>
      <div class="card stat"><div class="label"><i data-lucide="activity"></i>S&P 500 (SPY)</div><div class="value num" data-count="${spy.price}" data-fmt="num:2">${fmt(spy.price, 2)}</div><div class="delta">${(isLT() ? "" : ratingBadge(spy.rating))} <span class="${cls(spy.changePct)} num">${pct(spy.changePct)}</span></div></div>
      <div class="card stat"><div class="label"><i data-lucide="bar-chart-3"></i>Market breadth</div><div class="value num">${breadth}%</div><div class="delta sec">of tracked stocks above their 50-day average</div></div>
      <div class="card stat"><div class="label"><i data-lucide="flame"></i>Strong Buy signals</div><div class="value num" data-count="${strong.length}" data-fmt="int">${strong.length}</div><div class="delta sec">${zone.length} in a buy zone right now</div></div>`;
    if (isLT() && window.LT) {
      $("#stats").children[3].innerHTML = `<div class="label"><i data-lucide="gem"></i>Quality on sale</div><div class="value num" id="qCount">…</div><div class="delta sec">strong businesses below their usual price</div>`;
      $("#top").innerHTML = `<p class="muted" style="font-size:13px">Scoring stocks for quality and value (the first time takes about a minute)…</p>`;
      const u = await getUniverse();
      const prof = await window.LT.profiles([...new Set(Object.values(u.stocks).flat())]).catch(() => []);
      if (!$("#top")) return;
      const sale = prof.filter((p) => p.zone === "Accumulate+").sort((a, b) => b.score - a.score);
      const core = prof.filter((p) => p.score >= 75).sort((a, b) => b.score - a.score);
      $("#qCount").textContent = sale.length;
      saleSyms = sale.slice(0, 8).map((p) => p.symbol);
      if (sale.length) await homeSale();
      else $("#top").innerHTML = `<p class="empty">No quality names on sale right now: keep your monthly plan.</p>`;
      sortableTable($("#zone"), core.slice(0, 8), [COLS.sym, LTC.score, LTC.c5], { sort: "lts" });
      return;
    }
    sortableTable($("#top"), strong.slice(0, 8), [COLS.sym, COLS.price, COLS.chg, COLS.score, COLS.entry], { sort: "score" });
    sortableTable($("#zone"), zone.slice(0, 8), [COLS.sym, COLS.price, { key: "score", label: "Score", r: true, val: (r) => r.score, html: (r) => `<b class="num">${r.score}</b>` }], { sort: "score" });
  }
  async function homeWatch() {
    const wl = watchlist();
    if (!wl.length) { if ($("#wl")) $("#wl").innerHTML = `<p class="empty">Tap ★ on any stock to watch it here.</p>`; return; }
    await liveRows($("#wl"), wl, isLT() && window.LT ? (q) => { const p = window.LT.cache[q.symbol]; return p ? window.LT.zoneBadge(p.zone) : ""; } : null);
  }
  let saleSyms = [];
  async function homeSale() {
    if (!saleSyms.length) return;
    await liveRows($("#top"), saleSyms, (q) => { const p = window.LT.cache[q.symbol]; return p ? `<span class="lt-chip" title="Long-term score">${p.score}</span>` : ""; });
  }

  pages.markets = async function (arg, params) {
    const f = Object.assign({ group: "stocks", sector: "", rating: "", q: "", view: "rated" }, store.get("mfilter", {}));
    if (params && params.get("view")) f.view = params.get("view");
    if (f.view === "all") return marketsAll(f);
    view.innerHTML = `<h1>Markets</h1><p class="sub">The core list, fully rated and scored. Switch to <b>All stocks &amp; ETFs</b> to browse every listing.</p>
      ${marketsTabs("rated")}
      <div class="toolbar">
        <a class="btn sm" href="#/map"><i data-lucide="layout-grid"></i> Map view</a>
        <div class="seg" id="grp"><button data-g="stocks">Stocks</button><button data-g="etfs">ETFs</button><button data-g="all">All</button></div>
        <select id="sector" aria-label="Sector"></select>
        <select id="rating" aria-label="Rating" ${isLT() ? "hidden" : ""}><option value="">All ratings</option><option>Strong Buy</option><option>Buy</option><option>Hold</option><option>Sell</option><option>Strong Sell</option></select>
        <input type="text" id="filter" placeholder="Filter symbol or name" aria-label="Filter">
        ${rf("screener")}
      </div>
      <div class="card" id="tbl">${skeleton(14)}</div>`;
    let rows = await getScreener();
    if (!$("#tbl")) return;
    const u = await getUniverse();
    const paint = () => {
      store.set("mfilter", f);
      $$("#grp button").forEach((b) => b.classList.toggle("on", b.dataset.g === f.group));
      const sectors = f.group === "all" ? [...Object.keys(u.stocks), ...Object.keys(u.etfs)] : Object.keys(u[f.group]);
      if (!sectors.includes(f.sector)) f.sector = "";
      $("#sector").innerHTML = `<option value="">All sectors</option>` + sectors.map((s) => `<option ${s === f.sector ? "selected" : ""}>${esc(s)}</option>`).join("");
      $("#rating").value = f.rating; $("#filter").value = f.q;
      const q = f.q.toLowerCase();
      let data = rows.filter((r) => (f.group === "all" || r.group === f.group) && (!f.sector || r.sector === f.sector) && (!f.rating || r.rating === f.rating) &&
        (!q || r.symbol.toLowerCase().includes(q) || (r.name || "").toLowerCase().includes(q)));
      if (f.group === "all") { const s = new Set(); data = data.filter((r) => !s.has(r.symbol) && s.add(r.symbol)); }
      if (isLT() && window.LT) {
        data.forEach((r) => { r.lt = window.LT.cache[r.symbol]; });
        sortableTable($("#tbl"), data, [COLS.star, COLS.sym, COLS.price, COLS.chg, COLS.y1, LTC.c5, LTC.ath, LTC.score, LTC.zone, COLS.sector], { sort: "lts" });
        const missing = data.filter((r) => !r.lt).map((r) => r.symbol);
        if (missing.length && !paint._busy) {
          paint._busy = true;
          window.LT.profiles(missing).then(() => { paint._busy = false; if ($("#tbl")) paint(); }).catch(() => { paint._busy = false; });
        }
        return;
      }
      sortableTable($("#tbl"), data, [COLS.star, COLS.sym, COLS.price, COLS.chg, COLS.m1, COLS.m3, COLS.y1, COLS.rsi, COLS.score, COLS.rating, COLS.entry, COLS.sector], { sort: "score" });
    };
    $$("#grp button").forEach((b) => b.addEventListener("click", () => { f.group = b.dataset.g; paint(); }));
    $("#sector").addEventListener("change", (e) => { f.sector = e.target.value; paint(); });
    $("#rating").addEventListener("change", (e) => { f.rating = e.target.value; paint(); });
    $("#filter").addEventListener("input", (e) => { f.q = e.target.value; clearTimeout(paint._t); paint._t = setTimeout(paint, 150); });
    RF.screener = async () => { rows = await getScreener(true); paint(); };
    paint(); stamp("screener");
  };

  const marketsTabs = (on) => `<div class="seg big-seg" id="mTabs" style="margin-bottom:12px"><button data-v="rated" class="${on === "rated" ? "on" : ""}">Rated &amp; scored</button><button data-v="all" class="${on === "all" ? "on" : ""}">All stocks &amp; ETFs</button></div>`;
  document.addEventListener("click", (e) => {
    const b = e.target.closest("#mTabs button");
    if (!b) return;
    store.set("mfilter", Object.assign(store.get("mfilter", {}), { view: b.dataset.v }));
    pages.markets("", new URLSearchParams());
  });

  async function marketsAll(f) {
    const af = Object.assign({ q: "", type: "", region: "", page: 1 }, store.get("allf", {}));
    view.innerHTML = `<h1>Markets</h1><p class="sub" id="allSub">Every US-listed stock and ETF plus the main stocks and UCITS ETFs of Europe, the UK, Switzerland, the Nordics, Asia, Canada and Australia, with today's live trend. Anything else on any exchange: use the search box at the top.</p>
      ${marketsTabs("all")}
      <div class="toolbar">
        <input type="text" id="aq" placeholder="Symbol or company / fund name" aria-label="Search the list" value="${esc(af.q)}" style="min-width:240px">
        <select id="atype" aria-label="Type"><option value="">Stocks and ETFs</option><option value="Stock" ${af.type === "Stock" ? "selected" : ""}>Stocks</option><option value="ETF" ${af.type === "ETF" ? "selected" : ""}>ETFs</option></select>
        <select id="aregion" aria-label="Region"><option value="">All regions</option></select>
        ${rf("all")}
      </div>
      <div class="card" id="allBox">${skeleton(14)}</div>`;
    let seq = 0;
    const load = async () => {
      store.set("allf", af);
      const my = ++seq;
      const d = await api(`/api/directory?q=${encodeURIComponent(af.q)}&type=${encodeURIComponent(af.type)}&region=${encodeURIComponent(af.region)}&page=${af.page}`);
      if (my !== seq || !$("#allBox")) return;
      const reg = $("#aregion");
      if (reg.options.length <= 1) reg.innerHTML = `<option value="">All regions (${d.all.toLocaleString()})</option>` + d.regions.map(([r, n]) => `<option value="${esc(r)}" ${r === af.region ? "selected" : ""}>${esc(r)} (${n.toLocaleString()})</option>`).join("");
      const pages_ = Math.max(1, Math.ceil(d.total / d.size));
      const pager = `<div class="pager"><button class="btn sm" type="button" data-pg="${af.page - 1}" ${af.page <= 1 ? "disabled" : ""}>← Prev</button>
        <span class="muted">${d.total.toLocaleString()} found · page ${af.page} of ${pages_.toLocaleString()}</span>
        <button class="btn sm" type="button" data-pg="${af.page + 1}" ${af.page >= pages_ ? "disabled" : ""}>Next →</button></div>`;
      const meta = Object.fromEntries(d.rows.map((r) => [r.s, r]));
      $("#allBox").innerHTML = pager + `<div id="allRows">${liveRowsHtml(d.rows.map((r) => ({ symbol: r.s, name: r.n, spark: [], price: null })), (q) => `<span class="tag">${esc(meta[q.symbol].t)}</span><span class="nm">${esc(meta[q.symbol].x || meta[q.symbol].r)}</span>`)}</div>` + pager;
      $$("#allBox [data-pg]").forEach((b) => b.addEventListener("click", () => { af.page = +b.dataset.pg; load(); window.scrollTo(0, 0); }));
      const sp = await api("/api/spark?symbols=" + encodeURIComponent(d.rows.map((r) => r.s).join(","))).catch(() => []);
      if (my !== seq || !$("#allRows")) return;
      const by = Object.fromEntries(sp.map((x) => [x.symbol, x]));
      $("#allRows").innerHTML = liveRowsHtml(d.rows.map((r) => Object.assign({ symbol: r.s, name: r.n, spark: [], price: null }, by[r.s] || {}, { name: r.n })),
        (q) => `<span class="tag">${esc(meta[q.symbol].t)}</span><span class="nm">${esc(meta[q.symbol].x || meta[q.symbol].r)}</span>`);
    };
    $("#aq").addEventListener("input", (e) => { af.q = e.target.value; af.page = 1; clearTimeout(load._t); load._t = setTimeout(load, 250); });
    $("#atype").addEventListener("change", (e) => { af.type = e.target.value; af.page = 1; load(); });
    $("#aregion").addEventListener("change", (e) => { af.region = e.target.value; af.page = 1; load(); });
    RF.all = load;
    await load(); stamp("all");
  }

  pages.signals = async function () {
    if (isLT() && window.LT) return window.LT.qualityPage(view);
    view.innerHTML = `<h1>Strong Buys &amp; Best Entries</h1><p class="sub">Stocks and ETFs where trend, momentum, volume and relative strength line up, with the entry, stop and targets for each.</p>
      <div class="toolbar"><div class="seg" id="sg"><button data-g="now" class="on">Buy now</button><button data-g="strong">All Strong Buys</button><button data-g="watch">Watch list setups</button></div>${rf("signals")}</div>
      <div class="grid g3" id="cards">${[1, 2, 3].map(() => `<div class="card">${skeleton(6)}</div>`).join("")}</div>`;
    const rows = await getScreener();
    if (!$("#cards")) return;
    RF.signals = async () => { const rid = routeId; await getScreener(true); if (rid === routeId) await pages.signals(); };
    stamp("signals");
    const uniq = []; const s = new Set(); rows.forEach((r) => { if (!s.has(r.symbol)) { s.add(r.symbol); uniq.push(r); } });
    const sets = {
      now: uniq.filter((r) => (r.entryStatus || "").startsWith("Buy") && /Buy/.test(r.rating || "")),
      strong: uniq.filter((r) => r.rating === "Strong Buy"),
      watch: uniq.filter((r) => r.entryStatus === "Watch" || r.entryStatus === "Wait: extended"),
    };
    const paint = (g) => {
      $$("#sg button").forEach((b) => b.classList.toggle("on", b.dataset.g === g));
      const list = sets[g].sort((a, b) => b.score - a.score);
      $("#cards").innerHTML = list.map(signalCard).join("") || `<div class="card empty">No stocks match right now. Markets change daily: check back after the next session.</div>`;
    };
    $$("#sg button").forEach((b) => b.addEventListener("click", () => paint(b.dataset.g)));
    paint("now");
  };

  function signalCard(r) {
    const p = r.plan;
    return `<div class="card sigcard">
      <div class="card-head"><div class="symwrap">${logo(r.symbol, 32)}<div><a class="sym" style="font-size:18px" href="#/stock/${encodeURIComponent(r.symbol)}">${esc(r.symbol)}</a><span class="nm">${esc(r.name || "")}</span></div></div>
      <div style="text-align:right"><div class="num">${priceStr(r.price, r.currency)}</div><div class="num ${cls(r.changePct)}" style="font-size:13px">${pct(r.changePct)}</div></div></div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">${ratingBadge(r.rating)} ${entryBadge(r.entryStatus)} ${meter(r.score)}</div>
      <p class="sec" style="font-size:13px;margin:0 0 10px">${esc(r.entryWhy)}</p>
      ${p ? `<div class="plan"><div><div class="k">Entry</div><div class="v num">${fmt(p.entry, dp(p.entry))}</div></div><div><div class="k">Stop (−${p.riskPct}%)</div><div class="v num down">${fmt(p.stop, dp(p.stop))}</div></div>
      <div><div class="k">Target 1 (2R)</div><div class="v num up">${fmt(p.target1, dp(p.target1))}</div></div><div><div class="k">Target 2 (3R)</div><div class="v num up">${fmt(p.target2, dp(p.target2))}</div></div></div>` : ""}
      ${r.earnings && r.earnings.days <= 14 ? `<p class="earn-note"><i data-lucide="calendar-clock"></i> Earnings ${r.earnings.days === 0 ? "today" : "in " + r.earnings.days + " days"} (${esc(r.earnings.date)})</p>` : ""}
      <div class="sig-actions"><a class="btn sm" href="#/stock/${encodeURIComponent(r.symbol)}"><i data-lucide="line-chart"></i> Analysis</a>${p && (r.entryStatus || "").startsWith("Buy") ? `<a class="btn sm primary" href="#/stock/${encodeURIComponent(r.symbol)}?ticket=1"><i data-lucide="clipboard-list"></i> Order ticket</a>` : ""}</div>
    </div>`;
  }

  pages.stock = async function (sym, params) {
    if (current) { try { current(); } catch (e) { /* ignore */ } current = null; }
    sym = decodeURIComponent(sym || "SPY").toUpperCase();
    view.innerHTML = `<div class="card">${skeleton(3)}</div><div class="card" style="margin-top:16px;height:440px">${skeleton(10)}</div>`;
    let a;
    const rid = routeId;
    try { a = await api("/api/analysis?symbol=" + encodeURIComponent(sym)); if (rid !== routeId) return; }
    catch (e) { if (rid !== routeId) return; view.innerHTML = `<div class="card empty"><h2>Couldn't load ${esc(sym)}</h2><p class="error">${esc(e.message)}</p><p>Try the search box: some tickers need an exchange suffix (e.g. VUSA.L for London, SAP.DE for Xetra).</p></div>`; return; }
    const t212 = state.t212 && !state.t212.error ? state.t212 : null;
    const held = brokerPositions().concat(manual()).find((p) => p.symbol === a.symbol);
    const p = a.plan;
    view.innerHTML = `
      <div class="quote-head">
        <div><h1>${logo(a.symbol, 36)} ${esc(a.symbol)} <button class="star ${watchlist().includes(a.symbol) ? "on" : ""}" id="wstar" aria-label="Toggle watchlist">★</button></h1>
          <div class="sec">${esc(a.name)} · ${esc(a.exchange || "")} · ${esc(a.type || "")} · ${esc(a.currency || "")}</div></div>
        <div><div class="px num">${priceStr(a.price, a.currency)}</div><div class="num ${cls(a.change)}">${a.change >= 0 ? "+" : ""}${fmt(a.change, dp(a.price))} (${pct(a.changePct)}) today</div></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center" id="hdrBadges">${isLT() ? "" : ratingBadge(a.rating) + " " + entryBadge(a.entryStatus)}
          ${a.earnings ? `<span class="badge ${a.earnings.days <= 7 ? "e-wait" : "e-none"}" title="Next earnings report"><i data-lucide="calendar-clock" class="ico"></i> Earnings ${a.earnings.days === 0 ? "today" : "in " + a.earnings.days + "d"}</span>` : ""}
          <button class="btn sm" id="alertBtn" type="button"><i data-lucide="bell-plus"></i> Alert</button>
          <button class="btn sm" id="cmpBtn" type="button"><i data-lucide="git-compare-arrows"></i> Compare</button> ${rf("quote")}</div>
      </div>
      ${isLT() ? `<a class="entry-strip" id="entryStrip" href="#ltEntryCard" hidden></a>` : ""}
      <div class="grid ${isLT() ? "" : "g2"}">
        <div class="card chart-card">
          <div class="card-head" style="flex-wrap:wrap"><h2 id="chartTitle">Price chart (daily)</h2>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${rf("chart")}
              <label class="check" style="font-size:13px"><input type="checkbox" id="fcOn" ${isLT() ? "" : "checked"}> Forecast</label>
              ${isLT() ? `<label class="check" style="font-size:13px"><input type="checkbox" id="proOn" ${store.get("traderView", false) ? "checked" : ""}> Trader view</label>` : ""}
              <div class="seg" id="rng"><button data-b="1D">1D</button><button data-b="7D">7D</button><button data-b="63">3M</button><button data-b="126" class="on">6M</button><button data-b="252">1Y</button><button data-b="504">2Y</button></div></div></div>
          <div class="chart-box" id="chart"></div>
          <div class="legend" id="legend"></div>
          <div id="fcNote" class="muted" style="font-size:12px;margin-top:6px"></div>
        </div>
        <div class="grid ${isLT() ? "g2 lt-cols" : ""}" style="align-content:start">
          ${isLT() ? `<div class="card entry-card" id="ltEntryCard"><div class="card-head"><h2 style="margin:0"><i data-lucide="crosshair"></i>Right moment to buy?</h2>${rf("entry")}</div><div id="ltEntry"></div></div>
          <div class="card"><div class="card-head"><h2 style="margin:0">Long-term view</h2>${rf("ltv")}</div><div id="ltCard"></div><div id="ltBt" style="margin-top:14px"></div></div>
          <details class="card swing" id="swingBox"><summary><h2 style="margin:0;display:inline">Swing trading plan</h2> <span class="muted" style="font-size:13px">entry, stop, targets for short trades</span></summary>` : `<div class="card">`}
            <div class="card-head"><h2 style="margin:0">${isLT() ? "" : "Best moment to buy"}</h2>${isLT() ? "" : rf("quote")}</div>
            <div>${entryBadge(a.entryStatus)}</div>
            <div class="callout">${esc(a.entryWhy)}</div>
            ${p ? `<div class="plan"><div><div class="k">Entry</div><div class="v num">${fmt(p.entry, dp(p.entry))}</div></div><div><div class="k">Stop loss (−${p.riskPct}%)</div><div class="v num down">${fmt(p.stop, dp(p.stop))}</div></div>
              <div><div class="k">Target 1 · 2R</div><div class="v num up">${fmt(p.target1, dp(p.target1))}</div></div><div><div class="k">Target 2 · 3R</div><div class="v num up">${fmt(p.target2, dp(p.target2))}</div></div></div>
              ${p.resistance ? `<p class="muted" style="font-size:12.5px;margin:8px 0 0"><i data-lucide="triangle-alert" class="ico"></i> The 52-week high (${fmt(p.resistance, dp(p.resistance))}) sits before target 1: expect selling there.</p>` : ""}
              <h2 style="margin-top:16px">Position size</h2>
              <div class="sec" id="sizeOut">${skeleton(1)}</div>
              <div class="tk-actions" style="margin-top:12px"><button class="btn primary" id="ticketBtn" type="button"><i data-lucide="clipboard-list"></i> Prepare Trading 212 order</button></div>` : `<p class="muted">No entry plan: there is no buy setup today.</p>`}
            <div id="btBox" style="margin-top:14px"></div>
          ${isLT() ? "</details>" : "</div>"}
          <div class="card" ${isLT() ? "hidden" : ""}><div class="card-head"><h2>Signal rating</h2>${meter(a.score)}</div>
            <ul class="reasons">${a.reasons.map((x) => `<li class="${x.ok ? "" : "no"}">${esc(x.text)}</li>`).join("")}</ul></div>
        </div>
      </div>
      <div class="card" id="hourlyCard" style="margin-top:16px" hidden></div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>Performance overview</h2>${rf("perf")}</div><p class="muted" style="font-size:12px;margin:-6px 0 10px">Price return vs the S&amp;P 500</p><div id="perf">${skeleton(3)}</div></div>
        <div class="card"><div class="card-head"><h2>Forecast &amp; analysts</h2>${rf("fund")}</div><div id="fcCard">${skeleton(4)}</div></div>
      </div>
      <details class="card fold" style="margin-top:16px" ${isLT() ? "" : "open"}><summary class="card-head"><h2>Statistics</h2>${rf("fund")}</summary><p class="muted" id="statSrc" style="font-size:12px;margin:-6px 0 10px"></p><div id="stats">${skeleton(6)}</div></details>
      <details class="card fold" style="margin-top:16px" id="earnCard" ${isLT() ? "" : "open"}><summary class="card-head"><h2>Earnings trends</h2>${rf("fund")}</summary><p class="muted" id="nextEarn" style="font-size:13px;margin:-6px 0 10px"></p><div id="earn">${skeleton(6)}</div></details>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><h2>Key stats</h2><div class="kv">
          <div>52-week high<b class="num">${fmt(a.high52, dp(a.high52))}</b></div><div>52-week low<b class="num">${fmt(a.low52, dp(a.low52))}</b></div>
          <div>From 52w high<b class="num ${cls(a.price / a.high52 - 1)}">${pct(100 * (a.price / a.high52 - 1), 1)}</b></div>
          <div>1 month<b class="num ${cls(a.ret1m)}">${pct(a.ret1m, 1)}</b></div><div>3 months<b class="num ${cls(a.ret3m)}">${pct(a.ret3m, 1)}</b></div><div>1 year<b class="num ${cls(a.ret1y)}">${pct(a.ret1y, 1)}</b></div>
          <div>RSI (14)<b class="num">${fmt(a.rsi, 1)}</b></div><div>ATR (14)<b class="num">${fmt(a.atr, dp(a.atr))}</b></div><div>Volume<b class="num">${fmtVol(a.volume)}</b></div>
          <div>Avg volume (20d)<b class="num">${fmtVol(a.avgVolume || 0)}</b></div><div>SMA 50<b class="num">${fmt(a.sma50, dp(a.sma50))}</b></div><div>SMA 200<b class="num">${fmt(a.sma200, dp(a.sma200))}</b></div>
        </div>
        ${held ? `<div class="callout" style="margin-top:14px"><b>You hold ${shares(held.qty)} shares</b> at avg ${fmt(held.avgPrice, dp(held.avgPrice))}. Open P/L: <span class="${cls(a.price - held.avgPrice)}">${pct(100 * (a.price / held.avgPrice - 1))}</span>${p && a.price < p.stop ? " · <b class='down'>Price is below the suggested stop.</b>" : ""}</div>` : ""}
        <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap"><button class="btn" id="addPf">+ Add to manual portfolio</button></div></div>
        <div class="card"><div class="card-head"><h2>News: ${esc(a.symbol)}</h2>${rf("snews")}</div><div id="snews" class="news-list news-compact">${skeleton(5)}</div></div>
      </div>`;

    // ---- chart: daily ranges, 1D / 7D intraday, forecast cone
    const ui = { mode: stockMode[a.symbol] || (isLT() ? "504" : "126"), intra: null, fund: null, chart: null };
    $$("#rng button").forEach((x) => x.classList.toggle("on", x.dataset.b === ui.mode));
    const legendDaily = `<span><i style="background:var(--series-2)"></i>SMA 20</span><span><i style="background:var(--series-1)"></i>SMA 50</span><span><i style="background:var(--series-5)"></i>SMA 200</span><span><i style="background:var(--series-7)"></i>RSI 14</span>` +
      (p && !isLT() ? `<span style="color:var(--accent)"><i class="dash"></i>Entry</span><span style="color:var(--bad)"><i class="dash"></i>Stop</span><span style="color:var(--good)"><i class="dash"></i>Targets</span>` : "");
    const legendFc = `<span><i style="background:rgba(57,135,229,.45)"></i>Forecast range (68% / 95%)</span><span style="color:var(--accent)"><i class="dash"></i>Trend path</span><span><i style="background:var(--warning);width:9px;height:9px;transform:rotate(45deg)"></i>Analyst target</span>`;
    async function drawChart() {
      if (ui.chart) ui.chart.destroy();
      const m = ui.mode, fcOn = $("#fcOn").checked;
      $("#fcOn").parentElement.style.display = m === "1D" || m === "7D" ? "none" : "";
      if (m === "1D" || m === "7D") {
        $("#chartTitle").textContent = m === "1D" ? "Latest session (5-minute bars)" : "Last 7 days (hourly bars)";
        $("#legend").innerHTML = m === "1D" ? `<span><i class="dash" style="color:var(--text-muted)"></i>Previous close</span><span class="muted">Times in your local time zone</span>` : `<span class="muted">Times in your local time zone</span>`;
        $("#fcNote").textContent = "";
        $("#chart").innerHTML = skeleton(8);
        try { ui.intra = ui.intra || await api("/api/intraday?symbol=" + encodeURIComponent(a.symbol)); }
        catch (e) { $("#chart").innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
        const ser = m === "1D" ? ui.intra.day : ui.intra.week;
        if (!ser.t.length) { $("#chart").innerHTML = `<p class="empty">No intraday data yet for this session.</p>`; return; }
        ui.chart = Price($("#chart"), ser, { bars: ser.t.length, intraday: m === "1D" ? "day" : "week", prevClose: ui.intra.prevClose });
        renderHourly(ui.intra, m);
        return;
      }
      $("#hourlyCard").hidden = true;
      $("#chartTitle").textContent = "Price chart (daily)";
      const calmView = isLT() && !($("#proOn") && $("#proOn").checked);
      $("#legend").innerHTML = (calmView ? `<span><i style="background:var(--accent)"></i>Price</span><span><i style="background:var(--series-5)"></i>200-day average (the long-term trend)</span>` : legendDaily) + (fcOn && a.forecast ? legendFc : "");
      const tgt = ui.fund && ui.fund.analyst ? ui.fund.analyst.avg : null;
      $("#fcNote").textContent = fcOn && a.forecast ? "Forecast: the last 6 months' trend (halved, since trends fade) with ranges from recent volatility. A statistical range, not a prediction." : "";
      ui.chart = Price($("#chart"), a.series, { bars: +m, plan: isLT() ? null : p, forecast: fcOn ? a.forecast : null, target: fcOn ? tgt : null,
        calm: isLT() && !($("#proOn") && $("#proOn").checked) });
    }
    function renderHourly(d, m) {
      const card = $("#hourlyCard"); card.hidden = false;
      const t = (ts) => new Date(ts * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
      const dd = (ds) => new Date(ds + "T12:00:00Z").toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
      const f = (x) => fmt(x, dp(x));
      const hourly = d.hourly.length ? `<h2>Hourly levels · ${new Date(d.hourly[0].t * 1000).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short" })}</h2>
        <div class="table-wrap"><table><thead><tr><th scope="col">Hour</th><th class="r" scope="col">Open</th><th class="r" scope="col">High</th><th class="r" scope="col">Low</th><th class="r" scope="col">Close</th><th class="r" scope="col">Change</th><th class="r hide-sm" scope="col">Volume</th></tr></thead><tbody>
        ${d.hourly.map((h) => `<tr style="cursor:default"><td>${t(h.t)}</td><td class="r num">${f(h.o)}</td><td class="r num">${f(h.h)}</td><td class="r num">${f(h.l)}</td><td class="r num">${f(h.c)}</td><td class="r num ${cls(h.chgPct)}">${pct(h.chgPct)}</td><td class="r num hide-sm">${fmtVol(h.v)}</td></tr>`).join("")}
        </tbody></table></div><p class="muted" style="font-size:12px">Change is against the previous hour (first hour: against yesterday's close ${f(d.prevClose)}).</p>` : "";
      const days = `<h2 style="margin-top:14px">Last 7 days</h2><div class="table-wrap"><table><thead><tr><th scope="col">Day</th><th class="r" scope="col">Open</th><th class="r" scope="col">High</th><th class="r" scope="col">Low</th><th class="r" scope="col">Close</th><th class="r" scope="col">Change</th><th class="r hide-sm" scope="col">Volume</th></tr></thead><tbody>
        ${d.days.slice().reverse().map((x) => `<tr style="cursor:default"><td>${dd(x.date)}</td><td class="r num">${f(x.o)}</td><td class="r num">${f(x.h)}</td><td class="r num">${f(x.l)}</td><td class="r num">${f(x.c)}</td><td class="r num ${cls(x.chgPct)}">${pct(x.chgPct)}</td><td class="r num hide-sm">${fmtVol(x.v)}</td></tr>`).join("")}</tbody></table></div>`;
      card.innerHTML = m === "1D" ? hourly + days : days + hourly;
    }
    $$("#rng button").forEach((b) => b.addEventListener("click", () => {
      $$("#rng button").forEach((x) => x.classList.toggle("on", x === b));
      ui.mode = stockMode[a.symbol] = b.dataset.b; drawChart();
    }));
    $("#fcOn").addEventListener("change", drawChart);
    if ($("#proOn")) $("#proOn").addEventListener("change", (e) => { store.set("traderView", e.target.checked); drawChart(); });
    drawChart();
    RF.quote = () => pages.stock(a.symbol);
    RF.chart = async () => { if (/D$/.test(ui.mode)) { ui.intra = null; await drawChart(); } else await pages.stock(a.symbol); };
    ["quote", "chart"].forEach(stamp);
    current = () => ui.chart && ui.chart.destroy();
    if (isLT() && window.LT) {
      RF.ltv = async () => { delete window.LT.cache[a.symbol]; await window.LT.stockCard(a, $("#ltCard")); };
      window.LT.stockCard(a, $("#ltCard")).then((lp) => {
        stamp("ltv");
        if (lp && $("#hdrBadges")) $("#hdrBadges").insertAdjacentHTML("afterbegin", window.LT.bandBadge(lp.band) + " " + window.LT.zoneBadge(lp.zone) + " ");
      });
      window.LT.backtestCard(a.symbol, $("#ltBt"));
      const owned = brokerPositions().concat(manual()).find((p) => p.symbol === a.symbol);
      RF.entry = async () => { $("#ltEntry").dataset.fresh = "1"; await window.LT.entryCard(a, $("#ltEntry"), owned); };
      window.LT.entryCard(a, $("#ltEntry"), owned).then(async () => {
        stamp("entry");
        const e = await window.LT.entry(a.symbol).catch(() => null), s = $("#entryStrip");
        if (!e || !s) return;
        const lp = window.LT.cache[a.symbol];
        s.className = "entry-strip " + e.verdict.tone; s.hidden = false;
        s.innerHTML = `<i data-lucide="crosshair"></i><span>Right moment to buy? <b>${esc(e.verdict.title)}</b></span>` +
          (lp && lp.score != null ? `<span class="muted">Long-term score <b>${lp.score}</b>${lp.zone ? " · " + esc(window.LT.zoneLabel(lp.zone)) : ""}</span>` : "") + `<span class="go">Details ↓</span>`;
        if (window.lucide) window.lucide.createIcons();
      });
    }

    // ---- performance overview
    RF.perf = () => api("/api/performance?symbol=" + encodeURIComponent(a.symbol)).then((pf) => {
      if (!$("#perf")) return;
      const keys = ["1W", "1M", "3M", "6M", "YTD", "1Y", "2Y", "5Y", "Max"];
      $("#perf").innerHTML = `<div class="perf-grid">${keys.map((k) => {
        const v = pf.returns[k], b = pf.spy[k];
        return `<div class="perf-tile"><div class="k">${k === "Max" ? "Max" + (pf.since ? " (since " + new Date(pf.since * 1000).getFullYear() + ")" : "") : k}</div>
          <div class="v num ${cls(v)}" ${v != null && v < 1000 ? `data-count="${v}" data-fmt="pct:1"` : ""}>${pct(v, 1)}</div><div class="b num">S&amp;P ${pct(b, 1)}</div>
          ${v != null && b != null ? `<div class="vs ${v >= b ? "up" : "down"}">${v >= b ? "▲ beat" : "▼ lagged"} by ${Math.abs(v - b).toFixed(1)} pts</div>` : ""}</div>`;
      }).join("")}</div>`;
    }).catch((e) => { $("#perf") && ($("#perf").innerHTML = `<p class="muted">${esc(e.message)}</p>`); });
    RF.perf().then(() => stamp("perf"));

    // ---- forecast card, statistics, earnings
    const fcHtml = (fa) => {
      const f = a.forecast, an = fa && fa.analyst && fa.analyst.avg ? fa.analyst : null;
      const rows = [];
      if (f) rows.push(`<div class="plan"><div><div class="k">3-month trend path</div><div class="v num">${fmt(f.midEnd, dp(f.midEnd))}</div><div class="k ${cls(f.midEnd - a.price)}">${pct(100 * (f.midEnd / a.price - 1), 1)}</div></div>
        <div><div class="k">Likely range (68%)</div><div class="v num" style="font-size:16px">${fmt(f.lo1End, dp(f.lo1End))} – ${fmt(f.hi1End, dp(f.hi1End))}</div><div class="k">Wide (95%): ${fmt(f.lo2End, dp(f.lo2End))} – ${fmt(f.hi2End, dp(f.hi2End))}</div></div></div>
        <p class="muted" style="font-size:12px">From the last 6 months: trend ${pct(f.drift, 1)} a year (halved for the path), volatility ${f.vol}% a year.</p>`);
      if (an) {
        const lo = an.low, hi = an.high, span = hi - lo || 1, pos = (v) => Math.max(0, Math.min(100, 100 * (v - lo) / span));
        const tot = (an.buy || 0) + (an.hold || 0) + (an.sell || 0) || 1;
        rows.push(`<h2 style="margin-top:14px">Analyst 12-month price target</h2>
          <div class="target-bar"><i style="left:${pos(a.price)}%" class="now" title="Current ${fmt(a.price, 2)}"></i><i style="left:${pos(an.avg)}%" class="avg" title="Average target ${fmt(an.avg, 2)}"></i></div>
          <div style="display:flex;justify-content:space-between;font-size:12px" class="sec num"><span>Low ${fmt(lo, 2)}</span><span>Avg <b>${fmt(an.avg, 2)}</b> (${pct(an.upside, 1)})</span><span>High ${fmt(hi, 2)}</span></div>
          <div class="muted" style="font-size:12px;margin-top:2px">▲ white = current price ${fmt(a.price, 2)} · ◆ yellow = average target</div>
          <div class="reco"><span style="width:${100 * an.buy / tot}%" class="rb">Buy ${an.buy}</span><span style="width:${100 * an.hold / tot}%" class="rh">Hold ${an.hold}</span><span style="width:${100 * an.sell / tot}%" class="rs">Sell ${an.sell}</span></div>`);
      }
      return rows.join("") || `<p class="muted">Not enough history for a forecast.</p>`;
    };
    $("#fcCard").innerHTML = fcHtml(null);
    RF.fund = () => api("/api/fundamentals?symbol=" + encodeURIComponent(a.symbol)).then((fa) => {
      if (!$("#stats")) return;
      ui.fund = fa;
      $("#fcCard").innerHTML = fcHtml(fa);
      if (!/D$/.test(ui.mode)) drawChart();
      if (!fa.available) {
        $("#stats").innerHTML = `<p class="muted">${esc(fa.why)}</p>`;
        $("#earnCard").hidden = true;
        return;
      }
      $("#statSrc").textContent = "Source: " + fa.source + " · computed from the last 4 reported quarters";
      $("#stats").innerHTML = statsHtml(fa);
      renderEarnings(fa);
    }).catch((e) => { $("#stats") && ($("#stats").innerHTML = `<p class="muted">Fundamentals unavailable: ${esc(e.message)}</p>`); $("#earnCard") && ($("#earnCard").hidden = true); });
    RF.fund().then(() => stamp("fund"));
    $("#wstar").addEventListener("click", (e) => e.target.classList.toggle("on", toggleWatch(a.symbol)));
    $("#cmpBtn").addEventListener("click", () => {
      const list = store.get("compare", []).filter((x) => x !== a.symbol);
      list.unshift(a.symbol);
      store.set("compare", list.slice(0, 3));
      location.hash = "#/compare";
    });
    $("#addPf").addEventListener("click", () => { location.hash = "#/portfolio?add=" + encodeURIComponent(a.symbol) + "&price=" + a.price; });
    if (window.Trade) {
      if (p) {
        window.Trade.sizeLine(a, $("#sizeOut"));
        $("#ticketBtn").addEventListener("click", () => window.Trade.openTicket(a));
        if (params && params.get("ticket")) window.Trade.openTicket(a);
      }
      if (!isLT()) window.Trade.backtest(a.symbol, $("#btBox"));
      else $("#swingBox").addEventListener("toggle", function once() { window.Trade.backtest(a.symbol, $("#btBox")); $("#swingBox").removeEventListener("toggle", once); });
      $("#alertBtn").addEventListener("click", () => window.Trade.openAlerts({ symbol: a.symbol, price: p ? p.entry : a.price }));
    }
    RF.snews = () => api("/api/news?symbols=" + encodeURIComponent(a.symbol)).then((n) => { $("#snews") && ($("#snews").innerHTML = newsHtml(n.slice(0, 8), true)); })
      .catch(() => { $("#snews") && ($("#snews").innerHTML = `<p class="muted">No news available.</p>`); });
    RF.snews().then(() => stamp("snews"));
  };
  const big = (v) => (v == null ? "–" : Math.abs(v) >= 1e12 ? (v / 1e12).toFixed(2) + "T" : Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(2) + "B" : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + "M" : fmt(v, 0));
  const xr = (v) => (v == null ? "–" : Number(v).toFixed(2));
  const pc = (v) => (v == null ? "–" : Number(v).toFixed(2) + "%");
  function statsHtml(fa) {
    const v = fa.valuation, h = fa.highlights;
    const row = (k, val, tip) => `<tr style="cursor:default"><td>${k}${tip ? ` <span class="muted" title="${esc(tip)}">ⓘ</span>` : ""}</td><td class="r num"><b>${val}</b></td></tr>`;
    return `<div class="grid g11" style="gap:24px">
      <div><h3 class="h3">Valuation measures</h3><table class="kvt"><tbody>
        ${row("Market cap", big(v.marketCap))}${row("Enterprise value", big(v.enterpriseValue), "Market cap + debt - cash")}
        ${row("P/E ratio (TTM)", xr(v.peTTM), "Price / earnings per share of the last 4 quarters")}
        ${row("Forward P/E", xr(v.forwardPE), "Price / analysts' EPS forecast for the next 4 quarters")}
        ${row("PEG ratio (12m forward)", xr(v.peg), "P/E divided by expected growth. Around 1 is fair, lower is cheaper")}
        ${row("Price / sales (TTM)", xr(v.priceSales))}${row("Price / book", xr(v.priceBook))}
        ${row("EV / revenue", xr(v.evRevenue))}${row("EV / EBITDA", xr(v.evEbitda))}
      </tbody></table></div>
      <div><h3 class="h3">Financial highlights</h3><table class="kvt"><tbody>
        ${row("Profit margin", pc(h.profitMargin))}${row("Operating margin", pc(h.operatingMargin))}
        ${row("Return on assets (TTM)", pc(h.roa))}${row("Return on equity (TTM)", pc(h.roe))}
        ${row("Revenue (TTM)", big(h.revenueTTM))}${row("Net income (TTM)", big(h.netIncomeTTM))}${row("Diluted EPS (TTM)", xr(h.epsTTM))}
        ${row("Total cash", big(h.totalCash))}${row("Total debt / equity", pc(h.debtEquity))}
        ${row("Free cash flow", big(h.freeCashFlow) + (h.fcfPeriod ? ` <span class="muted" style="font-weight:400">(FY ${esc(h.fcfPeriod.slice(-4))})</span>` : ""))}
        ${h.dividendYield ? row("Dividend / yield", esc(h.dividend || "–") + " · " + esc(h.dividendYield)) : ""}
      </tbody></table></div></div>`;
  }
  function renderEarnings(fa) {
    $("#nextEarn").textContent = fa.nextEarnings ? "Next report: " + fa.nextEarnings : "";
    const qs = fa.earnings.slice(-5);
    const paint = (mode) => {
      $$("#rvSeg button").forEach((b) => b.classList.toggle("on", b.dataset.m === mode));
      $("#rvChart").innerHTML = TChart.revBars(fa.revVsEarnings[mode] || []);
    };
    $("#earn").innerHTML = `<div class="grid g11" style="gap:24px">
      <div><div class="card-head"><h3 class="h3" style="margin:0">Earnings per share</h3></div>
        ${qs.length ? TChart.epsChart(qs, fa.forecasts.slice(0, 2)) : `<p class="muted">No EPS history.</p>`}
        <div class="legend"><span><i style="background:var(--good);width:10px;height:10px;border-radius:50%"></i>Reported EPS</span><span><i style="border:2px solid var(--text-secondary);width:10px;height:10px;border-radius:50%;background:none"></i>Analyst forecast (line = high/low)</span></div>
        <p class="muted" style="font-size:12px">YoY = growth vs the same quarter a year earlier. Past consensus estimates (beat/miss) aren't in the free data.</p></div>
      <div><div class="card-head"><h3 class="h3" style="margin:0">Revenue vs. earnings</h3><div class="seg" id="rvSeg"><button data-m="quarterly">Quarterly</button><button data-m="annual">Annual</button></div></div>
        <div id="rvChart"></div>
        <div class="legend"><span><i style="background:var(--series-1);height:10px;width:10px"></i>Revenue</span><span><i style="background:var(--series-3);height:10px;width:10px"></i>Net income</span></div></div></div>`;
    $$("#rvSeg button").forEach((b) => b.addEventListener("click", () => paint(b.dataset.m)));
    paint("quarterly");
  }

  // ------------------------------------------------------------ portfolio
  function portfolioSummary(t212, rows) {
    const quotes = Object.fromEntries((rows || []).map((r) => [r.symbol, r]));
    const t = t212 && !t212.error ? t212 : null;
    const rv = state.revolut && state.revolut.linked ? state.revolut : null;
    const m = manual();
    if (!t && !rv && !m.length) return null;
    let value = 0, ppl = 0, ccy = t ? t.currency : rv ? rv.currency : settings().ccy || "USD";
    if (t) { value += t.cash.total || 0; ppl += t.cash.ppl || 0; }
    if (rv) { value += rv.totals.value || 0; ppl += rv.ppl || 0; }
    for (const p of m) {
      const q = quotes[p.symbol]; const px = q ? q.price : p.avgPrice;
      value += p.qty * px; ppl += p.qty * (px - p.avgPrice);
    }
    return { value, ppl, ccy };
  }

  pages.portfolio = async function (arg, params) {
    if (current) { try { current(); } catch (e) { /* ignore */ } current = null; }
    const lt = isLT();
    view.innerHTML = `<h1>My Portfolio</h1><p class="sub">${lt ? "Your Trading 212 account (read-only), Revolut statement and manual holdings: what to accumulate, hold or trim, your monthly plan, diversification and dividends." : "Your Trading 212 account (read-only), Revolut statement and any holdings you add by hand, with a live rating and exit check on every position."}</p>
      <div class="grid g4" id="pstats">${[1, 2, 3, 4].map(() => `<div class="card stat">${skeleton(2)}</div>`).join("")}</div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>Positions</h2>${rf("pos")}</div><div id="ptbl">${skeleton(8)}</div></div>
        <div class="grid" style="align-content:start">
          <div class="card" id="link">${skeleton(4)}</div>
          <div class="card" id="revBox">${skeleton(3)}</div>
          <div class="card"><div class="card-head"><h2>${lt ? "Diversification" : "Risk check"}</h2>${rf("pos")}</div><div id="riskBox">${skeleton(4)}</div></div>
          <div class="card"><div class="card-head"><h2>Allocation</h2>${rf("pos")}</div><div id="alloc">${skeleton(4)}</div></div>
        </div>
      </div>
      <div class="card" style="margin-top:16px"><div class="card-head" style="flex-wrap:wrap"><h2>Performance</h2>${rf("hist")}</div><p class="muted" id="phNote" style="font-size:12px;margin:-6px 0 10px"></p>
        <div id="pret" class="ret-grid ret7">${skeleton(2)}</div>
        <div class="card-head" style="margin-top:16px;flex-wrap:wrap"><h2 style="margin:0">Money invested vs value</h2>
          <div class="seg" id="vrng"><button data-r="1M">1M</button><button data-r="6M">6M</button><button data-r="1Y">1Y</button><button data-r="5Y">5Y</button><button data-r="Max" class="on">Max</button></div></div>
        <div class="chart-box" id="vchart" style="height:320px">${skeleton(8)}</div>
        <div class="legend"><span><i style="background:var(--series-1)"></i>Portfolio value</span><span style="color:var(--text-muted)"><i class="dash"></i>Money invested (cost of shares held)</span><span style="color:var(--series-2)"><i class="dash"></i>Same money in a world index fund (VWRL)</span><span><i style="background:rgba(12,163,12,.4);height:10px"></i>Gain</span><span><i style="background:rgba(208,59,59,.4);height:10px"></i>Loss</span></div>
        <div id="phWarn" class="muted" style="font-size:12px;margin-top:6px"></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="card-head" style="flex-wrap:wrap"><h2><i data-lucide="grid-3x3"></i>How your holdings move together</h2>${rf("corr")}</div><div id="corrBox">${skeleton(5)}</div></div>
      <div class="card" style="margin-top:16px"><div class="card-head" style="flex-wrap:wrap"><h2><i data-lucide="telescope"></i>10-year plan</h2><span class="muted" style="font-size:12.5px">what monthly investing could grow to</span></div><div id="projBox">${skeleton(5)}</div></div>
      ${lt ? `<div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2><i data-lucide="calendar-check"></i>Monthly plan</h2></div><div id="planBox">${skeleton(5)}</div></div>
        <div class="card"><div class="card-head"><h2><i data-lucide="coins"></i>Dividends</h2>${rf("divs")}</div><div id="divBox"><p class="muted">Link Trading 212 to see the dividends you receive.</p></div></div></div>` : ""}
      <div class="card" style="margin-top:16px${lt ? ";display:none" : ""}" id="journalCard"><div class="card-head"><h2>Trade journal</h2>${rf("journal")}</div><div id="journal"><p class="muted">Link Trading 212 to see your closed trades, win rate and average win and loss.</p></div></div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><h2>Add a holding manually</h2><p class="muted" style="margin-top:-6px">For shares held outside Trading 212, or to plan before you link. Stored only in this browser.</p>
          <form class="form" id="mform"><div class="form-row">
            <label class="field">Symbol<input name="symbol" required placeholder="AAPL" value="${esc(params.get("add") || "")}"></label>
            <label class="field">Shares<input name="qty" type="number" step="any" min="0" required></label>
            <label class="field">Avg price<input name="avgPrice" type="number" step="any" min="0" required value="${esc(params.get("price") || "")}"></label>
            <label class="field">Buy date<input name="date" type="date" required value="${new Date().toISOString().slice(0, 10)}"></label>
            <button class="btn primary" type="submit">Add</button></div></form></div>
        <div class="card"><div class="card-head"><h2><i data-lucide="plug"></i>Data connections</h2></div><div id="connBox">${skeleton(3)}</div></div>
        <details class="card fold" ${lt ? "" : "open"}><summary class="card-head"><h2>${lt ? "Settings (swing trading and account)" : "Risk settings"}</h2></summary><form class="form" id="sform"><div class="form-row">
          <label class="field">Risk per trade %<input name="riskPct" type="number" step="0.1" min="0.1" max="10" value="${settings().riskPct}"></label>
          <label class="field">Max position %<input name="maxPosPct" type="number" step="1" min="1" max="100" value="${settings().maxPosPct || 25}"></label>
          <label class="field">Max open risk %<input name="maxHeatPct" type="number" step="0.5" min="0.5" max="50" value="${settings().maxHeatPct || 6}"></label>
          <label class="field">Account size (if not linked)<input name="account" type="number" step="100" min="0" value="${settings().account}"></label>
          <label class="field">Account currency (if not linked)<select name="ccy">${["USD", "EUR", "GBP", "CHF"].map((c) => `<option ${c === (settings().ccy || "USD") ? "selected" : ""}>${c}</option>`).join("")}</select></label>
          <button class="btn" type="submit">Save</button></div>
          <p class="muted" style="margin:0;font-size:13px">Pros risk 0.5–2% of the account per trade and keep total open risk under about 6%. Every order ticket is sized from these numbers.</p></form>
          <div class="mode-row"><span>Style</span><div class="seg" id="modeSeg2"><button data-m="lt">Long-term investing</button><button data-m="swing">Swing trading</button></div></div></details>
      </div>`;

    $("#mform").addEventListener("submit", (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const m = manual();
      m.push({ symbol: fd.get("symbol").trim().toUpperCase(), qty: +fd.get("qty"), avgPrice: +fd.get("avgPrice"), date: fd.get("date"), source: "manual" });
      store.set("manual", m); toast("Added " + fd.get("symbol").toUpperCase()); history.replaceState(null, "", "#/portfolio"); pages.portfolio("", new URLSearchParams());
    });
    $$("#modeSeg2 button").forEach((b) => { b.classList.toggle("on", b.dataset.m === (lt ? "lt" : "swing")); b.addEventListener("click", () => setMode(b.dataset.m)); });
    $("#sform").addEventListener("submit", (e) => {
      e.preventDefault(); const fd = new FormData(e.target);
      store.set("settings", Object.assign(settings(), { riskPct: +fd.get("riskPct"), account: +fd.get("account"), maxPosPct: +fd.get("maxPosPct"), maxHeatPct: +fd.get("maxHeatPct"), ccy: fd.get("ccy") })); toast("Saved");
    });

    if (window.LT && $("#connBox")) window.LT.connectionsCard($("#connBox"));
    const t212 = await getT212(true).catch(() => null);
    if (!$("#link")) return;
    renderLink(t212);
    RF.pos = () => pages.portfolio("", new URLSearchParams());
    if (!$("#pstats")) return;
    RF.hist = () => loadHistory(state.t212);
    RF.journal = () => (window.Trade && state.t212 && !state.t212.error ? window.Trade.journal($("#journal")) : null);
    if (t212 && !t212.error && window.Trade) window.Trade.journal($("#journal")).then(() => stamp("journal"));
    loadHistory(t212).then(() => stamp("hist"));

    const t = t212 && !t212.error ? t212 : null;
    const rv = state.revolut && state.revolut.linked ? state.revolut : null;
    if ($("#revBox") && window.Insights) window.Insights.revolutCard($("#revBox"), () => pages.portfolio("", new URLSearchParams()));
    const positions = brokerPositions().concat(manual().map((p, i) => Object.assign({ source: "Manual", idx: i }, p)));
    const syms = [...new Set(positions.map((p) => p.symbol))];
    const quotes = syms.length ? await api("/api/quotes?symbols=" + encodeURIComponent(syms.join(","))).catch(() => []) : [];
    const Q = Object.fromEntries(quotes.filter((q) => !q.error).map((q) => [q.symbol, q]));
    for (const p of positions) {
      const q = Q[p.symbol] || {};
      p.q = q; p.name = p.name || q.name;
      p.price = p.source === "Manual" ? q.price : p.price != null ? p.price : q.price;
      p.mv = p.value != null ? p.value : (p.qty || 0) * (p.price || 0);
      p.plPct = p.avgPrice ? 100 * ((p.price || 0) / p.avgPrice - 1) : null;
      if (p.source === "Manual") p.ppl = (p.qty || 0) * ((p.price || 0) - p.avgPrice);
      const trail = q.chandelier; // highest close of the last 22 days minus 3 ATR
      const samePx = q.price && p.price && Math.abs(q.price / p.price - 1) < 0.2; // same units (pence vs pounds guard)
      p.alert = !q.price ? "" : trail && samePx && q.price < trail ? "Below trailing stop " + fmt(trail, dp(trail))
        : q.rating === "Strong Sell" || q.rating === "Sell" ? "Rating turned " + q.rating
        : q.entryStatus === "Avoid" ? "In a downtrend"
        : q.earnings && q.earnings.days <= 7 ? "Earnings in " + q.earnings.days + "d: gap risk"
        : q.rsi > 75 ? "Overbought: consider taking profit" : p.plPct > 20 && q.price < q.sma20 ? "Lost 20-day avg: protect gains" : "OK";
    }
    const acctR = window.Trade ? await window.Trade.account() : null;
    const uni = await getUniverse().catch(() => ({ stocks: {}, etfs: {} }));
    const secMap = {};
    for (const grp of ["stocks", "etfs"]) for (const [sec, list] of Object.entries(uni[grp] || {})) list.forEach((x) => (secMap[x] = secMap[x] || sec));
    const R = acctR && positions.length ? await window.Trade.risk(positions, acctR, (s) => secMap[s] || "Other") : null;
    for (const p of positions) if (p.unprotected && p.alert === "OK") p.alert = "No stop order";
    let ltMap = {};
    if (lt && window.LT && positions.length) {
      const prof = await window.LT.profiles(syms).catch(() => []);
      ltMap = Object.fromEntries(prof.map((x) => [x.symbol, x]));
      const L = await api("/api/lookthrough").catch(() => null);
      const isFund = (sym) => !!(L && Object.values(L.indexes).some((v) => v.funds.includes(sym))) || (Q[sym] && /ETF/i.test(Q[sym].type || ""));
      const targets = store.get("targets", {});
      const tsum = Object.values(targets).reduce((a, b) => a + (+b || 0), 0) || 100;
      const totAcct = positions.reduce((a, p) => a + (p.valueAcct || p.mv || 0), 0) + (t && t.cash.free > 0 ? t.cash.free : 0);
      const ts = await window.LT.themeShares(positions, totAcct);
      for (const p of positions) {
        p.weight = totAcct ? 100 * (p.valueAcct || p.mv || 0) / totAcct : 0;
        const tg = targets[p.symbol] != null ? 100 * targets[p.symbol] / tsum : null;
        const grp = ts.groupOf(p.symbol);
        const vd = window.LT.verdict(p, p.weight, tg, ltMap[p.symbol], isFund(p.symbol), grp ? { name: grp, pct: ts.byGroup[grp] } : null);
        p.verdict = vd.v; p.verdictWhy = vd.why;
        p.alert = vd.v === "Trim" || vd.v === "Review thesis" ? vd.v : "OK";
      }
      window.LT.plan($("#planBox"), positions, acctR, ltMap, () => pages.portfolio("", new URLSearchParams()));
      RF.divs = () => (t ? window.LT.dividends($("#divBox"), t.currency) : null);
      if (t) window.LT.dividends($("#divBox"), t.currency).then(() => stamp("divs"));
    }
    const ccy = t ? t.currency : rv ? rv.currency : settings().ccy || "USD";
    const invested = positions.reduce((a, p) => a + (p.avgPrice || 0) * (p.qty || 0), 0);
    const manualVal = manual().reduce((a, p) => a + p.qty * (Q[p.symbol] ? Q[p.symbol].price : p.avgPrice), 0);
    const total = t || rv ? (t ? t.cash.total || 0 : 0) + (rv ? rv.totals.value || 0 : 0) + manualVal : positions.reduce((a, p) => a + p.mv, 0);
    const ppl = (t && t.cash.ppl != null ? t.cash.ppl : positions.filter((p) => p.source === "Trading 212").reduce((a, p) => a + (p.ppl || 0), 0)) +
      (rv ? rv.ppl || 0 : 0) + positions.filter((p) => p.source === "Manual").reduce((a, p) => a + (p.ppl || 0), 0);
    const alerts = positions.filter((p) => p.alert && p.alert !== "OK").length;
    if (lt && window.LT && positions.length) window.LT.diversification($("#riskBox"), positions, acctR, ltMap);
    else if (R) window.Trade.riskPanel($("#riskBox"), R, acctR); else $("#riskBox").innerHTML = `<p class="muted">Add positions to see your risk.</p>`;
    $("#pstats").innerHTML = `
      <div class="card stat"><div class="label"><i data-lucide="wallet"></i>Total value</div><div class="value num" data-count="${total}" data-fmt="money:${ccy}">${money(total, ccy)}</div><div class="delta sec">${[t ? "Trading 212 " + esc(t.env) : "", rv ? rv.broker || "Revolut" : "", manual().length ? "manual" : ""].filter(Boolean).join(" + ") || "manual holdings"}</div></div>
      <div class="card stat"><div class="label"><i data-lucide="trending-up"></i>Gain so far (not sold)</div><div class="value num ${cls(ppl)}">${ppl >= 0 ? "+" : ""}${money(ppl, ccy)}</div><div class="delta num ${cls(ppl)}">${invested && !t && !rv ? pct(100 * ppl / invested) : ""}</div></div>
      <div class="card stat"><div class="label"><i data-lucide="banknote"></i>Free cash</div><div class="value num">${t ? money(t.cash.free, ccy) : "–"}</div><div class="delta sec">${t && t.cash.result != null ? "Realised P/L " + money(t.cash.result, ccy) : "link Trading 212 to see cash"}</div></div>
      <div class="card stat"><div class="label"><i data-lucide="bell-ring"></i>${lt ? "To trim or review" : "Positions needing attention"}</div><div class="value num ${alerts ? "warn" : ""}">${alerts}</div><div class="delta sec">of ${positions.length} positions</div></div>`;
    if (window.Insights && $("#corrBox")) {
      const bySym = {};
      positions.forEach((p) => { bySym[p.symbol] = (bySym[p.symbol] || 0) + (p.valueAcct || p.mv || 0); });
      const cs = Object.keys(bySym).sort((a, b) => bySym[b] - bySym[a]);
      RF.corr = () => window.Insights.correlation($("#corrBox"), cs);
      RF.corr().then(() => stamp("corr"));
    }
    if (window.Projection && $("#projBox")) {
      const etfVal = positions.filter((p) => /ETF|MUTUALFUND/i.test((p.q && p.q.type) || "")).reduce((a, p) => a + (p.valueAcct || p.mv || 0), 0);
      const posVal = positions.reduce((a, p) => a + (p.valueAcct || p.mv || 0), 0);
      window.Projection.render($("#projBox"), { value: total, ccy, etfPct: posVal ? 100 * etfVal / posVal : 0 });
    }
    stamp("pos");

    if (!positions.length) {
      $("#ptbl").innerHTML = `<p class="empty">No positions yet. Link Trading 212, import a Revolut statement or add a holding below.</p>`;
      if ($("#corrBox")) $("#corrBox").innerHTML = `<p class="muted">Add holdings to see how they move together.</p>`;
      $("#alloc").innerHTML = `<p class="empty">Nothing to chart yet.</p>`;
      return;
    }
    sortableTable($("#ptbl"), positions, [
      { key: "symbol", label: "Holding", val: (p) => p.symbol, html: (p) => symCell(p) + `<span class="nm">${esc(p.source)}</span>` },
      { key: "qty", label: "Shares", r: true, val: (p) => p.qty, html: (p) => shares(p.qty) },
      { key: "avg", label: "Avg", r: true, sm: true, val: (p) => p.avgPrice, html: (p) => fmt(p.avgPrice, dp(p.avgPrice)) },
      { key: "price", label: "Price", r: true, val: (p) => p.price, html: (p) => fmt(p.price, dp(p.price)) },
      { key: "pl", label: "P/L", r: true, val: (p) => p.plPct, html: (p) => `<span class="${cls(p.plPct)}">${pct(p.plPct)}</span><span class="nm ${cls(p.ppl)}">${p.ppl != null ? (p.ppl >= 0 ? "+" : "") + fmt(p.ppl, 2) : ""}</span>` },
      ...(lt ? [
        { key: "weight", label: "Weight", r: true, val: (p) => p.weight, html: (p) => p.weight != null ? p.weight.toFixed(1) + "%" : "–" },
        { key: "lts", label: "Long-term score", val: (p) => (ltMap[p.symbol] || {}).score, html: (p) => { const x = ltMap[p.symbol]; return x && x.score != null ? `${meter(x.score)}<span class="nm">${esc(x.band || "")}</span>` : "–"; } },
        { key: "verdict", label: "Action", val: (p) => ["Review thesis", "Trim", "Accumulate+", "Accumulate", "Hold"].indexOf(p.verdict), html: (p) => p.verdict ? `<span class="badge ${window.LT.verdictCls(p.verdict)}">${esc(window.LT.zoneLabel(p.verdict))}</span><span class="nm">${esc(p.verdictWhy || "")}</span>` : "" },
      ] : [
      { key: "stop", label: "Stop", r: true, sm: true, val: (p) => p.stopOrder || p.suggestedStop, html: (p) => p.stopOrder ? `<span class="num">${fmt(p.stopOrder, dp(p.stopOrder))}</span><span class="nm">T212 stop order</span>`
        : p.suggestedStop ? `<span class="num ${p.unprotected ? "down" : "muted"}">${fmt(p.suggestedStop, dp(p.suggestedStop))}</span><span class="nm">${p.unprotected ? "⚠ none set · suggested" : "suggested"}</span>` : "–" },
      { key: "rating", label: "Rating", val: (p) => p.q.score, html: (p) => ratingBadge(p.q.rating) },
      { key: "alert", label: "Check", val: (p) => (p.alert === "OK" ? 0 : 1), html: (p) => p.alert === "OK" ? `<span class="muted">✓ OK</span>` : p.alert ? `<span class="badge e-wait">${esc(p.alert)}</span>` : "" },
      ]),
      { key: "x", label: "", val: () => 0, html: (p) => p.source === "Manual" ? `<button class="btn sm danger" data-del="${p.idx}" aria-label="Remove">✕</button>` : "" },
    ], { sort: lt ? "weight" : "pl" });
    $$("[data-del]").forEach((b) => b.addEventListener("click", () => {
      const m = manual(); m.splice(+b.dataset.del, 1); store.set("manual", m); pages.portfolio("", new URLSearchParams());
    }));

    // allocation donut: top 7 + Other, fixed color order
    const colors = [1, 2, 3, 4, 5, 6, 7].map((i) => `var(--series-${i})`);
    positions.forEach((p) => { if (p.valueAcct) p.mv = p.valueAcct; }); // weights in the account currency
    const sorted = positions.filter((p) => p.mv > 0).sort((a, b) => b.mv - a.mv);
    let items = sorted.slice(0, 7).map((p, i) => ({ label: p.symbol, value: p.mv, color: colors[i] }));
    const rest = sorted.slice(7).reduce((a, p) => a + p.mv, 0);
    if (rest > 0) items.push({ label: "Other", value: rest, color: "#5a5955" });
    if (t && t.cash.free > 0) items.push({ label: "Cash", value: t.cash.free, color: "var(--text-muted)" });
    const tot = items.reduce((a, b) => a + b.value, 0);
    const mixed = new Set(positions.map((p) => p.currency || p.q.currency).filter(Boolean)).size > 1;
    $("#alloc").innerHTML = `<div class="donut-wrap"><div id="allocPie" style="width:200px;height:200px;flex:0 0 auto"></div>
      <ul class="donut-legend">${items.map((it) => `<li><span><i style="background:${it.color}"></i>${esc(it.label)}</span><span class="num">${(100 * it.value / tot).toFixed(1)}%</span></li>`).join("")}</ul></div>
      ${mixed && !R ? `<p class="muted" style="font-size:12px">Holdings trade in different currencies, so weights are approximate.</p>` : ""}`;
    const pie = PRO ? PRO.AllocPie($("#allocPie"), items, items.length + " slices", "by value") : (($("#allocPie").innerHTML = donut(items, 200, items.length + " slices", "by value")), null);
    if (pie) { const prev = current; current = () => { prev && prev(); pie.destroy(); }; }
  };

  async function loadHistory(t212) {
    const t = t212 && !t212.error ? t212 : null;
    if (!t && !(state.revolut && state.revolut.linked) && !manual().length) {
      $("#pret").innerHTML = `<p class="muted">Link Trading 212, import a Revolut statement or add holdings to see your returns.</p>`;
      $("#vchart").innerHTML = `<p class="empty">No history yet.</p>`; $("#vchart").style.height = "auto";
      return;
    }
    let h;
    try { h = await post("/api/portfolio/history", { manual: manual(), base: settings().ccy || "USD" }); }
    catch (e) { $("#pret").innerHTML = `<p class="error">${esc(e.message)}</p>`; $("#vchart").innerHTML = ""; return; }
    if (!$("#pret")) return;
    const ccy = h.base;
    const m = (v) => money(v, ccy);
    const label = { "1D": "Today", "1W": "1 week", "1M": "1 month", "3M": "3 months", YTD: "This year", "1Y": "1 year", "5Y": "5 years", Max: "All time" };
    const tw = h.twr || {};
    $("#pret").innerHTML = (isLT() && tw.years ? `<div class="perf-tile"><div class="k">Growth a year</div><div class="v num ${cls(tw.cagr)}">${tw.cagr != null ? pct(tw.cagr) : "–"}</div><div class="b">${tw.cagr != null ? "over " + tw.years + " years" : "after 1 year of history"}</div></div>
      <div class="perf-tile"><div class="k">Worst fall</div><div class="v num down">${pct(tw.maxdd)}</div><div class="b">peak to bottom</div></div>` : "") +
      (isLT() && h.bench && h.bench.length ? (() => { const bv = h.bench[h.bench.length - 1], v = h.value[h.value.length - 1]; return bv ? `<div class="perf-tile"><div class="k">vs world index fund</div><div class="v num ${cls(v - bv)}">${v - bv >= 0 ? "+" : ""}${m(v - bv)}</div><div class="b">same deposits in VWRL: ${m(bv)}</div></div>` : ""; })() : "") +
      ["1D", "1W", "1M", "YTD", "1Y", "5Y", "Max"].filter((k) => !(k === "Max" && h.returns.Max && h.returns["5Y"] && h.returns.Max.pct === h.returns["5Y"].pct && h.returns["5Y"].partial)).map((k) => {
      const r = h.returns[k];
      return `<div class="perf-tile"><div class="k">${label[k]}</div>${r ? `<div class="v num ${cls(r.gain)}" ${r.pct != null ? `data-count="${r.pct}" data-fmt="pct"` : ""}>${pct(r.pct)}</div><div class="b num ${cls(r.gain)}">${r.gain >= 0 ? "+" : ""}${m(r.gain)}</div>`
        : `<div class="v muted">–</div><div class="b">history too short</div>`}${r && r.partial ? `<div class="b">since your first buy</div>` : ""}</div>`;
    }).join("");
    $("#phNote").textContent = "Gains exclude money you added or withdrew. Values in " + ccy + ".";
    $("#phWarn").textContent = (h.warnings || []).join(" · ");
    if (!h.dates.length) { $("#vchart").innerHTML = `<p class="empty">No history yet.</p>`; return; }
    let vc;
    const draw = (rk) => {
      $$("#vrng button").forEach((b) => b.classList.toggle("on", b.dataset.r === rk));
      const days = { "1M": 31, "6M": 183, "1Y": 366, "5Y": 1827 }[rk];
      const cut = days ? new Date(Date.parse(h.dates[h.dates.length - 1]) - days * 86400000).toISOString().slice(0, 10) : "";
      let from = days ? h.dates.findIndex((d) => d >= cut) : 0;
      const firstHeld = h.value.findIndex((v) => v > 0);
      from = Math.max(from, firstHeld > 0 ? firstHeld : 0);
      if (vc) vc.destroy();
      vc = TChart.ValueChart($("#vchart"), h, { from, money: (v) => m(v).replace(/\.\d+$/, "") });
    };
    $$("#vrng button").forEach((b) => b.addEventListener("click", () => draw(b.dataset.r)));
    draw("Max");
    const prev = current; current = () => { prev && prev(); vc && vc.destroy(); };
  }

  function renderLink(t212) {
    const st = state.t212Status || {};
    const el = $("#link");
    if (st.linked) {
      el.innerHTML = `<div class="card-head"><h2>Trading 212</h2><span class="pill ${st.env === "demo" ? "demo" : "live"}">${st.env === "demo" ? "Practice" : "Live"} · linked</span></div>
        ${t212 && t212.error ? `<p class="error">${esc(t212.error)}</p>` : `<p class="sec" style="margin-top:0">Read-only connection. Positions and cash refresh every time you open this page.</p>`}
        <div style="display:flex;gap:8px"><button class="btn" id="t212r">↻ Refresh</button>${st.source === "env" ? `<span class="muted" style="font-size:12px">Key set by environment variable</span>` : `<button class="btn danger" id="t212d">Disconnect</button>`}</div>`;
      $("#t212r").addEventListener("click", (e) => runRefresh("pos", e.currentTarget));
      $("#t212d") && $("#t212d").addEventListener("click", async () => { await post("/api/t212/disconnect", {}); state.t212 = null; toast("Trading 212 disconnected"); pages.portfolio("", new URLSearchParams()); });
      return;
    }
    el.innerHTML = `<h2>Link Trading 212</h2>
      <ol class="steps"><li>Open the Trading 212 app → <b>Settings</b> → <b>API (Beta)</b>.</li>
        <li>Generate an API key. Tick only the <b>read</b> permissions (Account data, Portfolio). Leave <b>Orders: execute</b> off.</li>
        <li>Copy the key and the secret (the secret is shown once) and paste them here.</li></ol>
      <form class="form" id="t212f" style="margin-top:12px">
        <label class="field">API key<input name="key" required autocomplete="off" spellcheck="false"></label>
        <label class="field">API secret<input name="secret" type="password" autocomplete="off" spellcheck="false"></label>
        <div class="form-row"><label class="field">Account<select name="env"><option value="live">Live (real money)</option><option value="demo">Practice (demo)</option></select></label></div>
        <label class="check"><input type="checkbox" name="remember" checked> Remember on this computer</label>
        <button class="btn primary" type="submit">Connect</button>
        <p class="muted" style="font-size:12px;margin:0">Your key goes only to the dashboard server running on your own computer, which talks to Trading 212 directly. It is never stored in the browser or sent anywhere else. This site cannot place orders.</p>
        <p class="error" id="t212e" role="alert"></p>
      </form>`;
    $("#t212f").addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const btn = $("button[type=submit]", e.target); btn.disabled = true; btn.textContent = "Connecting…"; $("#t212e").textContent = "";
      try {
        await post("/api/t212/connect", { key: fd.get("key"), secret: fd.get("secret"), env: fd.get("env"), remember: !!fd.get("remember") });
        toast("Trading 212 linked"); state.t212Status = null; pages.portfolio("", new URLSearchParams());
      } catch (err) { $("#t212e").textContent = err.message; btn.disabled = false; btn.textContent = "Connect"; }
    });
  }



  // ------------------------------------------------------------ compare 2-3 stocks
  pages.compare = async function (arg, params) {
    if (!window.Compare) { view.innerHTML = `<p class="error">Compare module missing.</p>`; return; }
    const cleanup = await window.Compare.page(view, params);
    current = cleanup;
  };

  pages.runners = async function () {
    if (!window.Runners) { view.innerHTML = `<p class="error">Runners module missing.</p>`; return; }
    current = await window.Runners.page(view);
  };

  // ------------------------------------------------------------ market map (ECharts treemap)
  pages.map = async function () {
    const f = Object.assign({ group: "stocks", metric: "changePct", view: "map" }, store.get("mapf", {}));
    view.innerHTML = `<div class="card-head" style="margin-bottom:4px"><h1 style="margin:0"><i data-lucide="layout-grid" class="ico"></i> Market Map</h1>${rf("map")}</div>
      <p class="sub">Every tracked stock and ETF at a glance, grouped by sector. Bigger tiles trade more money each day; colour shows the move. Click a tile for the full analysis.</p>
      <div class="toolbar">
        <div class="seg" id="mGrp"><button data-g="stocks">Stocks</button><button data-g="etfs">ETFs</button><button data-g="all">All</button></div>
        <div class="seg" id="mView"><button data-v="map">Map</button><button data-v="list">List</button></div>
        <div class="seg" id="mMet"><button data-m="changePct">Today</button><button data-m="ret1m">1 month</button><button data-m="ret3m">3 months</button><button data-m="score">Signal score</button></div>
        <span class="scale-bar"><span id="scaleLo"></span><i></i><span id="scaleHi"></span></span>
      </div>
      <div class="card" style="padding:8px"><div class="map-box" id="mapBox">${skeleton(14)}</div></div>`;
    let rows = await getScreener();
    if (!$("#mapBox")) return;
    let mm = null;
    const spans = { changePct: ["−3%", "+3%"], ret1m: ["−15%", "+15%"], ret3m: ["−30%", "+30%"], score: ["0 weak", "100 strong"] };
    const paint = () => {
      store.set("mapf", f);
      $$("#mGrp button").forEach((b) => b.classList.toggle("on", b.dataset.g === f.group));
      $$("#mMet button").forEach((b) => b.classList.toggle("on", b.dataset.m === f.metric));
      $("#scaleLo").textContent = spans[f.metric][0]; $("#scaleHi").textContent = spans[f.metric][1];
      let data = rows.filter((r) => f.group === "all" || r.group === f.group);
      if (f.group === "all") { const seen = new Set(); data = data.filter((r) => !seen.has(r.symbol) && seen.add(r.symbol)); }
      if (mm) mm.destroy();
      mm = null;
      $$("#mView button").forEach((b) => b.classList.toggle("on", b.dataset.v === f.view));
      $("#mapBox").innerHTML = "";
      $("#mapBox").classList.toggle("as-list", f.view === "list");
      if (f.view === "list") {
        const m = { changePct: COLS.chg, ret1m: COLS.m1, ret3m: COLS.m3, score: COLS.score }[f.metric];
        sortableTable($("#mapBox"), data, [COLS.sym, COLS.price, m, COLS.rating, COLS.sector], { sort: m.key });
        return;
      }
      mm = PRO ? PRO.MarketMap($("#mapBox"), data, f.metric, (sym) => (location.hash = "#/stock/" + encodeURIComponent(sym)))
        : (($("#mapBox").innerHTML = `<p class="empty">Map needs the ECharts library (dashboard/static/vendor).</p>`), null);
    };
    $$("#mGrp button").forEach((b) => b.addEventListener("click", () => { f.group = b.dataset.g; paint(); }));
    $$("#mMet button").forEach((b) => b.addEventListener("click", () => { f.metric = b.dataset.m; paint(); }));
    $$("#mView button").forEach((b) => b.addEventListener("click", () => { f.view = b.dataset.v; paint(); }));
    RF.map = async () => { rows = await getScreener(true); paint(); };
    current = () => mm && mm.destroy();
    paint(); stamp("map");
  };
  // ------------------------------------------------------------ AI multibagger radar
  pages.radar = async function () {
    const f = Object.assign({ theme: "", stage: "", sort: "score" }, store.get("rfilter", {}));
    view.innerHTML = `
      <section class="ai-hero">
        <div class="ai-hero-text">
          <span class="ai-kicker">✦ Pattern scanner · every sector</span>
          <h1>Find the next big winner</h1>
          <p>The radar learned what <b>NVIDIA, Micron, ASML, Palantir, Broadcom, Eli Lilly, Vistra, Axon, Celsius, Robinhood</b> and others looked like on the day their 100% to 1,000% runs began. Every day it scans ${"<span id='nScan'>120</span>"} stocks in every sector (AI and tech, health, energy, defense, banks, consumer, industry, mining, software) for the same fingerprint, then checks the earnings growth behind them.</p>
          <div class="ai-stats" id="aiStats">${skeleton(2)}</div>
          <p class="ai-warn">⚠ Pattern matching, not a promise. Most stocks that look like past winners don't become one, and these stocks can fall 50% or more. Size positions small.</p>
        </div>
        <div class="ai-scope" id="scope"><div class="scope-loading"><div class="pulse"></div><p>Scanning every sector…<br><span class="muted">first scan of all sectors takes about 4 minutes, then it's quick</span></p></div></div>
      </section>
      <div class="card-head" style="margin:22px 0 10px"><h2 style="margin:0">The legends: what they did after the launch signal</h2>${rf("radar")}</div>
      <div class="legends" id="legends">${[1, 2, 3, 4].map(() => `<div class="card">${skeleton(4)}</div>`).join("")}</div>
      <h2 style="margin:22px 0 10px">Theme heat</h2>
      <div class="heat" id="heat">${skeleton(2)}</div>
      <div class="toolbar" style="margin-top:22px">
        <h2 style="margin:0 12px 0 0">Candidates</h2>
        <div class="seg" id="rGroup"><button data-g="">All sectors</button><button data-g="Other sectors">Not AI</button><button data-g="AI & tech">AI &amp; tech</button></div>
        <select id="rTheme" aria-label="Theme"><option value="">All themes</option></select>
        <select id="rStage" aria-label="Stage"><option value="">All stages</option><option>Launch pattern</option><option>Building</option><option>Not yet</option><option>Extended</option><option>Late: already ran</option></select>
        <label class="check"><input type="checkbox" id="rLeg"> Include the legends</label>
        <div class="seg" id="rSort"><button data-s="score">Radar score</button><button data-s="similarity">Pattern match</button><button data-s="growth">Growth</button><button data-s="upside">Analyst upside</button></div>
      </div>
      <div class="cand-grid" id="cands">${[1, 2, 3].map(() => `<div class="card">${skeleton(8)}</div>`).join("")}</div>
      <div class="card" style="margin-top:22px"><h2>How the radar works</h2>
        <ol class="steps" style="font-size:14px;gap:8px">
          <li><b>Learn the launch fingerprint.</b> For each legend it finds the first day of a confirmed uptrend (price above a rising 50-day average, which is above the 200-day) before its best 12 months, and measures 9 price-pattern traits that day: 3, 6 and 12-month returns, strength vs the S&amp;P 500, distance from the 52-week high and the 200-day average, the 50-day slope, volume trend and volatility. The fingerprint is the median of the legends.</li>
          <li><b>Pattern match (0 to 100).</b> How close each stock's traits are today, each trait scaled by how much it normally varies.</li>
          <li><b>Growth (0 to 100).</b> Revenue and EPS growth vs a year ago, whether growth is accelerating, analysts' EPS forecast for the next 4 quarters, operating margin and the analyst price target (Nasdaq.com data).</li>
          <li><b>Radar score</b> = 55% pattern match + 45% growth (a stock without enough earnings data counts as 35 for growth). Stages: <i>Launch pattern</i> = strong match and not already up 100%; <i>Late: already ran</i> = up more than 250% in a year.</li>
        </ol>
        <p class="muted" style="font-size:12px;margin:8px 0 0">The legends were picked because they won, so the fingerprint describes winners after the fact. It has not been tested on stocks that looked the same and failed. Treat it as a shortlist to research, not a buy list.</p></div>`;
    let data;
    const load = async () => {
      data = await api("/api/radar");
      if (!$("#cands")) return;
      paint();
    };
    RF.radar = load;
    const paint = () => {
      const W = data.winners, C = data.candidates.filter((x) => !x.isPastWinner); // the legends aren't "the next" one
      $("#nScan").textContent = C.length;
      const launch = C.filter((x) => x.stage === "Launch pattern");
      $("#aiStats").innerHTML = `<div><b data-count="${C.length}" data-fmt="int">${C.length}</b><span>stocks scanned</span></div><div><b>${W.length}</b><span>legends learned</span></div>
        <div><b data-count="${launch.length}" data-fmt="int">${launch.length}</b><span>show the launch pattern</span></div><div><b>${esc(C[0].symbol)}</b><span>top score (${C[0].score})</span></div>`;
      $("#scope").innerHTML = TChart.radarScope(C.slice(0, 24)) + `<p class="muted scope-cap">Closer to the centre = higher score · green = 75+</p>`;
      $("#legends").innerHTML = W.map((w) => `<a class="card legend-card" href="#/stock/${encodeURIComponent(w.symbol)}">
        <div class="card-head" style="margin-bottom:4px"><span class="symwrap">${logo(w.symbol, 26)}<span class="sym" style="font-size:17px">${esc(w.symbol)}</span></span><span class="badge b-strongbuy">+${w.peak12}% peak</span></div>
        <div class="muted" style="font-size:12px">Launch signal ${new Date(w.date + "T12:00:00Z").toLocaleDateString(undefined, { month: "short", year: "numeric" })} at ${fmt(w.price, 2)}</div>
        ${TChart.legendPath(w.path)}
        <div style="display:flex;justify-content:space-between;font-size:12px"><span class="sec">12 months later <b class="${cls(w.gain12)}">${w.gain12 >= 0 ? "+" : ""}${w.gain12}%</b></span><span class="sec">Today <b class="up">+${w.sinceLaunch}%</b></span></div></a>`).join("");
      const blue = (v) => `rgba(57,135,229,${(0.12 + 0.75 * Math.max(0, v - 20) / 70).toFixed(2)})`;
      $("#heat").innerHTML = data.themes.map((t) => `<button class="heat-tile" data-theme="${esc(t.theme)}" style="background:${blue(t.avg)}"><span>${esc(t.theme)}</span><b>${t.avg}</b><small>avg of ${t.n} · best ${t.top}</small></button>`).join("");
      $$("#heat .heat-tile").forEach((b) => b.addEventListener("click", () => { f.theme = f.theme === b.dataset.theme ? "" : b.dataset.theme; cards(); }));
      $("#rTheme").innerHTML = `<option value="">All themes</option>` + ["AI & tech", "Other sectors"].map((g) => `<optgroup label="${g === "AI & tech" ? "AI &amp; tech" : "Other sectors"}">` +
        data.themes.filter((t) => (t.group || "AI & tech") === g).map((t) => `<option ${t.theme === f.theme ? "selected" : ""}>${esc(t.theme)}</option>`).join("") + "</optgroup>").join("");
      cards();
    };
    const cards = () => {
      store.set("rfilter", f);
      $("#rTheme").value = f.theme; $("#rStage").value = f.stage;
      $$("#rSort button").forEach((b) => b.classList.toggle("on", b.dataset.s === f.sort));
      $$("#heat .heat-tile").forEach((b) => b.classList.toggle("on", b.dataset.theme === f.theme));
      $$("#rGroup button").forEach((b) => b.classList.toggle("on", b.dataset.g === (f.group || "")));
      const rows = data.candidates.filter((x) => (f.legends || !x.isPastWinner) && (!f.group || x.group === f.group) && (!f.theme || x.theme === f.theme) && (!f.stage || x.stage === f.stage))
        .sort((a, b) => (b[f.sort] ?? -999) - (a[f.sort] ?? -999));
      $("#cands").innerHTML = rows.map((x, i) => candCard(x, i + 1)).join("") || `<div class="card empty">No stocks match these filters.</div>`;
      $$("#cands [data-open]").forEach((b) => b.addEventListener("click", () => openDetail(b.dataset.open, b)));
    };
    const stageCls = (s) => s === "Launch pattern" ? "e-now" : s === "Building" ? "e-watch" : s.startsWith("Late") || s === "Extended" ? "e-wait" : "e-none";
    const bar = (label, v) => `<div class="mbar"><span>${label}</span><i><b style="width:${v ?? 0}%"></b></i><em class="num">${v ?? "–"}</em></div>`;
    const candCard = (x, rank) => `<div class="card cand" id="c-${esc(x.symbol)}">
      <div class="cand-top">
        <div class="rank">#${rank}</div>${logo(x.symbol, 34)}
        <div style="flex:1;min-width:0"><a href="#/stock/${encodeURIComponent(x.symbol)}" class="sym" style="font-size:18px">${esc(x.symbol)}</a>${x.isPastWinner ? ` <span class="pill" title="One of the legends the radar learned from">legend</span>` : ""}
          <span class="nm">${esc(x.name)}</span><span class="tag" style="margin-top:4px;display:inline-block">${esc(x.theme)}</span></div>
        ${TChart.ring(x.score, 66, "Radar score")}
      </div>
      <div style="display:flex;justify-content:space-between;align-items:end;gap:8px;margin:8px 0">
        <div><div class="num" style="font-size:18px;font-weight:600">${priceStr(x.price, x.currency)}</div><div class="num ${cls(x.changePct)}" style="font-size:12px">${pct(x.changePct)} today · ${pct(100 * x.features.r12, 0)} 1y</div></div>
        <div style="width:110px">${sparkline(x.spark, 110, 34)}</div>
      </div>
      ${bar("Pattern match", x.similarity)}${x.growth == null ? `<div class="mbar"><span>Growth</span><i></i><em class="muted" title="Not enough earnings data">n/a</em></div>` : bar("Growth", x.growth)}
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 6px"><span class="badge ${stageCls(x.stage)}">${esc(x.stage)}</span>${x.upside != null ? `<span class="badge ${x.upside >= 0 ? "b-buy" : "b-sell"}">Analysts ${pct(x.upside, 0)}</span>` : ""}</div>
      <p class="sec" style="font-size:12.5px;margin:4px 0">Matches the legends on: ${x.matches.map(esc).join(", ")}</p>
      <button class="btn sm" type="button" aria-expanded="false" data-open="${esc(x.symbol)}" style="width:100%;margin-top:6px">Compare with the legends ▾</button>
      <div class="cand-detail" hidden></div></div>`;
    const openDetail = (sym, btn) => {
      const x = data.candidates.find((c) => c.symbol === sym);
      const box = btn.nextElementSibling;
      const card = btn.closest(".cand");
      if (!box.hidden) { box.hidden = true; card.classList.remove("open"); btn.setAttribute("aria-expanded", "false"); btn.textContent = "Compare with the legends ▾"; return; }
      const ap = TChart.analogPaths(x.price, data.winners);
      box.innerHTML = `<div class="detail-grid"><div><h3 class="h3" style="margin-top:12px">Fingerprint vs the legends at launch</h3>${TChart.spider(data.features, x.features, data.profile, 300)}
        <div class="legend"><span><i style="background:var(--series-1)"></i>${esc(x.symbol)} today</span><span style="color:var(--series-2)"><i class="dash"></i>Legends at launch</span></div>
        <p class="muted" style="font-size:12px">Furthest from the legends: ${x.differs.map(esc).join(", ")}.</p>
        ${x.growthWhy.length ? `<h3 class="h3" style="margin-top:12px">Growth check</h3><ul class="reasons">${x.growthWhy.map((g) => `<li class="${g.ok ? "" : "no"}">${esc(g.text)}</li>`).join("")}</ul>` : ""}</div>
        <div><h3 class="h3" style="margin-top:12px">What if ${esc(x.symbol)} repeated a legend's next 12 months?</h3>${ap.svg}
        <div class="legend">${data.winners.map((w, j) => `<span><i style="background:var(--series-${(j % 8) + 1})"></i>${esc(w.symbol)} ${w.path[w.path.length - 1] >= 1 ? "+" : ""}${Math.round((w.path[w.path.length - 1] - 1) * 100)}%</span>`).join("")}<span><i class="dash" style="color:var(--text-primary)"></i>Median</span></div>
        <p class="muted" style="font-size:12px">Each line takes today's price along one legend's actual 12 months after its launch signal. The median legend path ends at ${pct(100 * (ap.median - 1), 0)}. Hypothetical: it shows what the legends did, not what ${esc(x.symbol)} will do.</p></div></div>`;
      box.hidden = false; card.classList.add("open"); card.scrollIntoView({ behavior: "smooth", block: "nearest" }); btn.textContent = "Hide comparison ▴"; btn.setAttribute("aria-expanded", "true");
    };
    $("#rTheme").addEventListener("change", (e) => { f.theme = e.target.value; cards(); });
    $$("#rGroup button").forEach((b) => b.addEventListener("click", () => { f.group = b.dataset.g; f.theme = ""; cards(); }));
    $("#rStage").addEventListener("change", (e) => { f.stage = e.target.value; cards(); });
    $("#rLeg").checked = !!f.legends;
    $("#rLeg").addEventListener("change", (e) => { f.legends = e.target.checked; cards(); });
    $$("#rSort button").forEach((b) => b.addEventListener("click", () => { f.sort = b.dataset.s; cards(); }));
    try { await load(); stamp("radar"); }
    catch (e) { $("#scope") && ($("#scope").innerHTML = `<p class="error">${esc(e.message)}</p>`); }
  };
  // ------------------------------------------------------------ news
  function newsHtml(items, compact) {
    if (!items.length) return `<p class="empty">No headlines right now.</p>`;
    return items.map((n) => `<a class="news-item" href="${safeUrl(n.link)}" target="_blank" rel="noopener noreferrer">
      ${!compact && n.thumb ? `<img src="${safeUrl(n.thumb)}" alt="" loading="lazy">` : ""}
      <div><div class="t">${esc(n.title)}</div>
      ${!compact && n.summary ? `<div class="d">${esc(n.summary)}</div>` : ""}
      <div class="m">${window.Insights ? window.Insights.newsBadges(n) : ""}${esc(n.publisher || "")} · ${ago(n.time)} ${(n.tickers || []).map((t) => `<span class="tag tag-go" role="link" data-go="${esc(t)}">${esc(t)}</span>`).join("")}${(n.tags || []).map((t) => `<span class="tag">#${esc(t)}</span>`).join("")}</div></div></a>`).join("");
  }

  pages.news = async function (arg, params) {
    if (state.revolut === undefined) await getT212().catch(() => null);
    const t = brokerPositions().map((p) => p.symbol);
    const mine = [...new Set([...t, ...manual().map((p) => p.symbol), ...watchlist()])];
    view.innerHTML = `<h1>Trading News</h1><p class="sub">Headlines for your holdings and watchlist, or the whole market, tagged bullish or bearish and by impact. Calendar shows earnings dates and the economic events that move markets.</p>
      <div class="toolbar"><div class="seg" id="ns"><button data-s="mine" class="on">My stocks</button><button data-s="market">Market</button><button data-s="cal">Calendar</button></div>
        <input type="text" id="nsym" placeholder="Ticker, e.g. AMD" aria-label="News for ticker" style="width:150px"><button class="btn" id="ngo" type="button">Show</button>
        <select id="ntag" aria-label="Filter by type"><option value="">All types</option><option value="!important">Important only</option><option value="!bull">Bullish</option><option value="!bear">Bearish</option><option value="earnings">Earnings</option><option value="analyst">Analyst</option><option value="deal">Deals</option><option value="legal">Legal</option><option value="macro">Macro</option></select>${rf("news")}</div>
      <div id="nl" class="news-list">${skeleton(10)}</div>`;
    let items = [];
    let shown = 20;
    const paint = () => {
      const tag = $("#ntag").value;
      const keep = { "!important": (n) => n.impact !== "low", "!bull": (n) => n.mood === "bullish", "!bear": (n) => n.mood === "bearish" }[tag] || ((n) => n.tags.includes(tag));
      const list = tag ? items.filter(keep) : items;
      $("#nl").innerHTML = newsHtml(list.slice(0, shown)) + (list.length > shown ? `<button class="btn" id="nMore" type="button">Load more (${list.length - shown})</button>` : "");
      const more = $("#nMore"); if (more) more.addEventListener("click", () => { shown += 20; paint(); });
    };
    let last = [];
    const load = async (syms) => {
      if (!syms) return;
      last = syms;
      $("#nl").innerHTML = skeleton(10);
      try { items = await api("/api/news?symbols=" + encodeURIComponent(syms.join(","))); paint(); stamp("news"); }
      catch (e) { $("#nl").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
    };
    $$("#ns button").forEach((b) => b.addEventListener("click", () => {
      $$("#ns button").forEach((x) => x.classList.toggle("on", x === b));
      if (b.dataset.s === "cal") { last = null; RF.news = () => window.Insights.calendar($("#nl"), mine); return RF.news().then(() => stamp("news")); }
      RF.news = () => load(last);
      load(b.dataset.s === "mine" ? mine.slice(0, 25) : ["stock market news", "SPY", "QQQ", "^VIX", "DIA"]);
    }));
    $("#ngo").addEventListener("click", () => { const s = $("#nsym").value.trim().toUpperCase(); if (s) load([s]); });
    $("#nsym").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#ngo").click(); });
    $("#ntag").addEventListener("change", paint);
    RF.news = () => load(last);
    if (params && params.get("tab") === "cal") $('#ns button[data-s="cal"]').click();
    else load(mine.length ? mine.slice(0, 25) : ["stock market news"]);
  };

  // ------------------------------------------------------------ router
  // phone: "More" in the bottom bar opens Compare, News and Market Map
  document.addEventListener("click", (e) => {
    const nav = $("#tabs"), btn = $("#tabMore");
    if (!nav || !btn) return;
    if (e.target.closest("#tabMore")) { const open = nav.classList.toggle("more-open"); btn.setAttribute("aria-expanded", String(open)); return; }
    if (nav.classList.contains("more-open") && !e.target.closest("#tabs a")) { nav.classList.remove("more-open"); btn.setAttribute("aria-expanded", "false"); }
  });
  async function route() {
    if (current) { try { current(); } catch (e) { /* ignore */ } current = null; }
    RF = {};
    routeId++;
    const [path, qs] = (location.hash.replace(/^#\/?/, "") || "").split("?");
    const [name, arg] = path.split("/");
    const page = pages[name || "home"] ? name || "home" : "home";
    const tab = { stock: "markets" }[page] || page;
    const nav = $("#tabs");
    nav.classList.remove("more-open"); $("#tabMore") && $("#tabMore").setAttribute("aria-expanded", "false");
    nav.classList.toggle("more-active", ["compare", "news", "map"].includes(tab));
    $$("#tabs a").forEach((a) => { const on = a.dataset.tab === tab; a.classList.toggle("active", on); on ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"); });
    window.scrollTo(0, 0);
    const first = routeId === 1;
    try { await pages[page](arg, new URLSearchParams(qs || "")); }
    catch (e) { view.innerHTML = `<div class="card empty"><h2>Something went wrong</h2><p class="error">${esc(e.message)}</p><p>Is the dashboard server still running?</p></div>`; }
    finally {
      const h = $("h1", view);
      document.title = (h ? h.textContent.replace(/[★]/g, "").trim() + " · " : "") + "TraderDash";
      if (window.Trade) window.Trade.badge();
      if (!first) view.focus({ preventScroll: true });
    }
  }
  new MutationObserver(() => {
    $$(".seg button, .heat-tile").forEach((b) => { const v = b.classList.contains("on") ? "true" : "false"; if (b.getAttribute("aria-pressed") !== v) b.setAttribute("aria-pressed", v); });
    $$("button:not([type])").forEach((b) => { if (!b.closest("form")) b.setAttribute("type", "button"); });
  }).observe(view, { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
  // shared with trade.js (order ticket, alerts, risk, journal, backtest)
  async function copyText(text) {
    try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; } } catch (e) { /* fall back */ }
    const ta = Object.assign(document.createElement("textarea"), { value: text });
    ta.setAttribute("readonly", ""); ta.style.cssText = "position:fixed;top:0;left:0;opacity:0;font-size:16px";
    document.body.appendChild(ta); ta.select(); ta.setSelectionRange(0, text.length);
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  }
  window.TD = { copyText, logo, isLT, api, post, esc, fmt, money, pct, cls, dp, toast, store, settings, state, getT212, getRevolut, brokerPositions, priceStr, entryBadge, ratingBadge, shares, sparkline, skeleton, rf, stamp, RF: () => RF, watchlist };
  window.addEventListener("hashchange", route);
  syncModeUI();
  route();
  loadStrip().catch(() => {});
  setInterval(() => { if (!document.hidden) loadStrip().catch(() => {}); }, 60000);
  getT212().catch(() => {});
})();
