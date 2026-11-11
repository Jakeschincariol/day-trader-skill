/* Day Runners: small caps up big today on heavy volume, each with a rule-based day-trade plan
   (entry, stop, two targets) from today's 5-minute bars. Uses helpers app.js shares on window.TD.
   The levels are rules, not a forecast: most runners give back their gains. */
(function () {
  "use strict";
  const T = () => window.TD;
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));

  const SETUPS = {
    breakout: { label: "Breakout", cls: "e-now", how: "Near the high of the day and above VWAP. Buy only if it trades above the entry (a new high)." },
    pullback: { label: "Pullback", cls: "e-watch", how: "Pulled back but still above VWAP. Buy only when a 5-minute candle trades above the entry." },
    pre: { label: "Pre-market", cls: "e-watch", how: "Market not open yet. Buy only if it trades above the pre-market high after the open." },
    next: { label: "Next session", cls: "e-watch", how: "Market closed. Next session, buy only if it trades above today's high." },
    below: { label: "Under VWAP", cls: "e-wait", how: "Sellers are in control. No trade unless it climbs back above VWAP (the entry)." },
    faded: { label: "Faded", cls: "e-avoid", how: "It already ran and gave a lot back. The move is over for today: chasing it is how traders lose." },
  };
  const SESSION = { pre: "Pre-market", open: "Market open", closed: "Market closed: plans are for the next session" };

  const extras = () => T().store.get("runnersExtra", []);
  const big = (v) => (v == null ? "–" : v >= 1e9 ? (v / 1e9).toFixed(1) + "B" : v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "K" : String(v));
  const px = (v) => (v == null ? "–" : "$" + T().fmt(v, T().dp(v)));

  function sizeLine(p) {
    const s = T().settings(), riskCash = (s.account * s.riskPct) / 100, per = p.entry - p.stop;
    if (!(per > 0)) return "";
    const n = Math.floor(riskCash / per), cost = n * p.entry;
    return `<p class="muted rn-size">Risking ${s.riskPct}% of a ${T().money(s.account)} account (${T().money(riskCash)}): <b>${n.toLocaleString()} shares</b> (${T().money(cost)}).
      <a href="#/portfolio">Change</a></p>`;
  }

  function card(x) {
    const t = T(), L = x.levels || {}, p = L.plan, st = SETUPS[L.setup] || { label: "No data", cls: "e-none", how: x.error ? "Could not load today's bars." : "" };
    const sym = encodeURIComponent(x.symbol);
    const chips = [
      x.relVol != null ? `<span class="pill" title="Volume today vs the 3-month average">${x.relVol}× volume</span>` : "",
      x.shares ? `<span class="pill" title="Shares outstanding (fewer shares move faster)">${big(x.shares)} shares</span>` : "",
      L.highPct != null ? `<span class="pill" title="Best price today vs yesterday's close">high ${t.pct(L.highPct, 0)}</span>` : "",
      L.vwap != null ? `<span class="pill" title="Volume-weighted average price today">VWAP ${px(L.vwap)}</span>` : "",
      x.mine ? `<span class="pill live">yours</span>` : "",
    ].join("");
    const news = (x.news || [])[0];
    return `<div class="card sigcard rn-card${L.setup === "faded" ? " rn-faded" : ""}">
      <div class="card-head"><div class="symwrap">${t.logo(x.symbol, 32)}<div><a class="sym" style="font-size:18px" href="#/stock/${sym}">${t.esc(x.symbol)}</a><span class="nm">${t.esc(x.name || "")}</span></div></div>
        <div style="text-align:right"><div class="num">${px(x.price)}</div><div class="num ${t.cls(x.changePct)}" style="font-size:13px">${t.pct(x.changePct)}</div></div></div>
      <div class="rn-row"><span class="badge ${st.cls}">${st.label}</span><span class="meter" title="Runner score ${x.score}/100"><i><b class="${x.score >= 70 ? "hi" : x.score >= 45 ? "mid" : "lo"}" style="width:${x.score}%"></b></i><span class="num">${x.score}</span></span>
        <span class="rn-spark">${L.spark && L.spark.length > 2 ? t.sparkline(L.spark, 96, 26) : ""}</span></div>
      <div class="rn-chips">${chips}</div>
      <p class="sec" style="font-size:13px;margin:0 0 10px">${t.esc(st.how)}${x.why && x.why.length ? ` <span class="muted">Why it's here: ${t.esc(x.why.join(", "))}.</span>` : ""}</p>
      ${p ? `<div class="plan">
        <div><div class="k">Entry (buy above)</div><div class="v num">${px(p.entry)}</div></div>
        <div><div class="k">Stop (−${p.riskPct}%)</div><div class="v num down">${px(p.stop)}</div></div>
        <div><div class="k">Sell half (2R)</div><div class="v num up">${px(p.t1)}</div></div>
        <div><div class="k">Sell rest (3R)</div><div class="v num up">${px(p.t2)}</div></div></div>
        ${p.wide ? `<p class="earn-note"><i data-lucide="triangle-alert"></i> Stop is far away (${p.riskPct}%): use a smaller position.</p>` : ""}
        ${sizeLine(p)}` : `<p class="muted" style="margin:0">No entry: ${L.setup === "faded" ? `high was ${px(L.hod)}, now ${px(L.last)} (${t.pct(L.fromHighPct, 0)} from the high).` : "not enough data yet."}</p>`}
      ${news ? `<p class="rn-news"><i data-lucide="newspaper"></i> <a href="${/^https?:\/\//.test(news.link || "") ? t.esc(news.link) : "#"}" target="_blank" rel="noopener">${t.esc(news.title)}</a></p>` : ""}
      <div class="sig-actions"><a class="btn sm" href="#/stock/${sym}"><i data-lucide="line-chart"></i> Chart</a>
        ${p && window.Trade ? `<button class="btn sm" data-alert="${t.esc(x.symbol)}" data-e="${p.entry}" data-s="${p.stop}" data-t1="${p.t1}" data-t2="${p.t2}"><i data-lucide="bell-plus"></i> Alerts at these levels</button>` : ""}
        ${x.mine ? `<button class="btn sm" data-drop="${t.esc(x.symbol)}" aria-label="Stop tracking ${t.esc(x.symbol)}"><i data-lucide="x"></i></button>` : ""}</div>
    </div>`;
  }

  async function page(view) {
    const t = T();
    let filter = t.store.get("runnersFilter", "trade"), minPct = t.store.get("runnersMin", 10), data = null, timer = null;
    view.innerHTML = `<h1>Day Runners</h1>
      <p class="sub">Stocks up big today on heavy volume, each with a plan: where to buy, where to cut the loss, where to take profit.</p>
      <div class="callout rn-warn"><b>Read this first.</b> Nobody knows which stock will double tomorrow, and anyone who promises that is selling something. These levels are momentum-trading rules, not predictions. Most runners give back much of their gain the same day, and stocks pushed on social media are often pump-and-dumps. Always place the stop, and never risk money you need. Not financial advice.</div>
      <div class="toolbar rn-tools">
        <div class="seg" id="rnF"><button data-f="trade">Tradable now</button><button data-f="all">All runners</button><button data-f="mine">Mine</button></div>
        <label class="field rn-min">Up at least <select id="rnMin">${[10, 20, 30, 50].map((v) => `<option value="${v}"${v === minPct ? " selected" : ""}>${v}%</option>`).join("")}</select></label>
        <form id="rnAdd" class="rn-add"><input type="text" id="rnSym" placeholder="Track a ticker (e.g. STAK)" aria-label="Ticker to track" maxlength="12" autocapitalize="characters"><button class="btn sm" type="submit">Track</button></form>
        ${t.rf("runners")}
      </div>
      <p class="muted rn-session" id="rnSession"></p>
      <div class="grid g3" id="rnCards">${[1, 2, 3].map(() => `<div class="card">${t.skeleton(7)}</div>`).join("")}</div>
      <div class="card" style="margin-top:22px"><h2>How the plan is built</h2><ul class="reasons rn-how">
        <li><span><b>Who gets in:</b> listed US stocks (no OTC) at $0.50 or more, up ${minPct}%+ today with at least 300K shares traded. Score: size of the move, volume vs normal, how few shares exist, price between $1 and $20, fresh news, and whether the setup still works.</span></li>
        <li><span><b>Entry:</b> buy only when the price trades <i>above</i> a level: the high of the day (breakout), the latest 5-minute high (pullback), the pre-market high, or VWAP if it fell under it. If it never gets there, there is no trade.</span></li>
        <li><span><b>Stop:</b> the lowest price of the last 30 minutes, at least 1.5% under the entry. Next-session plans use today's VWAP. If it hits, sell. No exceptions.</span></li>
        <li><span><b>Exit:</b> sell half at 2× your risk (2R) and move the stop to your entry, then sell the rest at 3R, or sooner if a 5-minute candle closes under VWAP.</span></li>
        <li><span><b>Size:</b> shares = the cash you accept to lose ÷ (entry − stop). Change your account size and risk % on the Portfolio page.</span></li></ul></div>`;

    const paint = () => {
      if (!data || !$("#rnCards")) return;
      $$("#rnF button").forEach((b) => b.classList.toggle("on", b.dataset.f === filter));
      $("#rnSession").innerHTML = `<span class="pill${data.session === "open" ? " live" : ""}">${t.esc(SESSION[data.session] || "")}</span> ${data.rows.filter((x) => !x.mine).length} runners found`;
      const rows = data.rows.filter((x) => filter === "mine" ? x.mine : filter === "trade" ? (x.mine || (x.levels && x.levels.plan && !["faded", "below"].includes(x.levels.setup))) : true);
      $("#rnCards").innerHTML = rows.map(card).join("") || `<div class="card empty">${filter === "mine" ? "Track a ticker above to see its plan here." : "No runners match right now. Big movers usually show up from about 30 minutes before the US open (9:30 New York time)."}</div>`;
    };
    const load = async () => {
      const held = t.brokerPositions().map((p) => p.symbol).filter(Boolean);
      const ex = Array.from(new Set(extras().concat(held))).slice(0, 15);
      data = await t.api(`/api/runners?min=${minPct}${ex.length ? "&extra=" + encodeURIComponent(ex.join(",")) : ""}`);
      paint(); t.stamp("runners");
    };
    t.RF().runners = load;

    $("#rnF").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; filter = b.dataset.f; t.store.set("runnersFilter", filter); paint(); });
    $("#rnMin").addEventListener("change", (e) => { minPct = +e.target.value; t.store.set("runnersMin", minPct); load().catch((er) => t.toast(er.message)); });
    $("#rnAdd").addEventListener("submit", (e) => {
      e.preventDefault();
      const s = $("#rnSym").value.trim().toUpperCase();
      if (!/^[A-Z0-9.\-]{1,12}$/.test(s)) return t.toast("Type a ticker like STAK");
      const list = extras().filter((x) => x !== s); list.unshift(s); t.store.set("runnersExtra", list.slice(0, 10));
      $("#rnSym").value = ""; filter = "mine"; t.toast("Tracking " + s); load().catch((er) => t.toast(er.message));
    });
    $("#rnCards").addEventListener("click", (e) => {
      const d = e.target.closest("[data-drop]");
      if (d) { t.store.set("runnersExtra", extras().filter((x) => x !== d.dataset.drop)); return load().catch(() => {}); }
      const a = e.target.closest("[data-alert]");
      if (a && window.Trade) {
        const s = a.dataset.alert;
        window.Trade.addAlert({ symbol: s, op: ">=", price: +a.dataset.e, note: "Runner entry" });
        window.Trade.addAlert({ symbol: s, op: "<=", price: +a.dataset.s, note: "Runner stop" });
        window.Trade.addAlert({ symbol: s, op: ">=", price: +a.dataset.t1, note: "Runner: sell half (2R)" });
        window.Trade.addAlert({ symbol: s, op: ">=", price: +a.dataset.t2, note: "Runner: sell rest (3R)" });
        window.Trade.badge && window.Trade.badge();
        t.toast("Alerts set for " + s + ": entry, stop and both targets");
      }
    });

    try { await t.getT212(); } catch (e) { /* not linked */ }
    try { await load(); } catch (e) { if ($("#rnCards")) $("#rnCards").innerHTML = `<div class="card empty"><p class="error">${t.esc(e.message)}</p></div>`; }
    // while the market is open or pre-market, refresh every minute
    timer = setInterval(() => { if (!document.hidden && data && data.session !== "closed") load().catch(() => {}); }, 60000);
    return () => clearInterval(timer);
  }

  window.Runners = { page };
})();
