/* Trading tools for Trader Dashboard: order ticket, alerts, market mood, signal backtest,
   risk panel and trade journal. Nothing here places an order: tickets are prepared for
   you to copy into Trading 212 yourself. Uses helpers app.js shares on window.TD. */
(function () {
  "use strict";
  const T = () => window.TD;
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));

  // ------------------------------------------------------------ currencies and Trading 212 tickers
  const fxCache = {};
  async function fx(from, to) {
    if (!from || !to || from === to) return 1;
    const k = from + ">" + to;
    if (fxCache[k] && Date.now() - fxCache[k].at < 600000) return fxCache[k].rate;
    const d = await T().api("/api/fx?from=" + encodeURIComponent(from) + "&to=" + encodeURIComponent(to));
    if (!d.rate) throw new Error("No exchange rate " + from + " to " + to);
    fxCache[k] = { rate: d.rate, at: Date.now() };
    return d.rate;
  }
  const SUFFIX = { L: "l", DE: "d", PA: "p", AS: "a", MI: "m", MC: "e", SW: "s", BR: "b" };
  function t212Ticker(sym) {
    const m = /^(.+)\.([A-Z]{1,2})$/.exec(sym);
    if (m && SUFFIX[m[2]]) return m[1] + SUFFIX[m[2]] + "_EQ";
    return sym.replace("-", ".") + "_US_EQ";
  }
  const unitLabel = (ccy) => (ccy === "GBp" || ccy === "GBX" ? "pence (GBX)" : ccy || "");

  // ------------------------------------------------------------ account context for sizing
  async function account() {
    const td = T(), st = td.settings();
    let t = td.state.t212;
    if (!td.state.t212Status) { try { t = await td.getT212(); } catch (e) { t = null; } }
    t = t && !t.error ? t : null;
    const rv = td.state.revolut && td.state.revolut.linked ? td.state.revolut : null;
    const total = (t && t.cash.total ? t.cash.total : 0) + (rv ? rv.totals.value || 0 : 0);
    return {
      linked: !!t, ccy: t ? t.currency || "USD" : rv ? rv.currency : st.ccy || "USD",
      total: total || st.account, free: t ? t.cash.free : null,
      positions: td.brokerPositions(), pending: t ? t.pending : null,
      riskPct: st.riskPct || 1, maxPosPct: st.maxPosPct || 25, maxHeatPct: st.maxHeatPct || 6,
    };
  }

  /** Size a plan in the account's currency. Returns everything the ticket needs. */
  async function size(a, acct, riskPct, regime) {
    const p = a.plan;
    const rate = await fx(a.currency, acct.ccy); // account units per 1 unit of the quote currency
    const perShareRisk = (p.entry - p.stop) * rate;
    const riskAmt = acct.total * riskPct / 100 * (regime === "amber" ? 0.5 : 1);
    let qty = perShareRisk > 0 ? riskAmt / perShareRisk : 0;
    const costPer = p.entry * rate;
    const capPos = acct.total * acct.maxPosPct / 100 / costPer;
    const capped = qty > capPos;
    qty = Math.floor(Math.min(qty, capPos) * 100) / 100; // Trading 212 fractional shares: 2 decimals is safe
    return { qty, rate, cost: qty * costPer, risk: qty * perShareRisk, riskAmt, posPct: 100 * qty * costPer / acct.total, capped, halved: regime === "amber" };
  }

  // ------------------------------------------------------------ order ticket (prepared, never sent)
  let dlg = null;
  function dialog() {
    if (dlg) return dlg;
    dlg = document.createElement("dialog");
    dlg.className = "sheet";
    dlg.setAttribute("aria-labelledby", "sheetTitle");
    document.body.appendChild(dlg);
    dlg.addEventListener("click", (e) => { if (e.target === dlg || e.target.closest("[data-close]")) dlg.close(); });
    return dlg;
  }

  async function openTicket(a) {
    const td = T(), d = dialog();
    d.innerHTML = `<div class="sheet-body"><p>${td.skeleton(6)}</p></div>`;
    d.showModal();
    let acct, sz;
    try {
      acct = await account();
      sz = await size(a, acct, acct.riskPct, a.regime && a.regime.level);
    } catch (e) {
      d.innerHTML = `<div class="sheet-body"><h2>Order ticket</h2><p class="error">${td.esc(e.message)}</p><button class="btn" data-close>Close</button></div>`;
      return;
    }
    const p = a.plan, dp = td.dp(p.entry), f = (x) => td.fmt(x, dp);
    const draw = () => {
      const qty = +$("#tkQty", d).value || 0;
      const lim = +$("#tkLimit", d).value || p.entry;
      const stop = +$("#tkStop", d).value || p.stop;
      const cost = qty * lim * sz.rate, risk = qty * Math.max(0, lim - stop) * sz.rate;
      const t1 = lim + 2 * (lim - stop), t2 = lim + 3 * (lim - stop);
      const warn = [];
      if (acct.free != null && cost > acct.free) warn.push(`Costs ${td.money(cost, acct.ccy)}, more than your free cash ${td.money(acct.free, acct.ccy)}.`);
      if (100 * cost / acct.total > acct.maxPosPct) warn.push(`This would be ${(100 * cost / acct.total).toFixed(0)}% of your account (your limit: ${acct.maxPosPct}%).`);
      if (a.earnings && a.earnings.days <= 14) warn.push(`Earnings in ${a.earnings.days} day${a.earnings.days === 1 ? "" : "s"} (${a.earnings.date}): the price can gap straight through your stop.`);
      if (a.regime && a.regime.level === "red") warn.push("Market is weak (red light): most new buys fail in this tape.");
      if (a.regime && a.regime.level === "amber") warn.push("Market is mixed (amber light): size already halved.");
      if (lim > a.price * 1.01) warn.push(`Your limit is above the current price ${f(a.price)}: it may fill immediately at market.`);
      if (stop >= lim) warn.push("The stop must be below the buy price.");
      const tk = a._t212 || t212Ticker(a.symbol);
      $("#tkSum", d).innerHTML = `
        <div class="tk-grid">
          <div><span>Cost</span><b class="num">${td.money(cost, acct.ccy)}</b><small>${td.fmt(qty * lim, 2)} ${td.esc(unitLabel(a.currency))}</small></div>
          <div><span>Max loss at stop</span><b class="num down">−${td.money(risk, acct.ccy)}</b><small>${(100 * risk / acct.total).toFixed(2)}% of account</small></div>
          <div><span>Target 1 · 2R</span><b class="num up">${f(t1)}</b><small>+${td.money(2 * risk, acct.ccy)}</small></div>
          <div><span>Target 2 · 3R</span><b class="num up">${f(t2)}</b><small>+${td.money(3 * risk, acct.ccy)}</small></div>
        </div>
        ${warn.length ? `<ul class="tk-warn">${warn.map((w) => `<li>${td.esc(w)}</li>`).join("")}</ul>` : `<p class="tk-ok">✓ Within your risk rules.</p>`}
        <h3 class="h3">Place it in Trading 212</h3>
        <ol class="steps tk-steps">
          <li>Search <b>${td.esc(a.symbol)}</b> (${td.esc(a.name || "")}) → <b>Buy</b> → <b>Limit order</b>: price <b class="num">${f(lim)}</b>, quantity <b class="num">${td.shares(qty)}</b>.</li>
          <li>Once filled → <b>Sell</b> → <b>Stop order</b>: stop price <b class="num">${f(stop)}</b>, quantity <b class="num">${td.shares(qty)}</b>.</li>
          <li>Take profit: set a price alert at <b class="num">${f(t1)}</b> (button below) and sell half there; move the stop to <b class="num">${f(lim)}</b> (break-even) for the rest, aiming for <b class="num">${f(t2)}</b>. Trading 212 may refuse a limit sell while the stop already covers the shares.</li>
        </ol>
        <p class="muted" style="font-size:12px">Trading 212 ticker: <code>${td.esc(tk)}</code> · prices in ${td.esc(unitLabel(a.currency))} · 1 ${td.esc(a.currency)} = ${sz.rate.toFixed(4)} ${td.esc(acct.ccy)}</p>`;
      d._ticket = `BUY ${a.symbol} (${tk})\nLimit ${f(lim)} x ${td.shares(qty)} shares  (~${td.money(cost, acct.ccy)})\nStop ${f(stop)}  (max loss ~${td.money(risk, acct.ccy)})\nTarget 1 ${f(t1)}  |  Target 2 ${f(t2)}` +
        (warn.length ? "\nWarnings: " + warn.join(" ") : "");
    };
    d.innerHTML = `<div class="sheet-body">
      <div class="card-head"><h2 id="sheetTitle"><i data-lucide="clipboard-list"></i>Order ticket · ${T().esc(a.symbol)}</h2><button class="rf" data-close aria-label="Close"><i data-lucide="x"></i></button></div>
      <p class="muted" style="margin-top:-6px;font-size:13px">Prepared for you to enter in Trading 212. This site never places orders.</p>
      <div class="form-row">
        <label class="field">Shares<input id="tkQty" type="number" inputmode="decimal" step="0.01" min="0" value="${sz.qty}"></label>
        <label class="field">Buy limit<input id="tkLimit" type="number" inputmode="decimal" step="any" value="${p.entry}"></label>
        <label class="field">Stop<input id="tkStop" type="number" inputmode="decimal" step="any" value="${p.stop}"></label>
      </div>
      <p class="muted" style="font-size:12px;margin:6px 0 0">Sized to risk ${acct.riskPct}% of ${T().money(acct.total, acct.ccy)}${sz.halved ? ", halved for the amber market" : ""}${sz.capped ? `, capped at ${acct.maxPosPct}% of the account` : ""}.${acct.linked ? "" : " Link Trading 212 for your real balance."}</p>
      <div id="tkSum"></div>
      <div class="tk-actions">
        <button class="btn primary" id="tkCopy"><i data-lucide="copy"></i> Copy ticket</button>
        <button class="btn" id="tkAlerts"><i data-lucide="bell-plus"></i> Alerts at stop &amp; targets</button>
        <button class="btn" data-close>Close</button>
      </div></div>`;
    $$("#tkQty,#tkLimit,#tkStop", d).forEach((x) => x.addEventListener("input", draw));
    draw();
    $("#tkCopy", d).addEventListener("click", async () => {
      try { if (!(await T().copyText(d._ticket))) throw new Error("blocked"); T().toast("Ticket copied"); }
      catch (e) { T().toast("Copy blocked by the browser: select the text instead"); }
    });
    $("#tkAlerts", d).addEventListener("click", () => {
      const lim = +$("#tkLimit", d).value, stop = +$("#tkStop", d).value;
      addAlert({ symbol: a.symbol, op: "<=", price: stop, note: "Stop hit" });
      addAlert({ symbol: a.symbol, op: ">=", price: +(lim + 2 * (lim - stop)).toFixed(4), note: "Target 1 (2R)" });
      addAlert({ symbol: a.symbol, op: ">=", price: +(lim + 3 * (lim - stop)).toFixed(4), note: "Target 2 (3R)" });
      T().toast("3 alerts added");
    });
  }

  /** The sizing line on the stock page (account currency, market light, caps). */
  async function sizeLine(a, el) {
    const td = T();
    if (!a.plan) return;
    try {
      const acct = await account();
      const sz = await size(a, acct, acct.riskPct, a.regime && a.regime.level);
      el.innerHTML = `Buy <b class="num">${td.shares(sz.qty)}</b> shares ≈ <b class="num">${td.money(sz.cost, acct.ccy)}</b> (${sz.posPct.toFixed(0)}% of the account). ` +
        `If the stop is hit you lose about <b class="num">${td.money(sz.risk, acct.ccy)}</b>` +
        `${sz.halved ? " · <span class='e-wait badge'>half size: amber market</span>" : ""}${sz.capped ? ` · capped at ${acct.maxPosPct}% of the account` : ""}.` +
        `<br><span class="muted" style="font-size:12px">Account ${td.money(acct.total, acct.ccy)}${acct.linked ? " (Trading 212)" : " (set in Portfolio → Risk settings)"} · risk ${acct.riskPct}% per trade${a.currency !== acct.ccy ? ` · 1 ${td.esc(a.currency)} = ${sz.rate.toFixed(4)} ${td.esc(acct.ccy)}` : ""}</span>`;
    } catch (e) { el.textContent = "Sizing unavailable: " + e.message; }
  }

  // ------------------------------------------------------------ alerts (checked while the dashboard is open)
  const alerts = () => T().store.get("alerts", []);
  const saveAlerts = (x) => { T().store.set("alerts", x); badge(); };
  function addAlert(x) {
    const list = alerts();
    list.push(Object.assign({ id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), created: Date.now(), triggered: null }, x));
    saveAlerts(list);
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission().catch(() => {});
    check();
  }
  function badge() {
    const n = alerts().filter((a) => !a.triggered).length, hit = alerts().filter((a) => a.triggered && !a.seen).length;
    const b = $("#bellCount");
    if (b) { b.textContent = hit ? "!" + hit : n || ""; b.hidden = !(n || hit); b.classList.toggle("hit", !!hit); }
    document.title = (hit ? "(" + hit + ") " : "") + document.title.replace(/^\(\d+\) /, "");
  }
  let checking = false;
  async function check() {
    const live = alerts().filter((a) => !a.triggered);
    if (!live.length || checking || document.hidden) return;
    checking = true;
    try {
      const syms = [...new Set(live.map((a) => a.symbol))];
      const q = await T().api("/api/quotes?symbols=" + encodeURIComponent(syms.join(",")));
      const px = Object.fromEntries(q.filter((r) => !r.error).map((r) => [r.symbol, r.price]));
      const list = alerts();
      let fired = 0;
      for (const a of list) {
        const p = px[a.symbol];
        if (a.triggered || p == null) continue;
        if ((a.op === ">=" && p >= a.price) || (a.op === "<=" && p <= a.price)) {
          a.triggered = Date.now(); a.hitPrice = p; fired++;
          const msg = `${a.symbol} ${a.op === ">=" ? "rose to" : "fell to"} ${p} (${a.note || "alert"} at ${a.price})`;
          T().toast("🔔 " + msg);
          if ("Notification" in window && Notification.permission === "granted") { try { new Notification("TraderDash alert", { body: msg }); } catch (e) { /* ignore */ } }
        }
      }
      if (fired) saveAlerts(list);
    } catch (e) { /* offline: try again next tick */ }
    finally { checking = false; }
  }
  setInterval(check, 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) check(); });

  function openAlerts(prefill) {
    const td = T(), d = dialog();
    const paint = () => {
      const list = alerts().sort((a, b) => (a.triggered ? 1 : 0) - (b.triggered ? 1 : 0) || b.created - a.created);
      d.innerHTML = `<div class="sheet-body">
        <div class="card-head"><h2 id="sheetTitle"><i data-lucide="bell"></i>Price alerts</h2><button class="rf" data-close aria-label="Close"><i data-lucide="x"></i></button></div>
        <p class="muted" style="margin-top:-6px;font-size:13px">Checked every minute while this dashboard is open (a browser notification fires if you allow it).</p>
        <form class="form-row" id="alForm">
          <label class="field">Symbol<input name="symbol" required value="${td.esc((prefill && prefill.symbol) || "")}" autocapitalize="characters"></label>
          <label class="field">When price is<select name="op"><option value=">=">at or above</option><option value="<=">at or below</option></select></label>
          <label class="field">Price<input name="price" type="number" step="any" inputmode="decimal" required value="${prefill && prefill.price != null ? prefill.price : ""}"></label>
          <button class="btn primary" type="submit">Add</button>
        </form>
        <ul class="al-list">${list.map((a) => `<li class="${a.triggered ? "hit" : ""}">
          <span><b>${td.esc(a.symbol)}</b> ${a.op === ">=" ? "≥" : "≤"} <span class="num">${a.price}</span> <span class="muted">${td.esc(a.note || "")}</span></span>
          <span>${a.triggered ? `<span class="badge e-now">hit ${new Date(a.triggered).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} at ${a.hitPrice}</span>` : `<span class="muted">waiting</span>`}
          <button class="rf" data-del="${a.id}" aria-label="Delete alert ${td.esc(a.symbol)} ${a.price}"><i data-lucide="trash-2"></i></button></span></li>`).join("") || `<li class="muted">No alerts yet.</li>`}</ul></div>`;
      $("#alForm", d).addEventListener("submit", (e) => {
        e.preventDefault();
        const f = new FormData(e.target);
        addAlert({ symbol: f.get("symbol").trim().toUpperCase(), op: f.get("op"), price: +f.get("price"), note: "custom" });
        prefill = null; paint();
      });
      $$("[data-del]", d).forEach((b) => b.addEventListener("click", () => { saveAlerts(alerts().filter((a) => a.id !== b.dataset.del)); paint(); }));
      const l = alerts(); l.forEach((a) => { if (a.triggered) a.seen = true; }); saveAlerts(l);
    };
    paint();
    if (!d.open) d.showModal();
  }

  // ------------------------------------------------------------ market mood light
  async function regime(el, compact) {
    const td = T();
    try {
      const r = await td.api("/api/regime");
      const icon = { green: "circle-check", amber: "triangle-alert", red: "octagon-alert" }[r.level] || "circle-help";
      if (td.isLT && td.isLT()) r.label = { green: "Market healthy: keep your monthly plan",
        amber: "Market mixed: nothing to change for long-term investing, keep your monthly plan",
        red: "Market weak: keep your monthly plan, but buy in parts: dips can go further than usual" }[r.level] || r.label;
      const okN = r.notes.filter((n) => n.ok).length;
      el.innerHTML = compact
        ? `<span class="mood-dot ${r.level}"></span><span class="s">Market</span><b>${r.level === "unknown" ? "–" : r.level}</b>`
        : `<div class="mood ${r.level}"><i data-lucide="${icon}"></i><div><b>${td.esc(r.label)}</b>
            <div class="mood-notes">${r.notes.map((n) => `<span class="${n.ok ? "up" : "down"}">${n.ok ? "✓" : "✕"} ${td.esc(n.text)}</span>`).join("")}</div></div>
            <span class="mood-score num" title="Healthy checks">${r.notes.length ? okN + "/" + r.notes.length : "–"}</span></div>`;
      return r;
    } catch (e) { el.innerHTML = ""; return null; }
  }

  // ------------------------------------------------------------ signal backtest
  async function backtest(sym, el) {
    const td = T();
    el.innerHTML = `<p class="muted" style="font-size:13px">Backtesting these rules on ${td.esc(sym)}…</p>`;
    try {
      const b = await td.api("/api/backtest?symbol=" + encodeURIComponent(sym));
      if (!b.n) { el.innerHTML = `<p class="muted" style="font-size:13px">Backtest: no buy signals for ${td.esc(sym)} in ${b.years} years.</p>`; return; }
      const good = b.expectancy > 0;
      el.innerHTML = `<div class="bt">
        <div class="bt-head"><b>How this signal did on ${td.esc(sym)}</b><span class="muted">last ${b.years} years · ${b.n} trades</span></div>
        <div class="bt-grid">
          <div><span>Hit 2R target</span><b class="num">${b.hitTarget}%</b></div>
          <div><span>Win rate</span><b class="num">${b.winRate}%</b></div>
          <div><span>Avg per trade</span><b class="num ${good ? "up" : "down"}">${b.expectancy > 0 ? "+" : ""}${b.expectancy}R</b></div>
          <div><span>Median hold</span><b class="num">${b.medianDays}d</b></div>
          ${b.buyHold != null ? `<div><span>Just holding it</span><b class="num ${b.buyHold >= 0 ? "up" : "down"}">${td.pct(b.buyHold, 0)}</b></div>` : ""}
        </div>
        ${b.buyHold != null ? `<p class="muted" style="font-size:12px;margin:4px 0 0">The signal was in the market ${b.inMarket}% of the time. Compare its total (${b.equity[b.equity.length - 1]}R, about ${b.equity[b.equity.length - 1]}% at 1% risk a trade) with simply holding the stock.</p>` : ""}
        <div class="bt-curve" title="Running total in R (1R = the risk of one trade)">${td.sparkline([0].concat(b.equity), 320, 46)}<span class="muted">cumulative ${b.equity[b.equity.length - 1]}R</span></div>
        <details><summary>Last trades</summary><table class="kvt"><tbody>${b.trades.map((t) => `<tr><td>${t.date}</td><td>${td.esc(t.setup)}</td><td class="r num ${t.R >= 0 ? "up" : "down"}">${t.R > 0 ? "+" : ""}${t.R}R</td><td class="r muted">${t.days}d · ${td.esc(t.outcome)}</td></tr>`).join("")}</tbody></table></details>
        <p class="muted" style="font-size:11.5px;margin:6px 0 0">${td.esc(b.note)} 1R = the amount risked. Past results don't guarantee future ones.</p></div>`;
    } catch (e) { el.innerHTML = `<p class="muted" style="font-size:13px">Backtest unavailable: ${td.esc(e.message)}</p>`; }
  }

  // ------------------------------------------------------------ risk panel + protective stops
  /** Adds acct-currency values, stops and risk to positions; returns the panel numbers. */
  async function risk(positions, acct, sectorOf) {
    const rates = {};
    for (const c of new Set(positions.map((p) => p.q.currency || p.currency).filter(Boolean))) {
      try { rates[c] = await fx(c, acct.ccy); } catch (e) { rates[c] = null; }
    }
    const pend = acct.pending || [];
    let heat = 0, unprot = 0;
    const sectors = {};
    for (const p of positions) {
      const ccy = p.q.currency || p.currency, rate = rates[ccy] ?? 1;
      p.valueAcct = (p.qty || 0) * (p.price || 0) * rate;
      const stopOrder = pend.filter((o) => o.symbol === p.symbol && o.side === "SELL" && /STOP/.test(o.type) && o.stopPrice)
        .sort((a, b) => b.stopPrice - a.stopPrice)[0];
      p.stopOrder = stopOrder ? stopOrder.stopPrice : null;
      p.suggestedStop = p.q.chandelier || null;
      const stop = p.stopOrder || p.suggestedStop;
      p.stopBroken = !!(stop && p.price <= stop);
      p.riskAcct = stop && p.price > stop ? (p.qty || 0) * (p.price - stop) * rate : null;
      if (p.riskAcct) heat += p.riskAcct;
      p.unprotected = p.source === "Trading 212" && acct.pending != null && !stopOrder;
      if (p.unprotected) unprot++;
      const sec = sectorOf(p.symbol);
      sectors[sec] = (sectors[sec] || 0) + p.valueAcct;
    }
    const invested = positions.reduce((s, p) => s + (p.valueAcct || 0), 0);
    const largest = positions.slice().sort((a, b) => (b.valueAcct || 0) - (a.valueAcct || 0))[0];
    const topSector = Object.entries(sectors).sort((a, b) => b[1] - a[1])[0];
    const broken = positions.filter((p) => p.stopBroken).map((p) => p.symbol);
    return { broken, heat, heatPct: 100 * heat / acct.total, unprot, invested, cashPct: acct.free != null ? 100 * acct.free / acct.total : null,
      largest, largestPct: largest ? 100 * largest.valueAcct / acct.total : 0, topSector, topSectorPct: topSector ? 100 * topSector[1] / acct.total : 0, pendingKnown: acct.pending != null };
  }

  function riskPanel(el, R, acct) {
    const td = T();
    const row = (label, value, ok, hint) => `<li class="${ok ? "" : "no"}"><span>${label}</span><b class="num">${value}</b>${hint ? `<small>${hint}</small>` : ""}</li>`;
    el.innerHTML = `<ul class="risk-list">
      ${row("Open risk if every stop hits", `${td.money(R.heat, acct.ccy)} · ${R.heatPct.toFixed(1)}%`, R.heatPct <= acct.maxHeatPct, `limit ${acct.maxHeatPct}% · uses your Trading 212 stops, else the suggested trailing stop`)}
      ${R.broken && R.broken.length ? row("Already below their stop", R.broken.map(td.esc).join(", "), false, "the stop was hit: these aren't counted in the open risk above. Sell, or decide on a new lower stop") : ""}
      ${R.pendingKnown ? row("Positions without a stop order", R.unprot, R.unprot === 0, R.unprot ? "set a Stop order in Trading 212 for each" : "every position is protected") : row("Stop orders", "unknown", false, "your API key can't read orders: enable the 'orders: read' permission")}
      ${row("Largest position", R.largest ? `${td.esc(R.largest.symbol)} · ${R.largestPct.toFixed(0)}%` : "–", R.largestPct <= acct.maxPosPct, `limit ${acct.maxPosPct}%`)}
      ${row("Biggest sector", R.topSector ? `${td.esc(R.topSector[0])} · ${R.topSectorPct.toFixed(0)}%` : "–", R.topSectorPct <= 40, "over 40% in one sector moves as one bet")}
      ${R.cashPct != null ? row("Cash", R.cashPct.toFixed(0) + "%", R.cashPct >= 5, "keep some dry powder") : ""}
    </ul>`;
  }

  // ------------------------------------------------------------ trade journal
  async function journal(el) {
    const td = T();
    el.innerHTML = td.skeleton(4);
    try {
      const j = await td.api("/api/t212/journal");
      const s = j.stats;
      if (!s.n) { el.innerHTML = `<p class="muted">No closed trades in your Trading 212 history yet${j.complete ? "" : " (older orders still loading: refresh in a minute)"}.</p>`; return; }
      const tile = (k, v, c) => `<div class="perf-tile"><div class="k">${k}</div><div class="v num ${c || ""}">${v}</div></div>`;
      const maxAbs = Math.max(...j.months.map((m) => Math.abs(m.sumPct)), 1);
      el.innerHTML = `<div class="ret-grid">
          ${tile("Closed trades", s.n)}${tile("Win rate", s.winRate + "%", s.winRate >= 50 ? "up" : "down")}
          ${tile("Avg win", s.avgWin != null ? "+" + s.avgWin + "%" : "–", "up")}${tile("Avg loss", s.avgLoss != null ? s.avgLoss + "%" : "–", "down")}
          ${tile("Per trade", (s.expectancy > 0 ? "+" : "") + s.expectancy + "%", s.expectancy >= 0 ? "up" : "down")}${tile("Profit factor", s.profitFactor ?? "–")}
          ${tile("Avg hold", s.avgDays + "d")}</div>
        <div class="months" role="img" aria-label="Sum of trade returns by month">${j.months.slice(-12).map((m) => `<div title="${m.month}: ${m.n} trades, ${m.sumPct.toFixed(1)}%"><i style="height:${(40 * Math.abs(m.sumPct) / maxAbs).toFixed(0)}px" class="${m.sumPct >= 0 ? "pos" : "neg"}"></i><span>${m.month.slice(5)}</span></div>`).join("")}</div>
        <div class="table-wrap"><table><thead><tr><th scope="col">Stock</th><th scope="col">Opened → closed</th><th class="r" scope="col">Qty</th><th class="r" scope="col">Entry → exit</th><th class="r" scope="col">Result</th></tr></thead><tbody>
          ${j.trades.slice(0, 25).map((t) => `<tr style="cursor:default"><td><a class="sym" href="#/stock/${encodeURIComponent(t.symbol)}">${td.esc(t.symbol)}</a></td><td class="muted">${t.opened} → ${t.closed} · ${t.days}d</td><td class="r num">${td.shares(t.qty)}</td><td class="r num">${td.fmt(t.entry, 2)} → ${td.fmt(t.exit, 2)}</td><td class="r num ${t.pct >= 0 ? "up" : "down"}">${t.pct > 0 ? "+" : ""}${t.pct}%<span class="nm">${t.pnl > 0 ? "+" : ""}${td.fmt(t.pnl, 2)}</span></td></tr>`).join("")}
        </tbody></table></div>
        <p class="muted" style="font-size:12px">${td.esc(j.note)}${j.complete ? "" : " Older orders are still loading."}</p>`;
    } catch (e) { el.innerHTML = `<p class="muted">Journal unavailable: ${td.esc(e.message)}</p>`; }
  }


  // ------------------------------------------------------------ use on iPhone (QR code)
  async function openPhone() {
    const td = T(), d = dialog();
    let info;
    const head = `<div class="card-head"><h2 id="sheetTitle"><i data-lucide="smartphone"></i>Use on iPhone</h2><button class="rf" data-close aria-label="Close"><i data-lucide="x"></i></button></div>`;
    const res = await fetch("/api/phone").catch(() => null);
    if (!res || res.status === 404) {
      d.innerHTML = `<div class="sheet-body">${head}
        <p><b>Your dashboard is still running the old version.</b></p>
        <ol class="steps" style="font-size:14px;gap:6px"><li>Close the black window (the dashboard server).</li>
          <li>Open the <b>new</b> <code>dashboard</code> folder and double-click <b>start-phone.bat</b> (Mac: <b>start-phone.command</b>).</li>
          <li>Come back to <b>http://127.0.0.1:8212</b> and click <b>Use on iPhone</b> again.</li></ol></div>`;
      d.showModal(); return;
    }
    if (!res.ok) {
      const onPhone = /iPhone|iPad|Android/i.test(navigator.userAgent);
      d.innerHTML = `<div class="sheet-body">${head}
        ${onPhone ? `<p>You're already on your phone. 👍 To keep it on your Home Screen: tap <b>Share</b> <i data-lucide="share"></i> → <b>Add to Home Screen</b>.</p>`
          : `<p>This page was opened through the network link. On the computer running the dashboard, open <b><a href="http://127.0.0.1:${location.port || 8212}/">http://127.0.0.1:${location.port || 8212}</a></b> and click <b>Use on iPhone</b> again.</p>`}</div>`;
      d.showModal(); return;
    }
    info = await res.json();
    let qr = "";
    if (info.url && window.qrcode) {
      const q = window.qrcode(0, "M"); q.addData(info.url); q.make();
      qr = q.createSvgTag({ cellSize: 6, margin: 3, scalable: true });
    }
    let awayQr = "";
    if (info.awayUrl && window.qrcode) {
      const q2 = window.qrcode(0, "M"); q2.addData(info.awayUrl); q2.make();
      awayQr = q2.createSvgTag({ cellSize: 5, margin: 3, scalable: true });
    }
    d.innerHTML = `<div class="sheet-body">
      <div class="card-head"><h2 id="sheetTitle"><i data-lucide="smartphone"></i>Use on iPhone</h2><button class="rf" data-close aria-label="Close"><i data-lucide="x"></i></button></div>
      ${info.enabled ? `
        <div class="phone-grid"><div class="qr">${qr}</div>
        <ol class="steps" style="font-size:14px;gap:8px">
          <li>Make sure the iPhone is on the <b>same Wi-Fi</b> as this computer.</li>
          <li>Open the iPhone <b>Camera</b>, point it at this code and tap the link (opens in Safari).</li>
          <li>In Safari tap <b>Share</b> → <b>Add to Home Screen</b> → <b>Add</b>. TraderDash now opens like an app.</li>
          <li>Keep this computer on with the dashboard running while you use it.</li>
        </ol></div>
        <p class="muted" style="font-size:12px">Link: <code style="word-break:break-all">${td.esc(info.url)}</code><br>It contains a secret key: don't share it. To log every phone out, restart with <code>--phone --new-key</code>.</p>
        ${info.awayUrl ? `<h3 class="h3" style="margin-top:14px">Away from home (Tailscale)</h3>
          <div class="phone-grid"><div class="qr">${awayQr}</div><ol class="steps" style="font-size:14px;gap:8px">
            <li>Tailscale is running on this computer (${td.esc(info.tailscaleIp)}).</li>
            <li>On the iPhone, install <b>Tailscale</b> from the App Store and sign in with the <b>same account</b>.</li>
            <li>Scan this code: it works on 4G and any Wi-Fi, and only your own devices can reach it.</li>
            <li>Add it to the Home Screen too (Share → Add to Home Screen), e.g. as "TraderDash away".</li></ol></div>`
        : `<p class="muted" style="font-size:12.5px"><b>Away from home?</b> Install the free <b>Tailscale</b> app (tailscale.com) on this computer and on the iPhone, sign in to both with the same account, then open this window again: a second QR code appears that works on 4G and any Wi-Fi.</p>`}`
      : `<p>Phone mode is off. Stop the dashboard (Ctrl+C in its window) and start it again with phone mode:</p>
        <ul class="steps" style="font-size:14px"><li><b>Windows:</b> double-click <code>dashboard\\start-phone.bat</code>, or run <code>python dashboard/server.py --phone</code></li>
        <li><b>Mac:</b> double-click <code>dashboard/start-phone.command</code>, or run <code>python3 dashboard/server.py --phone</code></li></ul>
        <p class="muted" style="font-size:13px">If Windows asks whether Python may use the network, tick <b>Private networks</b> and click Allow. Then come back here and click <b>Use on iPhone</b> again for the QR code.</p>`}
    </div>`;
    if (!d.open) d.showModal();
  }
  document.addEventListener("click", (e) => { if (e.target.closest("#phoneBtn")) openPhone(); });

  window.Trade = { openPhone, openTicket, sizeLine, openAlerts, addAlert, badge, check, regime, backtest, risk, riskPanel, journal, t212Ticker, account };
  document.addEventListener("DOMContentLoaded", () => { badge(); check(); });
})();
