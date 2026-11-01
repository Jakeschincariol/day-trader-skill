/* Canvas charts for Trader Dashboard. No dependencies. */
(function () {
  "use strict";
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const fmt = (x, d) => (x == null ? "–" : Number(x).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
  const fmtVol = (v) => (v >= 1e9 ? (v / 1e9).toFixed(2) + "B" : v >= 1e6 ? (v / 1e6).toFixed(1) + "M" : v >= 1e3 ? (v / 1e3).toFixed(0) + "K" : String(v));
  const day = (t) => new Date(t * 1000);
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function niceTicks(lo, hi, n) {
    const span = hi - lo || 1;
    const step0 = span / n;
    const mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || mag * 10;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(v);
    return { ticks: out, step };
  }

  /**
   * Price chart.
   * s: series {t,o,h,l,c,v,sma20,sma50,sma200,rsi}
   * opts: {bars: number of bars to show, plan: {entry,stop,target1,target2}, decimals}
   */
  function PriceChart(box, s, opts) {
    const canvas = document.createElement("canvas");
    const tip = document.createElement("div");
    tip.className = "chart-tip";
    tip.hidden = true;
    box.innerHTML = "";
    box.appendChild(canvas);
    box.appendChild(tip);
    canvas.setAttribute("role", "img");
    const ctx = canvas.getContext("2d");
    let W = 0, H = 0, hover = -1, geom = null;
    const n = s.c.length;
    const start = Math.max(0, n - (opts.bars || 126));
    const intra = opts.intraday; // "day" | "week" | undefined
    const fcAll = !intra && opts.forecast ? opts.forecast : null;
    const F = fcAll ? Math.min(fcAll.days, Math.max(10, Math.round((n - start) * 0.4))) : 0;
    const tgt = !intra && opts.target ? opts.target : null;
    const dec = opts.decimals != null ? opts.decimals : s.c[n - 1] < 2 ? 4 : 2;
    const C = {
      up: css("--good"), down: css("--bad"), grid: css("--grid"), axis: css("--axis"), muted: css("--text-muted"),
      text: css("--text-secondary"), primary: css("--text-primary"), surface: css("--surface-1"),
      s20: css("--series-2"), s50: css("--series-1"), s200: css("--series-5"), accent: css("--accent"),
      rsi: css("--series-7"), warn: css("--warning"),
    };
    canvas.setAttribute("aria-label", (intra ? "Intraday" : "Daily") + " candlestick chart, last " + (n - start) + " sessions, close " + fmt(s.c[n - 1], dec));

    function draw() {
      const dpr = window.devicePixelRatio || 1;
      W = box.clientWidth; H = box.clientHeight;
      canvas.width = W * dpr; canvas.height = H * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.font = "11px " + css("--mono");

      const right = 62, left = 6, top = 8, xAxisH = 20;
      const hasRsi = !intra && s.rsi;
      const rsiH = hasRsi ? Math.max(60, Math.round(H * 0.2)) : 0;
      const gap = hasRsi ? 14 : 0;
      const priceH = H - top - xAxisH - rsiH - gap;
      const plotW = W - left - right;
      const count = n - start + F;
      const bw = plotW / count;
      const x = (i) => left + (i - start + 0.5) * bw;

      let lo = Infinity, hi = -Infinity;
      for (let i = start; i < n; i++) { lo = Math.min(lo, s.l[i]); hi = Math.max(hi, s.h[i]); }
      for (const k of ["sma20", "sma50", "sma200"]) if (s[k]) for (let i = start; i < n; i++) if (s[k][i] != null) { lo = Math.min(lo, s[k][i]); hi = Math.max(hi, s[k][i]); }
      const p = opts.plan;
      if (p) for (const k of ["entry", "stop", "target1"]) if (p[k] != null) { lo = Math.min(lo, p[k]); hi = Math.max(hi, p[k]); }
      if (F) { lo = Math.min(lo, fcAll.lo2[F - 1]); hi = Math.max(hi, fcAll.hi2[F - 1]); }
      if (tgt && F) { lo = Math.min(lo, tgt); hi = Math.max(hi, tgt); }
      if (intra === "day" && opts.prevClose) { lo = Math.min(lo, opts.prevClose); hi = Math.max(hi, opts.prevClose); }
      const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
      const y = (v) => top + (hi - v) / (hi - lo) * priceH;

      // grid + y labels
      const { ticks } = niceTicks(lo, hi, 6);
      ctx.strokeStyle = C.grid; ctx.lineWidth = 1; ctx.fillStyle = C.muted; ctx.textAlign = "left"; ctx.textBaseline = "middle";
      for (const t of ticks) {
        const yy = Math.round(y(t)) + 0.5;
        ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(left + plotW, yy); ctx.stroke();
        ctx.fillText(fmt(t, dec > 2 ? dec : t < 10 ? 2 : t < 1000 ? 1 : 0), left + plotW + 6, yy);
      }

      // volume (bottom 18% of price panel)
      let vmax = 0;
      for (let i = start; i < n; i++) vmax = Math.max(vmax, s.v[i]);
      const vH = priceH * 0.18, vBase = top + priceH;
      for (let i = start; i < n; i++) {
        const h = vmax ? s.v[i] / vmax * vH : 0;
        ctx.fillStyle = s.c[i] >= s.o[i] ? "rgba(12,163,12,.28)" : "rgba(208,59,59,.28)";
        ctx.fillRect(x(i) - Math.max(1, bw * 0.35), vBase - h, Math.max(1, bw * 0.7), h);
      }

      // candles
      const cw = Math.max(1, Math.min(10, bw * 0.62));
      for (let i = start; i < n; i++) {
        const upBar = s.c[i] >= s.o[i];
        ctx.strokeStyle = ctx.fillStyle = upBar ? C.up : C.down;
        const xx = Math.round(x(i)) + 0.5;
        ctx.beginPath(); ctx.moveTo(xx, y(s.h[i])); ctx.lineTo(xx, y(s.l[i])); ctx.stroke();
        const y1 = y(Math.max(s.o[i], s.c[i])), y2 = y(Math.min(s.o[i], s.c[i]));
        ctx.fillRect(xx - cw / 2, y1, cw, Math.max(1, y2 - y1));
      }

      // moving averages, 2px
      const line = (arr, color, from, to, yf, width) => {
        ctx.strokeStyle = color; ctx.lineWidth = width || 2; ctx.lineJoin = "round"; ctx.beginPath();
        let on = false;
        for (let i = from; i < to; i++) {
          if (arr[i] == null) { on = false; continue; }
          on ? ctx.lineTo(x(i), yf(arr[i])) : ctx.moveTo(x(i), yf(arr[i]));
          on = true;
        }
        ctx.stroke();
      };
      if (s.sma200) line(s.sma200, C.s200, start, n, y);
      if (s.sma50) line(s.sma50, C.s50, start, n, y);
      if (s.sma20) line(s.sma20, C.s20, start, n, y);

      // previous close (1D)
      if (intra === "day" && opts.prevClose) {
        const yy = Math.round(y(opts.prevClose)) + 0.5;
        ctx.setLineDash([2, 4]); ctx.strokeStyle = C.muted; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(left + plotW, yy); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = C.muted; ctx.textAlign = "left"; ctx.fillText("Prev close " + fmt(opts.prevClose, dec), left + 6, yy - 8);
      }

      // forecast cone: 95% band, 68% band, centre line
      let tgtLabel = null;
      if (F) {
        const fx = (k) => x(n - 1 + k);
        const band = (loA, hiA, alpha) => {
          ctx.beginPath(); ctx.moveTo(fx(0), y(s.c[n - 1]));
          for (let k = 1; k <= F; k++) ctx.lineTo(fx(k), y(hiA[k - 1]));
          for (let k = F; k >= 1; k--) ctx.lineTo(fx(k), y(loA[k - 1]));
          ctx.closePath(); ctx.fillStyle = "rgba(57,135,229," + alpha + ")"; ctx.fill();
        };
        band(fcAll.lo2, fcAll.hi2, 0.08);
        band(fcAll.lo1, fcAll.hi1, 0.16);
        ctx.setLineDash([6, 4]); ctx.strokeStyle = C.accent; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(fx(0), y(s.c[n - 1]));
        for (let k = 1; k <= F; k++) ctx.lineTo(fx(k), y(fcAll.mid[k - 1]));
        ctx.stroke(); ctx.setLineDash([]);
        ctx.strokeStyle = C.axis; ctx.beginPath(); ctx.moveTo(Math.round(fx(0)) + 0.5, top); ctx.lineTo(Math.round(fx(0)) + 0.5, top + priceH); ctx.stroke();
        ctx.fillStyle = C.text; ctx.textAlign = "left"; ctx.fillText("Forecast →", fx(0) + 6, top + 10);
        if (tgt) {
          const tx = fx(F), ty = y(tgt);
          ctx.fillStyle = C.warn; ctx.strokeStyle = C.surface; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo(tx, ty - 6); ctx.lineTo(tx + 6, ty); ctx.lineTo(tx, ty + 6); ctx.lineTo(tx - 6, ty); ctx.closePath(); ctx.fill(); ctx.stroke();
          tgtLabel = { tx, ty };
        }
      }

      // plan lines with labels
      if (p) {
        const lines = [["Entry", p.entry, C.accent], ["Stop", p.stop, C.down], ["Target 1", p.target1, C.up], ["Target 2", p.target2, C.up]];
        ctx.setLineDash([5, 4]); ctx.lineWidth = 1.5;
        for (const [label, v, color] of lines) {
          if (v == null || v < lo || v > hi) continue;
          const yy = Math.round(y(v)) + 0.5;
          ctx.strokeStyle = color; ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(left + plotW, yy); ctx.stroke();
          ctx.setLineDash([]);
          const txt = label + " " + fmt(v, dec);
          const tw = ctx.measureText(txt).width + 10;
          ctx.fillStyle = C.surface; ctx.fillRect(left + plotW - tw - 4, yy - 9, tw, 18);
          ctx.strokeStyle = color; ctx.strokeRect(left + plotW - tw - 4 + 0.5, yy - 8.5, tw - 1, 17);
          ctx.fillStyle = C.primary; ctx.textAlign = "left"; ctx.fillText(txt, left + plotW - tw + 1, yy);
          ctx.setLineDash([5, 4]);
        }
        ctx.setLineDash([]);
      }

      // analyst target label, drawn above the plan labels so it stays readable
      if (tgtLabel) {
        const label = "Analyst target " + fmt(tgt, dec);
        const tw = ctx.measureText(label).width + 10;
        const lx = Math.max(left, tgtLabel.tx - tw - 10), ly = tgtLabel.ty + (tgtLabel.ty > top + priceH - 30 ? -22 : 16);
        ctx.fillStyle = C.surface; ctx.fillRect(lx, ly - 9, tw, 18);
        ctx.strokeStyle = C.warn; ctx.lineWidth = 1; ctx.strokeRect(lx + 0.5, ly - 8.5, tw - 1, 17);
        ctx.fillStyle = C.primary; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(label, lx + 5, ly);
      }

      // last price tag
      const lastY = y(s.c[n - 1]);
      ctx.fillStyle = s.c[n - 1] >= s.c[n - 2] ? C.up : C.down;
      ctx.fillRect(left + plotW + 1, lastY - 9, right - 2, 18);
      ctx.fillStyle = "#fff"; ctx.textAlign = "left";
      ctx.fillText(fmt(s.c[n - 1], dec), left + plotW + 5, lastY);

      // RSI panel
      const rTop = top + priceH + gap, ry = (v) => rTop + (100 - v) / 100 * rsiH;
      if (hasRsi) {
      ctx.fillStyle = "rgba(255,255,255,.03)"; ctx.fillRect(left, ry(70), plotW, ry(30) - ry(70));
      ctx.strokeStyle = C.grid; ctx.lineWidth = 1;
      for (const lv of [30, 50, 70]) {
        const yy = Math.round(ry(lv)) + 0.5;
        ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(left + plotW, yy); ctx.stroke();
        ctx.fillStyle = C.muted; ctx.fillText(String(lv), left + plotW + 6, yy);
      }
      ctx.strokeStyle = C.axis; ctx.strokeRect(left + 0.5, rTop + 0.5, plotW - 1, rsiH - 1);
      line(s.rsi, C.rsi, start, n, ry);
      ctx.fillStyle = C.text; ctx.fillText("RSI 14", left + 6, rTop + 10);
      }

      // x axis: month labels
      ctx.fillStyle = C.muted; ctx.textAlign = "center"; ctx.textBaseline = "top";
      let lastM = -1, lastX = -100;
      const tAt = (i) => (i < n ? s.t[i] : s.t[n - 1] + Math.round((i - n + 1) * 7 / 5) * 86400);
      for (let i = start; i < n + F; i++) {
        const d = day(tAt(i));
        const m = intra === "day" ? d.getHours() : intra === "week" ? d.getDate() : d.getMonth();
        if (m !== lastM && x(i) - lastX > 44) {
          const label = intra === "day" ? String(d.getHours()).padStart(2, "0") + ":00"
            : intra === "week" ? d.toLocaleDateString(undefined, { weekday: "short", day: "numeric" })
            : m === 0 ? String(d.getFullYear()) : MONTHS[m];
          ctx.fillText(label, Math.min(Math.max(x(i), left + 14), left + plotW - 14), rTop + rsiH + 5);
          lastX = x(i);
        }
        lastM = m;
      }

      // crosshair
      if (hover >= start && hover < n + F) {
        const xx = Math.round(x(hover)) + 0.5;
        const hv = hover < n ? s.c[hover] : fcAll.mid[hover - n];
        ctx.strokeStyle = "rgba(240,239,236,.35)"; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
        ctx.beginPath(); ctx.moveTo(xx, top); ctx.lineTo(xx, rTop + rsiH); ctx.stroke(); ctx.setLineDash([]);
        ctx.fillStyle = C.primary; ctx.strokeStyle = C.surface; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(xx, y(hv), 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      }
      geom = { left, plotW, bw, start, x, tAt };
    }

    function showTip(i, px, py) {
      const row = (k, v, cls) => `<div class="row"><span class="muted">${k}</span><span class="num ${cls || ""}">${v}</span></div>`;
      if (i >= n) {
        const k = i - n;
        const d = day(geom.tAt(i));
        tip.innerHTML = `<div style="font-weight:600;margin-bottom:2px">Forecast · ~${d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</div>` +
          row("Trend path", fmt(fcAll.mid[k], dec)) + row("Likely (68%)", fmt(fcAll.lo1[k], dec) + " – " + fmt(fcAll.hi1[k], dec)) +
          row("Wide (95%)", fmt(fcAll.lo2[k], dec) + " – " + fmt(fcAll.hi2[k], dec)) + (tgt ? row("Analyst 12m target", fmt(tgt, dec)) : "") +
          `<div class="muted" style="margin-top:4px;max-width:200px;white-space:normal">Statistical range from recent trend and volatility. Not a prediction.</div>`;
        return place(px, py);
      }
      const d = day(s.t[i]);
      const chg = i > 0 ? (s.c[i] / s.c[i - 1] - 1) * 100 : 0;
      const when = intra ? d.toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
        : d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
      const base = intra === "day" && opts.prevClose ? opts.prevClose : i > 0 ? s.c[i - 1] : s.c[i];
      const chg2 = (s.c[i] / base - 1) * 100;
      tip.innerHTML = `<div style="font-weight:600;margin-bottom:2px">${when}</div>` +
        row("Open", fmt(s.o[i], dec)) + row("High", fmt(s.h[i], dec)) + row("Low", fmt(s.l[i], dec)) +
        row(intra === "day" ? "Close (vs prev close)" : "Close", fmt(s.c[i], dec) + ` (${chg2 >= 0 ? "+" : ""}${chg2.toFixed(2)}%)`, chg2 >= 0 ? "up" : "down") +
        row("Volume", fmtVol(s.v[i])) +
        (s.sma20 ? row("SMA 20 / 50", fmt(s.sma20[i], dec) + " / " + fmt(s.sma50[i], dec)) + row("SMA 200", fmt(s.sma200[i], dec)) : "") +
        (s.rsi && !intra ? row("RSI", s.rsi[i] == null ? "–" : s.rsi[i].toFixed(1)) : "");
      place(px, py);
    }
    function place(px, py) {
      tip.hidden = false;
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      let lx = px + 16; if (lx + tw > W) lx = px - tw - 16;
      tip.style.left = Math.max(0, lx) + "px";
      tip.style.top = Math.max(0, Math.min(H - th, py - th / 2)) + "px";
    }

    function onMove(ev) {
      if (!geom) return;
      const rect = canvas.getBoundingClientRect();
      const px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left;
      const py = (ev.touches ? ev.touches[0].clientY : ev.clientY) - rect.top;
      const i = Math.floor((px - geom.left) / geom.bw) + geom.start;
      if (i < geom.start || i >= n + F) return onLeave();
      if (i !== hover) { hover = i; draw(); }
      showTip(i, px, py);
    }
    function onLeave() { hover = -1; tip.hidden = true; draw(); }
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("touchmove", onMove, { passive: true });
    canvas.addEventListener("mouseleave", onLeave);
    canvas.addEventListener("touchend", onLeave);
    const ro = new ResizeObserver(() => draw());
    ro.observe(box);
    draw();
    return { destroy() { ro.disconnect(); } };
  }

  /** Tiny inline sparkline (SVG string) of the last closes. */
  function sparkline(values, w, h) {
    w = w || 90; h = h || 28;
    const v = values.filter((x) => x != null);
    if (v.length < 2) return "";
    const lo = Math.min(...v), hi = Math.max(...v);
    const pts = v.map((y, i) => `${(i / (v.length - 1) * w).toFixed(1)},${(h - 2 - (y - lo) / (hi - lo || 1) * (h - 4)).toFixed(1)}`).join(" ");
    const color = v[v.length - 1] >= v[0] ? "var(--good)" : "var(--bad)";
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" points="${pts}"/></svg>`;
  }

  /**
   * Donut (SVG). items: [{label, value, color}] - caller folds anything past 8 into "Other".
   * 2px surface gap between segments.
   */
  function donut(items, size, centerTop, centerBottom) {
    size = size || 180;
    const total = items.reduce((a, b) => a + b.value, 0) || 1;
    const r = size / 2 - 4, inner = r * 0.64, cx = size / 2, cy = size / 2;
    let a0 = -Math.PI / 2, paths = "";
    for (const it of items) {
      const frac = it.value / total;
      const a1 = a0 + frac * Math.PI * 2;
      if (frac >= 0.999) {
        paths += `<circle cx="${cx}" cy="${cy}" r="${(r + inner) / 2}" fill="none" stroke="${it.color}" stroke-width="${r - inner}"><title>${it.label}: ${(frac * 100).toFixed(1)}%</title></circle>`;
      } else {
        const large = a1 - a0 > Math.PI ? 1 : 0;
        const p = (rad, a) => `${(cx + rad * Math.cos(a)).toFixed(2)},${(cy + rad * Math.sin(a)).toFixed(2)}`;
        paths += `<path d="M${p(r, a0)} A${r},${r} 0 ${large} 1 ${p(r, a1)} L${p(inner, a1)} A${inner},${inner} 0 ${large} 0 ${p(inner, a0)} Z" fill="${it.color}" stroke="var(--surface-1)" stroke-width="2"><title>${it.label}: ${(frac * 100).toFixed(1)}%</title></path>`;
      }
      a0 = a1;
    }
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="Allocation chart">${paths}` +
      `<text x="${cx}" y="${cy - 4}" text-anchor="middle" fill="var(--text-primary)" font-size="16" font-weight="600">${centerTop || ""}</text>` +
      `<text x="${cx}" y="${cy + 16}" text-anchor="middle" fill="var(--text-muted)" font-size="11">${centerBottom || ""}</text></svg>`;
  }


  /**
   * Portfolio value vs money invested over time (canvas, one y-axis, crosshair tooltip).
   * d: {dates:[YYYY-MM-DD], value:[], invested:[]}, opts: {from: index, ccy}
   */
  function ValueChart(box, d, opts) {
    const canvas = document.createElement("canvas");
    const tip = document.createElement("div");
    tip.className = "chart-tip"; tip.hidden = true;
    box.innerHTML = ""; box.appendChild(canvas); box.appendChild(tip);
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", "Portfolio value compared with money invested");
    const ctx = canvas.getContext("2d");
    const start = Math.max(0, opts.from || 0), n = d.dates.length;
    const money = opts.money || ((v) => fmt(v, 0));
    let W, H, hover = -1, g;
    const C = { val: css("--series-1"), inv: css("--text-muted"), up: css("--good"), down: css("--bad"), grid: css("--grid"), muted: css("--text-muted"), primary: css("--text-primary"), surface: css("--surface-1") };
    function draw() {
      const dpr = window.devicePixelRatio || 1;
      W = box.clientWidth; H = box.clientHeight;
      canvas.width = W * dpr; canvas.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H); ctx.font = "11px " + css("--mono");
      const left = 6, right = 70, top = 10, bottom = 22, pw = W - left - right, ph = H - top - bottom;
      const cnt = Math.max(1, n - start - 1);
      const x = (i) => left + (i - start) / cnt * pw;
      let lo = Infinity, hi = -Infinity;
      for (let i = start; i < n; i++) { lo = Math.min(lo, d.value[i], d.invested[i]); hi = Math.max(hi, d.value[i], d.invested[i]); }
      lo = Math.max(0, lo - (hi - lo) * 0.08); hi += (hi - lo) * 0.08 || 1;
      const y = (v) => top + (hi - v) / (hi - lo) * ph;
      const { ticks } = niceTicks(lo, hi, 5);
      ctx.strokeStyle = C.grid; ctx.fillStyle = C.muted; ctx.textBaseline = "middle"; ctx.textAlign = "left"; ctx.lineWidth = 1;
      for (const t of ticks) { const yy = Math.round(y(t)) + 0.5; ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(left + pw, yy); ctx.stroke(); ctx.fillText(money(t), left + pw + 6, yy); }
      // gain/loss area between the lines
      for (let i = start; i < n - 1; i++) {
        const gain = d.value[i] >= d.invested[i];
        ctx.fillStyle = gain ? "rgba(12,163,12,.16)" : "rgba(208,59,59,.18)";
        ctx.beginPath(); ctx.moveTo(x(i), y(d.value[i])); ctx.lineTo(x(i + 1), y(d.value[i + 1]));
        ctx.lineTo(x(i + 1), y(d.invested[i + 1])); ctx.lineTo(x(i), y(d.invested[i])); ctx.closePath(); ctx.fill();
      }
      const line = (arr, color, dash) => {
        ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.setLineDash(dash || []); ctx.beginPath();
        for (let i = start; i < n; i++) i === start ? ctx.moveTo(x(i), y(arr[i])) : ctx.lineTo(x(i), y(arr[i]));
        ctx.stroke(); ctx.setLineDash([]);
      };
      line(d.invested, C.inv, [6, 4]);
      line(d.value, C.val);
      // x labels
      ctx.fillStyle = C.muted; ctx.textAlign = "center"; ctx.textBaseline = "top";
      let lastX = -100, lastKey = "";
      const span = (Date.parse(d.dates[n - 1]) - Date.parse(d.dates[start])) / 86400000;
      for (let i = start; i < n; i++) {
        const [yy, mm, dd] = d.dates[i].split("-");
        const key = span > 800 ? yy : span > 70 ? yy + mm : yy + mm + dd;
        if (key !== lastKey && x(i) - lastX > 56) {
          const lab = span > 800 ? yy : span > 70 ? (mm === "01" ? yy : MONTHS[+mm - 1]) : dd + " " + MONTHS[+mm - 1];
          ctx.fillText(lab, Math.min(Math.max(x(i), left + 16), left + pw - 16), top + ph + 6); lastX = x(i);
        }
        lastKey = key;
      }
      if (hover >= start && hover < n) {
        const xx = Math.round(x(hover)) + 0.5;
        ctx.strokeStyle = "rgba(240,239,236,.35)"; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(xx, top); ctx.lineTo(xx, top + ph); ctx.stroke(); ctx.setLineDash([]);
        for (const [arr, col] of [[d.invested, C.inv], [d.value, C.val]]) { ctx.fillStyle = col; ctx.strokeStyle = C.surface; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(xx, y(arr[hover]), 4.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
      }
      g = { left, pw, cnt };
    }
    function move(ev) {
      const rect = canvas.getBoundingClientRect();
      const px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left, py = (ev.touches ? ev.touches[0].clientY : ev.clientY) - rect.top;
      const i = Math.round((px - g.left) / g.pw * g.cnt) + start;
      if (i < start || i >= n) return leave();
      if (i !== hover) { hover = i; draw(); }
      const gain = d.value[i] - d.invested[i];
      const row = (k, v, c) => `<div class="row"><span class="muted">${k}</span><span class="num ${c || ""}">${v}</span></div>`;
      tip.innerHTML = `<div style="font-weight:600;margin-bottom:2px">${new Date(d.dates[i] + "T12:00:00Z").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</div>` +
        row("Value", money(d.value[i])) + row("Invested", money(d.invested[i])) +
        row("Unrealised", (gain >= 0 ? "+" : "") + money(gain) + (d.invested[i] ? ` (${gain >= 0 ? "+" : ""}${(100 * gain / d.invested[i]).toFixed(1)}%)` : ""), gain >= 0 ? "up" : "down") +
        (d.realized ? row("Realised so far", money(d.realized[i])) : "");
      tip.hidden = false;
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      let lx = px + 16; if (lx + tw > W) lx = px - tw - 16;
      tip.style.left = Math.max(0, lx) + "px"; tip.style.top = Math.max(0, Math.min(H - th, py - th / 2)) + "px";
    }
    function leave() { hover = -1; tip.hidden = true; draw(); }
    canvas.addEventListener("mousemove", move); canvas.addEventListener("touchmove", move, { passive: true });
    canvas.addEventListener("mouseleave", leave); canvas.addEventListener("touchend", leave);
    const ro = new ResizeObserver(draw); ro.observe(box); draw();
    return { destroy() { ro.disconnect(); } };
  }

  /** EPS dots: actual (filled) per quarter, analyst forecast (hollow) with high/low whisker. SVG string. */
  function epsChart(actual, forecasts, w, h) {
    w = w || 620; h = h || 250;
    const pts = actual.map((q) => ({ label: q.label, v: q.eps, kind: "a", sub: q.epsYoY })).concat(
      forecasts.map((f) => ({ label: f.fiscalEnd, v: f.eps, lo: f.low, hi: f.high, kind: "f" })));
    const vals = pts.flatMap((p) => [p.v, p.lo, p.hi]).filter((v) => typeof v === "number");
    if (!vals.length) return "";
    let lo = Math.min(...vals, 0 < Math.min(...vals) ? Math.min(...vals) : 0), hi = Math.max(...vals);
    lo = Math.min(...vals); const pad = (hi - lo) * 0.15 || 0.5; lo -= pad; hi += pad;
    const left = 44, right = 10, top = 12, bottom = 52, pw = w - left - right, ph = h - top - bottom;
    const x = (i) => left + (i + 0.5) * pw / pts.length, y = (v) => top + (hi - v) / (hi - lo) * ph;
    const { ticks } = niceTicks(lo, hi, 4);
    let g = ticks.map((t) => `<line x1="${left}" x2="${w - right}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${left - 6}" y="${y(t) + 4}" text-anchor="end" fill="var(--text-muted)" font-size="11">${t.toFixed(2)}</text>`).join("");
    const nA = actual.length;
    if (forecasts.length && nA) g += `<line x1="${(x(nA - 1) + x(nA)) / 2}" x2="${(x(nA - 1) + x(nA)) / 2}" y1="${top}" y2="${top + ph}" stroke="var(--axis)" stroke-dasharray="3 3"/>`;
    pts.forEach((p, i) => {
      if (typeof p.v !== "number") return;
      const tt = `${p.kind === "a" ? "Actual" : "Forecast"} EPS ${p.label}: ${p.v.toFixed(2)}${p.kind === "f" && p.lo != null ? ` (range ${p.lo}–${p.hi})` : ""}`;
      if (p.kind === "f" && p.lo != null) g += `<line x1="${x(i)}" x2="${x(i)}" y1="${y(p.hi)}" y2="${y(p.lo)}" stroke="var(--text-muted)" stroke-width="2"/>`;
      g += p.kind === "a"
        ? `<circle cx="${x(i)}" cy="${y(p.v)}" r="9" fill="var(--good)" stroke="var(--surface-1)" stroke-width="2"><title>${tt}</title></circle>`
        : `<circle cx="${x(i)}" cy="${y(p.v)}" r="8" fill="var(--surface-1)" stroke="var(--text-secondary)" stroke-width="2.5"><title>${tt}</title></circle>`;
      g += `<text x="${x(i)}" y="${top + ph + 16}" text-anchor="middle" fill="var(--text-secondary)" font-size="11">${p.label}</text>`;
      g += `<text x="${x(i)}" y="${top + ph + 31}" text-anchor="middle" font-size="11" font-weight="600" fill="${p.kind === "f" ? "var(--text-muted)" : "var(--text-primary)"}">${p.kind === "f" ? "est " : ""}${p.v.toFixed(2)}</text>`;
      if (p.kind === "a" && p.sub != null) g += `<text x="${x(i)}" y="${top + ph + 45}" text-anchor="middle" font-size="10.5" fill="${p.sub >= 0 ? "var(--good-text)" : "var(--bad-text)"}">${p.sub >= 0 ? "▲ +" : "▼ "}${p.sub}%</text>`;
    });
    return `<svg viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="Earnings per share by quarter">${g}</svg>`;
  }

  /** Revenue vs net income bars per period, profit margin printed under each group. SVG string. */
  function revBars(rows, w, h) {
    w = w || 620; h = h || 250;
    if (!rows.length) return "";
    const short = (v) => (v == null ? "–" : Math.abs(v) >= 1e12 ? (v / 1e12).toFixed(2) + "T" : Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(1) + "B" : (v / 1e6).toFixed(0) + "M");
    const vals = rows.flatMap((r) => [r.revenue || 0, r.netIncome || 0]);
    const hi = Math.max(...vals) * 1.1 || 1, lo = Math.min(0, ...vals);
    const left = 48, right = 8, top = 10, bottom = 44, pw = w - left - right, ph = h - top - bottom;
    const y = (v) => top + (hi - v) / (hi - lo) * ph, gw = pw / rows.length, bw = Math.min(34, gw * 0.3);
    const { ticks } = niceTicks(lo, hi, 4);
    let g = ticks.map((t) => `<line x1="${left}" x2="${w - right}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text x="${left - 6}" y="${y(t) + 4}" text-anchor="end" fill="var(--text-muted)" font-size="11">${short(t)}</text>`).join("");
    const bar = (cx, v, color, label) => {
      const y0 = y(Math.max(0, v)), y1 = y(Math.min(0, v));
      return `<rect x="${cx - bw / 2}" y="${y0}" width="${bw}" height="${Math.max(1, y1 - y0)}" rx="3" fill="${color}"><title>${label}</title></rect>`;
    };
    rows.forEach((r, i) => {
      const cx = left + gw * (i + 0.5);
      const per = String(r.period).replace(/^(\d+)\/(\d+)\/(\d{4})$/, (_, m, d, yy) => MONTHS[+m - 1] + " " + yy.slice(2));
      g += bar(cx - bw / 2 - 1, r.revenue || 0, "var(--series-1)", `Revenue ${per}: ${short(r.revenue)}`);
      g += bar(cx + bw / 2 + 1, r.netIncome || 0, "var(--series-3)", `Net income ${per}: ${short(r.netIncome)}`);
      g += `<text x="${cx}" y="${top + ph + 15}" text-anchor="middle" fill="var(--text-secondary)" font-size="11">${per}</text>`;
      g += `<text x="${cx}" y="${top + ph + 30}" text-anchor="middle" fill="var(--text-muted)" font-size="10.5">margin ${r.margin == null ? "–" : r.margin.toFixed(1) + "%"}</text>`;
    });
    return `<svg viewBox="0 0 ${w} ${h}" width="100%" role="img" aria-label="Revenue and net income by period">${g}</svg>`;
  }

  window.TChart = { PriceChart, ValueChart, epsChart, revBars, sparkline, donut, fmt, fmtVol };
})();
