# VAYYMATİK0 ses tasarımı — tamamen kodla üretilen (telifsiz) müzik + efekt sentezi ve miks araçları. Tüm bölümlerde ortak.
# Müzik 24 kHz'de sentezlenir (pad/piyano/bas için yeterli), efektler 48 kHz. Çıkışlar stereo float32 (N, 2).
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve, resample_poly
from scipy.ndimage import minimum_filter1d
SR, SRM = 48000, 24000
R = np.random.default_rng(11)
hz = lambda m: 440. * 2 ** ((m - 69) / 12)
def _f(x, kind, f, sr, o=2): return sosfilt(butter(o, f, kind, fs=sr, output='sos'), x, axis=0)
lp = lambda x, f, sr=SR, o=2: _f(x, 'low', f, sr, o)
hp = lambda x, f, sr=SR, o=2: _f(x, 'high', f, sr, o)
bp = lambda x, a, b, sr=SR, o=2: _f(x, 'band', [a, b], sr, o)
def tt(d, sr=SR): return np.arange(int(d * sr)) / sr
def gurultu(n): return R.standard_normal(n).astype(np.float32)
def zarf(n, a, r, sr, tepe=1.):  # atak / bırakma (sn)
    e = np.full(n, tepe, np.float32); na, nr = min(n, int(a * sr)), min(n, int(r * sr))
    if na: e[:na] *= np.linspace(0, 1, na) ** 1.5
    if nr: e[n - nr:] *= np.linspace(1, 0, nr) ** 2
    return e
def ekle(buf, x, t, sr, kaz=1.):  # stereo tampona yerleştir
    i = int(t * sr)
    if i >= len(buf) or i + len(x) <= 0: return
    if x.ndim == 1: x = np.stack([x, x], 1)
    a, b = max(0, i), min(len(buf), i + len(x)); buf[a:b] += x[a - i:b - i] * kaz
def pan(x, p):  # p: -1 sol .. 1 sağ (eşit güç)
    a = (p + 1) * np.pi / 4; return np.stack([x * np.cos(a), x * np.sin(a)], 1)
# ---------- dalga tablosu osilatörleri ----------
_N = 4096; _ph = np.arange(_N) / _N
WT = {'saw': sum(np.sin(2 * np.pi * k * _ph) / k for k in range(1, 25)) * .55, 'sin': np.sin(2 * np.pi * _ph),
      'kare': sum(np.sin(2 * np.pi * k * _ph) / k for k in range(1, 24, 2)) * .8, 'ucgen': sum(((-1) ** (k // 2)) * np.sin(2 * np.pi * k * _ph) / k ** 2 for k in range(1, 22, 2)) * .8}
def osc(f, n, sr=SRM, dalga='saw', faz=None):
    f = np.broadcast_to(np.asarray(f, np.float64), (n,)); ph = (np.cumsum(f / sr) + (R.random() if faz is None else faz)) % 1.
    return WT[dalga][(ph * _N).astype(np.int64) % _N].astype(np.float32)
# ---------- enstrümanlar (SRM) ----------
def piyano(m, d=3.2, v=.6):
    t = tt(d, SRM); f = hz(m); y = np.zeros_like(t)
    for k in range(1, 9):
        fk = k * f * np.sqrt(1 + .0004 * k * k)
        if fk > SRM / 2.2: break
        y += np.sin(2 * np.pi * fk * t) * (k ** -1.25) * np.exp(-t * (1.1 + .85 * k) * (f / 440) ** .3)
    y *= zarf(len(t), .004, .25, SRM); y[:int(.012 * SRM)] += bp(gurultu(int(.012 * SRM)), 1800, 5000, SRM) * .08
    return (y * v * .35).astype(np.float32)
def pluck(m, d=.9, v=.5, parlak=1.):
    t = tt(d, SRM); f = hz(m); y = np.zeros_like(t)
    for k in range(1, 12):
        if k * f > SRM / 2.2: break
        y += np.sin(2 * np.pi * k * f * t) / k * np.exp(-t * (3 + 4.5 * k / parlak))
    return (y * zarf(len(t), .002, .08, SRM) * v * .3).astype(np.float32)
def bas(m, d, v=.5):
    t = tt(d, SRM); f = hz(m); y = np.sin(2 * np.pi * f * t) + .28 * np.sin(4 * np.pi * f * t) + .1 * np.sin(6 * np.pi * f * t)
    return (np.tanh(y * 1.3) * zarf(len(t), .01, min(.25, d * .4), SRM) * v * .45).astype(np.float32)
def pad(notalar, d, v=.5, kesim=1400, atak=1.6, birak=2.2, trem=0.):  # dedune testere yaylı/synth pad, stereo
    n = int(d * SRM); out = np.zeros((n, 2), np.float32)
    for j, m in enumerate(notalar):
        for c, p in ((-9, -.7), (0, 0), (8, .7)):
            out += pan(osc(hz(m) * 2 ** (c / 1200), n), p) * (.33 / len(notalar) ** .5)
    out = lp(lp(out, kesim, SRM), kesim * 1.4, SRM)
    if trem: out *= (1 - .45 + .45 * np.sin(2 * np.pi * trem * tt(d, SRM)))[:, None]
    return out * zarf(n, atak, birak, SRM)[:, None] * v
def drone(m, d, v=.5):
    n = int(d * SRM); t = tt(d, SRM); x = osc(hz(m), n, dalga='saw') * .5 + np.sin(2 * np.pi * hz(m) * t) * .8 + np.sin(np.pi * hz(m) * t) * .5
    x = lp(x, 260 + 120 * np.sin(t[-1] * .1), SRM); x *= .8 + .2 * np.sin(2 * np.pi * .07 * t)
    return pan(x * zarf(n, 3, 3, SRM) * v * .45, 0)
def davul(tip, v=.6, sr=SRM):
    if tip == 'kick': t = tt(.4, sr); f = 45 + 80 * np.exp(-t * 28); y = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 7.5); y[:int(.004 * sr)] += gurultu(int(.004 * sr)) * .15
    elif tip == 'clap':
        n = int(.25 * sr); y = np.zeros(n, np.float32); g = bp(gurultu(n), 900, 3200, sr); tn = np.arange(n) / sr
        for o in (0, .011, .022): i0 = int(o * sr); y[i0:] += (g * np.exp(-tn * (60 if o < .02 else 18)))[:n - i0] * .6
    elif tip == 'hat': n = int(.06 * sr); y = hp(gurultu(n), 7000, sr) * np.exp(-np.arange(n) / sr * 70) * .5
    elif tip == 'shaker': n = int(.09 * sr); y = bp(gurultu(n), 5000, 10500, sr) * zarf(n, .02, .06, sr) * .35
    elif tip == 'kalp': t = tt(.6, sr); y = (np.sin(2 * np.pi * 52 * t) * np.exp(-t * 16) + .7 * np.where(t > .27, np.sin(2 * np.pi * 47 * (t - .27)) * np.exp(-(t - .27) * 18), 0))
    elif tip == 'tik': n = int(.03 * sr); y = bp(gurultu(n), 2500, 6000 if sr > 20000 else 5000, sr) * np.exp(-np.arange(n) / sr * 260) * 1.4
    elif tip == 'tak': n = int(.04 * sr); t = np.arange(n) / sr; y = (np.sin(2 * np.pi * 1300 * t) * .6 + bp(gurultu(n), 900, 2500, sr) * .7) * np.exp(-t * 160)
    return (np.asarray(y, np.float32) * v)
def yanki(x, sr, rt=2.2, islak=.25, on=.02):  # stereo konvolüsyon yankısı (sentetik IR)
    n = int(rt * sr); t = np.arange(n) / sr; ir = np.stack([gurultu(n), gurultu(n)], 1) * np.exp(-t * 6.9 / rt)[:, None]
    ir = lp(ir, 5500 if sr > 30000 else 4200, sr); ir[:int(on * sr)] = 0; ir /= np.sqrt(np.sum(ir ** 2) / 2)
    x2 = x if x.ndim > 1 else np.stack([x, x], 1); w = np.stack([fftconvolve(x2[:, c], ir[:, c])[:len(x2)] for c in (0, 1)], 1)
    return (x2 * (1 - islak * .5) + w * islak * .35).astype(np.float32)
# ---------- müzik işaretleri (cue) ----------
AK = {'Dm': [50, 53, 57], 'Bb': [46, 50, 53], 'Gm': [43, 46, 50], 'A': [45, 49, 52], 'F': [41, 45, 48], 'C': [48, 52, 55], 'Am': [45, 48, 52], 'G': [43, 47, 50], 'Em': [40, 43, 47], 'Dsus': [50, 55, 57]}
def ilerle(d, akorlar, sure):  # akor zaman çizelgesi: [(t0, ad)]
    out, t, i = [], 0., 0
    while t < d: out.append((t, akorlar[i % len(akorlar)])); t += sure; i += 1
    return out
def cue(ruh, d, yogunluk=1.):
    """ruh: gerilim | melankoli | umut | tedirgin | kriz | suspense | yukselis | tefekkur | final. d: süre (sn). Döner: SRM stereo."""
    n = int(d * SRM); M = np.zeros((n, 2), np.float32)
    def pd(ak, sure, v, kesim, trem=0., oktav=0):
        for t0, a in ilerle(d, ak, sure): ekle(M, pad([m + oktav for m in AK[a]], min(sure + 2.4, d - t0 + 2), v, kesim, trem=trem), t0, SRM)
    def bs(ak, sure, v, desen=None, bpm=80):
        for t0, a in ilerle(d, ak, sure):
            k = AK[a][0] - 12 if AK[a][0] >= 40 else AK[a][0]
            if desen is None: ekle(M, pan(bas(k, sure * .98, v), 0), t0, SRM)
            else:
                st = 60 / bpm * desen; x = t0
                while x < min(d, t0 + sure) - .01: ekle(M, pan(bas(k, st * .85, v), 0), x, SRM); x += st
    if ruh in ('gerilim', 'final', 'suspense'):
        ekle(M, drone(38, d + 1, .55 if ruh != 'suspense' else .42), 0, SRM); pd(['Dm', 'Bb', 'Gm', 'A'], 8., .32, 900, trem=0)
        t = 1.5
        while t < d - 1: m = R.choice([74, 77, 81, 69, 72]); ekle(M, pan(piyano(m, 3.5, .32), R.uniform(-.5, .5)), t, SRM); t += R.uniform(2.6, 4.6)
        if ruh == 'suspense':
            st, t = 60 / 100 / 2, 0.
            while t < d: ekle(M, pan(bas(38, st * .5, .32), 0), t, SRM); t += st
    elif ruh == 'melankoli':
        pd(['Am', 'F', 'C', 'G'], 6.8, .22, 1200); st = 60 / 70 / 2
        for t0, a in ilerle(d, ['Am', 'F', 'C', 'G'], 6.8):
            ar = [AK[a][0] + 12, AK[a][1] + 12, AK[a][2] + 12, AK[a][1] + 24]; x, j = t0, 0
            while x < min(d, t0 + 6.8) - .05: ekle(M, pan(piyano(ar[j % 4], 2.6, .36 if j % 4 == 0 else .26), [-.3, .1, .3, -.1][j % 4]), x, SRM); x += st; j += 1
        bs(['Am', 'F', 'C', 'G'], 6.8, .28)
    elif ruh in ('umut', 'yukselis', 'tedirgin'):
        bpm = {'umut': 84, 'yukselis': 100, 'tedirgin': 92}[ruh]; b = 60 / bpm; bar = b * 4
        ak = {'umut': ['C', 'G', 'Am', 'F'], 'yukselis': ['F', 'C', 'Dm', 'Bb'], 'tedirgin': ['Dm', 'Bb', 'F', 'C']}[ruh]
        pd(ak, bar * 2, .26 if ruh != 'tedirgin' else .22, 1600 if ruh == 'yukselis' else 1100)
        bs(ak, bar * 2, .3, desen=.5 if ruh != 'umut' else 1, bpm=bpm)
        for t0, a in ilerle(d, ak, bar * 2):
            ar = AK[a] + [AK[a][0] + 12]; x, j = t0, 0
            while x < min(d, t0 + bar * 2) - .02:
                if ruh != 'tedirgin' or j % 2 == 0: ekle(M, pan(pluck(ar[j % 4] + 12, .8, .42 if ruh == 'yukselis' else .34, 1.4 if ruh == 'yukselis' else 1), [-.4, .4, -.2, .2][j % 4]), x, SRM)
                x += b / 2; j += 1
        g0 = 0 if ruh != 'yukselis' else min(d * .25, 12.)  # yükselişte davul giriş gecikmesi
        x, j = 0., 0
        while x < d:
            if x >= g0:
                if ruh == 'yukselis': ekle(M, pan(davul('kick', .55), 0), x, SRM) if j % 2 == 0 else None; ekle(M, pan(davul('clap', .28), 0), x, SRM) if j % 4 == 2 else None
                elif j % 4 == 0: ekle(M, pan(davul('kick', .32 if ruh == 'umut' else .4), 0), x, SRM)
                ekle(M, pan(davul('shaker' if ruh != 'tedirgin' else 'hat', .22 if ruh != 'tedirgin' else .2), .25), x, SRM)
            x += b / 2; j += 1
    elif ruh == 'kriz':
        ekle(M, drone(38, d + 1, .5), 0, SRM); pd(['Dm', 'Bb', 'Dm', 'A'], 6., .3, 1000, trem=7.)
        x, j = 0., 0
        while x < d: ekle(M, pan(davul('kalp', .55), 0), x, SRM) if j % 2 == 0 else None; x += .45; j += 1
    elif ruh == 'tefekkur':
        pd(['F', 'Am', 'Bb', 'C'], 7.2, .22, 1100)
        for t0, a in ilerle(d, ['F', 'Am', 'Bb', 'C'], 7.2):
            for j, m in enumerate(AK[a] + [AK[a][0] + 12]): ekle(M, pan(piyano(m + 12, 4.5, .28), [-.3, -.1, .1, .3][j]), t0 + j * .09, SRM)
            ekle(M, pan(piyano(AK[a][2] + 24, 3, .2), .2), t0 + 3.6, SRM)
        bs(['F', 'Am', 'Bb', 'C'], 7.2, .22)
    M = yanki(M, SRM, 2.6 if ruh in ('gerilim', 'final', 'tefekkur', 'melankoli') else 1.8, .3)
    f = int(min(1.2, d / 4) * SRM); M[:f] *= np.linspace(0, 1, f)[:, None]; M[-f:] *= np.linspace(1, 0, f)[:, None] ** 1.5
    return M * yogunluk
def srm_to_sr(x): return resample_poly(x, SR // SRM, 1, axis=0).astype(np.float32)
# ---------- efektler (SR) ----------
def yagmur(d, ic=False):
    n = int(d * SR); x = np.stack([gurultu(n), gurultu(n)], 1); x = bp(x, 400, 9000) * .18 + lp(x, 300) * .25
    dam = np.zeros((n, 2), np.float32); k = int(d * 55); idx = R.integers(0, n - 2000, k)
    for i in idx: L = int(R.uniform(.004, .012) * SR); dam[i:i + L, R.integers(0, 2)] += bp(gurultu(L), 2000, 7000)[:L] * np.exp(-np.arange(L) / SR * 400) * R.uniform(.1, .5)
    y = x + dam; y = lp(y, 1600) * 1.6 if ic else y
    return y * zarf(n, 1.0, 1.0, SR)[:, None]
def sokak(d):
    n = int(d * SR); x = lp(np.stack([gurultu(n), gurultu(n)], 1), 500) * .35 + bp(np.stack([gurultu(n), gurultu(n)], 1), 800, 2500) * .04
    t = tt(d); x *= (1 + .35 * np.sin(2 * np.pi * .05 * t + 1))[:, None]
    for t0 in np.arange(R.uniform(1, 4), d - 3, R.uniform(6, 10)):  # geçen araba
        L = int(3.2 * SR); e = np.exp(-((np.arange(L) / SR - 1.6) / .7) ** 2); a = lp(gurultu(L), 700) * e * .8; ekle(x, pan(a, R.uniform(-.8, .8)), t0, SR)
    return x * zarf(n, .8, .8, SR)[:, None]
def oda(d, saat=False, klima=False):
    n = int(d * SR); x = lp(np.stack([gurultu(n), gurultu(n)], 1), 250) * .08
    if klima: x += lp(bp(np.stack([gurultu(n), gurultu(n)], 1), 120, 900), 600) * .05 + pan(np.sin(2 * np.pi * 120 * tt(d)) * .004, 0)
    if saat:
        for k, t0 in enumerate(np.arange(.3, d, 1.)): ekle(x, pan(davul('tik' if k % 2 else 'tak', .12, SR), .5), t0, SR)
    return x * zarf(n, .6, .6, SR)[:, None]
def kapi_zili():
    t = tt(2.2); y = sum(np.sin(2 * np.pi * f * t) * a * np.exp(-t * dc) for f, a, dc in ((1568, .5, 2.2), (2093, .35, 2.8), (2637, .25, 3.5), (3951, .1, 5)))
    y2 = np.zeros_like(y); s = int(.14 * SR); y2[s:] = (sum(np.sin(2 * np.pi * f * t) * a * np.exp(-t * dc) for f, a, dc in ((1319, .45, 2.4), (1760, .3, 3), (2637, .15, 4))))[:-s]
    return pan((y + y2) * .35, .3)
def yazarkasa():
    x = np.zeros(int(1.6 * SR), np.float32)
    for k in range(5): ekle2 = davul('tak', .3, SR); x[int(k * .07 * SR):int(k * .07 * SR) + len(ekle2)] += ekle2
    L = int(.5 * SR); x[int(.42 * SR):int(.42 * SR) + L] += lp(gurultu(L), 1800) * np.exp(-np.arange(L) / SR * 9) * .5  # çekmece
    t = tt(1.1); x[int(.4 * SR):int(.4 * SR) + len(t)] += (np.sin(2 * np.pi * 2637 * t) + .4 * np.sin(2 * np.pi * 5274 * t)) * np.exp(-t * 4) * .35  # zil
    return pan(x * .6, -.1)
def bozuk_para(k=6):
    x = np.zeros(int(1.4 * SR), np.float32)
    for i in range(k):
        t0 = R.uniform(0, .6); L = int(.35 * SR); t = np.arange(L) / SR; f = R.uniform(3000, 7000)
        s = sum(np.sin(2 * np.pi * f * r * t) * a for r, a in ((1, .6), (1.47, .3), (2.09, .2))) * np.exp(-t * R.uniform(14, 30)); i0 = int(t0 * SR); x[i0:i0 + L] += s * R.uniform(.15, .4)
    return pan(x, .15)
def telefon_cal(kez=2):
    x = np.zeros(int(kez * 1.6 * SR), np.float32)
    for k in range(kez):  # marimba benzeri melodik zil
        for j, m in enumerate([83, 88, 91, 88, 83, 88]):
            t = tt(.35); s = (np.sin(2 * np.pi * hz(m) * t) + .3 * np.sin(2 * np.pi * hz(m) * 4 * t)) * np.exp(-t * 14); i0 = int((k * 1.6 + j * .11) * SR); x[i0:i0 + len(s)] += s * .3
    return pan(lp(x, 6000), .2)
def kalem(d):
    n = int(d * SR); x = bp(gurultu(n), 2500, 7000) * .12; t = tt(d); m = (np.sin(2 * np.pi * 7 * t) > .2) * (np.sin(2 * np.pi * .9 * t) > -.4)
    return pan(x * lp(m.astype(np.float32), 30), -.2)
def kepenk(d=2.4):
    n = int(d * SR); t = tt(d); x = bp(gurultu(n), 300, 3500) * (np.abs(np.sin(2 * np.pi * 9 * t)) ** 3) * .35 + lp(gurultu(n), 160) * .4
    x *= zarf(n, .1, .5, SR)
    return pan(x, 0)
def matkap(d=2.2):
    n = int(d * SR); t = tt(d); f = 180 + 60 * np.minimum(t * 4, 1); x = np.tanh(np.sin(2 * np.pi * np.cumsum(f) / SR) * 3) * .12 + bp(gurultu(n), 1500, 5000) * .05
    x *= zarf(n, .05, .2, SR) * (t < 1.2); y = np.zeros(n, np.float32)
    for t0 in (1.45, 1.75, 2.0): i0 = int(t0 * SR); h = davul('tak', .7, SR); y[i0:i0 + len(h)] += h[:n - i0]
    return pan(x + y, .35)
def alev(d):
    n = int(d * SR); return pan(bp(gurultu(n), 800, 6000) * .06 * zarf(n, .3, .3, SR), .3)
def whoosh(d=.7, yukari=True, v=.5):
    n = int(d * SR); t = tt(d); fc = (np.linspace(400, 4000, n) if yukari else np.linspace(3500, 300, n)); x = gurultu(n); y = np.zeros(n, np.float32)
    for k in range(0, n, 1200): a, b = k, min(n, k + 1200); f0 = fc[a]; y[a:b] = bp(x[max(0, a - 600):b], f0 * .7, min(f0 * 1.4, 20000))[-(b - a):]
    return pan(y * np.sin(np.pi * t / d) ** 2 * v, 0)
def vurus(d=3.5, v=.8):  # sinematik darbe
    t = tt(d); f = 32 + 60 * np.exp(-t * 6); x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6) + lp(gurultu(len(t)), 1200) * np.exp(-t * 9) * .5
    return yanki(pan(np.tanh(x * 1.4) * v * .7, 0), SR, 3.0, .35)
def yukselen(d=2.5, v=.4):
    t = tt(d); x = bp(gurultu(len(t)), 600, 8000) * (t / d) ** 2.2; return pan(x * v, 0)
def hud_tik(k=5, v=.12):
    x = np.zeros(int(k * .07 * SR + .05 * SR), np.float32)
    for i in range(k): t = tt(.03); s = np.sin(2 * np.pi * (2400 + 160 * i) * t) * np.exp(-t * 180); x[int(i * .07 * SR):int(i * .07 * SR) + len(s)] += s * v
    return pan(x, .4)
def araba_kapi():
    x = np.zeros(int(1.6 * SR), np.float32); h = lp(gurultu(int(.25 * SR)), 900) * np.exp(-np.arange(int(.25 * SR)) / SR * 22); x[:len(h)] += h * 1.1
    for k in range(6): t = tt(.12); s = sum(np.sin(2 * np.pi * f * t) for f in (4100, 6200)) * np.exp(-t * 40) * .08; i0 = int((.6 + k * .09) * SR); x[i0:i0 + len(s)] += s
    return pan(x, -.3)
def telefon_filtre(y): return np.tanh(bp(y, 280, 4200, o=3) * 2.2) * .62  # telefondan gelen ses
# ---------- miks araçları ----------
def limiter(x, ceil_db, look=.005, rel=.08, B=32):  # 4x aşırı örneklemeli gerçek tepe sınırlayıcı (uzun dosyalar için blok tabanlı)
    x2 = x if x.ndim > 1 else x[:, None]; c = 10 ** (ceil_db / 20); n = len(x2); pk = np.empty(n, np.float32)
    for i in range(0, n, 480000):
        j = min(n, i + 480000); a0 = max(0, i - 64); up = np.abs(resample_poly(x2[a0:min(n, j + 64)], 4, 1, axis=0)).max(1).reshape(-1, 4).max(1); pk[i:j] = up[i - a0:i - a0 + j - i]
    need = np.minimum(1, c / np.maximum(pk, 1e-9)); L = int(look * SR); g = minimum_filter1d(np.concatenate([need[L:], np.ones(L, np.float32)]), 2 * L + 1)
    m = -(-n // B); gb = np.concatenate([g, np.ones(m * B - n, np.float32)]).reshape(m, B).min(1); a = np.exp(-B / (rel * SR)); yb = np.empty(m); v = 1.
    for i, s in enumerate(gb): v = s if s < v else a * v + (1 - a) * s; yb[i] = v
    y = np.minimum(np.interp(np.arange(n), np.arange(m) * B + B / 2, yb), g).astype(np.float32); r = x2 * y[:, None]; return r if x.ndim > 1 else r[:, 0]
def zarf_takip(v, sn=.12):  # ses zarfı (ducking için), 0..1
    a = np.abs(v if v.ndim == 1 else v.mean(1)); w = int(sn * SR); e = np.convolve(a, np.ones(w) / w, 'same'); e = np.convolve(e, np.ones(2 * w) / (2 * w), 'same')
    return np.clip(e / (np.percentile(e[e > 1e-5], 90) + 1e-9), 0, 1) if np.any(e > 1e-5) else e
