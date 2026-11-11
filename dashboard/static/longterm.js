/* Long-term investing mode for Trader Dashboard: quality score, buy zone, buy-and-hold
   backtests, monthly plan, diversification with ETF look-through, dividends.
   Uses helpers app.js shares on window.TD. Nothing here places an order. */
(function () {
  "use strict";
  const T = () => window.TD;
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const cache = {};

  const mode = () => (T().settings().mode || "lt");
  const zoneCls = (z) => ({ "Accumulate+": "e-now", Accumulate: "e-watch", Stretched: "e-wait", Speculative: "e-avoid" }[z] || "e-none");
  // plain words for the labels (the rules keep their internal names)
  const LABELS = { "Accumulate+": "Good time to add", Accumulate: "Keep buying as planned", Stretched: "Pricey: buy small", Speculative: "Speculative",
    Hold: "Hold", Trim: "Trim", "Review thesis": "Review it", "Theme full": "Theme full" };
  const zoneLabel = (z) => LABELS[z] || z;
  const zoneBadge = (z) => (z ? `<span class="badge ${zoneCls(z)}" title="${T().esc(z)}">${T().esc(zoneLabel(z))}</span>` : "");
  const bandCls = (b) => (/Core|Strong/.test(b) ? "b-strongbuy" : /Good|Solid/.test(b) ? "b-buy" : /Fair|Mixed/.test(b) ? "b-hold" : "b-sell");
  const bandBadge = (b) => (b ? `<span class="badge ${bandCls(b)}">${T().esc(b)}</span>` : "");

  async function profiles(symbols, fresh) {
    const need = symbols.filter((s) => fresh || !cache[s]);
    for (let i = 0; i < need.length; i += 40) {
      const chunk = need.slice(i, i + 40);
      const rows = await T().api("/api/lt?symbols=" + encodeURIComponent(chunk.join(",")));
      rows.forEach((r) => { cache[r.symbol] = r; });
    }
    return symbols.map((s) => cache[s]).filter((r) => r && !r.error);
  }
  async function profile(sym) {
    if (cache[sym]) return cache[sym];
    return (cache[sym] = await T().api("/api/lt?symbol=" + encodeURIComponent(sym)));
  }


  // ------------------------------------------------------------ entry check: buy now, in parts, or wait?
  const entryCache = {};
  async function entry(sym, fresh) {
    if (!fresh && entryCache[sym]) return entryCache[sym];
    return (entryCache[sym] = await T().api("/api/ltentry?symbol=" + encodeURIComponent(sym)));
  }
  function ladderHtml(e, amount, ccy) {
    const td = T();
    return `<table class="entry-ladder"><tbody>${e.ladder.map((l) => `<tr><td>${td.esc(l.label)}${l.price != null ? ` <b class="num">${td.priceStr(l.price, e.currency)}</b> <span class="muted">(${((l.price / e.price - 1) * 100).toFixed(0)}%)</span>` : ""}</td>
      <td class="r num"><b>${amount ? td.money(amount * l.share, ccy) : Math.round(l.share * 100) + "%"}</b></td></tr>`).join("")}</tbody></table>`;
  }
  async function entryCard(a, el, held) {
    const td = T();
    el.innerHTML = td.skeleton(5);
    let e;
    try { e = await entry(a.symbol, el.dataset.fresh); } catch (err) { el.innerHTML = `<p class="muted">Entry check unavailable: ${td.esc(err.message)}</p>`; return; }
    delete el.dataset.fresh;
    if (!el.isConnected) return;
    const v = e.verdict, s = e.same, any = e.any;
    const mine = held && held.avgPrice && held.qty ? held : null;
    const down = mine && e.price ? 100 * (e.price / mine.avgPrice - 1) : null;
    el.innerHTML = `<div class="entry-head ${v.tone}"><b>${td.esc(v.title)}</b><span>${td.esc(v.text)}</span></div>
      <p class="entry-state"><span class="badge ${e.tone === "down" ? "e-avoid" : e.tone === "up" ? "e-now" : "e-wait"}">${td.esc(e.title)}</span> ${td.esc(e.why)}
        ${e.fromHigh3m < -3 ? ` It is <b class="down">${td.pct(e.fromHigh3m)}</b> from its 3-month high.` : ""}</p>
      ${v.notes.map((n) => `<p class="entry-note">${td.esc(n)}</p>`).join("")}
      <h3 class="h3">Buy in parts</h3>
      ${ladderHtml(e, 0, "")}
      <p class="muted" style="font-size:12.5px;margin:4px 0 0">The lower prices are how far ${td.esc(e.symbol)} typically fell further within 3 months after days like today. Set them as <b>limit orders</b> or price alerts. They may never fill: that's fine, it means you bought the first part at a good price.
        ${e.stopAdding ? ` <b>Stop adding</b> if it closes below ${td.priceStr(e.stopAdding, e.currency)} or its long-term score falls under 45: then something bigger is wrong.` : ""}</p>
      ${s || any ? `<h3 class="h3">What usually happens after buying</h3><div class="ret-grid entry-stats">
        ${s ? `<div class="perf-tile"><div class="k">After days like today</div><div class="v num down">${td.pct(s.typicalDip, 1)}</div><div class="b">typical further dip within 3 months · 1 in 5 times ${td.pct(s.deepDip, 1)} or more</div></div>` : ""}
        ${s && s.up12m != null ? `<div class="perf-tile"><div class="k">A year later</div><div class="v num ${td.cls(s.median12m)}">higher ${s.up12m}% of the time</div><div class="b">typical result ${td.pct(s.median12m, 0)} · from ${s.episodes} separate past drops</div></div>`
          : s ? `<div class="perf-tile"><div class="k">A year later</div><div class="v num muted">too few cases</div><div class="b">only ${s.episodes} separate past episodes like today</div></div>` : ""}
        ${any ? `<div class="perf-tile"><div class="k">After any day</div><div class="v num down">${td.pct(any.typicalDip)}</div><div class="b">typical dip within 3 months, higher a year later ${any.up12m ?? "–"}% of the time</div></div>` : ""}</div>
        <p class="muted" style="font-size:12px;margin:6px 0 0">This is only ${td.esc(e.symbol)}'s own past, which includes its best years. It does not repeat by itself.</p>
        <p class="muted" style="font-size:12.5px;margin:6px 0 0">So a drop right after you buy is normal: over ${e.years} years, half of all buys in ${td.esc(e.symbol)} saw the price fall at least ${Math.abs(any ? any.typicalDip : s.typicalDip).toFixed(1)}% within 3 months. What matters for a long-term investor is the business and the price you pay on average.</p>` : ""}
      ${mine && down < -3 ? `<div class="entry-own"><b>You own it at ${td.priceStr(mine.avgPrice, e.currency)} (${td.pct(down)}).</b> ${e.score != null && e.score >= 60 && e.zone !== "Speculative"
        ? "The long-term score is still good, so adding at the lower levels above brings your average price down. Keep the holding under about 10% of your portfolio."
        : "The long-term score is weak: check the reasons before adding more, don't average down just to get even."}</div>` : ""}
      <p class="muted" style="font-size:11.5px;margin:8px 0 0">Based on ${e.years} years of daily prices with dividends. Past patterns, not a forecast or advice.</p>`;
  }

  // ------------------------------------------------------------ stock page card
  async function stockCard(a, el) {
    const td = T();
    el.innerHTML = td.skeleton(6);
    let p;
    try { p = await profile(a.symbol); } catch (e) { el.innerHTML = `<p class="muted">Long-term view unavailable: ${td.esc(e.message)}</p>`; return null; }
    const g = p.groups || {}, h = p.history || {};
    const bar = (k) => g[k] == null ? "" : `<div class="mbar"><span>${k}</span><i><b style="width:${g[k]}%"></b></i><em class="num">${g[k]}</em></div>`;
    el.innerHTML = `
      <div class="lt-top">${window.TChart.ring(p.score ?? 0, 72, "Long-term score")}
        <div><div style="display:flex;gap:6px;flex-wrap:wrap">${bandBadge(p.band)} ${zoneBadge(p.zone)}</div>
          <p class="sec" style="margin:6px 0 0;font-size:13.5px">${td.esc(p.zoneWhy)}</p></div></div>
      <ul class="lt-reasons">${p.zoneReasons.map((x) => `<li>${td.esc(x)}</li>`).join("")}</ul>
      <div style="margin-top:10px">${["Quality", "Growth", "Valuation", "Balance sheet", "Dividend", "Trend"].map(bar).join("")}</div>
      <details style="margin-top:8px"><summary>What the score is made of</summary>
        <ul class="reasons" style="margin-top:8px">${p.why.map((w) => `<li class="${w.ok ? "" : "no"}"><span><b>${td.esc(w.group)}</b> · ${td.esc(w.text)} <span class="muted">(${w.score}/100)</span></span></li>`).join("")}</ul>
        ${p.fundamentals ? `<p class="muted" style="font-size:12px">Company figures from ${td.esc(p.figuresFrom || "Nasdaq.com")}${p.industry ? " · " + td.esc(p.industry) : ""}${p.country ? " · " + td.esc(p.country) : ""}.</p>`
          : `<p class="muted" style="font-size:12px">No company figures for this listing (ETF, or non-US without a Financial Modeling Prep key): scored on its track record only. Add a free key on the Portfolio page → Data connections.</p>`}</details>
      <div class="kv" style="margin-top:12px">
        <div>Return a year, 3y<b class="num ${td.cls(h.cagr3)}">${td.pct(h.cagr3, 1)}</b></div><div>5y<b class="num ${td.cls(h.cagr5)}">${td.pct(h.cagr5, 1)}</b></div>
        <div>10y<b class="num ${td.cls(h.cagr10)}">${td.pct(h.cagr10, 1)}</b></div><div>Worst fall (3y)<b class="num down">${td.pct(h.maxdd3, 1)}</b></div></div>
      <p class="muted" style="font-size:11.5px;margin:6px 0 0">Returns include dividends. Score: quality 25%, growth 20%, valuation 20%, balance sheet 15%, trend 15%, dividend 5%.</p>
      <div class="tk-actions"><button class="btn primary" type="button" id="ltBuy"><i data-lucide="hand-coins"></i> Buy an amount</button>
        <button class="btn" type="button" id="ltPlan"><i data-lucide="calendar-plus"></i> Add to monthly plan</button></div>`;
    $("#ltBuy", el).addEventListener("click", () => openBuy(a, p));
    $("#ltPlan", el).addEventListener("click", () => {
      const t = td.store.get("targets", {});
      if (t[a.symbol] == null) { t[a.symbol] = 5; td.store.set("targets", t); }
      td.toast(a.symbol + " added to your monthly plan (5% target, edit it in Portfolio)");
    });
    return p;
  }

  async function backtestCard(sym, el) {
    const td = T();
    el.innerHTML = `<p class="muted" style="font-size:13px">Loading 10 years of history…</p>`;
    try {
      const b = await td.api("/api/ltbacktest?symbol=" + encodeURIComponent(sym));
      const bn = b.benchmark === "SPY" ? "S&P 500" : b.benchmark;
      const yrs = ["1", "3", "5", "10"].filter((y) => b.me.lump[y]);
      const d = b.me.dca, db = b.bench && b.bench.dca;
      el.innerHTML = `<div class="bt">
        <div class="bt-head"><b>If you had bought and held ${td.esc(sym)}</b><span class="muted">vs ${td.esc(bn)}, dividends reinvested</span></div>
        <div class="table-wrap"><table class="kvt"><thead><tr><th scope="col">Held for</th><th class="r" scope="col">Total</th><th class="r" scope="col">A year</th><th class="r" scope="col">Worst fall</th><th class="r" scope="col">${td.esc(bn)} a year</th></tr></thead><tbody>
          ${yrs.map((y) => { const m = b.me.lump[y], x = (b.bench.lump || {})[y] || {}; return `<tr><td>${y} year${y === "1" ? "" : "s"}</td><td class="r num ${td.cls(m.total)}">${td.pct(m.total, 0)}</td><td class="r num ${td.cls(m.cagr)}">${td.pct(m.cagr, 1)}</td><td class="r num down">${td.pct(m.maxdd, 0)}</td><td class="r num muted">${td.pct(x.cagr, 1)}</td></tr>`; }).join("")}
        </tbody></table></div>
        ${d ? `<div class="dca"><b>Investing 100 every month for 5 years</b>
          <div class="bt-grid"><div><span>Put in</span><b class="num">${td.fmt(d.invested, 0)}</b></div><div><span>Worth now</span><b class="num ${td.cls(d.value - d.invested)}">${td.fmt(d.value, 0)}</b></div>
          <div><span>Return a year</span><b class="num ${td.cls(d.irr)}">${td.pct(d.irr, 1)}</b></div><div><span>${td.esc(bn)}</span><b class="num muted">${db ? td.pct(db.irr, 1) : "–"}</b></div></div>
          <div class="bt-curve">${td.sparkline(d.path.map((x) => x[2]), 320, 46)}<span class="muted">${d.positiveYears}% of 12-month periods ended up</span></div></div>` : ""}
        <p class="muted" style="font-size:11.5px;margin:6px 0 0">${td.esc(b.note)} Past returns don't guarantee future ones.</p></div>`;
    } catch (e) { el.innerHTML = `<p class="muted" style="font-size:13px">History unavailable: ${td.esc(e.message)}</p>`; }
  }

  // ------------------------------------------------------------ buy an amount (prepared, never sent)
  async function openBuy(a, p, amount) {
    const td = T(), Tr = window.Trade;
    const d = document.querySelector("dialog.sheet") || (Tr && Tr._dialog && Tr._dialog());
    const acct = Tr ? await Tr.account() : { ccy: "USD", total: td.settings().account, free: null };
    let rate = 1;
    try { rate = (await td.api(`/api/fx?from=${encodeURIComponent(a.currency || p.currency)}&to=${encodeURIComponent(acct.ccy)}`)).rate || 1; } catch (e) { /* same currency */ }
    const amt0 = amount || Math.round((td.settings().monthly || 200) / 5);
    const dlg = d || document.body.appendChild(Object.assign(document.createElement("dialog"), { className: "sheet" }));
    const draw = () => {
      const amt = +$("#byAmt", dlg).value || 0;
      const px = a.price * rate;
      const qty = px ? Math.floor(amt / px * 1e4) / 1e4 : 0;
      const fee = a.currency && a.currency !== acct.ccy ? amt * 0.0015 : 0;
      const split = dlg._entry && dlg._entry.ladder.length > 1;
      $("#bySum", dlg).innerHTML = `<div class="tk-grid">
          <div><span>Amount</span><b class="num">${td.money(amt, acct.ccy)}</b></div>
          <div><span>About</span><b class="num">${td.shares(qty)} shares</b></div>
          <div><span>Price</span><b class="num">${td.priceStr(a.price, a.currency)}</b></div>
          <div><span>FX fee (0.15%)</span><b class="num">${fee ? td.money(fee, acct.ccy) : "none"}</b></div></div>
        ${acct.free != null && amt > acct.free ? `<ul class="tk-warn"><li>More than your free cash (${td.money(acct.free, acct.ccy)}).</li></ul>` : ""}
        ${dlg._entry && dlg._entry.ladder.length > 1 ? `<h3 class="h3">${td.esc(dlg._entry.verdict.title)}: split it</h3>${ladderHtml(dlg._entry, amt, acct.ccy)}
          <p class="muted" style="font-size:12px;margin:2px 0 0">Buy the first part now; set limit orders for the rest at those prices.</p>` : ""}
        ${p.zone === "Stretched" ? `<ul class="tk-warn"><li>Stretched: consider a smaller amount this month and the rest later.</li></ul>` : ""}
        ${p.zone === "Speculative" ? `<ul class="tk-warn"><li>Speculative: keep it a small part of the portfolio.</li></ul>` : ""}
        <h3 class="h3">In Trading 212</h3>
        <ol class="steps tk-steps"><li>Search <b>${td.esc(a.symbol)}</b> → <b>Buy</b> → switch the amount to <b>Value</b>.</li>
          <li>Enter <b class="num">${td.money(split ? amt * dlg._entry.ladder[0].share : amt, acct.ccy)}</b>${split ? " (the first part)" : ""} → review → confirm. (A market order fills at the next price; ${td.esc(a.symbol)} trades in ${td.esc(a.currency || "")}.)</li>
          <li>Regular buying? Put it in a <b>Pie</b> with <b>AutoInvest</b> monthly so it happens automatically.</li></ol>`;
      dlg._ticket = `BUY ${a.symbol} by value: ${td.money(amt, acct.ccy)} (~${td.shares(qty)} shares at ${td.priceStr(a.price, a.currency)})`;
    };
    dlg.innerHTML = `<div class="sheet-body">
      <div class="card-head"><h2 id="sheetTitle"><i data-lucide="hand-coins"></i>Buy ${td.esc(a.symbol)} by amount</h2><button class="rf" data-close aria-label="Close"><i data-lucide="x"></i></button></div>
      <p class="muted" style="margin-top:-6px;font-size:13px">Long-term investing: buy a fixed amount (fractional shares), no stop or target. Prepared for you to enter in Trading 212.</p>
      <label class="field" style="max-width:220px">Amount (${td.esc(acct.ccy)})<input id="byAmt" type="number" inputmode="decimal" min="1" step="1" value="${amt0}"></label>
      <div id="bySum"></div>
      <div class="tk-actions"><button class="btn primary" id="byCopy" type="button"><i data-lucide="copy"></i> Copy</button><button class="btn" data-close type="button">Close</button></div></div>`;
    if (!dlg._wired) { dlg.addEventListener("click", (e) => { if (e.target === dlg || e.target.closest("[data-close]")) dlg.close(); }); dlg._wired = true; }
    $("#byAmt", dlg).addEventListener("input", draw);
    dlg._entry = null;
    entry(a.symbol).then((e) => { dlg._entry = e; if (dlg.open) draw(); }).catch(() => {});
    $("#byCopy", dlg).addEventListener("click", async () => { try { if (!(await td.copyText(dlg._ticket))) throw new Error("blocked"); td.toast("Copied"); } catch (e) { td.toast("Copy blocked: select the text instead"); } });
    draw();
    if (!dlg.open) dlg.showModal();
  }

  // ------------------------------------------------------------ quality on sale (replaces Strong Buys)
  function qualityCard(p) {
    const td = T();
    return `<div class="card sigcard">
      <div class="cand-top">${td.logo(p.symbol, 34)}<div style="flex:1;min-width:0"><a class="sym" style="font-size:17px" href="#/stock/${encodeURIComponent(p.symbol)}">${td.esc(p.symbol)}</a><span class="nm">${td.esc(p.name || "")}</span></div>${window.TChart.ring(p.score ?? 0, 58, "Long-term score")}</div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;margin:10px 0 6px">${bandBadge(p.band)} ${zoneBadge(p.zone)}</div>
      <p class="sec" style="font-size:13px;margin:0 0 8px">${td.esc(p.zoneReasons.slice(0, 2).join(" · "))}</p>
      <div class="kv"><div>Price<b class="num">${td.priceStr(p.price, p.currency)}</b></div><div>5y a year<b class="num ${td.cls(p.history.cagr5)}">${td.pct(p.history.cagr5, 1)}</b></div><div>From high<b class="num ${td.cls(p.fromATH)}">${td.pct(p.fromATH, 0)}</b></div></div>
      <div class="sig-actions"><a class="btn sm" href="#/stock/${encodeURIComponent(p.symbol)}"><i data-lucide="line-chart"></i> Analysis</a></div></div>`;
  }

  async function qualityPage(view, done) {
    const td = T();
    view.innerHTML = `<div class="card-head" style="margin-bottom:4px"><h1 style="margin:0">Quality on sale</h1>${td.rf("quality")}</div>
      <p class="sub">Strong businesses and funds for long-term investing, and which of them are cheaper than usual right now. Scores use quality, growth, valuation, balance sheet, dividends and trend.</p>
      <div class="toolbar"><div class="seg" id="qSeg"><button data-g="sale" class="on">On sale now</button><button data-g="core">Core quality</button><button data-g="etf">Best ETFs</button><button data-g="all">All scored</button></div></div>
      <p class="muted" id="qNote" style="font-size:13px">Scoring about 100 stocks and ETFs. The first time takes about a minute; then it's cached for hours.</p>
      <div class="cand-grid" id="qCards">${[1, 2, 3].map(() => `<div class="card">${td.skeleton(6)}</div>`).join("")}</div>`;
    const u = await td.api("/api/universe");
    const stocks = [...new Set(Object.values(u.stocks).flat())], etfs = [...new Set(Object.values(u.etfs).flat())];
    let all = [];
    const load = async (fresh) => { all = await profiles(stocks.concat(etfs), fresh); };
    const paint = (g) => {
      $$("#qSeg button").forEach((b) => b.classList.toggle("on", b.dataset.g === g));
      const isEtf = (p) => etfs.includes(p.symbol);
      const sets = {
        sale: all.filter((p) => p.zone === "Accumulate+"),
        core: all.filter((p) => !isEtf(p) && p.score >= 75),
        etf: all.filter(isEtf),
        all,
      };
      const list = sets[g].slice().sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
      $("#qCards").innerHTML = list.map(qualityCard).join("") || `<div class="card empty">Nothing on sale right now: good businesses are near their usual prices. Keep your monthly plan.</div>`;
      $("#qNote").textContent = `${all.length} scored · ${sets.sale.length} quality names on sale · ${all.filter((p) => p.score >= 75).length} score 75+`;
    };
    td.RF().quality = async () => { await load(true); paint($("#qSeg button.on").dataset.g); };
    $$("#qSeg button").forEach((b) => b.addEventListener("click", () => paint(b.dataset.g)));
    try { await load(false); } catch (e) { $("#qCards").innerHTML = `<p class="error">${td.esc(e.message)}</p>`; return; }
    if (!$("#qCards")) return;
    paint("sale"); td.stamp("quality");
    if (done) done(all);
  }

  // ------------------------------------------------------------ portfolio: verdicts, plan, diversification, dividends
  function verdict(pos, weight, target, p, isFund, theme) {
    if (p && p.fundamentals && p.score != null && p.score < 45) return { v: "Review thesis", why: "Long-term score " + p.score + " (speculative): check the story still holds" };
    if (p && p.groups && p.groups.Growth != null && p.fundamentals && p.groups.Growth < 20) return { v: "Review thesis", why: "Growth has stalled" };
    if (!isFund && weight > 20) return { v: "Trim", why: `${weight.toFixed(0)}% of the portfolio in one company` };
    if (target && weight > target * 1.5) return { v: "Trim", why: `${weight.toFixed(0)}% vs your ${target}% target` };
    if (theme && theme.pct > THEME_CAP) return { v: "Theme full", why: `${theme.name} is ${theme.pct.toFixed(0)}% of your portfolio: send new money elsewhere` };
    if (p && p.zone === "Accumulate+") return { v: "Accumulate+", why: "On sale: a good month to add" };
    if (target && weight < target) return { v: "Accumulate", why: `Below your ${target}% target` };
    if (p && p.zone === "Stretched") return { v: "Hold", why: "Price stretched: no rush to add" };
    if (p && p.groups && p.groups.Quality === 0 && p.fundamentals) return { v: "Hold", why: "Quality score 0: don't add until profits improve" };
    return { v: target ? "Hold" : "Accumulate", why: target ? "At target" : "Keep the regular buy" };
  }
  const verdictCls = (v) => ({ "Accumulate+": "e-now", Accumulate: "e-watch", Hold: "e-none", Trim: "e-wait", "Theme full": "e-wait", "Review thesis": "e-avoid" }[v] || "e-none");

  async function lookthrough() { return cache.__lt || (cache.__lt = await T().api("/api/lookthrough")); }
  async function themes(symbols) {
    const key = "__th" + (symbols || []).slice().sort().join(",");
    return cache[key] || (cache[key] = await T().api("/api/ltthemes?symbols=" + encodeURIComponent((symbols || []).join(","))).catch(() => ({ themes: {}, groups: {} })));
  }
  const THEME_CAP = 40; // % of the portfolio in one theme that moves together
  /** Share of the portfolio per theme and per umbrella group (AI build-out). */
  async function themeShares(positions, total) {
    const th = await themes([...new Set(positions.map((p) => p.symbol))]);
    const val = (p) => p.valueAcct || p.mv || 0;
    const byTheme = {}, byGroup = {};
    positions.forEach((p) => {
      const t = th.themes[p.symbol];
      if (!t) return;
      byTheme[t] = (byTheme[t] || 0) + val(p);
      const g = th.groups[t];
      if (g) byGroup[g] = (byGroup[g] || 0) + val(p);
    });
    const pctOf = (o) => Object.fromEntries(Object.entries(o).map(([k, v]) => [k, total ? 100 * v / total : 0]));
    return { byTheme: pctOf(byTheme), byGroup: pctOf(byGroup), themeOf: (s) => th.themes[s], groupOf: (s) => th.groups[th.themes[s]] };
  }

  async function diversification(el, positions, acct, lt) {
    const td = T(), L = await lookthrough().catch(() => null);
    const val = (p) => p.valueAcct || p.mv || 0;
    const total = positions.reduce((s, p) => s + val(p), 0) + (acct.free > 0 ? acct.free : 0);
    const fundIndex = (sym) => L && Object.entries(L.indexes).find(([, v]) => v.funds.includes(sym));
    const exposure = {}, idxHeld = {};
    for (const p of positions) {
      const fi = fundIndex(p.symbol);
      if (fi) {
        idxHeld[fi[0]] = (idxHeld[fi[0]] || []).concat(p.symbol);
        for (const [s, w] of Object.entries(fi[1].weights)) exposure[s] = (exposure[s] || 0) + val(p) * w / 100;
      } else exposure[p.symbol] = (exposure[p.symbol] || 0) + val(p);
    }
    const tops = Object.entries(exposure).sort((a, b) => b[1] - a[1]).slice(0, 6);
    const rows = [];
    const row = (label, value, ok, hint) => rows.push(`<li class="${ok ? "" : "no"}"><span>${label}</span><b class="num">${value}</b>${hint ? `<small>${hint}</small>` : ""}</li>`);
    const sorted = positions.slice().sort((a, b) => val(b) - val(a));
    const top5 = 100 * sorted.slice(0, 5).reduce((s, p) => s + val(p), 0) / total;
    const big = tops[0];
    row("Biggest single company (incl. inside ETFs)", big ? `${td.esc(big[0])} · ${(100 * big[1] / total).toFixed(1)}%` : "–", !big || 100 * big[1] / total <= 10, "keep any one company under about 10%");
    const dupes = Object.entries(idxHeld).filter(([, v]) => v.length > 1);
    row("Funds tracking the same index", dupes.length ? dupes.map(([k, v]) => `${k}: ${v.join(" + ")}`).join("; ") : "none", !dupes.length, dupes.length ? "they hold the same shares: pick one (the reinvesting 'Acc' version suits long-term)" : "");
    if (idxHeld.World && (idxHeld["S&P 500"] || idxHeld["Nasdaq 100"])) row("World fund + US fund", "overlap", false, `about ${L.indexes.World.usShare}% of a world fund is already US shares`);
    const singles = positions.filter((p) => !fundIndex(p.symbol)).length;
    row("Holdings", `${positions.length} (${singles} single stocks)`, positions.length >= 3, positions.length < 3 ? "very concentrated" : "");
    row("Top 5 holdings", top5.toFixed(0) + "%", top5 <= 60 || positions.length <= 5, "over 60% in five names is concentrated");
    const secs = {};
    positions.forEach((p) => { const s = fundIndex(p.symbol) ? "Index funds" : (lt[p.symbol] && lt[p.symbol].sector) || "Other"; secs[s] = (secs[s] || 0) + val(p); });
    const topSec = Object.entries(secs).filter(([k]) => k !== "Index funds").sort((a, b) => b[1] - a[1])[0];
    if (topSec) row("Biggest sector (single stocks)", `${td.esc(topSec[0])} · ${(100 * topSec[1] / total).toFixed(0)}%`, 100 * topSec[1] / total <= 30, "");
    const ts = await themeShares(positions, total);
    const ai = ts.byGroup["AI build-out"] || 0;
    if (ai) row("AI build-out (chips, chip equipment, memory, optics, power)", ai.toFixed(0) + "%", ai <= THEME_CAP,
      ai > THEME_CAP ? `these rise and fall together with AI spending: one bet, not ${positions.filter((p) => ts.groupOf(p.symbol)).length}. Keep it under about ${THEME_CAP}%` : "");
    const topTheme = Object.entries(ts.byTheme).sort((a, b) => b[1] - a[1])[0];
    if (topTheme) row("Biggest theme", `${td.esc(topTheme[0])} · ${topTheme[1].toFixed(0)}%`, topTheme[1] <= 25, topTheme[1] > 25 ? "over 25% in one theme" : "");
    const ccys = {};
    positions.forEach((p) => { const c = (p.q && p.q.currency) || p.currency || "?"; ccys[c === "GBp" ? "GBP" : c] = (ccys[c === "GBp" ? "GBP" : c] || 0) + val(p); });
    const ctry = {};
    positions.forEach((p) => { const c = fundIndex(p.symbol) ? "Index funds" : (lt[p.symbol] && lt[p.symbol].country) || null; if (c) ctry[c] = (ctry[c] || 0) + val(p); });
    const topC = Object.entries(ctry).filter(([k]) => k !== "Index funds").sort((a, b) => b[1] - a[1]);
    if (topC.length) row("Countries (single stocks)", topC.slice(0, 3).map(([c, v]) => `${td.esc(c)} ${(100 * v / total).toFixed(0)}%`).join(" · "), 100 * topC[0][1] / total <= 70, "where the companies are based (FinanceDatabase)");
    row("Currencies", Object.entries(ccys).sort((a, b) => b[1] - a[1]).map(([c, v]) => `${c} ${(100 * v / total).toFixed(0)}%`).join(" · "), true, "");
    if (acct.free != null) { const cp = 100 * acct.free / total; row("Cash", cp.toFixed(0) + "%", cp <= 10, cp > 10 ? "cash drag: idle money doesn't compound" : ""); }
    el.innerHTML = `<ul class="risk-list">${rows.join("")}</ul>
      ${tops.length ? `<h3 class="h3" style="margin-top:12px">What you really own (look-through)</h3><ul class="donut-legend">${tops.map(([s, v]) => `<li><span>${td.logo(s, 18)} ${td.esc(s)}</span><span class="num">${(100 * v / total).toFixed(1)}%</span></li>`).join("")}</ul>
      <p class="muted" style="font-size:11.5px">ETF weights are approximate (${td.esc(L ? L.asOf : "")}).</p>` : ""}`;
  }

  async function plan(el, positions, acct, lt, rerender) {
    const td = T(), st = td.settings();
    const targets = td.store.get("targets", {});
    const total = positions.reduce((s, p) => s + (p.valueAcct || p.mv || 0), 0);
    const syms = [...new Set(positions.map((p) => p.symbol).concat(Object.keys(targets)))];
    const cur = Object.fromEntries(syms.map((s) => [s, positions.filter((p) => p.symbol === s).reduce((a, p) => a + (p.valueAcct || p.mv || 0), 0)]));
    const monthly = st.monthly || 1200;
    let tsum = syms.reduce((a, s) => a + (+targets[s] || 0), 0);
    const implicit = !tsum && total > 0; // no targets yet: a starting model instead of today's mix
    const ts = await themeShares(positions, total);
    let core = null;
    if (implicit) {
      // AI build-out names share at most THEME_CAP%; other holdings share the rest; with nothing else, a world ETF is the core
      const inAI = syms.filter((s) => ts.groupOf(s));
      const other = syms.filter((s) => !ts.groupOf(s));
      if (inAI.length && !other.length) { core = "VWCE.DE"; syms.push(core); cur[core] = 0; other.push(core); }
      const aiShare = inAI.length ? (other.length ? Math.min(THEME_CAP, 100 * inAI.length / syms.length) : 100) : 0;
      inAI.forEach((s) => { targets[s] = Math.round(10 * aiShare / inAI.length) / 10; });
      other.forEach((s) => { targets[s] = Math.round(10 * (100 - aiShare) / other.length) / 10; });
      tsum = syms.reduce((a, s) => a + (+targets[s] || 0), 0);
    }
    const onSale = syms.filter((s) => lt[s] && lt[s].zone === "Accumulate+").length;
    const herd = onSale >= Math.max(3, syms.length / 2); // most holdings "on sale" at once = the whole theme is falling
    // split new money to the holdings furthest below target, tilted by the buy zone
    const after = total + monthly, gaps = {};
    syms.forEach((s) => {
      const tw = (+targets[s] || 0) / (tsum || 1);
      let gap = Math.max(0, tw * after - cur[s]);
      const z = lt[s] && lt[s].zone;
      gap *= z === "Accumulate+" && !herd ? 1.25 : z === "Stretched" ? 0.5 : z === "Speculative" ? 0.5 : 1;
      gaps[s] = gap;
    });
    const gsum = Object.values(gaps).reduce((a, b) => a + b, 0);
    const buys = Object.fromEntries(syms.map((s) => [s, gsum ? monthly * gaps[s] / gsum : 0]));
    el.innerHTML = `<div class="form-row" style="max-width:520px">
        <label class="field">Monthly amount (${td.esc(acct.ccy)})<input id="mAmt" type="number" min="0" step="10" inputmode="decimal" value="${monthly}"></label>
        <button class="btn" type="button" id="mCur">Targets = today's weights</button><button class="btn" type="button" id="mEq">Equal weights</button></div>
      <div class="table-wrap"><table class="rt"><thead><tr><th scope="col">Holding</th><th class="r" scope="col">Now</th><th class="r" scope="col">Target %</th><th class="r" scope="col">Buy this month</th></tr></thead><tbody>
      ${syms.map((s) => `<tr style="cursor:default"><td class="c-symbol">${td.logo(s, 22)} <a class="sym" href="#/stock/${encodeURIComponent(s)}">${td.esc(s)}</a> ${lt[s] ? `<span class="tag">${td.esc(zoneLabel(lt[s].zone))}</span>` : ""}</td>
        <td class="r num">${total ? (100 * cur[s] / total).toFixed(1) : 0}%</td>
        <td class="r"><input class="tgt" data-s="${td.esc(s)}" type="number" min="0" max="100" step="1" inputmode="decimal" ${implicit ? `placeholder="${targets[s]}"` : `value="${targets[s] ?? ""}"`} aria-label="Target % for ${td.esc(s)}"></td>
        <td class="r num"><b>${buys[s] >= 0.5 ? td.money(buys[s], acct.ccy) : "–"}</b></td></tr>`).join("")}
      </tbody></table></div>
      <form class="form-row" id="mAdd" style="max-width:420px;margin-top:8px"><label class="field">Add a holding to the plan<input name="s" placeholder="e.g. VWRL.L" autocapitalize="characters"></label><button class="btn" type="submit">Add</button></form>
      ${implicit ? `<p class="muted" style="font-size:12.5px">No targets set yet: a starting model is used, so new money goes to what's under-weight instead of copying today's mix. AI build-out names share at most ${THEME_CAP}%${core ? `, and a world ETF (${core}, in euros on Xetra) is the core for the rest` : ""}. Type your own target % to change it.</p>` : ""}
      ${herd ? `<p class="muted" style="font-size:12.5px">${onSale} of your ${syms.length} holdings look "on sale" at the same time: that usually means the whole theme is falling together, so no extra money is tilted towards them this month.</p>` : ""}
      <p class="muted" style="font-size:12.5px">Targets add up to ${tsum.toFixed(0)}%${Math.abs(tsum - 100) > 0.5 && tsum ? " (they're scaled to 100%)" : ""}. New money goes to what's furthest below target, a bit more to names "on sale" and less to stretched ones, so you rebalance without selling.
      In Trading 212 a <b>Pie</b> with these target % and <b>AutoInvest</b> does the monthly buying for you; in Revolut use a <b>recurring buy</b> for each holding.</p>`;
    const save = () => { td.store.set("targets", targets); rerender(); }; // editing one target saves today's mix for the rest
    $("#mAmt", el).addEventListener("change", (e) => { td.store.set("settings", Object.assign(td.settings(), { monthly: +e.target.value || 0 })); rerender(); });
    $$(".tgt", el).forEach((i) => i.addEventListener("change", () => { const v = i.value === "" ? null : +i.value; if (v == null) delete targets[i.dataset.s]; else targets[i.dataset.s] = v; save(); }));
    $("#mCur", el).addEventListener("click", () => { syms.forEach((s) => { targets[s] = total ? Math.round(100 * cur[s] / total) : 0; }); save(); });
    $("#mEq", el).addEventListener("click", () => { syms.forEach((s) => { targets[s] = Math.round(100 / syms.length); }); save(); });
    $("#mAdd", el).addEventListener("submit", (e) => { e.preventDefault(); const s = new FormData(e.target).get("s").trim().toUpperCase(); if (s) { targets[s] = targets[s] ?? 5; save(); } });
  }

  async function dividends(el, ccy) {
    const td = T();
    el.innerHTML = td.skeleton(3);
    try {
      const d = await td.api("/api/t212/dividends");
      if (!d.total) { el.innerHTML = `<p class="muted">No dividends received in your Trading 212 history yet.</p>`; return; }
      const max = Math.max(...d.months.map((m) => m.amount), 1);
      el.innerHTML = `<div class="ret-grid"><div class="perf-tile"><div class="k">Last 12 months</div><div class="v num up">${td.money(d.last12, ccy)}</div></div>
          <div class="perf-tile"><div class="k">This year</div><div class="v num">${td.money(d.thisYear, ccy)}</div></div>
          <div class="perf-tile"><div class="k">All time</div><div class="v num">${td.money(d.total, ccy)}</div></div></div>
        <div class="months" role="img" aria-label="Dividends by month">${d.months.slice(-12).map((m) => `<div title="${m.month}: ${td.money(m.amount, ccy)}"><i class="pos" style="height:${(46 * m.amount / max).toFixed(0)}px"></i><span>${m.month.slice(5)}</span></div>`).join("")}</div>
        ${d.bySymbol.length ? `<ul class="donut-legend">${d.bySymbol.slice(0, 8).map((x) => `<li><span>${td.logo(x.symbol, 18)} ${td.esc(x.symbol)}</span><span class="num">${td.money(x.amount, ccy)}</span></li>`).join("")}</ul>` : ""}`;
    } catch (e) { el.innerHTML = `<p class="muted">Dividends unavailable: ${td.esc(e.message)}</p>`; }
  }


  // ------------------------------------------------------------ data connections: FMP key, FinanceDatabase, Tailscale
  async function connectionsCard(el) {
    const td = T();
    const [f, d] = await Promise.all([td.api("/api/fmp/status").catch(() => ({})), td.api("/api/fdb/status").catch(() => ({}))]);
    if (!el.isConnected) return;
    const fdbTxt = d.state === "ready" ? `<b class="up">connected</b> · ${Number(d.companies || 0).toLocaleString()} companies worldwide${d.updated ? ` · updated ${new Date(d.updated * 1000).toLocaleDateString()}` : ""}`
      : d.state === "loading" ? "downloading (18 MB, once a month)…" : d.state === "failed" ? `<span class="down">not available</span> (${td.esc(d.error || "")})` : "starting…";
    el.innerHTML = `<ul class="risk-list conn-list">
        <li><span><b>Financial Modeling Prep</b><small>company figures and results dates for non-US stocks (SK hynix, Advantest, ASM International…)</small></span>
          <b class="num">${f.hasKey ? '<span class="up">key set</span>' : "no key"}</b>${f.hasKey ? `<small>${f.callsToday || 0} calls today · ${f.cached || 0} answers saved${f.lastError ? ` · last issue: ${td.esc(f.lastError)}` : ""}</small>` : ""}</li>
        <li><span><b>FinanceDatabase</b><small>sector, industry and country for any stock; wider Challenger search</small></span><b class="num">${fdbTxt}</b></li>
        <li><span><b>Tailscale</b><small>use the dashboard on the iPhone away from home</small></span><b class="num"><a href="#" id="connPhone">set up →</a></b></li></ul>
      ${f.fromEnv ? `<p class="muted" style="font-size:12.5px">The FMP key is set by the FMP_API_KEY environment variable.</p>` : `
      <form class="form-row" id="fmpForm" style="align-items:end;margin-top:8px">
        <label class="field" style="flex:1;min-width:220px">Financial Modeling Prep API key<input name="key" type="password" autocomplete="off" spellcheck="false" placeholder="${f.hasKey ? "•••••• saved (leave empty and Save to remove)" : "paste your key"}"></label>
        <button class="btn primary" type="submit">Save</button>${f.hasKey ? `<button class="btn" type="button" id="fmpTest">Test the key</button>` : ""}</form>
      <p class="muted" style="font-size:12.5px;margin:6px 0 0">Get a free key at <b>financialmodelingprep.com</b> → Sign up → Dashboard → API key. The free plan allows about 250 calls a day; the dashboard saves answers for 7 days so that's enough. Non-US companies may need a paid plan: <b>Test the key</b> shows what yours covers. The key stays on this computer (dashboard/.fmp.json).</p>`}
      <div id="fmpOut"></div>`;
    $("#connPhone", el).addEventListener("click", (e) => { e.preventDefault(); if (window.Trade) window.Trade.openPhone(); });
    const form = $("#fmpForm", el);
    if (form) form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await td.post("/api/fmp/key", { key: form.key.value.trim() }); td.toast(form.key.value.trim() ? "FMP key saved" : "FMP key removed"); delete cache.__lt; connectionsCard(el); }
      catch (err) { $("#fmpOut", el).innerHTML = `<p class="error">${td.esc(err.message)}</p>`; }
    });
    const test = $("#fmpTest", el);
    if (test) test.addEventListener("click", async () => {
      $("#fmpOut", el).innerHTML = `<p class="muted">Testing with Apple, ASML (Amsterdam), Advantest and SK hynix…</p>`;
      try {
        const r = await td.api("/api/fmp/test");
        $("#fmpOut", el).innerHTML = `<ul class="risk-list">${r.results.map((x) => `<li class="${x.ok ? "" : "no"}"><span>${td.esc(x.symbol)}</span><b class="num">${x.ok ? "✓" : "✕"}</b><small>${td.esc(x.text)}</small></li>`).join("")}</ul>
          ${r.results.some((x) => !x.ok && x.symbol !== "AAPL") ? `<p class="muted" style="font-size:12.5px">Stocks marked ✕ keep using their price history only.</p>` : ""}`;
      } catch (err) { $("#fmpOut", el).innerHTML = `<p class="error">${td.esc(err.message)}</p>`; }
    });
  }

  window.LT = { connectionsCard, zoneLabel, themeShares, THEME_CAP, mode, profiles, profile, entry, entryCard, stockCard, backtestCard, openBuy, qualityPage, verdict, verdictCls, diversification, plan, dividends, zoneBadge, bandBadge, cache };
})();
