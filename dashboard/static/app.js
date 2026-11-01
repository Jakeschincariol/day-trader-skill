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

  async function api(path, opts) {
    const res = await fetch(path, opts);
    const data = await res.json().catch(() => ({ error: "Bad response from server" }));
    if (!res.ok) throw new Error(data.error || "Request failed (" + res.status + ")");
    return data;
  }
  const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

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
  const pages = {};

  pages.home = async function () {
    view.innerHTML = `<h1>Market Dashboard</h1><p class="sub">Live overview of the market, today's best setups, your watchlist and portfolio.</p>
      <div class="grid g4" id="stats">${[1, 2, 3, 4].map(() => `<div class="card stat">${skeleton(2)}</div>`).join("")}</div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>Top Strong Buys</h2><a href="#/signals">See all →</a></div><div id="top">${skeleton(8)}</div></div>
        <div class="card"><div class="card-head"><h2>In the buy zone now</h2></div><div id="zone">${skeleton(6)}</div></div>
      </div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>Your watchlist</h2><a href="#/markets">Add more →</a></div><div id="wl">${skeleton(5)}</div></div>
        <div class="card"><div class="card-head"><h2>Latest news</h2><a href="#/news">All news →</a></div><div id="hn" class="news-list news-compact">${skeleton(6)}</div></div>
      </div>`;

    api("/api/news?symbols=" + encodeURIComponent(watchlist().slice(0, 8).join(","))).then((news) => {
      $("#hn") && ($("#hn").innerHTML = newsHtml(news.slice(0, 7), true));
    }).catch((e) => $("#hn") && ($("#hn").innerHTML = `<p class="error">${esc(e.message)}</p>`));

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
        <button class="btn sm" id="refresh">↻ Refresh</button>
        <span class="muted" id="asof"></span>
      </div>
      <div class="card" id="tbl">${skeleton(14)}</div>`;
    const rows = await getScreener();
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
      $("#asof").textContent = "Updated " + new Date(state.screenerAt).toLocaleTimeString();
    };
    $$("#grp button").forEach((b) => b.addEventListener("click", () => { f.group = b.dataset.g; paint(); }));
    $("#sector").addEventListener("change", (e) => { f.sector = e.target.value; paint(); });
    $("#rating").addEventListener("change", (e) => { f.rating = e.target.value; paint(); });
    $("#filter").addEventListener("input", (e) => { f.q = e.target.value; clearTimeout(paint._t); paint._t = setTimeout(paint, 150); });
    $("#refresh").addEventListener("click", async () => { $("#tbl").innerHTML = skeleton(14); await getScreener(true); paint(); });
    paint();
  };

  pages.signals = async function () {
    view.innerHTML = `<h1>Strong Buys &amp; Best Entries</h1><p class="sub">Stocks and ETFs where trend, momentum, volume and relative strength line up, with the entry, stop and targets for each.</p>
      <div class="toolbar"><div class="seg" id="sg"><button data-g="now" class="on">Buy now</button><button data-g="strong">All Strong Buys</button><button data-g="watch">Watch list setups</button></div></div>
      <div class="grid g3" id="cards">${[1, 2, 3].map(() => `<div class="card">${skeleton(6)}</div>`).join("")}</div>`;
    const rows = await getScreener();
    if (!$("#cards")) return;
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
    sym = decodeURIComponent(sym || "SPY").toUpperCase();
    view.innerHTML = `<div class="card">${skeleton(3)}</div><div class="card" style="margin-top:16px;height:440px">${skeleton(10)}</div>`;
    let a;
    try { a = await api("/api/analysis?symbol=" + encodeURIComponent(sym)); }
    catch (e) { view.innerHTML = `<div class="card empty"><h2>Couldn't load ${esc(sym)}</h2><p class="error">${esc(e.message)}</p><p>Try the search box: some tickers need an exchange suffix (e.g. VUSA.L for London, SAP.DE for Xetra).</p></div>`; return; }
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
        <div style="display:flex;gap:8px;flex-wrap:wrap">${ratingBadge(a.rating)} ${entryBadge(a.entryStatus)}</div>
      </div>
      <div class="grid g2">
        <div class="card chart-card">
          <div class="card-head"><h2>Price chart (daily)</h2><div class="seg" id="rng"><button data-b="63">3M</button><button data-b="126" class="on">6M</button><button data-b="252">1Y</button><button data-b="504">2Y</button></div></div>
          <div class="chart-box" id="chart"></div>
          <div class="legend"><span><i style="background:var(--series-2)"></i>SMA 20</span><span><i style="background:var(--series-1)"></i>SMA 50</span><span><i style="background:var(--series-5)"></i>SMA 200</span>
            <span><i style="background:var(--series-7)"></i>RSI 14</span>${p ? `<span style="color:var(--accent)"><i class="dash"></i>Entry</span><span style="color:var(--bad)"><i class="dash"></i>Stop</span><span style="color:var(--good)"><i class="dash"></i>Targets</span>` : ""}</div>
        </div>
        <div class="grid" style="align-content:start">
          <div class="card">
            <h2>Best moment to buy</h2>
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
        <div class="card"><h2>News: ${esc(a.symbol)}</h2><div id="snews" class="news-list news-compact">${skeleton(5)}</div></div>
      </div>`;

    let chart = PriceChart($("#chart"), a.series, { bars: 126, plan: p });
    $$("#rng button").forEach((b) => b.addEventListener("click", () => {
      $$("#rng button").forEach((x) => x.classList.toggle("on", x === b));
      chart.destroy(); chart = PriceChart($("#chart"), a.series, { bars: +b.dataset.b, plan: p });
    }));
    current = () => chart.destroy();
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
    api("/api/news?symbols=" + encodeURIComponent(a.symbol)).then((n) => { $("#snews") && ($("#snews").innerHTML = newsHtml(n.slice(0, 8), true)); })
      .catch(() => { $("#snews") && ($("#snews").innerHTML = `<p class="muted">No news available.</p>`); });
  };
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
    view.innerHTML = `<h1>My Portfolio</h1><p class="sub">Your Trading 212 account (read-only) plus any holdings you add by hand, with a live rating and exit check on every position.</p>
      <div class="grid g4" id="pstats">${[1, 2, 3, 4].map(() => `<div class="card stat">${skeleton(2)}</div>`).join("")}</div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><div class="card-head"><h2>Positions</h2><span id="psrc" class="muted"></span></div><div id="ptbl">${skeleton(8)}</div></div>
        <div class="grid" style="align-content:start">
          <div class="card" id="link">${skeleton(4)}</div>
          <div class="card"><h2>Allocation</h2><div id="alloc">${skeleton(4)}</div></div>
        </div>
      </div>
      <div class="grid g2" style="margin-top:16px">
        <div class="card"><h2>Add a holding manually</h2><p class="muted" style="margin-top:-6px">For shares held outside Trading 212, or to plan before you link. Stored only in this browser.</p>
          <form class="form" id="mform"><div class="form-row">
            <label class="field">Symbol<input name="symbol" required placeholder="AAPL" value="${esc(params.get("add") || "")}"></label>
            <label class="field">Shares<input name="qty" type="number" step="any" min="0" required></label>
            <label class="field">Avg price<input name="avgPrice" type="number" step="any" min="0" required value="${esc(params.get("price") || "")}"></label>
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
      m.push({ symbol: fd.get("symbol").trim().toUpperCase(), qty: +fd.get("qty"), avgPrice: +fd.get("avgPrice"), source: "manual" });
      store.set("manual", m); toast("Added " + fd.get("symbol").toUpperCase()); history.replaceState(null, "", "#/portfolio"); pages.portfolio("", new URLSearchParams());
    });
    $("#sform").addEventListener("submit", (e) => {
      e.preventDefault(); const fd = new FormData(e.target);
      store.set("settings", Object.assign(settings(), { riskPct: +fd.get("riskPct"), account: +fd.get("account") })); toast("Saved");
    });

    const t212 = await getT212(true).catch(() => null);
    if (!$("#link")) return;
    renderLink(t212);

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
    $("#psrc").textContent = t ? "Updated " + new Date(t.fetched * 1000).toLocaleTimeString() : "";

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

  function renderLink(t212) {
    const st = state.t212Status || {};
    const el = $("#link");
    if (st.linked) {
      el.innerHTML = `<div class="card-head"><h2>Trading 212</h2><span class="pill ${st.env === "demo" ? "demo" : "live"}">${st.env === "demo" ? "Practice" : "Live"} · linked</span></div>
        ${t212 && t212.error ? `<p class="error">${esc(t212.error)}</p>` : `<p class="sec" style="margin-top:0">Read-only connection. Positions and cash refresh every time you open this page.</p>`}
        <div style="display:flex;gap:8px"><button class="btn" id="t212r">↻ Refresh</button>${st.source === "env" ? `<span class="muted" style="font-size:12px">Key set by environment variable</span>` : `<button class="btn danger" id="t212d">Disconnect</button>`}</div>`;
      $("#t212r").addEventListener("click", () => pages.portfolio("", new URLSearchParams()));
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
        <select id="ntag" aria-label="Filter by type"><option value="">All types</option><option value="earnings">Earnings</option><option value="analyst">Analyst</option><option value="deal">Deals</option><option value="legal">Legal</option><option value="macro">Macro</option></select></div>
      <div id="nl" class="news-list">${skeleton(10)}</div>`;
    let items = [];
    const paint = () => { const tag = $("#ntag").value; $("#nl").innerHTML = newsHtml(tag ? items.filter((n) => n.tags.includes(tag)) : items); };
    const load = async (syms) => {
      $("#nl").innerHTML = skeleton(10);
      try { items = await api("/api/news?symbols=" + encodeURIComponent(syms.join(","))); paint(); }
      catch (e) { $("#nl").innerHTML = `<p class="error">${esc(e.message)}</p>`; }
    };
    $$("#ns button").forEach((b) => b.addEventListener("click", () => {
      $$("#ns button").forEach((x) => x.classList.toggle("on", x === b));
      load(b.dataset.s === "mine" ? mine.slice(0, 25) : ["stock market news", "SPY", "QQQ", "^VIX", "DIA"]);
    }));
    $("#ngo").addEventListener("click", () => { const s = $("#nsym").value.trim().toUpperCase(); if (s) load([s]); });
    $("#nsym").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#ngo").click(); });
    $("#ntag").addEventListener("change", paint);
    load(mine.length ? mine.slice(0, 25) : ["stock market news"]);
  };

  // ------------------------------------------------------------ router
  async function route() {
    if (current) { try { current(); } catch (e) { /* ignore */ } current = null; }
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
