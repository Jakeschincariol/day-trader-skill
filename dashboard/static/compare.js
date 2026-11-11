/* Compare 2-3 stocks or ETFs side by side: verdict scorecard, red flags, fit with my portfolio,
   quality, growth, valuation, health, risk, track record, momentum, analysts, dividends, events,
   news, and charts. Uses helpers app.js shares on window.TD. Not advice: it leans, never picks. */
(function () {
  "use strict";
  const T = () => window.TD;
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const COLORS = ["#4a95ee", "#ec835a", "#27c08a"];
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  let charts = [];

  // ------------------------------------------------------------ helpers
  const num = (x) => (typeof x === "number" && isFinite(x) ? x : null);
  const big = (v) => (v == null ? "–" : Math.abs(v) >= 1e12 ? (v / 1e12).toFixed(2) + "T" : Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(1) + "B" : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(0) + "M" : T().fmt(v, 0));
  const p1 = (v) => (v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(1) + "%");
  const p0 = (v) => (v == null ? "–" : v.toFixed(0) + "%");
  const x2 = (v) => (v == null ? "–" : v.toFixed(2));
  const avg = (xs) => { const v = xs.filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };

  async function get(path) { try { return await T().api(path); } catch (e) { return null; } }

  async function loadPick(sym, lt) {
    const e = encodeURIComponent(sym);
    const [a, l, f, bt, sb, news] = await Promise.all([
      get("/api/analysis?symbol=" + e), get("/api/lt?symbol=" + e), get("/api/fundamentals?symbol=" + e),
      get("/api/ltbacktest?symbol=" + e), lt ? null : get("/api/backtest?symbol=" + e), get("/api/news?symbols=" + e),
    ]);
    if (!a) throw new Error("No data for " + sym);
    return { sym, a, l: l || {}, f: f && f.available ? f : null, bt, sb, news: news || [] };
  }

  // derived numbers per pick (data the expert asked for)
  function derive(P) {
    const f = P.f, h = f ? f.highlights : {}, v = f ? f.valuation : {};
    const ann = f ? (f.revVsEarnings.annual || []).filter((x) => x.revenue) : [];
    const revCagr = ann.length >= 3 ? Math.pow(ann[ann.length - 1].revenue / ann[0].revenue, 1 / (ann.length - 1)) - 1 : null;
    const q = f ? f.earnings || [] : [];
    const yoy = q.map((x) => x.epsYoY).filter((x) => x != null);
    const fcfMargin = h.freeCashFlow != null && h.revenueTTM ? 100 * h.freeCashFlow / h.revenueTTM : null;
    const ebitda = v.enterpriseValue && v.evEbitda ? v.enterpriseValue / v.evEbitda : null;
    const netCash = h.totalCash != null && h.totalDebt != null ? h.totalCash - h.totalDebt : null;
    const an = f ? f.analyst || {} : {};
    const tot = (an.buy || 0) + (an.hold || 0) + (an.sell || 0);
    const divAmt = f ? parseFloat(String(h.dividend || "").replace(/[^0-9.]/g, "")) || null : null;
    const yld = f ? parseFloat(String(h.dividendYield || "").replace("%", "")) || null : null;
    const isTech = /tech|software|semicon/i.test((f && (f.sector + " " + f.industry)) || "");
    return {
      roe: num(h.roe), opm: num(h.operatingMargin), npm: num(h.profitMargin), fcfm: fcfMargin,
      profYears: ann.length ? ann.filter((x) => x.netIncome > 0).length : null, nYears: ann.length,
      revCagr: revCagr != null ? 100 * revCagr : null, epsAvg: yoy.length ? avg(yoy.slice(-4)) : null,
      epsCons: yoy.length >= 4 ? 100 * yoy.slice(-8).filter((x) => x > 0).length / yoy.slice(-8).length : null,
      fwdGrowth: v.peTTM && v.forwardPE ? 100 * (v.peTTM / v.forwardPE - 1) : null,
      rule40: isTech && revCagr != null && fcfMargin != null ? 100 * revCagr + fcfMargin : null,
      fpe: num(v.forwardPE), pe: num(v.peTTM), peg: num(v.peg), evEbitda: num(v.evEbitda), ps: num(v.priceSales),
      fcfYield: h.freeCashFlow && v.marketCap ? 100 * h.freeCashFlow / v.marketCap : null,
      netCash, de: num(h.debtEquity), ndEbitda: netCash != null && ebitda ? -netCash / ebitda : null,
      upside: num(an.upside), buyPct: tot ? 100 * an.buy / tot : null, dispersion: an.avg ? 100 * (an.high - an.low) / an.avg : null,
      yld, payout: divAmt && h.epsTTM ? 100 * divAmt / h.epsTTM : null,
      mcap: num(v.marketCap), sector: f ? f.sector : P.l.sector, margins: ann.map((x) => x.margin),
    };
  }

  function redFlags(P, D) {
    const out = [];
    const m = D.margins.filter((x) => x != null);
    if (m.length >= 3 && m[m.length - 1] < m[0] - 3) out.push(`Profit margin shrinking (${m[0].toFixed(0)}% → ${m[m.length - 1].toFixed(0)}%)`);
    const ann = P.f ? P.f.revVsEarnings.annual : [];
    if (ann.length >= 2) { const a = ann[ann.length - 2], b = ann[ann.length - 1]; if (b.revenue > a.revenue && b.netIncome < a.netIncome) out.push("Revenue up but profit down last year"); }
    const yoy = P.f ? (P.f.earnings || []).slice(-4).map((x) => x.epsYoY).filter((x) => x != null) : [];
    if (yoy.filter((x) => x < 0).length >= 2) out.push(`EPS fell year-over-year in ${yoy.filter((x) => x < 0).length} of the last 4 quarters`);
    if (D.fwdGrowth != null && D.fwdGrowth < 0) out.push("Analysts expect lower earnings next year");
    if (D.upside != null && D.upside < -2) out.push(`Price is above the average analyst target (${D.upside.toFixed(0)}%)`);
    if (D.ndEbitda != null && D.ndEbitda > 3) out.push(`High debt: net debt ${D.ndEbitda.toFixed(1)}× EBITDA`);
    if (D.payout != null && D.payout > 100) out.push(`Pays out more than it earns (payout ${D.payout.toFixed(0)}%)`);
    if (P.l.zone === "Speculative") out.push("Long-term score in the Speculative band");
    if (P.a.earnings && P.a.earnings.days <= 10) out.push(`Earnings in ${P.a.earnings.days} day${P.a.earnings.days === 1 ? "" : "s"} (${P.a.earnings.date}): expect a big move`);
    return out;
  }

  // ------------------------------------------------------------ rows and scoring
  // better: "high" | "low" | "mid" (RSI 40-65 best) ; tie when within 5% relative of the best
  function sections(picks, R, fit) {
    const S = (k) => (p) => (R && R.stats[p.sym] ? R.stats[p.sym][k] : null);
    const L = (k) => (p) => p.l[k] ?? null;
    const H = (k) => (p) => (p.l.history || {})[k] ?? null;
    const D = (k) => (p) => p.D[k];
    const B = (y, k) => (p) => (((p.bt || {}).me || {}).lump || {})[y]?.[k] ?? null;
    const A = (k) => (p) => p.a[k] ?? null;
    const anyF = picks.some((p) => p.f);
    return [
      { id: "fit", name: "Fit with my portfolio", rows: fit ? [
        { label: "You own today (incl. inside ETFs)", get: (p) => fit.expNow[p.sym], fmt: (v) => p1(v).replace("+", ""), better: "low", hint: "lower adds more diversity" },
        { label: `Your share if you invest ${fit.amountLabel}`, get: (p) => fit.expAfter[p.sym], fmt: (v) => p1(v).replace("+", ""), better: "low", flag: (v) => v > 10, hint: "after this purchase · change the amount above" },
        { label: "Moves with your portfolio (correlation)", get: (p) => R && R.portfolio ? R.portfolio.fit[p.sym]?.corr : null, fmt: x2, better: "low", hint: "1 = moves exactly like it" },
        { label: `Portfolio swings if you add ${R && R.portfolio ? R.portfolio.addPct : 10}%`, get: (p) => R && R.portfolio ? R.portfolio.fit[p.sym]?.volAfter : null, fmt: (v) => v == null ? "–" : v.toFixed(1) + "%", better: "low", hint: R && R.portfolio ? `today ${R.portfolio.volNow}%` : "" },
        { label: "Same theme as your holdings", get: (p) => fit.sameTheme[p.sym] ? 1 : 0, fmt: (v) => (v ? "yes" : "no"), better: "low" },
      ] : [] },
      { id: "quality", name: "Business quality", rows: !anyF ? [] : [
        { label: "Return on equity", get: D("roe"), fmt: p0, better: "high" },
        { label: "Operating margin", get: D("opm"), fmt: p0, better: "high" },
        { label: "Free-cash-flow margin", get: D("fcfm"), fmt: p0, better: "high" },
        { label: "Profit margin", get: D("npm"), fmt: p0, better: "high" },
        { label: "Profitable years", get: D("profYears"), fmt: (v, p) => v == null ? "–" : `${v} of ${p.D.nYears}`, better: "high" },
      ] },
      { id: "growth", name: "Growth", rows: !anyF ? [] : [
        { label: "Revenue growth a year", get: D("revCagr"), fmt: p1, better: "high" },
        { label: "EPS growth (last 4 quarters)", get: D("epsAvg"), fmt: p1, better: "high" },
        { label: "Quarters with EPS growth", get: D("epsCons"), fmt: p0, better: "high" },
        { label: "Expected EPS growth next year", get: D("fwdGrowth"), fmt: p1, better: "high" },
        { label: "Rule of 40 (tech)", get: D("rule40"), fmt: (v) => v == null ? "–" : v.toFixed(0), better: "high", hint: "growth % + FCF margin %; 40+ is strong" },
      ] },
      { id: "valuation", name: "Valuation", rows: [
        ...(anyF ? [
          { label: "Forward P/E", get: D("fpe"), fmt: x2, better: "low" },
          { label: "PEG", get: D("peg"), fmt: x2, better: "low", hint: "<1.5 attractive, >3 pricey" },
          { label: "EV / EBITDA", get: D("evEbitda"), fmt: x2, better: "low" },
          { label: "Price / sales", get: D("ps"), fmt: x2, better: "low" },
          { label: "Free-cash-flow yield", get: D("fcfYield"), fmt: (v) => v == null ? "–" : v.toFixed(1) + "%", better: "high" },
        ] : []),
        { label: "P/E vs its own 2-year range", get: L("pePercentile"), fmt: (v) => v == null ? "–" : v <= 33 ? `low (${v})` : v >= 90 ? `high (${v})` : `middle (${v})`, better: "low", hint: "0 = cheapest it has been" },
        { label: "Price vs 200-day average", get: L("z200"), fmt: p1, better: "low" },
      ] },
      { id: "health", name: "Financial health", rows: !anyF ? [] : [
        { label: "Net cash (cash − debt)", get: D("netCash"), fmt: big, better: "high" },
        { label: "Debt / equity", get: D("de"), fmt: p0, better: "low" },
        { label: "Net debt / EBITDA", get: D("ndEbitda"), fmt: (v) => v == null ? "–" : v < 0 ? "net cash" : v.toFixed(1) + "×", better: "low", flag: (v) => v > 3 },
      ] },
      { id: "risk", name: "Risk (5 years)", rows: [
        { label: "Price swings (volatility)", get: S("vol"), fmt: (v) => v == null ? "–" : v.toFixed(0) + "%", better: "low" },
        { label: "Moves vs the market (beta)", get: S("beta"), fmt: x2, better: "low", hint: "1 = like the S&P 500" },
        { label: "Worst fall", get: S("maxdd"), fmt: p0, better: "high" },
        { label: "Time back to the old high", get: S("recoveryDays"), fmt: (v, p) => R && R.stats[p.sym] && !R.stats[p.sym].recovered ? "not yet" : v == null ? "–" : v >= 250 ? (v / 252).toFixed(1) + " yrs" : Math.round(v / 21) + " months", better: "low" },
        { label: "Worst 12 months", get: S("worst12m"), fmt: p0, better: "high" },
        { label: "Return per unit of risk (Sharpe)", get: S("sharpe"), fmt: x2, better: "high" },
        { label: "Falls captured when the market falls", get: S("downCapture"), fmt: p0, better: "low" },
        { label: "Rises captured when the market rises", get: S("upCapture"), fmt: p0, better: "high" },
        ...((R && R.symbols ? Object.keys(R.stats[R.symbols[0]].crashes || {}) : []).map((c) => ({ label: c, get: (p) => R.stats[p.sym]?.crashes?.[c] ?? null, fmt: p0, better: "high" }))),
      ] },
      { id: "track", name: "Long-term track record", rows: [
        { label: "Return a year, 3y", get: B("3", "cagr"), fmt: p1, better: "high" },
        { label: "Return a year, 5y", get: B("5", "cagr"), fmt: p1, better: "high" },
        { label: "Return a year, 10y", get: B("10", "cagr"), fmt: p1, better: "high" },
        { label: R && R.base ? `Return a year in ${R.base} (5y)` : "Return a year (5y, shared days)", get: (p) => R && R.stats[p.sym] ? (R.stats[p.sym].cagrBase ?? R.stats[p.sym].cagr) : null, fmt: p1, better: "high" },
        { label: "Worst calendar year", get: B("5", "worstYear"), fmt: p0, better: "high" },
        { label: "Monthly investing, return a year (5y)", get: (p) => p.bt?.me?.dca?.irr ?? null, fmt: p1, better: "high" },
        { label: "12-month periods that ended up", get: (p) => p.bt?.me?.dca?.positiveYears ?? null, fmt: p0, better: "high" },
      ] },
      { id: "momentum", name: "Price & momentum", rows: [
        { label: "Today", get: A("changePct"), fmt: p1, better: "high", noScore: true },
        { label: "12 months", get: A("ret1y"), fmt: p1, better: "high" },
        { label: "3 months", get: A("ret3m"), fmt: p1, better: "high" },
        { label: "Position in 52-week range", get: L("range52"), fmt: p0, better: "high" },
        { label: "From all-time high", get: L("fromATH"), fmt: p0, better: "high" },
        { label: "RSI (14)", get: A("rsi"), fmt: (v) => v == null ? "–" : v.toFixed(0), better: "mid" },
        { label: "Swing signal score", get: A("score"), fmt: (v) => v == null ? "–" : v, better: "high" },
      ] },
      { id: "swingbt", name: "Swing signal backtest", rows: [
        { label: "Average per trade", get: (p) => p.sb?.expectancy ?? null, fmt: (v) => v == null ? "–" : (v > 0 ? "+" : "") + v + "R", better: "high" },
        { label: "Hit the 2R target", get: (p) => p.sb?.hitTarget ?? null, fmt: p0, better: "high" },
      ] },
      { id: "analysts", name: "Analysts", rows: !anyF ? [] : [
        { label: "Upside to average target", get: D("upside"), fmt: p1, better: "high" },
        { label: "Analysts saying buy", get: D("buyPct"), fmt: p0, better: "high" },
        { label: "Disagreement (target spread)", get: D("dispersion"), fmt: p0, better: "low", hint: "lower = analysts agree more" },
      ] },
      { id: "dividends", name: "Dividends", rows: !anyF ? [] : [
        { label: "Dividend yield", get: D("yld"), fmt: (v) => v == null ? "none" : v.toFixed(2) + "%", better: "high" },
        { label: "Payout of earnings", get: D("payout"), fmt: p0, better: "low", flag: (v) => v > 80 },
      ] },
      { id: "events", name: "Upcoming events", rows: [
        { label: "Next earnings", get: (p) => p.a.earnings ? p.a.earnings.days : null, fmt: (v, p) => v == null ? "–" : `${p.a.earnings.date} (${v}d)`, better: "high", flag: (v) => v <= 10 },
      ] },
    ].filter((s) => s.rows.length);
  }

  function scoreRow(row, picks) {
    const vals = picks.map((p) => { const v = row.get(p); return typeof v === "number" && isFinite(v) ? v : null; });
    const have = vals.filter((v) => v != null);
    if (have.length < 2 || row.noScore) return { vals, pts: picks.map(() => null) };
    const key = (v) => (row.better === "mid" ? -Math.abs(v - 52) : row.better === "low" ? -v : v);
    const best = Math.max(...have.map(key));
    const span = Math.max(1e-9, Math.abs(best) * 0.05, row.better === "mid" ? 3 : 0);
    const win = vals.map((v) => (v == null ? null : best - key(v) <= span));
    const nWin = win.filter(Boolean).length;
    const pts = win.map((w) => (w == null ? null : nWin === have.length ? 0.5 : w ? 1 : 0));
    return { vals, pts };
  }

  const WEIGHTS = {
    lt: { quality: 20, growth: 15, valuation: 15, health: 10, risk: 15, track: 10, fit: 15, momentum: 0, swingbt: 0, analysts: 5, dividends: 0, events: 0 },
    swing: { quality: 0, growth: 0, valuation: 5, health: 0, risk: 20, track: 0, fit: 10, momentum: 35, swingbt: 20, analysts: 0, dividends: 0, events: 10 },
  };

  function scorecard(secs, picks, mode, income) {
    const W = Object.assign({}, WEIGHTS[mode]);
    if (mode === "lt" && income) W.dividends = 10;
    const tot = picks.map(() => ({ w: 0, s: 0, checks: 0, all: 0 }));
    const per = {};
    for (const sec of secs) {
      const rows = sec.rows.map((row) => Object.assign({ row }, scoreRow(row, picks)));
      sec.scored = rows;
      const ss = picks.map((_, i) => { const p = rows.map((x) => x.pts[i]).filter((x) => x != null); return p.length ? p.reduce((a, b) => a + b, 0) / p.length : null; });
      sec.secScore = ss;
      rows.forEach((x) => x.pts.forEach((pt, i) => { tot[i].all++; if (pt != null) tot[i].checks++; }));
      const w = W[sec.id] || 0;
      if (!w) continue;
      ss.forEach((v, i) => { if (v != null) { tot[i].w += w; tot[i].s += w * v; } });
      per[sec.id] = ss;
    }
    return tot.map((t) => ({ score: t.w ? Math.round(100 * t.s / t.w) : null, checks: t.checks, all: t.all }));
  }

  // ------------------------------------------------------------ portfolio exposure (look-through)
  async function fitInfo(picks, amount) {
    const td = T();
    const manual = td.store.get("manual", []);
    const pos = td.brokerPositions().map((p) => ({ symbol: p.symbol, v: p.source !== "Trading 212" && p.valueAcct != null ? p.valueAcct : (p.qty || 0) * (p.price || 0) })).concat(manual.map((m) => ({ symbol: m.symbol, v: m.qty * m.avgPrice })));
    if (!pos.length) return null;
    const L = await get("/api/lookthrough");
    const total = pos.reduce((a, p) => a + p.v, 0);
    const exp = (sym, extraSym, extraV) => {
      let e = 0;
      const all = pos.concat(extraSym ? [{ symbol: extraSym, v: extraV }] : []);
      for (const p of all) {
        const idx = L && Object.values(L.indexes).find((x) => x.funds.includes(p.symbol));
        if (p.symbol === sym) e += p.v;
        else if (idx && idx.weights[sym]) e += p.v * idx.weights[sym] / 100;
      }
      return e;
    };
    const expNow = {}, expAfter = {}, sameTheme = {};
    const themes = (await get("/api/themes")) || {};
    const held = new Set(pos.map((p) => p.symbol));
    for (const P of picks) {
      expNow[P.sym] = total ? 100 * exp(P.sym) / total : 0;
      expAfter[P.sym] = 100 * exp(P.sym, P.sym, amount) / (total + amount);
      const th = themes[P.sym];
      sameTheme[P.sym] = !!th && [...held].some((h) => h !== P.sym && themes[h] === th);
    }
    const weights = {};
    pos.forEach((p) => { weights[p.symbol] = (weights[p.symbol] || 0) + p.v / total; });
    const t = td.state.t212 && !td.state.t212.error ? td.state.t212 : null;
    const rv = td.state.revolut && td.state.revolut.linked ? td.state.revolut : null;
    const ccy = t ? t.currency : rv ? rv.currency : (td.settings().ccy || "USD");
    return { expNow, expAfter, sameTheme, weights, total, amount, amountLabel: td.money(amount, ccy).replace(/[.,]00(?=\D*$)/, "") };
  }

  // ------------------------------------------------------------ charts (ECharts)
  function chartsInit(R, picks) {
    charts.forEach((c) => c.dispose()); charts = [];
    const EC = window.echarts;
    if (!EC || !R) return;
    const base = { backgroundColor: "transparent", textStyle: { fontFamily: "Inter", color: css("--text-secondary") },
      tooltip: { trigger: "axis", backgroundColor: "#2c2c2a", borderColor: "rgba(255,255,255,.1)", textStyle: { color: "#f0efec" } },
      grid: { left: 46, right: 16, top: 30, bottom: 30 }, animation: !matchMedia("(prefers-reduced-motion: reduce)").matches };
    const axis = { axisLine: { lineStyle: { color: css("--axis") } }, splitLine: { lineStyle: { color: css("--grid") } }, axisLabel: { color: css("--text-muted") } };
    const mk = (id, opt) => { const el = $("#" + id); if (!el) return; const c = EC.init(el); c.setOption(Object.assign({}, base, opt)); charts.push(c); new ResizeObserver(() => c.resize()).observe(el); };
    const legend = { top: 0, textStyle: { color: css("--text-secondary") } };
    mk("cmpNorm", { legend, xAxis: Object.assign({ type: "category", data: R.dates, boundaryGap: false }, axis), yAxis: Object.assign({ type: "log" }, axis), grid: { left: 46, right: 16, top: 56, bottom: 30 },
      series: R.symbols.map((s, i) => ({ name: s, type: "line", showSymbol: false, data: R.norm[s], lineStyle: { width: 2, color: COLORS[i] }, itemStyle: { color: COLORS[i] } }))
        .concat([{ name: "S&P 500", type: "line", showSymbol: false, data: R.norm[R.benchmark], lineStyle: { width: 1.5, type: "dashed", color: "#9a9891" }, itemStyle: { color: "#9a9891" } },
          { name: `${R.symbols.length === 2 ? "50/50" : "Equal"} split`, type: "line", showSymbol: false, data: R.blend, lineStyle: { width: 1.5, type: "dotted", color: "#f0efec" }, itemStyle: { color: "#f0efec" } }]) });
    mk("cmpDD", { legend, xAxis: Object.assign({ type: "category", data: R.dates, boundaryGap: false }, axis), yAxis: Object.assign({ type: "value", max: 0, axisLabel: { formatter: "{value}%", color: css("--text-muted") } }, axis),
      series: R.symbols.map((s, i) => ({ name: s, type: "line", showSymbol: false, data: R.drawdown[s], lineStyle: { width: 1.5, color: COLORS[i] }, itemStyle: { color: COLORS[i] }, areaStyle: { color: COLORS[i], opacity: 0.12 } })) });
    const pts = R.symbols.map((s, i) => ({ name: s, value: [R.stats[s].vol, R.stats[s].cagr], itemStyle: { color: COLORS[i] } }))
      .concat([{ name: "S&P 500", value: [R.bench.vol, R.bench.cagr], itemStyle: { color: "#9a9891" } }, { name: "Split", value: [R.blendStats.vol, R.blendStats.cagr], itemStyle: { color: "#f0efec" } }]);
    mk("cmpScatter", { tooltip: { trigger: "item", formatter: (p) => `${p.name}<br>swings ${p.value[0]}% · return ${p.value[1]}% a year`, backgroundColor: "#2c2c2a", textStyle: { color: "#f0efec" } },
      xAxis: Object.assign({ type: "value", name: "swings (volatility %)", nameLocation: "middle", nameGap: 24, scale: true }, axis), yAxis: Object.assign({ type: "value", name: "return a year %", scale: true }, axis),
      series: [{ type: "scatter", symbolSize: 16, data: pts, label: { show: true, formatter: "{b}", position: "right", color: css("--text-primary") } }] });
    const groups = ["Quality", "Growth", "Valuation", "Balance sheet", "Trend", "Dividend"].filter((g) => picks.some((p) => (p.l.groups || {})[g] != null));
    if (groups.length >= 3) mk("cmpRadar", { tooltip: { trigger: "item" }, legend, radar: { indicator: groups.map((g) => ({ name: g, max: 100 })), splitLine: { lineStyle: { color: css("--grid") } }, splitArea: { show: false }, axisName: { color: css("--text-secondary") } },
      series: [{ type: "radar", data: picks.map((p, i) => ({ name: p.sym, value: groups.map((g) => (p.l.groups || {})[g] ?? 0), lineStyle: { color: COLORS[i], width: 2 }, itemStyle: { color: COLORS[i] }, areaStyle: { color: COLORS[i], opacity: 0.12 } })) }] });
  }

  // ------------------------------------------------------------ pick for me (expert method; best odds, never a forecast)
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const isFund = (p) => !p.f && /ETF|MUTUALFUND/i.test(p.a.type || "");
  function minmax(vals) {
    const v = vals.filter((x) => x != null);
    const lo = Math.min(...v), hi = Math.max(...v);
    return vals.map((x) => (x == null ? 0.5 : hi > lo ? (x - lo) / (hi - lo) : 0.5));
  }
  function expectedReturn(p, R) {
    const st = (R && R.stats[p.sym]) || {};
    if (!p.f) {
      const raw = 0.5 * (st.median12m ?? st.cagr ?? 0) + 0.5 * (st.cagrBase ?? st.cagr ?? 0);
      return clamp(7 + 0.5 * (raw - 7), -5, 20); // shrunk toward 7%: past fund returns rarely repeat in full
    }
    const D = p.D;
    const g = D.fwdGrowth ?? D.epsAvg ?? 0;
    const er = 0.4 * Math.min(g, 25) + 0.3 * (D.fcfYield ?? 0) + 0.3 * clamp((D.upside ?? 0) * (D.buyPct ?? 50) / 100, -10, 20) + (D.yld ?? 0);
    return clamp(er, -5, 20);
  }
  function vetoes(p, R, fit) {
    const v = [];
    if (p.l.zone === "Speculative") v.push("speculative long-term score");
    if (p.f && p.l.score != null && p.l.score < 40) v.push(`long-term score only ${p.l.score}`);
    if (p.flags.length >= 3) v.push(`${p.flags.length} red flags`);
    if (p.D.ndEbitda != null && p.D.ndEbitda > 4) v.push("too much debt");
    if (fit && !isFund(p) && fit.expNow[p.sym] > 15) v.push(`you already own ${fit.expNow[p.sym].toFixed(0)}% of your portfolio in it`);
    const hy = R && R.stats[p.sym] ? R.stats[p.sym].historyYears : null;
    if (hy != null && hy < 1) v.push("less than a year of price history");
    return v;
  }
  function rankLT(picks, R, fit) {
    const el = picks.map((p) => ({ p, veto: vetoes(p, R, fit), er: expectedReturn(p, R) }));
    const ok = el.filter((x) => !x.veto.length);
    if (!ok.length) return { el, ok };
    const st = (x) => (R && R.stats[x.p.sym]) || {};
    const nER = minmax(ok.map((x) => x.er));
    const nSort = minmax(ok.map((x) => st(x).sortino ?? st(x).sharpe));
    ok.forEach((x, i) => {
      const dd = st(x).maxdd != null ? Math.max(0, 1 - Math.abs(st(x).maxdd) / 60) : 0.5;
      const val = (x.p.l.groups || {}).Valuation != null ? x.p.l.groups.Valuation / 100 : x.p.l.pePercentile != null ? 1 - x.p.l.pePercentile / 100 : 0.5;
      const pc = R && R.portfolio && R.portfolio.fit[x.p.sym] ? R.portfolio.fit[x.p.sym].corr : null;
      const fitT = pc != null ? clamp(1 - pc, 0, 1) : 0.5;
      x.terms = { er: nER[i], sortino: nSort[i], lt: (x.p.l.score ?? 50) / 100, dd, val, fit: fitT };
      let sc = 100 * (0.30 * nER[i] + 0.20 * nSort[i] + 0.15 * x.terms.lt + 0.15 * dd + 0.10 * val + 0.10 * fitT);
      sc -= 5 * x.p.flags.length;
      if (x.p.a.earnings && x.p.a.earnings.days <= 10) sc -= 5;
      if (x.p.l.zone === "Stretched") sc -= 5;
      const hy = R && R.stats[x.p.sym] ? R.stats[x.p.sym].historyYears : null;
      x.young = hy != null && hy < 3;
      if (x.young) sc -= 5; // a short track record makes every number less reliable
      x.rank = Math.round(sc);
    });
    ok.sort((a, b) => (b.rank - a.rank) || ((st(b).maxdd ?? -99) - (st(a).maxdd ?? -99)) || (isFund(b.p) - isFund(a.p)));
    return { el, ok };
  }
  function rankSwing(picks, R) {
    const el = picks.map((p) => {
      const veto = [];
      if (p.a.earnings && p.a.earnings.days <= 10) veto.push(`earnings in ${p.a.earnings.days} days`);
      if (!p.sb || p.sb.expectancy == null || p.sb.expectancy <= 0) veto.push("its signal has not paid off in the backtest");
      return { p, veto };
    });
    const ok = el.filter((x) => !x.veto.length);
    if (!ok.length) return { el, ok };
    const nExp = minmax(ok.map((x) => x.p.sb.expectancy)), nMom = minmax(ok.map((x) => x.p.a.ret3m)), nVol = minmax(ok.map((x) => -((R && R.stats[x.p.sym] || {}).vol ?? 30)));
    ok.forEach((x, i) => {
      const rsiT = x.p.a.rsi != null ? clamp(1 - Math.abs(x.p.a.rsi - 52) / 30, 0, 1) : 0.5;
      x.rank = Math.round(100 * (0.35 * (x.p.a.score ?? 50) / 100 + 0.25 * nExp[i] + 0.20 * rsiT + 0.10 * nMom[i] + 0.10 * nVol[i]));
      x.terms = { signal: (x.p.a.score ?? 50) / 100, exp: nExp[i], rsi: rsiT, mom: nMom[i] };
    });
    ok.sort((a, b) => b.rank - a.rank);
    return { el, ok };
  }
  // the most you can put in a single company and keep it under 10% of the portfolio
  function maxAmount(p, fit) {
    if (!fit || isFund(p) || !fit.total) return null;
    const cur = fit.expNow[p.sym] / 100 * fit.total;
    return Math.max(0, (0.1 * fit.total - cur) / 0.9);
  }
  function sizeNote(p, fit, amount, m) {
    const mx = maxAmount(p, fit);
    if (mx == null || !amount || fit.expAfter[p.sym] <= 10) return "";
    return `<p class="tk-warn" style="list-style:none;margin:8px 0">⚠ ${mx < 25 ? `You already own enough ${T().esc(p.sym)}: adding more pushes it over 10% of your portfolio.` : `Invest at most about ${m(mx)} in ${T().esc(p.sym)} to keep it under 10% of your portfolio (${m(amount)} would make it ${fit.expAfter[p.sym].toFixed(0)}%). Put the rest in the core or a broad ETF.`}</p>`;
  }
  function reasonsFor(x, R, others) {
    const td = T(), st = (R && R.stats[x.p.sym]) || {}, D = x.p.D, out = [];
    const o = others.map((y) => (R && R.stats[y.p.sym]) || {});
    if (st.crashes && st.crashes["2022 bear market"] != null) {
      const worse = others.filter((y) => (R.stats[y.p.sym]?.crashes?.["2022 bear market"] ?? 0) < st.crashes["2022 bear market"]);
      if (worse.length) out.push(`Lost ${Math.abs(st.crashes["2022 bear market"]).toFixed(0)}% in 2022 vs ${worse.map((y) => `${Math.abs(R.stats[y.p.sym].crashes["2022 bear market"]).toFixed(0)}% for ${y.p.sym}`).join(", ")}`);
    }
    if (D.fpe != null) out.push(`Forward P/E ${D.fpe.toFixed(0)}${D.upside != null ? `, analysts see ${D.upside > 0 ? "+" : ""}${D.upside.toFixed(0)}%` : ""}`);
    if (D.fwdGrowth != null && D.fwdGrowth > 5) out.push(`Earnings expected to grow ${D.fwdGrowth.toFixed(0)}% next year`);
    if (st.sortino != null && o.every((y) => (y.sortino ?? -9) < st.sortino)) out.push(`Best return for its downside risk (Sortino ${st.sortino})`);
    if (x.terms && x.terms.fit > 0.5 && R && R.portfolio) out.push("Adds the least overlap with your portfolio");
    if (st.cagrBase != null) out.push(`${st.cagrBase > 0 ? "+" : ""}${st.cagrBase}% a year over the last ${R.years} years in ${R.base}`);
    if (x.p.l.zone === "Accumulate+") out.push("Good business currently on sale");
    return out.slice(0, 3).map(td.esc);
  }
  const PROFILES = { cautious: { label: "Cautious", sat: 0.2, L: 0.05 }, balanced: { label: "Balanced", sat: 0.35, L: 0.08 }, bold: { label: "Bold", sat: 0.5, L: 0.12 } };
  function pairPlan(picks, R, fit, profile) {
    const st = (p) => (R && R.stats[p.sym]) || {};
    const ok = picks.filter((p) => !vetoes(p, R, fit).length);
    const risk = (p) => 0.4 * (st(p).vol ?? 50) + 0.4 * Math.abs(st(p).maxdd ?? 60) + 0.2 * (st(p).beta ?? 1.5) * 20;
    const coreOk = ok.filter((p) => isFund(p) || (p.l.score ?? 0) >= 55);
    if (picks.length < 2 || !ok.length) return { why: "No pick passes the basic checks, so no pair." };
    if (coreOk.length < 1) coreOk.push(...ok.filter((p) => (p.l.score ?? 0) >= 45)); // no strong core: use the steadiest acceptable one, flagged below
    if (coreOk.length < 1) return { why: "No pick is solid enough to be the core (needs a long-term score of 45+, or a broad fund)." };
    const funds = coreOk.filter(isFund);
    const core = (funds.length ? funds : coreOk).slice().sort((a, b) => risk(a) - risk(b))[0];
    const sats = ok.filter((p) => p !== core && (p.l.score ?? 50) >= 45 && p.flags.length <= 2 && (st(p).vol ?? 0) >= 1.15 * (st(core).vol ?? 0))
      .sort((a, b) => expectedReturn(b, R) - expectedReturn(a, R));
    if (!sats.length) return { core, why: "None of the others swings clearly more than the core (needs 15%+ more volatility and acceptable quality), so a pair adds little: use the single pick." };
    const sat = sats[0];
    const pk = R.corr[`${core.sym}|${sat.sym}`] !== undefined || (R.pairBlend && R.pairBlend[`${core.sym}|${sat.sym}`]) ? [core.sym, sat.sym] : [sat.sym, core.sym];
    const c = R.corr[pk.join("|")];
    if (c != null && c > 0.85) return { core, sat, why: `${core.sym} and ${sat.sym} move almost the same way (correlation ${c}): a pair doesn't spread risk. Use the single pick.` };
    const hot = (st(core).vol > 40 || st(core).beta > 1.5) && (st(sat).vol > 40 || st(sat).beta > 1.5);
    if (!st(sat).recovered && Math.abs(st(sat).maxdd ?? 0) > 70) return { core, sat, why: `${sat.sym} fell over 70% and hasn't recovered: too risky as a satellite.` };
    const P = PROFILES[profile];
    const loss = Math.abs(st(sat).crashes?.["2022 bear market"] ?? st(sat).maxdd ?? 50) / 100 || 0.5;
    let w = Math.min(P.sat, P.L / loss);
    w = Math.max(0.1, Math.round(w * 20) / 20);
    const capped = w < P.sat - 1e-9;
    const pb = R.pairBlend && R.pairBlend[pk.join("|")];
    const wFirst = pk[0] === core.sym ? 1 - w : w;
    const near = pb ? Object.keys(pb).sort((a, b) => Math.abs(+a - wFirst) - Math.abs(+b - wFirst))[0] : null;
    return { core, sat, w, capped, corr: c, blend: near ? pb[near] : null, P, hot };
  }

  function pickHtml(picks, R, fit, mode, amount) {
    const td = T();
    const base = (R && R.base) || "USD";
    const m = (v) => td.money(v, base).replace(/[.,]00(?=\D*$)/, "");
    const ranked = mode === "lt" ? rankLT(picks, R, fit) : rankSwing(picks, R);
    const { el, ok } = ranked;
    const excluded = el.filter((x) => x.veto.length);
    let single;
    if (!ok.length) {
      single = `<div class="pick-head bad"><b>None of these passes the basic checks.</b> Consider a broad, low-cost ETF instead (for example VWRL.L or CSPX.L).</div>`;
    } else {
      const top = ok[0], second = ok[1];
      const lead = second ? top.rank - second.rank : 99;
      const winsCore = top.terms && ok.length > 1 ? ["er", "sortino", "dd"].filter((k) => ok.every((y) => y === top || (top.terms[k] ?? 0) >= (y.terms[k] ?? 0))).length : 3;
      const conf = !second ? "Medium" : lead >= 12 && !top.young && !top.p.flags.length && (mode !== "lt" || (top.p.l.score ?? 0) >= 65) && winsCore >= 2 ? "High" : lead >= 6 ? "Medium" : "Low";
      const st = (R && R.stats[top.p.sym]) || {};
      single = `${conf === "Low" ? `<p class="sec" style="font-size:13px;margin:0 0 8px">Close call (${top.p.sym} ${top.rank} vs ${second.p.sym} ${second.rank}): splitting between them is also reasonable.</p>` : ""}<div class="pick-head good">${td.logo(top.p.sym, 34)}<div><span class="muted" style="font-size:12px">${conf === "Low" ? "Slight edge" : mode === "lt" ? "Best risk-adjusted odds" : "Best swing setup"}</span><br><b style="font-size:22px">${td.esc(top.p.sym)}</b> <span class="badge ${conf === "High" ? "b-strongbuy" : conf === "Low" ? "e-wait" : "b-hold"}">${conf} confidence</span></div></div>
          <ul class="reasons" style="margin:10px 0">${reasonsFor(top, R, ok.filter((y) => y !== top)).map((r) => `<li>${r}</li>`).join("")}</ul>
          ${top.young ? `<p class="muted" style="font-size:12.5px;margin:0 0 6px">Note: ${td.esc(top.p.sym)} has only ${R.stats[top.p.sym].historyYears} years of price history, so its risk numbers are less reliable.</p>` : ""}
          ${top.p.flags.filter((f) => !/of your portfolio/.test(f)).length ? `<ul class="tk-warn">${top.p.flags.filter((f) => !/of your portfolio/.test(f)).slice(0, 2).map((f) => `<li>${td.esc(f)}</li>`).join("")}</ul>` : ""}
          ${sizeNote(top.p, fit, amount, m)}
          ${amount && st.crashes && st.crashes["2022 bear market"] != null && mode === "lt" ? `<p class="sec" style="font-size:13px;margin:6px 0">If 2022 repeated, ${m(amount)} in ${td.esc(top.p.sym)} would have dropped to about ${m(amount * (1 + st.crashes["2022 bear market"] / 100))}. Typical 12 months: ${td.pct(st.median12m, 0)}.</p>` : ""}
          <p class="muted" style="font-size:12px;margin:4px 0 0">Ranking: ${ok.map((x) => `${td.esc(x.p.sym)} ${x.rank}`).join(" · ")}${mode === "lt" ? " (expected return 30%, return for downside risk 20%, long-term score 15%, worst fall 15%, valuation 10%, portfolio fit 10%, minus penalties)" : " (signal 35%, backtest 25%, RSI 20%, 3-month momentum 10%, calmness 10%)"}.</p>`;
    }
    const excl = excluded.length ? `<p class="muted" style="font-size:12.5px;margin:8px 0 0">Excluded: ${excluded.map((x) => `<b>${td.esc(x.p.sym)}</b> (${td.esc(x.veto.join(", "))})`).join(" · ")}</p>` : "";
    if (mode !== "lt") return `<div class="pick-col">${single}${excl}<p class="muted" style="font-size:12px">Swing mode: size by the stop on the stock page's order ticket, not by a % split.</p></div>`;
    const profile = td.settings().pickProfile || "balanced";
    const pp = pairPlan(picks, R, fit, profile);
    let pair;
    if (!pp.sat || pp.why) {
      pair = `<p class="sec" style="font-size:13.5px">${td.esc(pp.why || "No valid pair.")}</p>`;
    } else {
      const wc = 1 - pp.w, b = pp.blend;
      const pf = R.portfolio && R.portfolio.fit[pp.sat.sym];
      pair = `<div class="pair-grid">
          <div class="pair-side" style="--c:#4a95ee">${td.logo(pp.core.sym, 28)}<div><span class="muted" style="font-size:12px">Calmer core</span><br><b>${td.esc(pp.core.sym)}</b></div><div class="pair-amt"><b class="num">${Math.round(100 * wc)}%</b><span class="num">${amount ? m(amount * wc) : ""}</span></div></div>
          <div class="pair-side" style="--c:#ec835a">${td.logo(pp.sat.sym, 28)}<div><span class="muted" style="font-size:12px">Higher-growth satellite</span><br><b>${td.esc(pp.sat.sym)}</b></div><div class="pair-amt"><b class="num">${Math.round(100 * pp.w)}%</b><span class="num">${amount ? m(amount * pp.w) : ""}</span></div></div>
        </div>
        <div class="seg" id="pickProf" style="margin:10px 0">${Object.entries(PROFILES).map(([k, v]) => `<button type="button" data-p="${k}" class="${k === profile ? "on" : ""}">${v.label} ${Math.round(100 * (1 - v.sat))}/${Math.round(100 * v.sat)}</button>`).join("")}</div>
        ${amount ? sizeNote(pp.sat, fit, amount * pp.w, m) : ""}
        ${pp.hot ? `<p class="tk-warn" style="list-style:none;margin:8px 0">⚠ High-risk pair: both swing a lot (${td.esc(pp.core.sym)} ${R.stats[pp.core.sym].vol}%, ${td.esc(pp.sat.sym)} ${R.stats[pp.sat.sym].vol}% a year), so there's no truly calm core. For a steadier mix, use a broad ETF such as VWRL.L or CSPX.L as the core instead.</p>` : ""}
        ${pp.capped ? `<p class="muted" style="font-size:12.5px;margin:0 0 6px">The satellite is held to ${Math.round(100 * pp.w)}% (not ${Math.round(100 * pp.P.sat)}%) so a 2022-style fall in it costs at most about ${Math.round(100 * pp.P.L)}% of your amount.</p>` : ""}
        ${b && R.years < 3 ? `<p class="tk-warn" style="list-style:none;margin:8px 0">⚠ Only ${R.years} years of shared history (since ${R.from}), because ${R.symbols.filter((x) => (R.stats[x].historyYears ?? 9) < 3).map(td.esc).join(", ")} listed recently. These figures come from one short period and are probably too optimistic: don't expect them to repeat.</p>` : ""}
        ${b ? `<div class="ret-grid"><div class="perf-tile"><div class="k">This mix, a year (${R.years}y)</div><div class="v num ${td.cls(b.cagr)}">${td.pct(b.cagr, 1)}</div></div>
          <div class="perf-tile"><div class="k">Worst fall</div><div class="v num down">${td.pct(b.maxdd, 0)}</div></div>
          <div class="perf-tile"><div class="k">Worst 12 months</div><div class="v num down">${td.pct(b.worst12m, 0)}</div>${amount ? `<div class="b">about ${m(amount * b.worst12m / 100)}</div>` : ""}</div>
          <div class="perf-tile"><div class="k">Typical 12 months</div><div class="v num ${td.cls(b.median12m)}">${td.pct(b.median12m, 0)}</div>${amount ? `<div class="b">about ${m(amount * b.median12m / 100)}</div>` : ""}</div>
          <div class="perf-tile"><div class="k">If 2022 repeated</div><div class="v num down">${td.pct(b.crashes["2022 bear market"], 0)}</div>${amount && b.crashes["2022 bear market"] != null ? `<div class="b">about ${m(amount * b.crashes["2022 bear market"] / 100)}</div>` : ""}</div></div>` : ""}
        <ul class="reasons" style="margin:10px 0 0">
          <li>${td.esc(pp.core.sym)}: ${reasonsFor({ p: pp.core, terms: {} }, R, [{ p: pp.sat }]).slice(0, 2).join("; ") || "the steadier of the two"}</li>
          <li>${td.esc(pp.sat.sym)}: ${reasonsFor({ p: pp.sat, terms: {} }, R, [{ p: pp.core }]).slice(0, 2).join("; ") || "more upside, bigger swings"}</li>
          ${pp.corr != null ? `<li class="${pp.corr < 0.6 ? "" : "no"}">They move together ${pp.corr < 0.4 ? "little" : pp.corr < 0.6 ? "moderately" : "a lot"} (correlation ${pp.corr})</li>` : ""}
          ${pf && R.portfolio ? `<li class="${pf.volAfter <= R.portfolio.volNow + 2 ? "" : "no"}">Your portfolio swings ${R.portfolio.volNow}% → ${pf.volAfter}% if the whole amount went to ${td.esc(pp.sat.sym)}</li>` : ""}
          ${fit && fit.expAfter[pp.sat.sym] > 10 ? `<li class="no">Keep ${td.esc(pp.sat.sym)} under 10% of your whole portfolio</li>` : ""}
        </ul>
        ${R.equalRisk ? `<p class="muted" style="font-size:12px;margin:6px 0 0">Neutral reference (equal risk): ${Object.entries(R.equalRisk).map(([s, w]) => `${td.esc(s)} ${w}%`).join(" · ")}.</p>` : ""}`;
    }
    return `<div class="pick-grid"><div class="pick-col"><h3 class="h3">One pick</h3>${single}${excl}</div><div class="pick-col"><h3 class="h3">Or a pair: calmer core + higher-growth satellite</h3>${pair}</div></div>`;
  }

  // saved picks: record today's choice, see later how it actually did
  function savePick(picks, R, mode, fit) {
    const td = T(), log = td.store.get("pickLog", []);
    const ranked = mode === "lt" ? rankLT(picks, R, fit) : rankSwing(picks, R);
    const pp = mode === "lt" ? pairPlan(picks, R, fit, td.settings().pickProfile || "balanced") : {};
    const top = ranked.ok[0], second = ranked.ok[1];
    const tie = top && second && top.rank - second.rank < 6;
    log.unshift({ date: new Date().toISOString().slice(0, 10), mode, syms: picks.map((p) => p.sym), pick: top && !tie ? top.p.sym : null, tie: tie ? [top.p.sym, second.p.sym] : null,
      pair: pp.sat && !pp.why ? { core: pp.core.sym, sat: pp.sat.sym, w: pp.w } : null, prices: Object.fromEntries(picks.map((p) => [p.sym, p.a.price])) });
    td.store.set("pickLog", log.slice(0, 30));
    td.toast("Saved: come back later to see how it did");
  }
  async function pickLogHtml(el) {
    const td = T(), log = td.store.get("pickLog", []);
    if (!log.length) { el.innerHTML = `<p class="muted" style="font-size:13px">Save a pick to track how it really does over the next months.</p>`; return; }
    const syms = [...new Set(log.flatMap((l) => l.syms))];
    const quotes = await td.api("/api/spark?symbols=" + encodeURIComponent(syms.join(","))).catch(() => []);
    const now = Object.fromEntries(quotes.map((q) => [q.symbol, q.price]));
    const ch = (l, s) => (now[s] && l.prices[s] ? 100 * (now[s] / l.prices[s] - 1) : null);
    el.innerHTML = `<div class="table-wrap"><table class="kvt"><thead><tr><th scope="col">Saved</th><th scope="col">Compared</th><th scope="col">Pick</th><th class="r" scope="col">Pick since</th><th class="r" scope="col">Others since</th></tr></thead><tbody>
      ${log.map((l) => { const others = l.syms.filter((s) => s !== l.pick); const pc = l.pick ? ch(l, l.pick) : null;
        return `<tr><td>${l.date}</td><td>${l.syms.map(td.esc).join(", ")}</td><td><b>${td.esc(l.pick || (l.tie ? "tie: " + l.tie.join(" / ") : "none"))}</b>${l.pair ? `<span class="nm">pair ${td.esc(l.pair.core)} ${Math.round(100 * (1 - l.pair.w))}% / ${td.esc(l.pair.sat)} ${Math.round(100 * l.pair.w)}%</span>` : ""}</td>
          <td class="r num ${td.cls(pc)}">${pc == null ? "–" : td.pct(pc, 1)}</td><td class="r num">${others.map((s) => { const v = ch(l, s); return `${td.esc(s)} <span class="${td.cls(v)}">${v == null ? "–" : td.pct(v, 1)}</span>`; }).join(" · ")}</td></tr>`; }).join("")}
      </tbody></table></div><p class="muted" style="font-size:12px">Price change since the day you saved it (dividends not included). An honest check of how good these picks really are.</p>`;
  }

  // ------------------------------------------------------------ page
  async function page(view, params) {
    const td = T();
    let syms = (params.get("s") || td.store.get("compare", []).join(",")).split(",").map((s) => s.trim().toUpperCase()).filter(Boolean).slice(0, 3);
    const save = () => td.store.set("compare", syms);
    const mode = td.isLT() ? "lt" : "swing";
    const st = td.settings();
    view.innerHTML = `<div class="card-head" style="margin-bottom:4px"><h1 style="margin:0"><i data-lucide="git-compare-arrows" class="ico"></i> Compare</h1></div>
      <p class="sub">Hesitating between 2 or 3 stocks or ETFs? Line them up: quality, growth, valuation, risk, track record, and how each fits <b>your</b> portfolio. The scorecard leans; it never decides for you.</p>
      <div class="card" style="margin-bottom:16px">
        <div class="cmp-pick" id="cmpChips"></div>
        <form id="cmpForm" class="cmp-add" autocomplete="off"><input id="cmpIn" placeholder="Add a stock or ETF (e.g. MSFT, VUSA.L)…" aria-label="Add a stock or ETF to compare"><ul id="cmpRes" class="dropdown" hidden></ul><button class="btn primary" type="submit">Add</button></form>
        <div class="cmp-quick" id="cmpQuick"></div>
        <div class="form-row" style="max-width:640px;margin-top:10px">
          <label class="field">Amount you plan to invest<input id="cmpAmt" type="number" min="0" step="50" inputmode="decimal" value="${st.cmpAmount || 1000}"></label>
          <label class="check"><input type="checkbox" id="cmpInc" ${st.cmpIncome ? "checked" : ""}> I invest for dividend income</label>
        </div>
      </div>
      <div id="cmpBody"></div>`;
    const chips = () => {
      $("#cmpChips").innerHTML = syms.map((s, i) => `<span class="cmp-chip" style="--c:${COLORS[i]}">${td.logo(s, 22)}<b>${td.esc(s)}</b><button type="button" data-rm="${td.esc(s)}" aria-label="Remove ${td.esc(s)}">✕</button></span>`).join("") || `<span class="muted">Pick at least two.</span>`;
      $$("[data-rm]", view).forEach((b) => b.addEventListener("click", () => { syms = syms.filter((x) => x !== b.dataset.rm); save(); chips(); run(); }));
      const quick = [...new Set(td.watchlist().concat(td.brokerPositions().map((p) => p.symbol)))].filter((s) => !syms.includes(s)).slice(0, 10);
      $("#cmpQuick").innerHTML = syms.length < 3 && quick.length ? `<span class="muted" style="font-size:12.5px">Quick add:</span> ` + quick.map((s) => `<button type="button" class="btn sm" data-add="${td.esc(s)}">${td.esc(s)}</button>`).join(" ") : "";
      $$("[data-add]", view).forEach((b) => b.addEventListener("click", () => add(b.dataset.add)));
    };
    const add = (s) => { s = s.trim().toUpperCase(); if (!s || syms.includes(s)) return; if (syms.length >= 3) { td.toast("Compare up to 3 at a time"); return; } syms.push(s); save(); chips(); run(); };
    let timer, found = [];
    $("#cmpIn").addEventListener("input", (e) => {
      clearTimeout(timer); const q = e.target.value.trim();
      if (!q) { $("#cmpRes").hidden = true; return; }
      timer = setTimeout(async () => {
        found = (await get("/api/search?q=" + encodeURIComponent(q))) || [];
        $("#cmpRes").innerHTML = found.slice(0, 8).map((x) => `<li><a href="#" data-pick="${td.esc(x.symbol)}"><span><b>${td.esc(x.symbol)}</b> <span class="muted">${td.esc(x.name || "")}</span></span><span class="muted">${td.esc(x.type || "")} · ${td.esc(x.exchange || "")}</span></a></li>`).join("");
        $("#cmpRes").hidden = !found.length;
        $$("[data-pick]", view).forEach((a) => a.addEventListener("click", (ev) => { ev.preventDefault(); add(a.dataset.pick); $("#cmpIn").value = ""; $("#cmpRes").hidden = true; }));
      }, 250);
    });
    $("#cmpForm").addEventListener("submit", (e) => { e.preventDefault(); const v = $("#cmpIn").value; add(found[0] && found[0].symbol.toUpperCase().startsWith(v.trim().toUpperCase()) ? found[0].symbol : v); $("#cmpIn").value = ""; $("#cmpRes").hidden = true; });
    $("#cmpAmt").addEventListener("change", (e) => { td.store.set("settings", Object.assign(td.settings(), { cmpAmount: +e.target.value || 0 })); run(); });
    $("#cmpInc").addEventListener("change", (e) => { td.store.set("settings", Object.assign(td.settings(), { cmpIncome: e.target.checked })); run(); });
    chips();
    let seq = 0;
    async function run() {
      const my = ++seq, body = $("#cmpBody");
      if (syms.length < 2) { body.innerHTML = `<div class="card empty">Add two or three stocks or ETFs to compare. Tip: the <b>Compare</b> button on any stock page adds it here.</div>`; return; }
      body.innerHTML = `<div class="card">${td.skeleton(10)}<p class="muted" style="font-size:13px">Loading 10 years of history and fundamentals for ${syms.map(td.esc).join(", ")}…</p></div>`;
      if (!td.state.t212Status) await td.getT212().catch(() => null);
      let picks;
      try { picks = await Promise.all(syms.map((s) => loadPick(s, mode === "lt"))); }
      catch (e) { if (my === seq) body.innerHTML = `<div class="card"><p class="error">${td.esc(e.message)}</p></div>`; return; }
      if (my !== seq || !body.isConnected) return; // the user moved on while it loaded
      picks.forEach((p) => { p.D = derive(p); p.flags = redFlags(p, p.D); });
      const amount = +$("#cmpAmt").value || 0;
      const fit = await fitInfo(picks, amount);
      const acct = window.Trade ? await window.Trade.account().catch(() => null) : null;
      const base = acct ? acct.ccy : null;
      const pf = fit ? Object.entries(fit.weights).map(([k, w]) => `${k}:${w.toFixed(4)}`).join(",") : "";
      const addFrac = fit && fit.total ? Math.min(0.5, Math.max(0.01, amount / (fit.total + amount))) : 0.1;
      const R = await get(`/api/compare?symbols=${encodeURIComponent(syms.join(","))}&base=${base || ""}&pf=${encodeURIComponent(pf)}&add=${addFrac.toFixed(3)}`);
      if (my !== seq || !body.isConnected) return;
      const mixed = picks.some((p) => p.f) && picks.some((p) => !p.f);
      const secs = sections(picks, R, fit);
      const sc = scorecard(secs, picks, mode, $("#cmpInc").checked);
      render(body, picks, secs, sc, R, fit, mode, mixed, amount);
    }
    run();
    return () => { charts.forEach((c) => c.dispose()); charts = []; };
  }

  function render(body, picks, secs, sc, R, fit, mode, mixed, amount) {
    const td = T();
    const order = picks.map((p, i) => ({ p, i, s: sc[i].score ?? -1 })).sort((a, b) => b.s - a.s);
    const top = order[0], second = order[1];
    const close = second && top.s - second.s <= 5;
    const W = WEIGHTS[mode];
    let gapSec = null, gapVal = 0;
    for (const sec of secs) {
      if (!W[sec.id] || !sec.secScore) continue;
      const a = sec.secScore[top.i], b = sec.secScore[second.i];
      if (a != null && b != null && Math.abs(a - b) > gapVal) { gapVal = Math.abs(a - b); gapSec = sec.name; }
    }
    const hard = (p) => p.flags.filter((f) => /Speculative|debt|more than it earns|Earnings in [0-3] day/.test(f)).concat(fit && fit.expAfter[p.sym] > 10
      ? [`${fit.amountLabel} would make ${p.sym} ${fit.expAfter[p.sym].toFixed(0)}% of your portfolio (aim for under ~10%)`] : []);
    const who = mode === "lt" ? "a long-term investor" : "a swing trade";
    const headline = close
      ? `Too close to call (${top.s} vs ${second.s}): split it, or decide on ${gapSec || "what matters most to you"}.`
      : `Leans ${top.p.sym} for ${who} (${top.s} vs ${second.s}${order[2] ? " vs " + order[2].s : ""}).${hard(top.p).length ? ` But check its red flag first.` : ""}`;
    const bestWorst = (i) => {
      const rows = secs.filter((s) => s.secScore && s.secScore[i] != null && (W[s.id] || s.id === "fit"));
      const b = rows.slice().sort((a, c) => c.secScore[i] - a.secScore[i])[0], w = rows.slice().sort((a, c) => a.secScore[i] - c.secScore[i])[0];
      return b && w ? `Best at ${b.name.toLowerCase()} · weakest at ${w.name.toLowerCase()}` : "";
    };
    const cols = picks.length;
    const headRow = `<div class="cmp-row cmp-head" style="--n:${cols}"><span></span>${picks.map((p, i) => `<span style="color:${COLORS[i]}">${td.logo(p.sym, 20)} ${td.esc(p.sym)}</span>`).join("")}</div>`;
    const secHtml = secs.map((sec) => `<details class="card cmp-sec" ${["fit", "quality", "valuation", "risk", "track"].includes(sec.id) || mode === "swing" && ["momentum", "swingbt"].includes(sec.id) ? "open" : ""}>
      <summary><h2>${td.esc(sec.name)}</h2><span class="cmp-dots">${picks.map((p, i) => sec.secScore[i] == null ? "" : `<span title="${td.esc(p.sym)}: ${Math.round(100 * sec.secScore[i])}/100" style="--c:${COLORS[i]}" class="sdot">${Math.round(100 * sec.secScore[i])}</span>`).join("")}</span>
        <span class="muted" style="font-size:12px">${W[sec.id] ? "weight " + W[sec.id] : "not scored in this mode"}</span></summary>
      ${headRow}
      ${sec.scored.map((x) => `<div class="cmp-row" style="--n:${cols}"><span class="cmp-label">${td.esc(x.row.label)}${x.row.hint ? `<small>${td.esc(x.row.hint)}</small>` : ""}</span>
        ${picks.map((p, i) => { const v = x.vals[i], raw = x.row.get(p); const win = x.pts[i] === 1; const fl = x.row.flag && v != null && x.row.flag(v);
          return `<span class="cmp-val ${win ? "win" : ""} ${fl ? "flag" : ""}">${win ? `<i class="wdot" style="background:${COLORS[i]}"></i>` : ""}${td.esc(String(x.row.fmt(v ?? (typeof raw === "number" ? raw : null), p)))}</span>`; }).join("")}</div>`).join("")}
    </details>`).join("");
    const corr = R ? Object.entries(R.corr).map(([k, v]) => `${k.replace("|", " & ")}: <b>${v}</b>`).join(" · ") : "";
    const rs = R ? R.stats : {};
    const bestCagr = R ? Math.max(...R.symbols.map((s) => rs[s].cagr)) : null;
    body.innerHTML = `
      <a class="cmp-jump" href="#" id="cmpJump"><i data-lucide="arrow-down-circle"></i> The result and "Pick for me" are at the end, after all the details. Jump there</a>
      ${R ? `<div class="grid g2" style="margin-top:16px">
        <div class="card"><h2>Growth of 100 (dividends in)</h2><div id="cmpNorm" class="cmp-chart"></div><p class="muted" style="font-size:12px">${R.from} → ${R.to}, log scale. Dashed: S&P 500 · dotted: the same money split equally, rebalanced monthly.</p></div>
        <div class="card"><h2>Falls from the peak</h2><div id="cmpDD" class="cmp-chart"></div><p class="muted" style="font-size:12px">How deep each fell and how long it stayed under water: could you have held through it?</p></div>
        <div class="card"><h2>Risk vs return (5 years)</h2><div id="cmpScatter" class="cmp-chart"></div><p class="muted" style="font-size:12px">Up and to the left is best: more return for fewer swings.</p></div>
        <div class="card"><h2>Long-term score groups</h2><div id="cmpRadar" class="cmp-chart"></div></div>
      </div>
      <div class="card" style="margin-top:16px"><h2>Pick one, or split?</h2>
        <div class="ret-grid">
          <div class="perf-tile"><div class="k">${R.symbols.length === 2 ? "50/50" : "Equal"} split, a year</div><div class="v num ${td.cls(R.blendStats.cagr)}">${p1(R.blendStats.cagr)}</div><div class="b">worst fall ${p0(R.blendStats.maxdd)} · swings ${R.blendStats.vol}%</div></div>
          ${R.symbols.map((s, i) => `<div class="perf-tile" style="border-left:3px solid ${COLORS[i]}"><div class="k">${td.esc(s)} alone</div><div class="v num ${td.cls(rs[s].cagr)}">${p1(rs[s].cagr)}</div><div class="b">worst fall ${p0(rs[s].maxdd)} · swings ${rs[s].vol}%</div></div>`).join("")}
          <div class="perf-tile"><div class="k">Cost of not picking the best</div><div class="v num">${(bestCagr - R.blendStats.cagr).toFixed(1)} pts</div><div class="b">a year, with hindsight</div></div>
        </div>
        <p class="sec" style="font-size:13.5px;margin:10px 0 4px">They move together: ${corr} <span class="muted">(1 = identical, 0 = unrelated)</span>. ${Object.values(R.corr).every((c) => c < 0.6) ? "Low enough that splitting genuinely spreads your risk." : "Quite similar: splitting won't diversify much."}</p>
        ${R.equalRisk ? `<p class="sec" style="font-size:13.5px;margin:4px 0">For equal risk instead of equal money: ${R.symbols.map((s) => `<b>${R.equalRisk[s]}%</b> ${td.esc(s)}`).join(" · ")}${amount ? ` → ${R.symbols.map((s) => `${td.money(amount * R.equalRisk[s] / 100, R.base || "USD")} ${td.esc(s)}`).join(", ")}` : ""}.</p>` : ""}
        ${amount && R.symbols.some((s) => rs[s].crashes && rs[s].crashes["2022 bear market"] != null) ? `<p class="sec" style="font-size:13.5px;margin:4px 0">In a 2022-style bear market your ${td.money(amount, R.base || "USD")} would have dropped by about ${R.symbols.map((s) => `${td.money(-amount * (rs[s].crashes["2022 bear market"] || 0) / 100, R.base || "USD")} in ${td.esc(s)}`).join(", ")}.</p>` : ""}
      </div>` : ""}
      ${secHtml}
      <div class="card" style="margin-top:16px"><h2>Latest news</h2><div class="grid g${cols === 3 ? "3" : "2"}">${picks.map((p, i) => `<div><h3 class="h3" style="color:${COLORS[i]}">${td.esc(p.sym)}</h3>
        ${p.news.slice(0, 4).map((n) => `<a class="news-item" style="padding:8px 0;background:none;border:0;border-bottom:1px solid var(--grid);border-radius:0" href="${/^https?:/.test(n.link) ? td.esc(n.link) : "#"}" target="_blank" rel="noopener noreferrer"><div><div class="t" style="font-size:13.5px">${td.esc(n.title)}</div><div class="m">${td.esc(n.publisher || "")} ${(n.tags || []).map((t) => `<span class="tag ${/legal|deal/.test(t) ? "earn" : ""}">#${td.esc(t)}</span>`).join("")}</div></div></a>`).join("") || `<p class="muted">No recent headlines.</p>`}</div>`).join("")}</div></div>
      <div id="cmpResult" class="cmp-result-anchor"></div>
      <div class="card cmp-verdict" style="margin-top:16px">
        <h2 style="margin:0 0 4px">${td.esc(headline)}</h2>
        <p class="muted" style="margin:0 0 12px;font-size:13px">${mode === "lt" ? "Long-term weights: quality 20, growth 15, valuation 15, risk 15, fit 15, health 10, track record 10, analysts 5" : "Swing weights: momentum 35, risk 20, signal backtest 20, events 10, fit 10, valuation 5"}${$("#cmpInc").checked && mode === "lt" ? ", dividends 10" : ""}. Switch Long-term / Swing in the header.</p>
        <div class="cmp-cards" style="--n:${cols}">${picks.map((p, i) => `<div class="cmp-card" style="--c:${COLORS[i]}">
          <div class="cand-top">${td.logo(p.sym, 34)}<div style="flex:1;min-width:0"><a class="sym" href="#/stock/${encodeURIComponent(p.sym)}">${td.esc(p.sym)}</a><span class="nm">${td.esc(p.a.name || "")}</span></div>${window.TChart.ring(sc[i].score ?? 0, 60, "Comparison score")}</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin:8px 0">${window.LT ? window.LT.bandBadge(p.l.band) + " " + window.LT.zoneBadge(p.l.zone) : ""}</div>
          <div class="num" style="font-size:18px;font-weight:600">${td.priceStr(p.a.price, p.a.currency)} <span class="${td.cls(p.a.changePct)}" style="font-size:13px">${td.pct(p.a.changePct)}</span></div>
          <p class="sec" style="font-size:12.5px;margin:6px 0">${td.esc(bestWorst(i))}</p>
          <p class="muted" style="font-size:11.5px;margin:0">based on ${sc[i].checks} of ${sc[i].all} checks${p.f ? "" : " (no company fundamentals: track record & risk only)"}</p>
          ${p.flags.length || hard(p).length ? `<ul class="tk-warn" style="margin-top:8px">${[...new Set(hard(p).concat(p.flags))].map((f) => `<li>${td.esc(f)}</li>`).join("")}</ul>` : `<p class="tk-ok" style="margin-top:8px">✓ No red flags found</p>`}
        </div>`).join("")}</div>
        ${R && R.years < 4.5 ? `<p class="muted" style="font-size:12.5px">Risk and return rows use the ${R.years} years all picks share (${R.from} → ${R.to}), because ${R.symbols.filter((x) => (R.stats[x].historyYears ?? 9) < 4.5).map(T().esc).join(", ")} listed more recently.</p>` : ""}
        ${mixed ? `<p class="muted" style="font-size:12.5px">You're comparing a company with a fund (or a non-US listing): company-only checks show "–" for the fund and don't count against it.</p>` : ""}
      </div>
      <div class="card pick-card" style="margin-top:16px"><div class="card-head"><h2><i data-lucide="sparkles"></i>Pick for me</h2><button class="btn sm" type="button" id="pickSave"><i data-lucide="bookmark-plus"></i> Save this pick</button></div>
        <div id="pickBox">${pickHtml(picks, R, fit, mode, amount)}</div>
        <p class="muted" style="font-size:12px;margin:10px 0 0">Based on the last ${R ? R.years : 5} years of shared prices and current analyst data. Past results don't predict future returns. Nobody knows which will be most profitable. This is information, not advice.</p></div>
      <div class="card chal-card" style="margin-top:16px"><div class="card-head"><h2><i data-lucide="swords"></i>Challenger: is there something better than all of these?</h2></div><div id="chalBox"></div></div>
      <div class="card" style="margin-top:16px"><h2>Your saved picks</h2><div id="pickLog"></div></div>
      <p class="muted" style="font-size:12px;margin-top:12px">Past returns don't predict future ones. Company fundamentals come from Nasdaq.com (Zacks) for US listings only. ETF look-through weights are approximate. Returns ignore fees and tax${R && R.base ? "; the home-currency row converts with daily FX rates" : " and FX"}. This is a decision aid, not financial advice.</p>`;
    chartsInit(R, picks);
    $("#cmpJump", body).addEventListener("click", (e) => { e.preventDefault(); $("#cmpResult", body).scrollIntoView({ behavior: "smooth" }); });
    const wire = () => $$("#pickProf button", body).forEach((b) => b.addEventListener("click", () => {
      td.store.set("settings", Object.assign(td.settings(), { pickProfile: b.dataset.p }));
      $("#pickBox", body).innerHTML = pickHtml(picks, R, fit, mode, amount); wire();
    }));
    wire();
    $("#pickSave", body).addEventListener("click", () => { savePick(picks, R, mode, fit); pickLogHtml($("#pickLog", body)); });
    pickLogHtml($("#pickLog", body));
    loadChallenger($("#chalBox", body), picks.map((p) => p.sym));
  }


  // ------------------------------------------------------------ challenger: something that beats every pick
  function challengerHtml(c, syms) {
    const td = T();
    const why = (w) => {
      const b = c.picks.slice().sort((x, y) => y.score - x.score)[0];
      return `long-term score <b>${w.score}</b> vs best pick ${b.score} · return per unit of risk <b>${w.sortino}</b> vs ${c.bar.sortino} · worst fall ${td.pct(w.maxdd, 0)} · ${td.pct(w.cagr, 0)} a year over ${w.years}y`;
    };
    const weakest = c.picks.slice().sort((x, y) => x.score - y.score)[0].symbol;
    const swap = (s) => syms.map((x) => (x === weakest ? s : x)).join(",");
    const card = (title, sub, g) => {
      const w = g.winner;
      if (!w) {
        const n = g.closest;
        return `<div class="chal"><h3 class="h3">${title}</h3><p class="chal-none">No stock in this group beats all of your picks${g.searched ? ` (${g.searched} checked)` : ""}.
          That's a good sign: you're already choosing among the best of it.</p>
          ${n ? `<p class="muted" style="font-size:12.5px;margin:4px 0 0">Closest: <a href="#/stock/${encodeURIComponent(n.symbol)}">${td.esc(n.symbol)}</a> (${td.esc(n.name || "")}): ${["score", "sortino", "maxdd"].filter((k) => !n.beats[k]).map((k) => ({ score: "lower score", sortino: "weaker return for its risk", maxdd: "deeper worst fall" }[k])).join(", ")}.</p>` : ""}</div>`;
      }
      return `<div class="chal"><h3 class="h3">${title} <span class="muted" style="font-weight:400">${sub}</span></h3>
        <div class="chal-win">${td.logo(w.symbol, 34)}<div><b><a href="#/stock/${encodeURIComponent(w.symbol)}">${td.esc(w.symbol)}</a></b> <span class="muted">${td.esc(w.name || "")}</span>
          ${w.zone && window.LT ? window.LT.zoneBadge(w.zone) : ""}<div class="chal-why">${why(w)}</div></div>
          <a class="btn sm primary" href="#/compare?s=${encodeURIComponent(swap(w.symbol))}">Swap for ${td.esc(weakest)}</a></div>
        ${g.others.length ? `<p class="muted" style="font-size:12.5px;margin:6px 0 0">Also beats them all: ${g.others.map((o) => `<a href="#/stock/${encodeURIComponent(o.symbol)}">${td.esc(o.symbol)}</a> (score ${o.score})`).join(", ")}</p>` : ""}</div>`;
    };
    return card("Same group", "chips, sector or theme of your picks", c.sameGroup) +
      card("Outside the AI theme", "spreads your risk: you already hold mostly chip and AI stocks", c.outsideAI) +
      `<p class="muted" style="font-size:12px;margin:8px 0 0">${td.esc(c.note)} Past results, not a forecast: check the business before buying.</p>`;
  }
  async function loadChallenger(el, syms) {
    const td = T();
    el.innerHTML = `${td.skeleton(4)}<p class="muted" style="font-size:12.5px">Looking for a stock that beats all of ${syms.map(td.esc).join(", ")} (the first search takes 1–3 minutes, then it's quick)…</p>`;
    try {
      const c = await td.api("/api/challenger?symbols=" + encodeURIComponent(syms.join(",")));
      if (el.isConnected) { el.innerHTML = challengerHtml(c, syms); if (window.lucide) window.lucide.createIcons(); }
    } catch (e) { if (el.isConnected) el.innerHTML = `<p class="muted">Challenger unavailable: ${td.esc(e.message)}</p>`; }
  }

  window.Compare = { page };
})();
