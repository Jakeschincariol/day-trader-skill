/* 10-year plan: simulates thousands of possible futures for the portfolio plus a monthly deposit.
   Scenarios, not a forecast. Runs fully in the browser. */
(function () {
  "use strict";
  const T = () => window.TD;
  const $ = (s, el) => (el || document).querySelector(s);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  let chart = null;

  // long-run assumptions (yearly, before inflation): editable in the card
  const DEF = { etfRet: 7.5, etfVol: 15, stkRet: 11, stkVol: 42, corr: 0.75, infl: 2.5 };

  function rng(seed) { // mulberry32: same inputs give the same picture
    return function () {
      seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // monthly-rebalanced mix of a world ETF and the stock part
  function mixParams(etfShare, a) {
    const w = etfShare / 100, s = 1 - w;
    const mu = w * a.etfRet + s * a.stkRet;
    const v = Math.sqrt(w * w * a.etfVol ** 2 + s * s * a.stkVol ** 2 + 2 * w * s * a.corr * a.etfVol * a.stkVol);
    return { mu: mu / 100, vol: v / 100 };
  }

  function simulate(o, paths) {
    const { mu, vol } = mixParams(o.etf, o.a);
    const rand = rng(12345), months = o.years * 12;
    const mm = mu / 12, ms = vol / Math.sqrt(12);
    const byYear = Array.from({ length: o.years + 1 }, () => new Float64Array(paths));
    let below = 0;
    const deposits = [o.start];
    for (let y = 1, d = o.start, m = o.monthly; y <= o.years; y++) { d += 12 * m; deposits.push(d); m *= 1 + o.raise / 100; }
    for (let p = 0; p < paths; p++) {
      let v = o.start, m = o.monthly;
      byYear[0][p] = v;
      for (let i = 1; i <= months; i++) {
        const z = Math.sqrt(-2 * Math.log(rand() || 1e-12)) * Math.cos(2 * Math.PI * rand());
        v = Math.max(0, v * (1 + mm + ms * z)) + m;
        if (i % 12 === 0) { byYear[i / 12][p] = v; m *= 1 + o.raise / 100; }
      }
      if (v < deposits[o.years]) below++;
    }
    const q = (arr, f) => arr[Math.min(arr.length - 1, Math.floor(f * arr.length))];
    const pct = byYear.map((arr) => { arr.sort(); return { p10: q(arr, 0.1), p25: q(arr, 0.25), p50: q(arr, 0.5), p75: q(arr, 0.75), p90: q(arr, 0.9) }; });
    return { pct, deposits, below: below / paths, mu, vol };
  }

  function render(el, info) {
    const td = T(), st = td.settings(), ccy = info.ccy || "EUR";
    const saved = td.store.get("proj", {});
    const o = {
      start: Math.round(info.value || 0),
      monthly: st.monthly != null && st.monthly > 0 ? st.monthly : 1200,
      years: saved.years || 10,
      etf: saved.etf != null ? saved.etf : Math.round(info.etfPct || 0),
      raise: saved.raise || 0,
      a: Object.assign({}, DEF, saved.a || {}),
    };
    const m0 = (x) => td.money(x, ccy).replace(/[.,]\d\d(?=\D*$)/, "");
    el.innerHTML = `
      <div class="proj-ctl">
        <label class="field">Start value (${td.esc(ccy)})<input id="pjStart" type="number" min="0" step="100" inputmode="decimal" value="${o.start}"></label>
        <label class="field">Every month (${td.esc(ccy)})<input id="pjMon" type="number" min="0" step="50" inputmode="decimal" value="${o.monthly}"></label>
        <label class="field">Raise the deposit each year (%)<input id="pjRaise" type="number" min="0" max="20" step="1" inputmode="decimal" value="${o.raise}"></label>
        <label class="field proj-range"><span>Years: <b id="pjYv">${o.years}</b></span><input id="pjYears" type="range" min="3" max="30" step="1" value="${o.years}"></label>
        <label class="field proj-range"><span>In a world ETF: <b id="pjEv">${o.etf}%</b> <span class="muted" id="pjEnow"></span></span><input id="pjEtf" type="range" min="0" max="100" step="5" value="${o.etf}"></label>
      </div>
      <div class="ret-grid proj-tiles" id="pjTiles"></div>
      <div class="chart-box" id="pjChart" style="height:300px"></div>
      <div class="legend"><span><i style="background:var(--series-1)"></i>Middle outcome</span><span><i style="background:rgba(57,135,229,.35);height:10px"></i>Likely range (1 in 2)</span><span><i style="background:rgba(57,135,229,.15);height:10px"></i>Wide range (8 in 10)</span><span style="color:var(--text-muted)"><i class="dash"></i>Money you put in</span></div>
      <h3 class="proj-h">Same deposits, different mixes</h3>
      <div class="table-wrap"><table class="proj-tbl" id="pjCmp"></table></div>
      <div id="pjNote" class="muted" style="font-size:12.5px;margin-top:8px"></div>
      <details class="proj-adv"><summary>Assumptions (yearly, before inflation)</summary>
        <div class="proj-ctl">
          <label class="field">World ETF return %<input data-a="etfRet" type="number" step="0.5" value="${o.a.etfRet}"></label>
          <label class="field">World ETF swings %<input data-a="etfVol" type="number" step="1" min="1" value="${o.a.etfVol}"></label>
          <label class="field">Your stocks return %<input data-a="stkRet" type="number" step="0.5" value="${o.a.stkRet}"></label>
          <label class="field">Your stocks swings %<input data-a="stkVol" type="number" step="1" min="1" value="${o.a.stkVol}"></label>
          <label class="field">Inflation %<input data-a="infl" type="number" step="0.5" min="0" value="${o.a.infl}"></label>
          <button class="btn" type="button" id="pjReset">Reset</button>
        </div>
        <p class="muted" style="font-size:12.5px">World ETF (VWRL/VWCE): about 7–8% a year over the long run, swings about 15%. A concentrated chip and AI basket: higher hoped-for return, but swings of 40% or more, like most of the stocks you hold. Swings eat into growth: a big crash needs an even bigger rally to recover.</p>
      </details>`;
    if (info.etfPct != null) $("#pjEnow", el).textContent = `(today ${Math.round(info.etfPct)}%)`;

    const save = () => td.store.set("proj", { years: o.years, etf: o.etf, raise: o.raise, a: o.a });
    let raf = 0;
    const redraw = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(() => draw(el, o, ccy, m0)); };
    const num = (id, key, after) => $(id, el).addEventListener("input", (e) => { o[key] = Math.max(0, +e.target.value || 0); if (after) after(); redraw(); });
    num("#pjStart", "start");
    num("#pjMon", "monthly", () => td.store.set("settings", Object.assign(td.settings(), { monthly: o.monthly })));
    num("#pjRaise", "raise", save);
    $("#pjYears", el).addEventListener("input", (e) => { o.years = +e.target.value; $("#pjYv", el).textContent = o.years; save(); redraw(); });
    $("#pjEtf", el).addEventListener("input", (e) => { o.etf = +e.target.value; $("#pjEv", el).textContent = o.etf + "%"; save(); redraw(); });
    el.querySelectorAll("[data-a]").forEach((i) => i.addEventListener("input", () => { const v = parseFloat(i.value); if (!isNaN(v)) { o.a[i.dataset.a] = v; save(); redraw(); } }));
    $("#pjReset", el).addEventListener("click", () => { o.a = Object.assign({}, DEF); el.querySelectorAll("[data-a]").forEach((i) => (i.value = DEF[i.dataset.a])); save(); redraw(); });
    draw(el, o, ccy, m0);
  }

  function draw(el, o, ccy, m0) {
    const td = T();
    if (!$("#pjTiles", el)) return;
    const S = simulate(o, 4000), N = o.years, last = S.pct[N], put = S.deposits[N];
    const real = (x) => x / Math.pow(1 + o.a.infl / 100, N);
    $("#pjTiles", el).innerHTML = `
      <div class="perf-tile"><div class="k">You put in</div><div class="v num">${m0(put)}</div></div>
      <div class="perf-tile"><div class="k">Bad case (1 in 10)</div><div class="v num ${last.p10 < put ? "down" : ""}">${m0(last.p10)}</div></div>
      <div class="perf-tile"><div class="k">Middle</div><div class="v num">${m0(last.p50)}</div><div class="muted" style="font-size:11.5px">${m0(real(last.p50))} in today's money</div></div>
      <div class="perf-tile"><div class="k">Great case (1 in 10)</div><div class="v num up">${m0(last.p90)}</div></div>
      <div class="perf-tile"><div class="k">Chance to end below what you put in</div><div class="v num ${S.below > 0.2 ? "down" : ""}">${Math.round(100 * S.below)}%</div></div>`;

    // comparison of mixes with the same deposits
    const mk = (x) => m0(Math.round(x / 1000) * 1000).replace(/[.,]000(?=\D*$)/, "k");
    const mixes = [...new Set([0, 50, 100, o.etf])].sort((a, b) => a - b);
    const rows = mixes.map((e) => ({ e, r: e === o.etf ? S : simulate(Object.assign({}, o, { etf: e }), 2000) }));
    $("#pjCmp", el).innerHTML = `<thead><tr><th scope="col">World ETF</th><th class="r" scope="col">Bad</th><th class="r" scope="col">Middle</th><th class="r" scope="col">Great</th><th class="r" scope="col">Loss odds</th></tr></thead><tbody>
      ${rows.map(({ e, r }) => { const p = r.pct[N]; return `<tr${e === o.etf ? ' class="proj-on"' : ""}><td>${e}%${e === o.etf ? " <b>· you</b>" : ""}</td>
        <td class="r num">${mk(p.p10)}</td><td class="r num">${mk(p.p50)}</td><td class="r num">${mk(p.p90)}</td><td class="r num">${Math.round(100 * r.below)}%</td></tr>`; }).join("")}</tbody>`;
    const stockShare = 100 - o.etf;
    $("#pjNote", el).innerHTML = `Mix used: about ${(100 * S.mu).toFixed(1)}% a year hoped-for return with ${(100 * S.vol).toFixed(0)}% swings. ` +
      (stockShare >= 70 ? "Mostly single stocks: the widest range of outcomes. A world ETF core keeps the middle about the same and lifts the bad case. " : "") +
      `After ${N} years about ${Math.round(100 * (put - o.start) / Math.max(put, 1))}% of the money is your monthly deposits, so sticking to them matters most. ` +
      `Scenarios from 4,000 simulated markets, not a forecast and not advice. Taxes and fees not included.`;

    const EC = window.echarts, box = $("#pjChart", el);
    if (!EC || !box) return;
    if (chart && chart.getDom() !== box) { chart.dispose(); chart = null; }
    if (!chart) { chart = EC.init(box); new ResizeObserver(() => chart && chart.resize()).observe(box); }
    const yrs = S.pct.map((_, i) => (i === 0 ? "Now" : "Y" + i));
    const P = (k) => S.pct.map((x) => Math.round(x[k]));
    const diff = (a, b) => S.pct.map((x) => Math.round(x[a] - x[b]));
    const axis = { axisLine: { lineStyle: { color: css("--axis") } }, splitLine: { lineStyle: { color: css("--grid") } }, axisLabel: { color: css("--text-muted") } };
    const short = (v) => (v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? Math.round(v / 1e3) + "k" : v);
    chart.setOption({
      backgroundColor: "transparent", animation: false, textStyle: { fontFamily: "Inter", color: css("--text-secondary") },
      grid: { left: 52, right: 14, top: 14, bottom: 28 },
      tooltip: { trigger: "axis", backgroundColor: "#2c2c2a", borderColor: "rgba(255,255,255,.1)", textStyle: { color: "#f0efec" },
        formatter: (ps) => { const i = ps[0].dataIndex, x = S.pct[i]; return `<b>${yrs[i]}</b><br>Great case ${m0(x.p90)}<br>Middle <b>${m0(x.p50)}</b><br>Bad case ${m0(x.p10)}<br>Put in ${m0(S.deposits[i])}`; } },
      xAxis: Object.assign({ type: "category", data: yrs, boundaryGap: false }, axis),
      yAxis: Object.assign({ type: "value" }, axis, { axisLabel: { color: css("--text-muted"), formatter: short } }),
      series: [
        { type: "line", data: P("p10"), stack: "w", lineStyle: { opacity: 0 }, showSymbol: false, silent: true },
        { type: "line", data: diff("p25", "p10"), stack: "w", lineStyle: { opacity: 0 }, showSymbol: false, areaStyle: { color: "rgba(57,135,229,.15)" }, silent: true },
        { type: "line", data: diff("p75", "p25"), stack: "w", lineStyle: { opacity: 0 }, showSymbol: false, areaStyle: { color: "rgba(57,135,229,.35)" }, silent: true },
        { type: "line", data: diff("p90", "p75"), stack: "w", lineStyle: { opacity: 0 }, showSymbol: false, areaStyle: { color: "rgba(57,135,229,.15)" }, silent: true },
        { type: "line", data: P("p50"), showSymbol: false, lineStyle: { width: 2.5, color: css("--series-1") }, itemStyle: { color: css("--series-1") } },
        { type: "line", data: S.deposits.map(Math.round), showSymbol: false, lineStyle: { width: 1.5, type: "dashed", color: "#9a9891" }, itemStyle: { color: "#9a9891" } },
      ],
    }, true);
  }

  window.Projection = { render, simulate, mixParams };
})();
