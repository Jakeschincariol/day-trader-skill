/* Trader Dashboard - single page app. No dependencies. */
(function () {
  "use strict";
  const $ = (sel, el) => (el || document).querySelector(sel);
  const $$ = (sel, el) => Array.from((el || document).querySelectorAll(sel));
  const view = $("#view");
  const { fmt, fmtVol, sparkline, donut, PriceChart } = window.TChart;

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
  const pct = (x, d) => (x == null ? "–" : (x > 0 ? "+" : "") + Number(x).toFixed(d == null ? 2 : d) + "%");
  const cls = (x) => (x == null ? "" : x >= 0 ? "up" : "down");
  const ago = (t) => {
    if (!t) return "";
    const s = Date.now() / 1000 - t;
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + "m ago";
    if (s < 86400) return Math.round(s / 3600) + "h ago";
    return Math.round(s / 86400) + "d ago";
  };
  const ratingBadge = (r) => r ? `<span class="badge b-${r.toLowerCase().replace(/\s/g, "")}">${esc(r)}</span>` : "";
  const entryClass = (st) => !st ? "e-none" : st.startsWith("Buy") ? "e-now" : st.startsWith("Wait") ? "e-wait" : st === "Watch" ? "e-watch" : st === "Avoid" ? "e-avoid" : "e-none";
  const entryBadge = (st) => st ? `<span class="badge ${entryClass(st)}">${esc(st)}</span>` : "";
  const meter = (score) => `<span class="meter" title="Signal score ${score}/100"><i><b style="width:${score}%"></b></i><span class="num">${score}</span></span>`;
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
  const rf = (key) => `<span class="rf-wrap"><span class="upd" data-upd="${key}"></span><button type="button" class="rf" data-rf="${key}" title="Refresh with the latest data" aria-label="Refresh this section">↻</button></span>`;
  const stamp = (key) => $$(`[data-upd="${key}"]`).forEach((el) => (el.textContent = "Updated " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })));
  async function runRefresh(key, btn) {
    if (!RF[key]) return;
    btn && (btn.disabled = true, btn.classList.add("spin"));
    freshOn = true;
    try { await RF[key](); stamp(key); }
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
  async function getT212(force) {
    if (!state.t212Status || force) state.t212Status = await api("/api/t212/status").catch(() => ({ linked: false }));
    if (!state.t212Status.linked) return null;
    try { state.t212 = await api("/api/t212/portfolio"); } catch (e) { state.t212 = { error: e.message }; }
    return state.t212;
  }

  // ------------------------------------------------------------ index strip
  async function loadStrip() {
    const u = await getUniverse();
    const rows = await api("/api/quotes?symbols=" + encodeURIComponent(u.indices.join(",")));
    const names = { "^VIX": "VIX", "BTC-USD": "Bitcoin", "EURUSD=X": "EUR/USD", SPY: "S&P 500", QQQ: "Nasdaq 100", DIA: "Dow", IWM: "Russell 2000", GLD: "Gold" };
    $("#strip").innerHTML = rows.filter((r) => !r.error).map((r) =>
      `<a class="chip" href="#/stock/${encodeURIComponent(r.symbol)}"><span class="s">${esc(names[r.symbol] || r.symbol)}</span>` +
      `<span class="num">${fmt(r.price, dp(r.price))}</span><span class="num ${cls(r.changePct)}">${pct(r.changePct)}</span></a>`).join("");
  }

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
      el.innerHTML = `<div class="table-wrap"><table><thead><tr>${cols.map((c) =>
        `<th class="${c.r ? "r" : ""} ${c.sm ? "hide-sm" : ""}" data-k="${c.key}" ${c.key === key ? `aria-sort="${dir > 0 ? "ascending" : "descending"}"` : ""} scope="col">${c.label}</th>`).join("")}</tr></thead>` +
        `<tbody>${sorted.map((r) => `<tr data-sym="${esc(r.symbol)}">${cols.map((c) => `<td class="${c.r ? "r num" : ""} ${c.sm ? "hide-sm" : ""}">${c.html(r)}</td>`).join("")}</tr>`).join("") ||
        `<tr><td colspan="${cols.length}" class="empty">Nothing matches.</td></tr>`}</tbody></table></div>`;
      $$("th", el).forEach((th) => th.addEventListener("click", () => { const k = th.dataset.k; dir = k === key ? -dir : -1; key = k; paint(); }));
      $$("tbody tr[data-sym]", el).forEach((tr) => tr.addEventListener("click", (e) => {
        if (e.target.closest("button,a")) return;
        location.hash = "#/stock/" + encodeURIComponent(tr.dataset.sym);
      }));
      $$(".star", el).forEach((b) => b.addEventListener("click", () => { b.classList.toggle("on", toggleWatch(b.dataset.sym)); }));
    }
    paint();
  }
  const symCell = (r) => `<span class="sym">${esc(r.symbol)}</span><span class="nm">${esc(r.name || "")}</span>`;
  const star = (sym) => `<button class="star ${watchlist().includes(sym) ? "on" : ""}" data-sym="${esc(sym)}" aria-label="Toggle watchlist ${esc(sym)}" title="Watchlist">★</button>`;
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
    entry: { key: "entryStatus", label: "Entry", val: (r) => ({ "Buy now: breakout": 5, "Buy zone: pullback": 4, Watch: 3, "Wait: extended": 2, "No setup": 1, Avoid: 0 }[r.entryStatus]), html: (r) => entryBadge(r.entryStatus) },
    sector: { key: "sector", label: "Sector", sm: true, val: (r) => r.sector, html: (r) => `<span class="muted">${esc(r.sector || "")}</span>` },
  };

  // ------------------------------------------------------------ pages
  let current = null; // cleanup for the active page
  const stockMode = {}; // chart range picked per symbol
  let routeId = 0; // bumps on every page change, so late responses never draw over a newer page
  const pages = {};

  pages.home = async function () {
    view.innerHTML = `<h1>Market Dashboard</h1><p class="sub">Live overview of the market, today's best setups, your watchlist and portfolio.</p>
      <div class="grid g4" id="stats">${[1, 2, 3, 4].map(() => `<div class="card stat">${skeleton(2)}</div>`).join("")}</div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>Top Strong Buys</h2><span style="display:flex;gap:10px;align-items:center">${rf("market")}<a href="#/signals">See all →</a></span></div><div id="top">${skeleton(8)}</div></div>
        <div class="card"><div class="card-head"><h2>In the buy zone now</h2>${rf("market")}</div><div id="zone">${skeleton(6)}</div></div>
      </div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>Your watchlist</h2><span style="display:flex;gap:10px;align-items:center">${rf("wl")}<a href="#/markets">Add more →</a></span></div><div id="wl">${skeleton(5)}</div></div>
        <div class="card"><div class="card-head"><h2>Latest news</h2><span style="display:flex;gap:10px;align-items:center">${rf("hnews")}<a href="#/news">All news →</a></span></div><div id="hn" class="news-list news-compact">${skeleton(6)}</div></div>
      </div>`;

    RF.hnews = () => api("/api/news?symbols=" + encodeURIComponent(watchlist().slice(0, 8).join(","))).then((news) => {
      $("#hn") && ($("#hn").innerHTML = newsHtml(news.slice(0, 7), true));
    }).catch((e) => $("#hn") && ($("#hn").innerHTML = `<p class="error">${esc(e.message)}</p>`));
    RF.hnews().then(() => stamp("hnews"));
    RF.market = async () => { await Promise.all([homeMarket(), loadStrip()]); };
    RF.wl = homeWatch;
    await homeMarket(); stamp("market");
    await homeWatch(); stamp("wl");
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
      <div class="card stat"><div class="label">S&P 500 (SPY)</div><div class="value num">${fmt(spy.price, 2)}</div><div class="delta">${ratingBadge(spy.rating)} <span class="${cls(spy.changePct)} num">${pct(spy.changePct)}</span></div></div>
      <div class="card stat"><div class="label">Market breadth</div><div class="value num">${breadth}%</div><div class="delta sec">of tracked stocks above their 50-day average</div></div>
      <div class="card stat"><div class="label">Strong Buy signals</div><div class="value num">${strong.length}</div><div class="delta sec">${zone.length} in a buy zone right now</div></div>
      <div class="card stat"><div class="label">My portfolio</div>${pf ? `<div class="value num">${money(pf.value, pf.ccy)}</div><div class="delta num ${cls(pf.ppl)}">${pf.ppl >= 0 ? "+" : ""}${money(pf.ppl, pf.ccy)} open P/L</div>` : `<div class="value" style="font-size:16px;margin-top:8px"><a href="#/portfolio">Link Trading 212 →</a></div>`}</div>`;
    sortableTable($("#top"), strong.slice(0, 8), [COLS.sym, COLS.price, COLS.chg, COLS.score, COLS.entry], { sort: "score" });
    sortableTable($("#zone"), zone.slice(0, 8), [COLS.sym, COLS.price, COLS.score], { sort: "score" });
  }
  async function homeWatch() {
    const wl = watchlist();
    const wrows = await api("/api/quotes?symbols=" + encodeURIComponent(wl.join(","))).catch(() => []);
    if ($("#wl")) wrows.filter((r) => !r.error).length
      ? sortableTable($("#wl"), wrows.filter((r) => !r.error), [COLS.star, COLS.sym, COLS.price, COLS.chg, COLS.rating, COLS.entry], { sort: "changePct" })
      : ($("#wl").innerHTML = `<p class="empty">Tap ★ on any stock to watch it here.</p>`);
  };

  pages.markets = async function () {
    const f = Object.assign({ group: "stocks", sector: "", rating: "", q: "" }, store.get("mfilter", {}));
    view.innerHTML = `<h1>Markets</h1><p class="sub">Every tracked stock and ETF, rated and timed. Click a row for the full analysis. Use search (top) to open any other ticker.</p>
      <div class="toolbar">
        <div class="seg" id="grp"><button data-g="stocks">Stocks</button><button data-g="etfs">ETFs</button><button data-g="all">All</button></div>
        <select id="sector" aria-label="Sector"></select>
        <select id="rating" aria-label="Rating"><option value="">All ratings</option><option>Strong Buy</option><option>Buy</option><option>Hold</option><option>Sell</option><option>Strong Sell</option></select>
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
      sortableTable($("#tbl"), data, [COLS.star, COLS.sym, COLS.price, COLS.chg, COLS.m1, COLS.m3, COLS.y1, COLS.rsi, COLS.score, COLS.rating, COLS.entry, COLS.sector], { sort: "score" });
    };
    $$("#grp button").forEach((b) => b.addEventListener("click", () => { f.group = b.dataset.g; paint(); }));
    $("#sector").addEventListener("change", (e) => { f.sector = e.target.value; paint(); });
    $("#rating").addEventListener("change", (e) => { f.rating = e.target.value; paint(); });
    $("#filter").addEventListener("input", (e) => { f.q = e.target.value; clearTimeout(paint._t); paint._t = setTimeout(paint, 150); });
    RF.screener = async () => { rows = await getScreener(true); paint(); };
    paint(); stamp("screener");
  };

  pages.signals = async function () {
    view.innerHTML = `<h1>Strong Buys &amp; Best Entries</h1><p class="sub">Stocks and ETFs where trend, momentum, volume and relative strength line up, with the entry, stop and targets for each.</p>
      <div class="toolbar"><div class="seg" id="sg"><button data-g="now" class="on">Buy now</button><button data-g="strong">All Strong Buys</button><button data-g="watch">Watch list setups</button></div>${rf("signals")}</div>
      <div class="grid g3" id="cards">${[1, 2, 3].map(() => `<div class="card">${skeleton(6)}</div>`).join("")}</div>`;
    const rows = await getScreener();
    if (!$("#cards")) return;
    RF.signals = async () => { const rid = routeId; await getScreener(true); if (rid === routeId) await pages.signals(); };
    stamp("signals");
    const uniq = []; const s = new Set(); rows.forEach((r) => { if (!s.has(r.symbol)) { s.add(r.symbol); uniq.push(r); } });
    const sets = {
      now: uniq.filter((r) => (r.entryStatus || "").startsWith("Buy") && r.score >= 55),
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
    return `<a class="card" href="#/stock/${encodeURIComponent(r.symbol)}" style="color:inherit;text-decoration:none;display:block">
      <div class="card-head"><div><span class="sym" style="font-size:18px">${esc(r.symbol)}</span><span class="nm">${esc(r.name || "")}</span></div>
      <div style="text-align:right"><div class="num">${priceStr(r.price, r.currency)}</div><div class="num ${cls(r.changePct)}" style="font-size:13px">${pct(r.changePct)}</div></div></div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px">${ratingBadge(r.rating)} ${entryBadge(r.entryStatus)} ${meter(r.score)}</div>
      <p class="sec" style="font-size:13px;margin:0 0 10px">${esc(r.entryWhy)}</p>
      ${p ? `<div class="plan"><div><div class="k">Entry</div><div class="v num">${fmt(p.entry, dp(p.entry))}</div></div><div><div class="k">Stop (−${p.riskPct}%)</div><div class="v num down">${fmt(p.stop, dp(p.stop))}</div></div>
      <div><div class="k">Target 1 (2R)</div><div class="v num up">${fmt(p.target1, dp(p.target1))}</div></div><div><div class="k">Target 2 (3R)</div><div class="v num up">${fmt(p.target2, dp(p.target2))}</div></div></div>` : ""}
    </a>`;
  }

  pages.stock = async function (sym) {
    if (current) { try { current(); } catch (e) { /* ignore */ } current = null; }
    sym = decodeURIComponent(sym || "SPY").toUpperCase();
    view.innerHTML = `<div class="card">${skeleton(3)}</div><div class="card" style="margin-top:16px;height:440px">${skeleton(10)}</div>`;
    let a;
    const rid = routeId;
    try { a = await api("/api/analysis?symbol=" + encodeURIComponent(sym)); if (rid !== routeId) return; }
    catch (e) { if (rid !== routeId) return; view.innerHTML = `<div class="card empty"><h2>Couldn't load ${esc(sym)}</h2><p class="error">${esc(e.message)}</p><p>Try the search box: some tickers need an exchange suffix (e.g. VUSA.L for London, SAP.DE for Xetra).</p></div>`; return; }
    const st = settings();
    const t212 = state.t212 && !state.t212.error ? state.t212 : null;
    const acct = t212 && t212.cash && t212.cash.total ? t212.cash.total : st.account;
    const held = (t212 ? t212.positions : []).concat(manual()).find((p) => p.symbol === a.symbol);
    const p = a.plan;
    const sizing = (riskPct) => {
      if (!p) return null;
      const riskAmt = acct * riskPct / 100, perShare = p.entry - p.stop;
      const shares = perShare > 0 ? riskAmt / perShare : 0;
      const capped = Math.min(shares, acct / p.entry);
      return { riskAmt, shares: capped, cost: capped * p.entry };
    };
    const sz = sizing(st.riskPct);
    view.innerHTML = `
      <div class="quote-head">
        <div><h1>${esc(a.symbol)} <button class="star ${watchlist().includes(a.symbol) ? "on" : ""}" id="wstar" aria-label="Toggle watchlist">★</button></h1>
          <div class="sec">${esc(a.name)} · ${esc(a.exchange || "")} · ${esc(a.type || "")} · ${esc(a.currency || "")}</div></div>
        <div><div class="px num">${priceStr(a.price, a.currency)}</div><div class="num ${cls(a.change)}">${a.change >= 0 ? "+" : ""}${fmt(a.change, dp(a.price))} (${pct(a.changePct)}) today</div></div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">${ratingBadge(a.rating)} ${entryBadge(a.entryStatus)} ${rf("quote")}</div>
      </div>
      <div class="grid g2">
        <div class="card chart-card">
          <div class="card-head" style="flex-wrap:wrap"><h2 id="chartTitle">Price chart (daily)</h2>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${rf("chart")}
              <label class="check" style="font-size:13px"><input type="checkbox" id="fcOn" checked> Forecast</label>
              <div class="seg" id="rng"><button data-b="1D">1D</button><button data-b="7D">7D</button><button data-b="63">3M</button><button data-b="126" class="on">6M</button><button data-b="252">1Y</button><button data-b="504">2Y</button></div></div></div>
          <div class="chart-box" id="chart"></div>
          <div class="legend" id="legend"></div>
          <div id="fcNote" class="muted" style="font-size:12px;margin-top:6px"></div>
        </div>
        <div class="grid" style="align-content:start">
          <div class="card">
            <div class="card-head"><h2 style="margin:0">Best moment to buy</h2>${rf("quote")}</div>
            <div>${entryBadge(a.entryStatus)}</div>
            <div class="callout">${esc(a.entryWhy)}</div>
            ${p ? `<div class="plan"><div><div class="k">Entry</div><div class="v num">${fmt(p.entry, dp(p.entry))}</div></div><div><div class="k">Stop loss (−${p.riskPct}%)</div><div class="v num down">${fmt(p.stop, dp(p.stop))}</div></div>
              <div><div class="k">Target 1 · 2R</div><div class="v num up">${fmt(p.target1, dp(p.target1))}</div></div><div><div class="k">Target 2 · 3R</div><div class="v num up">${fmt(p.target2, dp(p.target2))}</div></div></div>
              <h2 style="margin-top:16px">Position size</h2>
              <div class="form-row"><label class="field">Account size<input id="acct" type="number" min="0" step="100" value="${Math.round(acct)}"></label>
                <label class="field">Risk per trade %<input id="riskp" type="number" min="0.1" max="10" step="0.1" value="${st.riskPct}"></label></div>
              <p class="sec" id="sizeOut" style="margin:10px 0 0">${sizeText(sz, a)}</p>
              <p class="muted" style="font-size:12px;margin:6px 0 0">Trading 212 supports fractional shares. Place the stop as a Stop order right after you buy.</p>` : `<p class="muted">No entry plan: there is no buy setup today.</p>`}
          </div>
          <div class="card"><div class="card-head"><h2>Signal rating</h2>${meter(a.score)}</div>
            <ul class="reasons">${a.reasons.map((x) => `<li class="${x.ok ? "" : "no"}">${esc(x.text)}</li>`).join("")}</ul></div>
        </div>
      </div>
      <div class="card" id="hourlyCard" style="margin-top:16px" hidden></div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>Performance overview</h2>${rf("perf")}</div><p class="muted" style="font-size:12px;margin:-6px 0 10px">Price return vs the S&amp;P 500</p><div id="perf">${skeleton(3)}</div></div>
        <div class="card"><div class="card-head"><h2>Forecast &amp; analysts</h2>${rf("fund")}</div><div id="fcCard">${skeleton(4)}</div></div>
      </div>
      <div class="card" style="margin-top:16px"><div class="card-head"><h2>Statistics</h2>${rf("fund")}</div><p class="muted" id="statSrc" style="font-size:12px;margin:-6px 0 10px"></p><div id="stats">${skeleton(6)}</div></div>
      <div class="card" style="margin-top:16px" id="earnCard"><div class="card-head"><h2>Earnings trends</h2>${rf("fund")}</div><p class="muted" id="nextEarn" style="font-size:13px;margin:-6px 0 10px"></p><div id="earn">${skeleton(6)}</div></div>
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
    const ui = { mode: stockMode[a.symbol] || "126", intra: null, fund: null, chart: null };
    $$("#rng button").forEach((x) => x.classList.toggle("on", x.dataset.b === ui.mode));
    const legendDaily = `<span><i style="background:var(--series-2)"></i>SMA 20</span><span><i style="background:var(--series-1)"></i>SMA 50</span><span><i style="background:var(--series-5)"></i>SMA 200</span><span><i style="background:var(--series-7)"></i>RSI 14</span>` +
      (p ? `<span style="color:var(--accent)"><i class="dash"></i>Entry</span><span style="color:var(--bad)"><i class="dash"></i>Stop</span><span style="color:var(--good)"><i class="dash"></i>Targets</span>` : "");
    const legendFc = `<span><i style="background:rgba(57,135,229,.45)"></i>Forecast range (68% / 95%)</span><span style="color:var(--accent)"><i class="dash"></i>Trend path</span><span><i style="background:var(--warning);width:9px;height:9px;transform:rotate(45deg)"></i>Analyst target</span>`;
    async function drawChart() {
      if (ui.chart) ui.chart.destroy();
      const m = ui.mode, fcOn = $("#fcOn").checked;
      $("#fcOn").parentElement.style.display = m === "1D" || m === "7D" ? "none" : "";
      if (m === "1D" || m === "7D") {
        $("#chartTitle").textContent = m === "1D" ? "Today (5-minute bars)" : "Last 7 days (hourly bars)";
        $("#legend").innerHTML = m === "1D" ? `<span><i class="dash" style="color:var(--text-muted)"></i>Previous close</span><span class="muted">Times in your local time zone</span>` : `<span class="muted">Times in your local time zone</span>`;
        $("#fcNote").textContent = "";
        $("#chart").innerHTML = skeleton(8);
        try { ui.intra = ui.intra || await api("/api/intraday?symbol=" + encodeURIComponent(a.symbol)); }
        catch (e) { $("#chart").innerHTML = `<p class="error">${esc(e.message)}</p>`; return; }
        const ser = m === "1D" ? ui.intra.day : ui.intra.week;
        if (!ser.t.length) { $("#chart").innerHTML = `<p class="empty">No intraday data yet for this session.</p>`; return; }
        ui.chart = PriceChart($("#chart"), ser, { bars: ser.t.length, intraday: m === "1D" ? "day" : "week", prevClose: ui.intra.prevClose });
        renderHourly(ui.intra, m);
        return;
      }
      $("#hourlyCard").hidden = true;
      $("#chartTitle").textContent = "Price chart (daily)";
      $("#legend").innerHTML = legendDaily + (fcOn && a.forecast ? legendFc : "");
      const tgt = ui.fund && ui.fund.analyst ? ui.fund.analyst.avg : null;
      $("#fcNote").textContent = fcOn && a.forecast ? "Forecast: the last 6 months' trend (halved, since trends fade) with ranges from recent volatility. A statistical range, not a prediction." : "";
      ui.chart = PriceChart($("#chart"), a.series, { bars: +m, plan: p, forecast: fcOn ? a.forecast : null, target: fcOn ? tgt : null });
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
    drawChart();
    RF.quote = () => pages.stock(a.symbol);
    RF.chart = async () => { if (/D$/.test(ui.mode)) { ui.intra = null; await drawChart(); } else await pages.stock(a.symbol); };
    ["quote", "chart"].forEach(stamp);
    current = () => ui.chart && ui.chart.destroy();

    // ---- performance overview
    RF.perf = () => api("/api/performance?symbol=" + encodeURIComponent(a.symbol)).then((pf) => {
      if (!$("#perf")) return;
      const keys = ["1W", "1M", "3M", "6M", "YTD", "1Y", "2Y", "5Y", "Max"];
      $("#perf").innerHTML = `<div class="perf-grid">${keys.map((k) => {
        const v = pf.returns[k], b = pf.spy[k];
        return `<div class="perf-tile"><div class="k">${k === "Max" ? "Max" + (pf.since ? " (since " + new Date(pf.since * 1000).getFullYear() + ")" : "") : k}</div>
          <div class="v num ${cls(v)}">${pct(v, 1)}</div><div class="b num">S&amp;P ${pct(b, 1)}</div>
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
    $("#addPf").addEventListener("click", () => { location.hash = "#/portfolio?add=" + encodeURIComponent(a.symbol) + "&price=" + a.price; });
    if (p) {
      const upd = () => {
        const s2 = settings(); s2.riskPct = +$("#riskp").value || 1; s2.account = +$("#acct").value || 0; store.set("settings", s2);
        const riskAmt = s2.account * s2.riskPct / 100, perShare = p.entry - p.stop;
        const shares = Math.min(perShare > 0 ? riskAmt / perShare : 0, s2.account / p.entry);
        $("#sizeOut").innerHTML = sizeText({ riskAmt, shares, cost: shares * p.entry }, a);
      };
      $("#acct").addEventListener("input", upd); $("#riskp").addEventListener("input", upd);
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
  function sizeText(sz, a) {
    if (!sz) return "";
    return `Buy <b class="num">${fmt(sz.shares, sz.shares < 10 ? 2 : 0)}</b> shares ≈ <b class="num">${priceStr(sz.cost, a.currency)}</b>. If the stop is hit you lose about <b class="num">${fmt(sz.riskAmt, 2)}</b>.`;
  }

  // ------------------------------------------------------------ portfolio
  function portfolioSummary(t212, rows) {
    const quotes = Object.fromEntries((rows || []).map((r) => [r.symbol, r]));
    const t = t212 && !t212.error ? t212 : null;
    const m = manual();
    if (!t && !m.length) return null;
    let value = 0, ppl = 0, ccy = t ? t.currency : settings().ccy || "USD";
    if (t) { value += t.cash.total || 0; ppl += t.cash.ppl || 0; }
    for (const p of m) {
      const q = quotes[p.symbol]; const px = q ? q.price : p.avgPrice;
      value += p.qty * px; ppl += p.qty * (px - p.avgPrice);
    }
    return { value, ppl, ccy };
  }

  pages.portfolio = async function (arg, params) {
    if (current) { try { current(); } catch (e) { /* ignore */ } current = null; }
    view.innerHTML = `<h1>My Portfolio</h1><p class="sub">Your Trading 212 account (read-only) plus any holdings you add by hand, with a live rating and exit check on every position.</p>
      <div class="grid g4" id="pstats">${[1, 2, 3, 4].map(() => `<div class="card stat">${skeleton(2)}</div>`).join("")}</div>
      <div class="card" style="margin-top:16px"><div class="card-head" style="flex-wrap:wrap"><h2>Performance</h2>${rf("hist")}</div><p class="muted" id="phNote" style="font-size:12px;margin:-6px 0 10px"></p>
        <div id="pret" class="ret-grid">${skeleton(2)}</div>
        <div class="card-head" style="margin-top:16px;flex-wrap:wrap"><h2 style="margin:0">Money invested vs value</h2>
          <div class="seg" id="vrng"><button data-r="1M">1M</button><button data-r="6M">6M</button><button data-r="1Y">1Y</button><button data-r="5Y">5Y</button><button data-r="Max" class="on">Max</button></div></div>
        <div class="chart-box" id="vchart" style="height:320px">${skeleton(8)}</div>
        <div class="legend"><span><i style="background:var(--series-1)"></i>Portfolio value</span><span style="color:var(--text-muted)"><i class="dash"></i>Money invested (cost of shares held)</span><span><i style="background:rgba(12,163,12,.4);height:10px"></i>Gain</span><span><i style="background:rgba(208,59,59,.4);height:10px"></i>Loss</span></div>
        <div id="phWarn" class="muted" style="font-size:12px;margin-top:6px"></div>
      </div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>Positions</h2>${rf("pos")}</div><div id="ptbl">${skeleton(8)}</div></div>
        <div class="grid" style="align-content:start">
          <div class="card" id="link">${skeleton(4)}</div>
          <div class="card"><div class="card-head"><h2>Allocation</h2>${rf("pos")}</div><div id="alloc">${skeleton(4)}</div></div>
        </div>
      </div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><h2>Add a holding manually</h2><p class="muted" style="margin-top:-6px">For shares held outside Trading 212, or to plan before you link. Stored only in this browser.</p>
          <form class="form" id="mform"><div class="form-row">
            <label class="field">Symbol<input name="symbol" required placeholder="AAPL" value="${esc(params.get("add") || "")}"></label>
            <label class="field">Shares<input name="qty" type="number" step="any" min="0" required></label>
            <label class="field">Avg price<input name="avgPrice" type="number" step="any" min="0" required value="${esc(params.get("price") || "")}"></label>
            <label class="field">Buy date<input name="date" type="date" required value="${new Date().toISOString().slice(0, 10)}"></label>
            <button class="btn primary" type="submit">Add</button></div></form></div>
        <div class="card"><h2>Risk settings</h2><form class="form" id="sform"><div class="form-row">
          <label class="field">Risk per trade %<input name="riskPct" type="number" step="0.1" min="0.1" max="10" value="${settings().riskPct}"></label>
          <label class="field">Account size (if not linked)<input name="account" type="number" step="100" min="0" value="${settings().account}"></label>
          <button class="btn" type="submit">Save</button></div>
          <p class="muted" style="margin:0;font-size:13px">Pros risk 0.5–2% of the account per trade. Every entry plan sizes the position from this number.</p></form></div>
      </div>`;

    $("#mform").addEventListener("submit", (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const m = manual();
      m.push({ symbol: fd.get("symbol").trim().toUpperCase(), qty: +fd.get("qty"), avgPrice: +fd.get("avgPrice"), date: fd.get("date"), source: "manual" });
      store.set("manual", m); toast("Added " + fd.get("symbol").toUpperCase()); history.replaceState(null, "", "#/portfolio"); pages.portfolio("", new URLSearchParams());
    });
    $("#sform").addEventListener("submit", (e) => {
      e.preventDefault(); const fd = new FormData(e.target);
      store.set("settings", Object.assign(settings(), { riskPct: +fd.get("riskPct"), account: +fd.get("account") })); toast("Saved");
    });

    const t212 = await getT212(true).catch(() => null);
    if (!$("#link")) return;
    renderLink(t212);
    RF.pos = () => pages.portfolio("", new URLSearchParams());
    if (!$("#pstats")) return;
    RF.hist = () => loadHistory(state.t212);
    loadHistory(t212).then(() => stamp("hist"));

    const t = t212 && !t212.error ? t212 : null;
    const positions = (t ? t.positions.map((p) => Object.assign({ source: "Trading 212" }, p)) : []).concat(manual().map((p, i) => Object.assign({ source: "Manual", idx: i }, p)));
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
      const stop = q.atr && p.avgPrice ? Math.max(p.avgPrice - 2 * q.atr, (q.sma50 || 0) * 0.97) : null;
      p.alert = !q.price ? "" : q.rating === "Strong Sell" || q.rating === "Sell" ? "Rating turned " + q.rating
        : q.entryStatus === "Avoid" ? "In a downtrend" : stop && q.price < stop ? "Below trailing stop " + fmt(stop, dp(stop))
        : q.rsi > 75 ? "Overbought: consider taking profit" : p.plPct > 20 && q.price < q.sma20 ? "Lost 20-day avg: protect gains" : "OK";
    }
    const ccy = t ? t.currency : "USD";
    const invested = positions.reduce((a, p) => a + (p.avgPrice || 0) * (p.qty || 0), 0);
    const total = t ? (t.cash.total || 0) + manual().reduce((a, p) => a + p.qty * (Q[p.symbol] ? Q[p.symbol].price : p.avgPrice), 0) : positions.reduce((a, p) => a + p.mv, 0);
    const ppl = (t && t.cash.ppl != null ? t.cash.ppl : positions.filter((p) => p.source === "Trading 212").reduce((a, p) => a + (p.ppl || 0), 0)) +
      positions.filter((p) => p.source === "Manual").reduce((a, p) => a + (p.ppl || 0), 0);
    const alerts = positions.filter((p) => p.alert && p.alert !== "OK").length;
    $("#pstats").innerHTML = `
      <div class="card stat"><div class="label">Total value</div><div class="value num">${money(total, ccy)}</div><div class="delta sec">${t ? "Trading 212 " + esc(t.env) + (manual().length ? " + manual" : "") : "manual holdings"}</div></div>
      <div class="card stat"><div class="label">Open P/L</div><div class="value num ${cls(ppl)}">${ppl >= 0 ? "+" : ""}${money(ppl, ccy)}</div><div class="delta num ${cls(ppl)}">${invested && !t ? pct(100 * ppl / invested) : ""}</div></div>
      <div class="card stat"><div class="label">Free cash</div><div class="value num">${t ? money(t.cash.free, ccy) : "–"}</div><div class="delta sec">${t && t.cash.result != null ? "Realised P/L " + money(t.cash.result, ccy) : "link Trading 212 to see cash"}</div></div>
      <div class="card stat"><div class="label">Positions needing attention</div><div class="value num ${alerts ? "down" : ""}">${alerts}</div><div class="delta sec">of ${positions.length} positions</div></div>`;
    stamp("pos");

    if (!positions.length) {
      $("#ptbl").innerHTML = `<p class="empty">No positions yet. Link Trading 212 or add a holding below.</p>`;
      $("#alloc").innerHTML = `<p class="empty">Nothing to chart yet.</p>`;
      return;
    }
    sortableTable($("#ptbl"), positions, [
      { key: "symbol", label: "Holding", val: (p) => p.symbol, html: (p) => symCell(p) + `<span class="nm">${esc(p.source)}</span>` },
      { key: "qty", label: "Shares", r: true, val: (p) => p.qty, html: (p) => shares(p.qty) },
      { key: "avg", label: "Avg", r: true, sm: true, val: (p) => p.avgPrice, html: (p) => fmt(p.avgPrice, dp(p.avgPrice)) },
      { key: "price", label: "Price", r: true, val: (p) => p.price, html: (p) => fmt(p.price, dp(p.price)) },
      { key: "pl", label: "P/L", r: true, val: (p) => p.plPct, html: (p) => `<span class="${cls(p.plPct)}">${pct(p.plPct)}</span><span class="nm ${cls(p.ppl)}">${p.ppl != null ? (p.ppl >= 0 ? "+" : "") + fmt(p.ppl, 2) : ""}</span>` },
      { key: "rating", label: "Rating", val: (p) => p.q.score, html: (p) => ratingBadge(p.q.rating) },
      { key: "alert", label: "Check", val: (p) => (p.alert === "OK" ? 0 : 1), html: (p) => p.alert === "OK" ? `<span class="muted">✓ OK</span>` : p.alert ? `<span class="badge e-wait">${esc(p.alert)}</span>` : "" },
      { key: "x", label: "", val: () => 0, html: (p) => p.source === "Manual" ? `<button class="btn sm danger" data-del="${p.idx}" aria-label="Remove">✕</button>` : "" },
    ], { sort: "pl" });
    $$("[data-del]").forEach((b) => b.addEventListener("click", () => {
      const m = manual(); m.splice(+b.dataset.del, 1); store.set("manual", m); pages.portfolio("", new URLSearchParams());
    }));

    // allocation donut: top 7 + Other, fixed color order
    const colors = [1, 2, 3, 4, 5, 6, 7].map((i) => `var(--series-${i})`);
    const sorted = positions.filter((p) => p.mv > 0).sort((a, b) => b.mv - a.mv);
    let items = sorted.slice(0, 7).map((p, i) => ({ label: p.symbol, value: p.mv, color: colors[i] }));
    const rest = sorted.slice(7).reduce((a, p) => a + p.mv, 0);
    if (rest > 0) items.push({ label: "Other", value: rest, color: "#5a5955" });
    if (t && t.cash.free > 0) items.push({ label: "Cash", value: t.cash.free, color: "var(--text-muted)" });
    const tot = items.reduce((a, b) => a + b.value, 0);
    const mixed = new Set(positions.map((p) => p.currency || p.q.currency).filter(Boolean)).size > 1;
    $("#alloc").innerHTML = `<div class="donut-wrap">${donut(items, 180, items.length + " slices", "by value")}
      <ul class="donut-legend">${items.map((it) => `<li><span><i style="background:${it.color}"></i>${esc(it.label)}</span><span class="num">${(100 * it.value / tot).toFixed(1)}%</span></li>`).join("")}</ul></div>
      ${mixed ? `<p class="muted" style="font-size:12px">Holdings trade in different currencies, so weights are approximate.</p>` : ""}`;
  };

  async function loadHistory(t212) {
    const t = t212 && !t212.error ? t212 : null;
    if (!t && !manual().length) {
      $("#pret").innerHTML = `<p class="muted">Link Trading 212 or add holdings to see your returns.</p>`;
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
    $("#pret").innerHTML = ["1D", "1W", "1M", "YTD", "1Y", "5Y", "Max"].map((k) => {
      const r = h.returns[k];
      return `<div class="perf-tile"><div class="k">${label[k]}</div>${r ? `<div class="v num ${cls(r.gain)}">${pct(r.pct)}</div><div class="b num ${cls(r.gain)}">${r.gain >= 0 ? "+" : ""}${m(r.gain)}</div>`
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
      from = Math.max(from, firstHeld > 0 ? firstHeld - 1 : 0);
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


  // ------------------------------------------------------------ AI multibagger radar
  pages.radar = async function () {
    const f = Object.assign({ theme: "", stage: "", sort: "score" }, store.get("rfilter", {}));
    view.innerHTML = `
      <section class="ai-hero">
        <div class="ai-hero-text">
          <span class="ai-kicker">✦ AI pattern scanner</span>
          <h1>Find the next NVIDIA</h1>
          <p>The radar learned what <b>NVIDIA, Micron, SanDisk, ASML, Western Digital, Palantir, AppLovin and Broadcom</b> looked like on the day their 100% to 1,000% runs began. Every day it scans ${"<span id='nScan'>45</span>"} AI-economy stocks for the same fingerprint, then checks the earnings growth behind them.</p>
          <div class="ai-stats" id="aiStats">${skeleton(2)}</div>
          <p class="ai-warn">⚠ Pattern matching, not a promise. Most stocks that look like past winners don't become one, and these stocks can fall 50% or more. Size positions small.</p>
        </div>
        <div class="ai-scope" id="scope"><div class="scope-loading"><div class="pulse"></div><p>Scanning the AI economy…<br><span class="muted">first scan takes about 2 minutes</span></p></div></div>
      </section>
      <div class="card-head" style="margin:22px 0 10px"><h2 style="margin:0">The legends: what they did after the launch signal</h2>${rf("radar")}</div>
      <div class="legends" id="legends">${[1, 2, 3, 4].map(() => `<div class="card">${skeleton(4)}</div>`).join("")}</div>
      <h2 style="margin:22px 0 10px">Theme heat</h2>
      <div class="heat" id="heat">${skeleton(2)}</div>
      <div class="toolbar" style="margin-top:22px">
        <h2 style="margin:0 12px 0 0">Candidates</h2>
        <select id="rTheme" aria-label="Theme"><option value="">All themes</option></select>
        <select id="rStage" aria-label="Stage"><option value="">All stages</option><option>Launch pattern</option><option>Building</option><option>Not yet</option><option>Extended</option><option>Late: already ran</option></select>
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
      const C = data.candidates, W = data.winners;
      $("#nScan").textContent = C.length;
      const launch = C.filter((x) => x.stage === "Launch pattern");
      $("#aiStats").innerHTML = `<div><b>${C.length}</b><span>stocks scanned</span></div><div><b>${W.length}</b><span>legends learned</span></div>
        <div><b>${launch.length}</b><span>show the launch pattern</span></div><div><b>${esc(C[0].symbol)}</b><span>top score (${C[0].score})</span></div>`;
      $("#scope").innerHTML = TChart.radarScope(C.slice(0, 24)) + `<p class="muted scope-cap">Closer to the centre = higher score · green = 75+</p>`;
      $("#legends").innerHTML = W.map((w) => `<a class="card legend" href="#/stock/${encodeURIComponent(w.symbol)}">
        <div class="card-head" style="margin-bottom:4px"><span class="sym" style="font-size:17px">${esc(w.symbol)}</span><span class="badge b-strongbuy">+${w.peak12}% peak</span></div>
        <div class="muted" style="font-size:12px">Launch signal ${new Date(w.date + "T12:00:00Z").toLocaleDateString(undefined, { month: "short", year: "numeric" })} at ${fmt(w.price, 2)}</div>
        ${TChart.legendPath(w.path)}
        <div style="display:flex;justify-content:space-between;font-size:12px"><span class="sec">12 months later <b class="${cls(w.gain12)}">${w.gain12 >= 0 ? "+" : ""}${w.gain12}%</b></span><span class="sec">Today <b class="up">+${w.sinceLaunch}%</b></span></div></a>`).join("");
      const blue = (v) => `rgba(57,135,229,${(0.12 + 0.75 * Math.max(0, v - 20) / 70).toFixed(2)})`;
      $("#heat").innerHTML = data.themes.map((t) => `<button class="heat-tile" data-theme="${esc(t.theme)}" style="background:${blue(t.avg)}"><span>${esc(t.theme)}</span><b>${t.avg}</b><small>avg of ${t.n} · best ${t.top}</small></button>`).join("");
      $$("#heat .heat-tile").forEach((b) => b.addEventListener("click", () => { f.theme = f.theme === b.dataset.theme ? "" : b.dataset.theme; cards(); }));
      $("#rTheme").innerHTML = `<option value="">All themes</option>` + data.themes.map((t) => `<option ${t.theme === f.theme ? "selected" : ""}>${esc(t.theme)}</option>`).join("");
      cards();
    };
    const cards = () => {
      store.set("rfilter", f);
      $("#rTheme").value = f.theme; $("#rStage").value = f.stage;
      $$("#rSort button").forEach((b) => b.classList.toggle("on", b.dataset.s === f.sort));
      $$("#heat .heat-tile").forEach((b) => b.classList.toggle("on", b.dataset.theme === f.theme));
      const rows = data.candidates.filter((x) => (!f.theme || x.theme === f.theme) && (!f.stage || x.stage === f.stage))
        .sort((a, b) => (b[f.sort] ?? -999) - (a[f.sort] ?? -999));
      $("#cands").innerHTML = rows.map((x, i) => candCard(x, i + 1)).join("") || `<div class="card empty">No stocks match these filters.</div>`;
      $$("#cands [data-open]").forEach((b) => b.addEventListener("click", () => openDetail(b.dataset.open, b)));
    };
    const stageCls = (s) => s === "Launch pattern" ? "e-now" : s === "Building" ? "e-watch" : s.startsWith("Late") || s === "Extended" ? "e-wait" : "e-none";
    const bar = (label, v) => `<div class="mbar"><span>${label}</span><i><b style="width:${v ?? 0}%"></b></i><em class="num">${v ?? "–"}</em></div>`;
    const candCard = (x, rank) => `<div class="card cand" id="c-${esc(x.symbol)}">
      <div class="cand-top">
        <div class="rank">#${rank}</div>
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
      <button class="btn sm" data-open="${esc(x.symbol)}" style="width:100%;margin-top:6px">Compare with the legends ▾</button>
      <div class="cand-detail" hidden></div></div>`;
    const openDetail = (sym, btn) => {
      const x = data.candidates.find((c) => c.symbol === sym);
      const box = btn.nextElementSibling;
      const card = btn.closest(".cand");
      if (!box.hidden) { box.hidden = true; card.classList.remove("open"); btn.textContent = "Compare with the legends ▾"; return; }
      const ap = TChart.analogPaths(x.price, data.winners);
      box.innerHTML = `<div class="detail-grid"><div><h3 class="h3" style="margin-top:12px">Fingerprint vs the legends at launch</h3>${TChart.spider(data.features, x.features, data.profile, 300)}
        <div class="legend"><span><i style="background:var(--series-1)"></i>${esc(x.symbol)} today</span><span style="color:var(--series-2)"><i class="dash"></i>Legends at launch</span></div>
        <p class="muted" style="font-size:12px">Furthest from the legends: ${x.differs.map(esc).join(", ")}.</p>
        ${x.growthWhy.length ? `<h3 class="h3" style="margin-top:12px">Growth check</h3><ul class="reasons">${x.growthWhy.map((g) => `<li class="${g.ok ? "" : "no"}">${esc(g.text)}</li>`).join("")}</ul>` : ""}</div>
        <div><h3 class="h3" style="margin-top:12px">What if ${esc(x.symbol)} repeated a legend's next 12 months?</h3>${ap.svg}
        <p class="muted" style="font-size:12px">Each line takes today's price along one legend's actual 12 months after its launch signal. The median legend path ends at ${pct(100 * (ap.median - 1), 0)}. Hypothetical: it shows what the legends did, not what ${esc(x.symbol)} will do.</p></div></div>`;
      box.hidden = false; card.classList.add("open"); card.scrollIntoView({ behavior: "smooth", block: "nearest" }); btn.textContent = "Hide comparison ▴";
    };
    $("#rTheme").addEventListener("change", (e) => { f.theme = e.target.value; cards(); });
    $("#rStage").addEventListener("change", (e) => { f.stage = e.target.value; cards(); });
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
      <div class="m">${esc(n.publisher || "")} · ${ago(n.time)} ${(n.tickers || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}${(n.tags || []).map((t) => `<span class="tag">#${esc(t)}</span>`).join("")}</div></div></a>`).join("");
  }

  pages.news = async function () {
    const t = state.t212 && !state.t212.error ? state.t212.positions.map((p) => p.symbol) : [];
    const mine = [...new Set([...t, ...manual().map((p) => p.symbol), ...watchlist()])];
    view.innerHTML = `<h1>Trading News</h1><p class="sub">Headlines for your holdings and watchlist, or the whole market. Tagged by type so earnings, analyst calls and deals stand out.</p>
      <div class="toolbar"><div class="seg" id="ns"><button data-s="mine" class="on">My stocks</button><button data-s="market">Market</button></div>
        <input type="text" id="nsym" placeholder="Ticker, e.g. AMD" aria-label="News for ticker" style="width:150px"><button class="btn sm" id="ngo">Show</button>
        <select id="ntag" aria-label="Filter by type"><option value="">All types</option><option value="earnings">Earnings</option><option value="analyst">Analyst</option><option value="deal">Deals</option><option value="legal">Legal</option><option value="macro">Macro</option></select>${rf("news")}</div>
      <div id="nl" class="news-list">${skeleton(10)}</div>`;
    let items = [];
    const paint = () => { const tag = $("#ntag").value; $("#nl").innerHTML = newsHtml(tag ? items.filter((n) => n.tags.includes(tag)) : items); };
    let last = [];
    const load = async (syms) => {
      last = syms;
      $("#nl").innerHTML = skeleton(10);
      try { items = await api("/api/news?symbols=" + encodeURIComponent(syms.join(","))); paint(); stamp("news"); }
      catch (e) { $("#nl").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
    };
    $$("#ns button").forEach((b) => b.addEventListener("click", () => {
      $$("#ns button").forEach((x) => x.classList.toggle("on", x === b));
      load(b.dataset.s === "mine" ? mine.slice(0, 25) : ["stock market news", "SPY", "QQQ", "^VIX", "DIA"]);
    }));
    $("#ngo").addEventListener("click", () => { const s = $("#nsym").value.trim().toUpperCase(); if (s) load([s]); });
    $("#nsym").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#ngo").click(); });
    $("#ntag").addEventListener("change", paint);
    RF.news = () => load(last);
    load(mine.length ? mine.slice(0, 25) : ["stock market news"]);
  };

  // ------------------------------------------------------------ router
  async function route() {
    if (current) { try { current(); } catch (e) { /* ignore */ } current = null; }
    RF = {};
    routeId++;
    const [path, qs] = (location.hash.replace(/^#\/?/, "") || "").split("?");
    const [name, arg] = path.split("/");
    const page = pages[name || "home"] ? name || "home" : "home";
    $$("#tabs a").forEach((a) => a.classList.toggle("active", a.dataset.tab === page));
    window.scrollTo(0, 0);
    try { await pages[page](arg, new URLSearchParams(qs || "")); }
    catch (e) { view.innerHTML = `<div class="card empty"><h2>Something went wrong</h2><p class="error">${esc(e.message)}</p><p>Is the dashboard server still running?</p></div>`; }
  }
  window.addEventListener("hashchange", route);
  route();
  loadStrip().catch(() => {});
  setInterval(() => { if (!document.hidden) loadStrip().catch(() => {}); }, 60000);
  getT212().catch(() => {});
})();
