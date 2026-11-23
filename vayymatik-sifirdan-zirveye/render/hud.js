// SIFIRDAN ZİRVEYE — premium yarı saydam finans HUD'u (tüm rakamlar finans.json'dan)
export const TL = (v, isaret) => { const s = Math.round(Math.abs(v)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.'); return (v < 0 ? '−' : isaret && v > 0 ? '+' : '') + s + ' TL'; };
const cl = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x)), ease = x => (x = cl(x), 1 - Math.pow(1 - x, 3));
const rr = (c, x, y, w, h, r) => { c.beginPath(); c.roundRect(x, y, w, h, r); };
function kart(c, x, y, w, h, a, vurgu = '#e8c46a') {
  c.save(); c.globalAlpha = a; c.shadowColor = 'rgba(0,0,0,.55)'; c.shadowBlur = 40; const g = c.createLinearGradient(x, y, x, y + h); g.addColorStop(0, 'rgba(14,20,32,.78)'); g.addColorStop(1, 'rgba(6,10,18,.86)');
  c.fillStyle = g; rr(c, x, y, w, h, 22); c.fill(); c.shadowBlur = 0; c.strokeStyle = 'rgba(232,196,106,.35)'; c.lineWidth = 1.5; c.stroke();
  const gl = c.createLinearGradient(x, y, x + w, y); gl.addColorStop(0, 'rgba(232,196,106,0)'); gl.addColorStop(.5, vurgu); gl.addColorStop(1, 'rgba(232,196,106,0)'); c.fillStyle = gl; c.fillRect(x + 30, y, w - 60, 2); c.restore();
}
function baslik(c, x, y, t, a, s = 1) { c.save(); c.globalAlpha = a; c.font = `800 ${22 * s}px Mont`; c.letterSpacing = `${4 * s}px`; c.fillStyle = '#e8c46a'; c.fillText(t, x, y); c.restore(); }
// Ana panel: yedi satır + isteğe bağlı ek satırlar
const SATIR = [['kasa', 'Kasa / nakit'], ['ciro', 'Satış geliri (ciro)'], ['smm', 'Satılan ürün maliyeti'], ['gider', 'İşletme giderleri'], ['net', 'Net kâr / zarar'], ['borc', 'Toplam borç'], ['ozkaynak', 'Emir’in özkaynağı']];
export function panel(c, o) { // o: {x,y,w,s, a, onceki, simdi, k (0..1 animasyon), baslik, olay, ek:[[ad, deger, renk]]}
  const { x, y, w, s = 1, a, simdi, onceki = simdi, k = 1 } = o; if (a <= .003) return;
  const sat = SATIR.length + (o.ek ? o.ek.length : 0), h = (120 + sat * 58) * s; kart(c, x, y, w, h, a);
  c.save(); c.globalAlpha = a; baslik(c, x + 34 * s, y + 46 * s, o.baslik || 'FİNANS PANELİ', 1, s);
  if (o.olay) { c.font = `700 ${21 * s}px Mont`; c.fillStyle = '#9fb3c8'; c.fillText(o.olay, x + 34 * s, y + 78 * s); }
  const rows = SATIR.map(([key, ad]) => [ad, onceki[key] + (simdi[key] - onceki[key]) * ease(k), simdi[key] - onceki[key], key]).concat((o.ek || []).map(([ad, v, renk]) => [ad, v, 0, 'ek', renk]));
  rows.forEach(([ad, v, d, key, renk], i) => { const yy = y + (120 + i * 58) * s, deg = Math.abs(d) > .5 && k < 1.6;
    if (deg) { c.fillStyle = `rgba(232,196,106,${.13 * (1 - cl((k - 1) / .6))})`; rr(c, x + 16 * s, yy - 34 * s, w - 32 * s, 50 * s, 12 * s); c.fill(); }
    c.font = `600 ${25 * s}px Mont`; c.fillStyle = key === 'ek' ? '#c8d2dc' : '#dfe6ee'; c.textAlign = 'left'; c.fillText(ad, x + 34 * s, yy);
    c.font = `800 ${28 * s}px Mont`; c.textAlign = 'right'; c.fillStyle = renk || (key === 'net' || key === 'kullanilabilir' ? (v < 0 ? '#ff6a5a' : '#5ff2a0') : key === 'borc' ? '#ffb46a' : '#ffffff'); c.fillText(typeof v === 'string' ? v : TL(v), x + w - 34 * s, yy);
    if (deg) { c.font = `700 ${19 * s}px Mont`; c.fillStyle = d > 0 ? (key === 'borc' || key === 'smm' || key === 'gider' ? '#ffb46a' : '#5ff2a0') : '#ff8a7a'; c.globalAlpha = a * cl(k * 3) * (1 - cl((k - 1.2) / .5)); c.fillText(TL(d, true), x + w - 34 * s, yy + 22 * s); c.globalAlpha = a; }
    if (i < rows.length - 1) { c.fillStyle = 'rgba(255,255,255,.06)'; c.fillRect(x + 30 * s, yy + 24 * s, w - 60 * s, 1); } });
  c.textAlign = 'left'; c.restore();
}
// Satır listesi (kaynaklar, kullanımlar, gider kalemleri, köprüler)
export function liste(c, o) { // o: {x,y,w,s,a,baslik, satirlar:[[ad, deger, renk, etiket]], n (görünen satır), toplam:[ad, deger, renk], not}
  const { x, y, w, s = 1, a } = o; if (a <= .003) return; const N = o.satirlar.length, h = (130 + N * 62 + (o.toplam ? 80 : 0) + (o.not ? 50 : 0)) * s; kart(c, x, y, w, h, a);
  c.save(); c.globalAlpha = a; baslik(c, x + 34 * s, y + 48 * s, o.baslik, 1, s);
  o.satirlar.forEach(([ad, v, renk, et], i) => { const g = cl((o.n ?? N) - i); if (g <= 0) return; const yy = y + (115 + i * 62) * s; c.globalAlpha = a * g;
    const vt = typeof v === 'number' ? TL(v) : v; c.font = `800 ${29 * s}px Mont`; const vx = x + w - 34 * s - c.measureText(vt).width;  // etiket ve rozet değerle çakışmasın
    let tw = 0; if (et) { c.font = `800 ${16 * s}px Mont`; tw = c.measureText(et).width + 22 * s; }
    let fs = 26 * s, lw; const sig = () => { c.font = `600 ${fs}px Mont`; lw = c.measureText(ad).width; return x + 34 * s + lw + (et ? 14 * s + tw : 0) + 14 * s <= vx; };
    while (!sig() && fs > 15 * s) fs -= 1;
    c.fillStyle = '#dfe6ee'; c.textAlign = 'left'; c.fillText(ad, x + 34 * s + (1 - g) * 30, yy);
    if (et) { const ex = Math.min(Math.max(x + w * .5, x + 34 * s + lw + 14 * s), vx - 14 * s - tw); c.font = `800 ${16 * s}px Mont`; c.fillStyle = renk || '#ffb46a'; rr(c, ex, yy - 22 * s, tw, 28 * s, 14 * s); c.globalAlpha = a * g * .2; c.fill(); c.globalAlpha = a * g; c.fillText(et, ex + 11 * s, yy - 2 * s); }
    c.font = `800 ${29 * s}px Mont`; c.textAlign = 'right'; c.fillStyle = renk || '#fff'; c.fillText(vt, x + w - 34 * s, yy); });
  c.globalAlpha = a; if (o.toplam) { const yy = y + (130 + N * 62 + 40) * s, g = cl((o.n ?? N) - N + 1); c.globalAlpha = a * g; c.fillStyle = 'rgba(232,196,106,.5)'; c.fillRect(x + 30 * s, yy - 50 * s, w - 60 * s, 2);
    c.font = `900 ${32 * s}px Mont`; c.textAlign = 'left'; c.fillStyle = '#e8c46a'; c.fillText(o.toplam[0], x + 34 * s, yy); c.textAlign = 'right'; c.fillStyle = o.toplam[2] || '#e8c46a'; c.fillText(typeof o.toplam[1] === 'number' ? TL(o.toplam[1]) : o.toplam[1], x + w - 34 * s, yy); }
  if (o.not) { c.globalAlpha = a; c.font = `600 ${20 * s}px Mont`; c.textAlign = 'left'; c.fillStyle = '#9fb3c8'; c.fillText(o.not, x + 34 * s, y + h - 26 * s); }
  c.textAlign = 'left'; c.restore();
}
// Şelale grafiği (nakit köprüsü, gelir tablosu)
export function selale(c, o) { // o: {x,y,w,h,s,a,baslik, adimlar:[[ad, deger, tip('bas'|'arti'|'eksi'|'son')]], k}
  const { x, y, w, h, s = 1, a, k = 1 } = o; if (a <= .003) return; kart(c, x, y, w, h, a); c.save(); c.globalAlpha = a; baslik(c, x + 34 * s, y + 48 * s, o.baslik, 1, s);
  const A = o.adimlar, n = A.length, max = Math.max(...A.map(z => Math.abs(z[1]))) * 1.08, x0 = x + 50 * s, bw = (w - 100 * s) / n, y0 = y + h - 120 * s, ph = h - 230 * s; let run = 0;
  A.forEach(([ad, v, tip], i) => { const g = ease(k * n - i); if (g <= 0) return; let a1, a2; if (tip === 'bas' || tip === 'son') { a1 = 0; a2 = v; run = v; } else { a1 = run; a2 = run + v; run = a2; }
    const yA = y0 - a1 / max * ph, yB = y0 - (a1 + (a2 - a1) * g) / max * ph, col = tip === 'eksi' ? '#ff6a5a' : tip === 'arti' ? '#5ff2a0' : '#e8c46a';
    const gr = c.createLinearGradient(0, Math.min(yA, yB), 0, Math.max(yA, yB) + 1); gr.addColorStop(0, col); gr.addColorStop(1, col + '88'); c.fillStyle = gr; rr(c, x0 + i * bw + bw * .14, Math.min(yA, yB), bw * .72, Math.max(3, Math.abs(yB - yA)), 8 * s); c.fill();
    c.globalAlpha = a * cl(g * 2 - 1); const vt = (tip === 'eksi' ? '' : tip === 'arti' ? '+' : '') + TL(v); let fs = 24 * s; c.font = `800 ${fs}px Mont`; while (c.measureText(vt).width > bw * .97 && fs > 11) { fs -= 1; c.font = `800 ${fs}px Mont`; } c.textAlign = 'center'; c.fillStyle = col; c.fillText(vt, x0 + i * bw + bw / 2, Math.min(yA, yB) - 14 * s);
    c.font = `600 ${20 * s}px Mont`; c.fillStyle = '#dfe6ee'; const satir = ad.split('\n'); satir.forEach((t, j) => c.fillText(t, x0 + i * bw + bw / 2, y0 + 36 * s + j * 24 * s)); c.globalAlpha = a; });
  c.textAlign = 'left'; if (o.not) { c.font = `600 ${20 * s}px Mont`; c.fillStyle = '#9fb3c8'; c.fillText(o.not, x + 34 * s, y + h - 24 * s); } c.restore();
}
// Basit çizgi grafik (altın fiyatı)
export function grafik(c, o) { const { x, y, w, h, s = 1, a, k = 1, veri } = o; if (a <= .003) return; kart(c, x, y, w, h, a); c.save(); c.globalAlpha = a; baslik(c, x + 34 * s, y + 48 * s, o.baslik, 1, s);
  const mn = Math.min(...veri), mx = Math.max(...veri), px = i => x + 50 * s + i / (veri.length - 1) * (w - 100 * s), py = v => y + h - 70 * s - (v - mn) / (mx - mn) * (h - 160 * s);
  c.strokeStyle = 'rgba(255,255,255,.08)'; for (let i = 0; i < 4; i++) { c.beginPath(); c.moveTo(x + 50 * s, y + 100 * s + i * (h - 170 * s) / 3); c.lineTo(x + w - 50 * s, y + 100 * s + i * (h - 170 * s) / 3); c.stroke(); }
  const n = Math.max(2, Math.floor(veri.length * ease(k))); c.strokeStyle = '#e8c46a'; c.lineWidth = 5 * s; c.shadowColor = '#e8c46a'; c.shadowBlur = 16; c.beginPath(); for (let i = 0; i < n; i++) i ? c.lineTo(px(i), py(veri[i])) : c.moveTo(px(i), py(veri[i])); c.stroke(); c.shadowBlur = 0;
  c.fillStyle = '#fff'; c.beginPath(); c.arc(px(n - 1), py(veri[n - 1]), 8 * s, 0, 7); c.fill(); (o.etiketler || []).forEach(([i, t, col]) => { if (i < n) { c.font = `700 ${20 * s}px Mont`; c.fillStyle = col; c.textAlign = 'center'; c.fillText(t, px(i), py(veri[i]) - 22 * s); } });
  c.textAlign = 'left'; c.restore(); }
export function rozet(c, x, y, t, a, renk = '#e8c46a', s = 1) { if (a <= .003) return; c.save(); c.globalAlpha = a; c.font = `800 ${22 * s}px Mont`; c.letterSpacing = `${3 * s}px`; const w = c.measureText(t).width + 50 * s; c.fillStyle = 'rgba(6,10,18,.72)'; rr(c, x - w / 2, y - 26 * s, w, 52 * s, 26 * s); c.fill(); c.strokeStyle = renk; c.lineWidth = 2; c.stroke(); c.fillStyle = renk; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillText(t, x, y + 1); c.restore(); }
export function kartYazi(c, W, H, satirlar, a, s = 1) { // siyah ekran yazıları
  c.save(); c.globalAlpha = a; c.textAlign = 'center'; c.textBaseline = 'middle'; satirlar.forEach(([t, font, renk, dy]) => { c.font = font.replace(/(\d+)px/, (m, p) => `${p * s}px`); c.fillStyle = renk; c.shadowColor = renk === '#e8c46a' ? 'rgba(232,196,106,.5)' : 'rgba(0,0,0,0)'; c.shadowBlur = 30; c.fillText(t, W / 2, H / 2 + dy * s); }); c.restore(); }
