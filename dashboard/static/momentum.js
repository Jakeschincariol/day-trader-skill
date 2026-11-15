/* Momentum page: momentum waves (WaveTrend 10/21) and MACD on your holdings and watchlist, with a plain tip per stock,
   how past green dots worked out on that stock, the weekly picture as confirmation, and an optional hourly check
   that tells you about new green dots while the dashboard is open. Uses helpers app.js shares on window.TD. */
(function () {
  "use strict";
  const T = () => window.TD;
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));

  const SETUPS = {
    "fresh-buy": { label: "Green dot", tone: "up", rank: 0, tip: "Momentum just turned up from oversold: one of the better moments for this month's buy." },
    "turning-up": { label: "Turning up", tone: "up", rank: 1, tip: "Momentum is turning up below zero: a fair moment to start buying, in parts." },
    "oversold-wait": { label: "Oversold", tone: "flat", rank: 2, tip: "Oversold and still falling: wait for the green dot, or buy only a third of your amount now." },
    "rising-low": { label: "Rising", tone: "up", rank: 3, tip: "Momentum is rising but still below zero: fine for your regular amount." },
    neutral: { label: "Neutral", tone: "muted", rank: 4, tip: "Nothing special: stick to your monthly plan." },
    cooling: { label: "Cooling", tone: "flat", rank: 5, tip: "Momentum fading from high levels: no rush, a better price often comes in the next weeks." },
    overbought: { label: "Overbought", tone: "down", rank: 6, tip: "Overbought: don't chase. Keep the buy small or wait until the waves come back toward zero." },
    "fresh-sell": { label: "Red dot", tone: "down", rank: 7, tip: "Momentum turned down from overbought: not a good moment to add. A long-term holder doesn't need to sell for this." },
  };
  const TF = { h: "Hourly", d: "Daily", w: "Weekly" };
  const FILTERS = { all: "All", buy: "Buy moments", wait: "Oversold, wait", hot: "Overbought" };

  function tipFor(r) {
    const s = SETUPS[r.setup] || SETUPS.neutral;
    let t = s.tip;
    const w = r.weekly;
    if (["fresh-buy", "turning-up", "rising-low"].includes(r.setup)) {
      if (w && w.up && w.wt1 < 40) t += " The weekly waves agree: the strongest kind of setup.";
      else if (w && !w.up) t += " But the weekly waves still point down: buy in parts (half now, half later).";
      if (r.trend === "down") t += " The price is still under both averages, so a second dip is common.";
    }
    if (r.setup === "oversold-wait" && w && w.up) t += " The weekly picture is still rising, so this dip is likely a pause.";
    const b = r.buyHistory;
    if (["fresh-buy", "turning-up"].includes(r.setup) && b && b.count >= 5 && b.worked < 50) t += ` Careful: on this stock green dots worked only ${b.worked}% of the time.`;
    return t;
  }
  const histText = (b, r, kind) => {
    if (!b) return `no past ${kind} dots`;
    const per = `${r.ahead} ${r.unit}${r.ahead === 1 ? "" : "s"}`;
    return b.count < 5 ? `only ${b.count} past ${kind} dot${b.count === 1 ? "" : "s"}: too few to judge`
      : `${b.count} past ${kind} dots: ${kind === "green" ? "higher" : "lower"} ${per} later in ${b.worked}% (typical ${b.median > 0 ? "+" : ""}${b.median}%)`;
  };
  function waveBar(v) {
    const x = Math.max(-100, Math.min(100, v)), left = 50 + x / 2;
    return `<span class="mo-bar" title="Momentum waves ${v}"><i class="z1"></i><i class="z2"></i><b style="left:${left}%"></b></span>`;
  }
  function spark(arr) {
    const v = (arr || []).filter((x) => x != null);
    if (v.length < 5) return "";
    const W = 120, H = 30, y = (x) => (H / 2 - (Math.max(-100, Math.min(100, x)) / 100) * (H / 2 - 2)).toFixed(1);
    const pts = v.map((x, i) => `${((i / (v.length - 1)) * W).toFixed(1)},${y(x)}`).join(" ");
    return `<svg class="mo-spark" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" aria-hidden="true"><line x1="0" x2="${W}" y1="${y(53)}" y2="${y(53)}" class="lv"/><line x1="0" x2="${W}" y1="${y(-53)}" y2="${y(-53)}" class="lv"/><line x1="0" x2="${W}" y1="${H / 2}" y2="${H / 2}" class="zero"/><polyline points="${pts}"/></svg>`;
  }
  function dotText(r) {
    const l = r.lastSignal;
    if (!l) return "no dot yet";
    const when = l.ago === 0 ? `on the last ${r.unit}` : `${l.ago} ${r.unit}${l.ago === 1 ? "" : "s"} ago`;
    return `${l.kind === "buy" ? "Green" : "Red"} dot ${when}`;
  }

  async function page(view, params) {
    const td = T();
    let tf = (params && params.get("tf")) || td.store.get("momTf", "d");
    let list = td.store.get("momList", "both"), filter = "all";
    const extras = () => td.store.get("momExtra", []);
    view.innerHTML = `<div class="page-title"><h1>Momentum</h1><p class="sub">Find a better moment to buy. Momentum waves on your stocks and watchlist, with a plain tip for each. Daily for your monthly buys, weekly for the big picture, hourly for the exact day.</p></div>
      <div class="toolbar">
        <div class="seg" id="moTf" role="group" aria-label="Candle size">${Object.entries(TF).map(([k, v]) => `<button type="button" data-tf="${k}">${v}</button>`).join("")}</div>
        <div class="seg" id="moList" role="group" aria-label="Which stocks"><button type="button" data-l="mine">My stocks</button><button type="button" data-l="wl">Watchlist</button><button type="button" data-l="both">Both</button></div>
        <form id="moAdd" class="mo-add" autocomplete="off"><input id="moIn" placeholder="Add a ticker, e.g. ASML" aria-label="Add a ticker" maxlength="15"><button class="btn sm" type="submit">Add</button></form>
        ${td.rf("mom")}
      </div>
      <div class="seg mo-filter" id="moFilter" role="group" aria-label="Show">${Object.entries(FILTERS).map(([k, v]) => `<button type="button" data-f="${k}">${v}</button>`).join("")}</div>
      <div class="card mo-hourly"><label class="check"><input type="checkbox" id="moHourly" ${td.store.get("momHourly", false) ? "checked" : ""}> <b>Hourly check</b></label>
        <span class="muted">Every hour, check your stocks and watchlist and tell me when a new green dot appears (daily or hourly). Works while the dashboard is open in a browser tab.</span></div>
      <div id="moSum" class="mo-sum"></div>
      <div class="card" style="margin-top:12px"><div id="moRows">${td.skeleton(10)}</div></div>
      <details class="card fold" style="margin-top:16px"><summary class="card-head"><h2><i data-lucide="lightbulb"></i>How to use momentum for your entry</h2></summary>
        <ul class="mo-guide">
          <li><b>Decide what to buy first, then use momentum for when.</b> The long-term score says if a stock is worth owning; the waves only help you pay a better price.</li>
          <li><b>Green dot = the best timing signal.</b> The fast wave crosses above the slow one while deep below zero (oversold). Selling is exhausted and buyers are coming back.</li>
          <li><b>Oversold is not a buy yet.</b> Falling stocks can stay oversold for weeks. Wait for the green dot, or buy only a third and keep the rest for after the turn.</li>
          <li><b>Check two time frames.</b> A daily green dot while the weekly waves are rising is the strongest setup. A daily green dot against a falling weekly is often only a pause: buy in parts.</li>
          <li><b>Use hourly only for the exact day.</b> After a daily green dot, an hourly green dot helps pick the day to place the order. On its own, hourly is noise.</li>
          <li><b>Overbought or a red dot: don't chase.</b> Keep your monthly amount small or wait for the waves to come back toward zero. You don't need to sell a long-term holding for this.</li>
          <li><b>Check the record.</b> "Past green dots" shows how often this stock was higher afterwards. Below 50%, the signal hasn't worked well on that stock.</li>
          <li><b>Before results, wait.</b> Earnings can move a stock 10% in a day and wipe out any signal: buy part before, the rest after.</li>
        </ul>
        <p class="muted" style="font-size:12px">Momentum waves: WaveTrend (10, 21), oversold below -53, overbought above +53. MACD (12, 26, 9). Standard public indicators, computed from Yahoo prices. Past signals don't guarantee future ones. Not advice.</p>
      </details>`;
    let data = null;
    const paintSegs = () => {
      $$("#moTf button").forEach((b) => b.classList.toggle("on", b.dataset.tf === tf));
      $$("#moList button").forEach((b) => b.classList.toggle("on", b.dataset.l === list));
      $$("#moFilter button").forEach((b) => b.classList.toggle("on", b.dataset.f === filter));
    };
    const symbols = async () => {
      await td.getT212().catch(() => null);
      const mine = td.brokerPositions().map((p) => p.symbol).concat(td.store.get("manual", []).map((m) => m.symbol));
      const wl = td.watchlist();
      const base = list === "mine" ? mine : list === "wl" ? wl : mine.concat(wl);
      return { syms: [...new Set(base.concat(extras()))], mine: new Set(mine) };
    };
    const render = () => {
      if (!data || !$("#moRows")) return;
      const ok = data.rows.filter((r) => !r.error);
      const n = (k) => ok.filter((r) => k.includes(r.setup)).length;
      $("#moSum").innerHTML = `<span class="pill up">${n(["fresh-buy", "turning-up", "rising-low"])} buy moment${n(["fresh-buy", "turning-up", "rising-low"]) === 1 ? "" : "s"}</span><span class="pill flat">${n(["oversold-wait"])} oversold, wait</span><span class="pill down">${n(["overbought", "fresh-sell"])} overbought or red dot</span><span class="muted">${TF[data.tf]} candles · ${ok.length} stocks</span>`;
      const keep = { all: () => true, buy: (r) => ["fresh-buy", "turning-up", "rising-low"].includes(r.setup), wait: (r) => r.setup === "oversold-wait", hot: (r) => ["overbought", "fresh-sell", "cooling"].includes(r.setup) }[filter];
      const rows = ok.filter(keep).sort((a, b) => (SETUPS[a.setup] || SETUPS.neutral).rank - (SETUPS[b.setup] || SETUPS.neutral).rank || a.wt1 - b.wt1);
      const bad = data.rows.filter((r) => r.error);
      $("#moRows").innerHTML = (rows.length ? rows.map((r) => {
        const s = SETUPS[r.setup] || SETUPS.neutral;
        const w = r.weekly ? SETUPS[r.weekly.setup] || SETUPS.neutral : null;
        const m = r.macd;
        return `<div class="mo-row">
          <a class="mo-name" href="#/stock/${encodeURIComponent(r.symbol)}" data-deep="1">${td.logo(r.symbol, 28)}<span><b>${td.esc(r.symbol)}</b>${data.mine.has(r.symbol) ? `<em class="mo-own">owned</em>` : ""}<small>${td.esc(r.name || "")}</small></span></a>
          <span class="mo-px num">${td.priceStr(r.price, r.currency)}<small class="${td.cls(r.changePct)}">${r.changePct == null ? "" : td.pct(r.changePct) + (data.tf === "h" ? " last hour" : data.tf === "w" ? " this week" : " today")}</small></span>
          <span class="mo-wave">${waveBar(r.wt1)}${spark(r.spark)}<small class="num">waves ${r.wt1}</small></span>
          <span class="mo-state"><span class="mo-pill ${s.tone}">${s.label}</span><small>${dotText(r)}</small>
            ${w ? `<small>Weekly: <b class="${w.tone}">${w.label.toLowerCase()}</b></small>` : ""}
            ${m ? `<small>MACD: ${m.above ? "buyers" : "sellers"} ${m.stronger ? "stronger" : "fading"}</small>` : ""}</span>
          <span class="mo-tip">${td.esc(tipFor(r))}<small>${td.esc(histText(r.buyHistory, r, "green"))}</small></span>
        </div>`;
      }).join("") : `<p class="empty">Nothing in this group right now.</p>`) +
        (bad.length ? `<p class="muted" style="font-size:12.5px;margin:10px 0 0">No data for ${bad.map((r) => td.esc(r.symbol)).join(", ")} (too little history or an unknown ticker).</p>` : "");
    };
    const load = async (fresh) => {
      paintSegs();
      $("#moRows").innerHTML = td.skeleton(10);
      const { syms, mine } = await symbols();
      if (!syms.length) { $("#moRows").innerHTML = `<p class="empty">Link your broker or add stocks to your watchlist (★ on any stock page), or add a ticker above.</p>`; return; }
      try {
        const d = await td.api(`/api/momentum?symbols=${encodeURIComponent(syms.join(","))}&tf=${tf}${fresh ? "&fresh=1" : ""}`);
        data = Object.assign(d, { mine });
      } catch (e) { if ($("#moRows")) $("#moRows").innerHTML = `<p class="error">${td.esc(e.message)}</p>`; return; }
      render();
    };
    $("#moTf").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; tf = b.dataset.tf; td.store.set("momTf", tf); load(); });
    $("#moList").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; list = b.dataset.l; td.store.set("momList", list); load(); });
    $("#moFilter").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; filter = b.dataset.f; paintSegs(); render(); });
    $("#moAdd").addEventListener("submit", (e) => {
      e.preventDefault();
      const v = $("#moIn").value.trim().toUpperCase();
      if (!/^[A-Z0-9.\-^=]{1,15}$/.test(v)) return;
      td.store.set("momExtra", [...new Set(extras().concat(v))].slice(-20)); $("#moIn").value = ""; load();
    });
    $("#moHourly").addEventListener("change", async (e) => {
      td.store.set("momHourly", e.target.checked);
      if (e.target.checked && "Notification" in window && Notification.permission === "default") { try { await Notification.requestPermission(); } catch (er) { /* ignore */ } }
      td.toast(e.target.checked ? "Hourly check on: I'll tell you about new green dots while the dashboard is open" : "Hourly check off");
      startHourly();
    });
    // opening a stock from here opens its Dig deeper chart too
    $("#moRows").addEventListener("click", (e) => { if (e.target.closest("a[data-deep]")) { td.store.set("deepOpen", true); td.store.set("deepTf", tf); } });
    const RFo = td.RF();
    RFo.mom = () => load(true);
    await load();
    return () => {};
  }

  // ------------------------------------------------------------ hourly check: new green dots while the dashboard is open
  let timer = null;
  async function checkNow() {
    const td = T();
    if (!td || !td.store.get("momHourly", false)) return;
    await td.getT212().catch(() => null);
    const syms = [...new Set(td.brokerPositions().map((p) => p.symbol).concat(td.store.get("manual", []).map((m) => m.symbol), td.watchlist()))].slice(0, 40);
    if (!syms.length) return;
    const seen = new Set(td.store.get("momSeen", []));
    const fresh = [];
    for (const tf of ["d", "h"]) {
      const d = await td.api(`/api/momentum?symbols=${encodeURIComponent(syms.join(","))}&tf=${tf}`).catch(() => null);
      (d ? d.rows : []).forEach((r) => {
        const l = r.lastSignal;
        if (r.error || !l || l.kind !== "buy" || l.ago > (tf === "h" ? 1 : 0)) return;
        const key = `${r.symbol}|${tf}|${r.at - (tf === "h" ? 3600 : 86400) * l.ago}`;
        if (seen.has(key)) return;
        seen.add(key);
        fresh.push(`${r.symbol} (${tf === "h" ? "hourly" : "daily"})`);
      });
    }
    td.store.set("momSeen", [...seen].slice(-300));
    if (!fresh.length) return;
    const msg = "New green dot: " + fresh.join(", ") + ". Momentum turned up from oversold.";
    td.toast(msg);
    if ("Notification" in window && Notification.permission === "granted") { try { new Notification("TraderDash momentum", { body: msg, icon: "/icon-192.png" }); } catch (e) { /* ignore */ } }
  }
  function startHourly() {
    if (timer) { clearInterval(timer); timer = null; }
    const td = T();
    if (!td || !td.store.get("momHourly", false)) return;
    setTimeout(checkNow, 20000);
    timer = setInterval(checkNow, 3600 * 1000);
  }
  window.addEventListener("load", () => setTimeout(startHourly, 1000));

  window.Momentum = { page, tipFor, SETUPS, checkNow };
})();
