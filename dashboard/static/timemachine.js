/* Time Machine: "what if I had invested", your portfolio in past crashes, and a 10,000-replay trade simulator. */
(function () {
  "use strict";
  const T = () => window.TD;
  const $ = (s, el) => (el || document).querySelector(s);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  let charts = [];
  const disposeCharts = () => { charts.forEach((c) => { try { c.dispose(); } catch (e) { /* gone */ } }); charts = []; };
  function chart(el, opt) {
    const EC = window.echarts;
    if (!EC || !el) return null;
    const c = EC.init(el);
    c.setOption(Object.assign({
      backgroundColor: "transparent", animation: !matchMedia("(prefers-reduced-motion: reduce)").matches,
      textStyle: { fontFamily: "Inter", color: css("--text-secondary") },
      tooltip: { trigger: "axis", backgroundColor: "#2c2c2a", borderColor: "rgba(255,255,255,.1)", textStyle: { color: "#f0efec" } },
      grid: { left: 56, right: 14, top: 30, bottom: 30 },
    }, opt));
    new ResizeObserver(() => c.resize()).observe(el);
    charts.push(c);
    return c;
  }
  const axis = () => ({ axisLine: { lineStyle: { color: css("--axis") } }, splitLine: { lineStyle: { color: css("--grid") } }, axisLabel: { color: css("--text-muted") } });
  const short = (v) => (Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + "M" : Math.abs(v) >= 1e3 ? Math.round(v / 1e3) + "k" : Math.round(v));

  function holdings() {
    const td = T();
    const w = {};
    td.brokerPositions().forEach((p) => { w[p.symbol] = (w[p.symbol] || 0) + (p.valueAcct || p.value || (p.qty || 0) * (p.price || 0)); });
    td.store.get("manual", []).forEach((m) => { w[m.symbol] = (w[m.symbol] || 0) + m.qty * m.avgPrice; });
    return w;
  }
  const baseCcy = () => { const td = T(); return (td.state.t212 && td.state.t212.currency) || (td.state.revolut && td.state.revolut.currency) || td.settings().ccy || "EUR"; };

  async function page(view, params) {
    const td = T();
    disposeCharts();
    if (td.state.revolut === undefined) await td.getT212().catch(() => null);
    const tab = params.get("tab") || td.store.get("tmTab", "whatif");
    view.innerHTML = `<h1><i data-lucide="history" class="ico"></i> Time Machine</h1>
      <p class="sub">Go back in time with real prices: what an investment would be worth today, how your portfolio would have done in past crashes, and the odds of a trade before you place it.</p>
      <div class="seg tm-tabs" id="tmTabs" role="tablist">
        <button type="button" data-t="whatif">What if I had invested</button><button type="button" data-t="crash">Past crashes</button><button type="button" data-t="trade">Replay a trade</button></div>
      <div id="tmBody" style="margin-top:16px"></div>`;
    const show = (t) => {
      disposeCharts();
      td.store.set("tmTab", t);
      view.querySelectorAll("#tmTabs button").forEach((b) => { b.classList.toggle("on", b.dataset.t === t); b.setAttribute("aria-selected", b.dataset.t === t); });
      const body = $("#tmBody");
      ({ whatif: whatIf, crash: crashes, trade: trade })[t](body, params);
      if (window.lucide) window.lucide.createIcons();
    };
    view.querySelectorAll("#tmTabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.t)));
    show(["whatif", "crash", "trade"].includes(tab) ? tab : "whatif");
    return disposeCharts;
  }

  // ------------------------------------------------------------ 1. what if I had invested
  function whatIf(el, params) {
    const td = T(), ccy = baseCcy();
    const w = holdings();
    const mine = Object.keys(w).sort((a, b) => w[b] - w[a]).slice(0, 8);
    const saved = td.store.get("tmWhatif", {});
    const sym = (params.get("s") || saved.s || mine[0] || "VWRL.L").toUpperCase();
    el.innerHTML = `<div class="card"><form class="tm-form" id="wiF">
        <label class="field">Stock or ETF<input name="s" value="${td.esc(sym)}" autocapitalize="characters" spellcheck="false" required></label>
        <label class="field">Start<input name="start" type="month" min="1990-01" max="${new Date().toISOString().slice(0, 7)}" value="${td.esc(saved.start || "2015-01")}" required></label>
        <label class="field">Every month (${td.esc(ccy)})<input name="monthly" type="number" min="0" step="50" inputmode="decimal" value="${saved.monthly ?? (td.settings().monthly || 1200)}"></label>
        <label class="field">One-off at the start (${td.esc(ccy)})<input name="lump" type="number" min="0" step="100" inputmode="decimal" value="${saved.lump ?? 0}"></label>
        <button class="btn primary" type="submit"><i data-lucide="play"></i> Go back in time</button></form>
        ${mine.length ? `<div class="quick" style="margin-top:8px">Your holdings: ${mine.map((s) => `<button type="button" class="chip-btn sm" data-s="${td.esc(s)}">${td.esc(s)}</button>`).join("")}</div>` : ""}
        <div class="quick" style="margin-top:6px">Ideas: ${["VWRL.L", "NVDA", "ASML", "MSFT", "SPY"].map((s) => `<button type="button" class="chip-btn sm" data-s="${s}">${s}</button>`).join("")}</div></div>
      <div id="wiOut" style="margin-top:16px"></div>`;
    const f = $("#wiF", el);
    el.querySelectorAll("[data-s]").forEach((b) => b.addEventListener("click", () => { f.s.value = b.dataset.s; f.requestSubmit(); }));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const v = { s: f.s.value.trim().toUpperCase(), start: f.start.value, monthly: +f.monthly.value || 0, lump: +f.lump.value || 0 };
      td.store.set("tmWhatif", v);
      const out = $("#wiOut", el);
      out.innerHTML = `<div class="card">${td.skeleton(6)}</div>`;
      let r;
      try { r = await td.api(`/api/tm/whatif?symbol=${encodeURIComponent(v.s)}&start=${v.start}&monthly=${v.monthly}&lump=${v.lump}&base=${ccy}`); }
      catch (err) { out.innerHTML = `<div class="card"><p class="error">${td.esc(err.message)}</p></div>`; return; }
      if (!out.isConnected) return;
      const m = (x) => td.money(x, r.currency).replace(/[.,]\d\d(?=\D*$)/, "");
      const me = r.me, b = r.bench;
      const diff = b ? me.final - b.final : null;
      out.innerHTML = `<div class="card">
          <h2 style="margin-top:0">${td.logo(r.symbol, 24)} ${td.esc(r.symbol)}${r.name ? ` <span class="muted" style="font-weight:400">${td.esc(r.name)}</span>` : ""}: ${r.years} years</h2>
          <p class="tm-lead">${v.monthly ? m(v.monthly) + " a month" : ""}${v.monthly && v.lump ? " plus " : ""}${v.lump ? m(v.lump) + " at the start" : ""} since ${td.esc(r.start)} would be worth
            <b class="${td.cls(me.gain)}">${m(me.final)}</b> today, from ${m(me.totalIn)} put in.</p>
          <div class="ret-grid tm-tiles">
            <div class="perf-tile"><div class="k">You put in</div><div class="v num">${m(me.totalIn)}</div></div>
            <div class="perf-tile"><div class="k">Worth today</div><div class="v num ${td.cls(me.gain)}">${m(me.final)}</div><div class="b">${me.multiple}× your money</div></div>
            <div class="perf-tile"><div class="k">Growth a year</div><div class="v num ${td.cls(me.irr)}">${me.irr != null ? td.pct(me.irr) : "–"}</div><div class="b">on money as it went in</div></div>
            ${b ? `<div class="perf-tile"><div class="k">Same in a world fund</div><div class="v num">${m(b.final)}</div><div class="b ${td.cls(diff)}">${diff >= 0 ? "+" : ""}${m(diff)} for ${td.esc(r.symbol)}</div></div>` : ""}
            <div class="perf-tile"><div class="k">Worst price fall</div><div class="v num down">${td.pct(me.worstDrop)}</div><div class="b">month-end, in ${td.esc(r.currency)}</div></div>
          </div>
          <div id="wiChart" class="chart-box" style="height:320px;margin-top:12px"></div>
          <ul class="tm-notes">
            <li>${me.worstLoss > 0 ? `At the worst moment your account was <b>${m(me.worstLoss)}</b> (${me.worstLossPct}%) below what you had put in. Keeping the monthly buys going through that is what made the result.` : "Your account never dropped below what you had put in."}</li>
            ${b ? `<li>The world fund grew ${td.pct(b.irr)} a year with a worst fall of ${td.pct(b.worstDrop)}. ${me.irr > b.irr ? `${td.esc(r.symbol)} beat it, but it was ${Math.abs(me.worstDrop) > Math.abs(b.worstDrop) + 10 ? "a much bumpier ride" : "a similar ride"}.` : `${td.esc(r.symbol)} did worse than simply owning the world.`}</li>` : ""}
            <li>Picked with hindsight: stocks that did well are easy to choose today. Past growth like this rarely repeats.</li>
            ${r.notes.map((n) => `<li>${td.esc(n)}</li>`).join("")}</ul>
          <p class="muted" style="font-size:12px;margin:6px 0 0">Real month-end prices with dividends reinvested, converted to ${td.esc(r.currency)} at each month's exchange rate. No fees or taxes.</p></div>`;
      chart($("#wiChart", out), {
        legend: { top: 0, textStyle: { color: css("--text-secondary") } },
        tooltip: { trigger: "axis", backgroundColor: "#2c2c2a", textStyle: { color: "#f0efec" }, valueFormatter: (x) => m(x) },
        xAxis: Object.assign({ type: "category", data: r.months, boundaryGap: false }, axis()),
        yAxis: Object.assign({ type: "value" }, axis(), { axisLabel: { color: css("--text-muted"), formatter: short } }),
        series: [
          { name: r.symbol, type: "line", showSymbol: false, data: me.value, lineStyle: { width: 2.5, color: css("--series-1") }, itemStyle: { color: css("--series-1") }, areaStyle: { color: "rgba(57,135,229,.12)" } },
          ...(b ? [{ name: "World fund", type: "line", showSymbol: false, data: b.value, lineStyle: { width: 1.5, color: css("--series-2") }, itemStyle: { color: css("--series-2") } }] : []),
          { name: "Put in", type: "line", showSymbol: false, data: me.invested, lineStyle: { width: 1.5, type: "dashed", color: "#9a9891" }, itemStyle: { color: "#9a9891" } },
        ],
      });
    });
    f.requestSubmit();
  }

  // ------------------------------------------------------------ 2. your portfolio in past crashes
  async function crashes(el) {
    const td = T(), ccy = baseCcy();
    const w = holdings();
    const syms = Object.keys(w).filter((s) => w[s] > 0);
    if (!syms.length) {
      el.innerHTML = `<div class="card empty"><p>Link Trading 212, import a Revolut statement or add holdings on the <a href="#/portfolio">Portfolio page</a> to replay your portfolio through past crashes.</p></div>`;
      return;
    }
    const total = Object.values(w).reduce((a, b) => a + b, 0);
    el.innerHTML = `<div class="card">${td.skeleton(8)}<p class="muted">Replaying ${syms.length} holdings through four crashes (the first time takes about 20 seconds)…</p></div>`;
    let r;
    try { r = await td.api(`/api/tm/crashes?w=${encodeURIComponent(syms.map((s) => s + ":" + Math.round(w[s])).join(","))}&base=${ccy}&value=${Math.round(total)}`); }
    catch (err) { el.innerHTML = `<div class="card"><p class="error">${td.esc(err.message)}</p></div>`; return; }
    if (!el.isConnected) return;
    const m = (x) => td.money(x, r.base).replace(/[.,]\d\d(?=\D*$)/, "");
    const gap = r.crashes.length ? r.crashes.reduce((a, c) => a + (c.bench.drop - c.drop), 0) / r.crashes.length : 0;
    const worst = r.crashes.reduce((a, c) => (c.drop < a.drop ? c : a), r.crashes[0] || { drop: 0 });
    el.innerHTML = `<div class="card">
        <p class="tm-lead">If today's portfolio (${m(total)}) had lived through these crashes, the worst was <b>${td.esc(worst.name)}</b>: <b class="down">${td.pct(worst.drop)}</b>, about <b class="down">${m(worst.lost)}</b> down at the bottom.</p>
        <div id="crChart" class="chart-box" style="height:300px"></div>
        <p class="muted" style="font-size:12px">Your portfolio's value after each crash's market peak (0% = the peak), until it recovered.</p></div>
      <div class="grid g2" style="margin-top:16px">${r.crashes.map((c) => `<div class="card tm-crash">
        <div class="card-head"><h2 style="margin:0">${td.esc(c.name)}</h2><span class="muted" style="font-size:12px">${td.esc(c.peak)} → ${td.esc(c.trough)}</span></div>
        <div class="ret-grid">
          <div class="perf-tile"><div class="k">Your portfolio</div><div class="v num down">${td.pct(c.drop)}</div><div class="b down">${c.lost != null ? "−" + m(c.lost) : ""}</div></div>
          <div class="perf-tile"><div class="k">Back to the peak</div><div class="v num">${c.recoveryMonths != null ? c.recoveryMonths + " mo" : "not yet"}</div><div class="b">after the bottom</div></div>
          <div class="perf-tile"><div class="k">${td.esc(c.bench.name)}</div><div class="v num down">${td.pct(c.bench.drop)}</div><div class="b">${c.bench.recoveryMonths != null ? "back in " + c.bench.recoveryMonths + " mo" : "not back yet"}</div></div></div>
        <p style="margin:10px 0 4px;font-size:13.5px">Hit hardest: ${c.worst.map((x) => `${td.esc(x.symbol)} <span class="down">${td.pct(x.drop)}</span>`).join(", ") || "–"}</p>
        ${c.covered < 100 ? `<p class="muted" style="font-size:12px;margin:0">${100 - c.covered}% of today's portfolio wasn't listed yet (${c.standIn.map(td.esc).join(", ")}): the world index stands in for it.</p>` : ""}
      </div>`).join("")}</div>
      <div class="card" style="margin-top:16px"><ul class="tm-notes" style="margin:0">
        <li>${gap > 5 ? `Your mix fell on average ${gap.toFixed(0)} points more than the index in these crashes, mainly because it is concentrated in chip and AI stocks.` : gap < -5 ? "Your mix fell less than the index in these crashes." : "Your mix falls about as much as the world index in crashes."}</li>
        <li>Every crash here recovered, but some single stocks never did. Selling at the bottom is what turns a paper loss into a real one.</li>
        <li>${td.esc(r.note)}</li></ul></div>`;
    const colors = ["--series-1", "--series-2", "--series-3", "--series-4"].map(css);
    const dayN = (a, b) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
    chart($("#crChart", el), {
      legend: { top: 0, textStyle: { color: css("--text-secondary") } },
      tooltip: { trigger: "axis", backgroundColor: "#2c2c2a", textStyle: { color: "#f0efec" }, valueFormatter: (x) => (x == null ? "" : x.toFixed(1) + "%") },
      xAxis: Object.assign({ type: "value", name: "days after the peak", nameLocation: "middle", nameGap: 22, min: 0 }, axis()),
      yAxis: Object.assign({ type: "value" }, axis(), { axisLabel: { color: css("--text-muted"), formatter: "{value}%" } }),
      series: r.crashes.map((c, i) => ({ name: c.name, type: "line", showSymbol: false, data: c.path.map(([d, v]) => [dayN(c.peak, d), v]),
        lineStyle: { width: 2, color: colors[i % 4] }, itemStyle: { color: colors[i % 4] } })),
    });
  }

  // ------------------------------------------------------------ 3. replay a trade (10,000 simulated futures)
  function trade(el, params) {
    const td = T();
    const saved = td.store.get("tmTrade", {});
    const sym = (params.get("s") || saved.s || "NVDA").toUpperCase();
    el.innerHTML = `<div class="card"><form class="tm-form" id="trF">
        <label class="field">Stock<input name="s" value="${td.esc(sym)}" autocapitalize="characters" spellcheck="false" required></label>
        <label class="field">Entry<input name="entry" type="number" step="any" min="0" inputmode="decimal" required></label>
        <label class="field">Stop<input name="stop" type="number" step="any" min="0" inputmode="decimal" required></label>
        <label class="field">Target<input name="target" type="number" step="any" min="0" inputmode="decimal" required></label>
        <label class="field">Hold up to<select name="days">${[5, 10, 20, 40, 60].map((d) => `<option value="${d}" ${d === (saved.days || 20) ? "selected" : ""}>${d} trading days</option>`).join("")}</select></label>
        <button class="btn primary" type="submit"><i data-lucide="play"></i> Replay 10,000 times</button></form>
        <p class="muted" id="trHint" style="font-size:12.5px;margin:8px 0 0"></p></div>
      <div id="trOut" style="margin-top:16px"></div>`;
    const f = $("#trF", el);
    const fill = async () => {
      const s = f.s.value.trim().toUpperCase();
      $("#trHint", el).textContent = "Loading the dashboard's plan for " + s + "…";
      try {
        const a = await td.api("/api/analysis?symbol=" + encodeURIComponent(s));
        const p = a.plan || { entry: a.price, stop: +(a.price - 2 * a.atr).toFixed(2), target1: +(a.price + 4 * a.atr).toFixed(2) };
        f.entry.value = p.entry; f.stop.value = p.stop; f.target.value = p.target1;
        $("#trHint", el).textContent = a.plan ? `Filled from the dashboard's plan for ${a.symbol}: entry ${p.entry}, stop ${p.stop} (2 ATR), target ${p.target1} (2R). Change them to test your own.`
          : `No buy setup on ${a.symbol} right now: filled with price ${a.price}, stop 2 ATR below, target 2R above.`;
      } catch (e) { $("#trHint", el).textContent = e.message; }
    };
    f.s.addEventListener("change", fill);
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const v = { s: f.s.value.trim().toUpperCase(), entry: +f.entry.value, stop: +f.stop.value, target: +f.target.value, days: +f.days.value };
      td.store.set("tmTrade", { s: v.s, days: v.days });
      const out = $("#trOut", el);
      out.innerHTML = `<div class="card">${td.skeleton(6)}</div>`;
      let r;
      try { r = await td.api(`/api/tm/trade?symbol=${encodeURIComponent(v.s)}&entry=${v.entry}&stop=${v.stop}&target=${v.target}&days=${v.days}`); }
      catch (err) { out.innerHTML = `<div class="card"><p class="error">${td.esc(err.message)}</p></div>`; return; }
      if (!out.isConnected) return;
      const h = r.history;
      const tone = /target/.test(r.verdict) ? "up" : /stop/.test(r.verdict) ? "down" : "";
      out.innerHTML = `<div class="card">
          <p class="tm-lead"><b class="${tone}">${td.esc(r.verdict)}</b>${r.winRateDecided != null ? ` When a replay reached the stop or the target, the target came first ${r.winRateDecided}% of the time; at ${r.rewardR}R you need ${r.breakeven}% to break even.` : ""} Out of ${r.replays.toLocaleString()} replays of the next ${r.days} trading days:</p>
          <div class="tm-bar" role="img" aria-label="Target first ${r.target1st}%, stop first ${r.stop1st}%, neither ${r.neither}%">
            <span class="t" style="width:${r.target1st}%">${r.target1st >= 9 ? r.target1st + "%" : ""}</span><span class="s" style="width:${r.stop1st}%">${r.stop1st >= 9 ? r.stop1st + "%" : ""}</span><span class="n" style="width:${r.neither}%"></span></div>
          <div class="legend"><span><i style="background:var(--good)"></i>Target first ${r.target1st}%</span><span><i style="background:var(--bad)"></i>Stop first ${r.stop1st}%</span><span><i style="background:var(--surface-3)"></i>Neither, still open ${r.neither}%</span></div>
          <div class="ret-grid tm-tiles" style="margin-top:12px">
            <div class="perf-tile"><div class="k">Average result</div><div class="v num ${td.cls(r.avgR)}">${r.avgR >= 0 ? "+" : ""}${r.avgR}R</div><div class="b">R = what you risk to the stop</div></div>
            <div class="perf-tile"><div class="k">Wins when decided</div><div class="v num">${r.winRateDecided ?? "–"}%</div><div class="b">break-even ${r.breakeven}% at ${r.rewardR}R</div></div>
            <div class="perf-tile"><div class="k">Typical time</div><div class="v num">${r.medianDaysToHit ?? "–"} days</div><div class="b">to hit the stop or target</div></div>
            ${h ? `<div class="perf-tile"><div class="k">Real past signals</div><div class="v num">${h.n}</div><div class="b">${h.hitTarget ?? "–"}% hit 2R · ${h.expectancy != null ? (h.expectancy >= 0 ? "+" : "") + h.expectancy + "R avg" : ""}</div></div>` : ""}</div>
          <div id="trChart" class="chart-box" style="height:300px;margin-top:12px"></div>
          <div class="legend"><span><i style="background:var(--series-1)"></i>Middle path</span><span><i style="background:rgba(57,135,229,.3);height:10px"></i>8 in 10 paths</span><span style="color:var(--good-text)"><i class="dash"></i>Target</span><span style="color:var(--bad-text)"><i class="dash"></i>Stop</span></div>
          <ul class="tm-notes"><li>A bigger target needs to win less often to break even: 1 in (1 + R). At ${r.rewardR}R that's ${r.breakeven}%.</li>
            ${h ? `<li>The dashboard's own buy rule fired ${h.n} times on ${td.esc(r.symbol)} in ${h.years} years: ${h.winRate}% of those trades made money (${td.esc(h.note)})</li>` : ""}
            <li>${td.esc(r.note)}</li><li>Earnings days and news can move a stock far more than a normal day. Not advice.</li></ul></div>`;
      const days = r.bands.map((b) => (b.day === 0 ? "Now" : "D" + b.day));
      const P = (k) => r.bands.map((b) => b[k]);
      chart($("#trChart", out), {
        grid: { left: 56, right: 14, top: 14, bottom: 28 },
        tooltip: { trigger: "axis", backgroundColor: "#2c2c2a", textStyle: { color: "#f0efec" },
          formatter: (ps) => { const b = r.bands[ps[0].dataIndex]; return `<b>${days[b.day]}</b><br>Great case ${b.p90}<br>Middle <b>${b.p50}</b><br>Bad case ${b.p10}`; } },
        xAxis: Object.assign({ type: "category", data: days, boundaryGap: false }, axis()),
        yAxis: Object.assign({ type: "value", scale: true }, axis()),
        series: [
          { type: "line", data: P("p10"), stack: "b", lineStyle: { opacity: 0 }, showSymbol: false, silent: true },
          { type: "line", data: r.bands.map((b) => +(b.p90 - b.p10).toFixed(4)), stack: "b", lineStyle: { opacity: 0 }, showSymbol: false, areaStyle: { color: "rgba(57,135,229,.25)" }, silent: true },
          { type: "line", data: P("p50"), showSymbol: false, lineStyle: { width: 2.5, color: css("--series-1") },
            markLine: { symbol: "none", silent: true, label: { color: css("--text-secondary"), position: "insideStartTop" }, data: [
              { yAxis: r.target, lineStyle: { color: css("--good"), type: "dashed" }, label: { formatter: "Target " + r.target } },
              { yAxis: r.stop, lineStyle: { color: css("--bad"), type: "dashed" }, label: { formatter: "Stop " + r.stop } },
              { yAxis: r.entry, lineStyle: { color: "#9a9891", type: "dotted" }, label: { formatter: "Entry" } }] } },
        ],
      });
    });
    fill().then(() => { if (params.get("s") || saved.s) f.requestSubmit(); });
  }

  window.TimeMachine = { page };
})();
