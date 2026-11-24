# VAYYMATİK0 – ses tasarımı: seslendirme işleme, özgün (sentezlenmiş) müzik, efektler, miks ve mastering.
# Tüm müzik ve efektler bu betikte sıfırdan sentezlenir: telif sorunu yoktur.
import json, sys, os, wave, numpy as np
from scipy.signal import butter, sosfilt, lfilter, resample_poly, fftconvolve
D = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(D)
SR, DUR = 48000, 45.0
N = int(SR * DUR); T = np.arange(N) / SR
R = np.random.default_rng(2026)

# ---------------- yardımcılar ----------------
def rd(p):
    with wave.open(p) as w: return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
def wr(p, x):
    x = np.atleast_2d(x.T).T if x.ndim == 1 else x
    with wave.open(p, 'wb') as w:
        w.setnchannels(x.shape[1] if x.ndim > 1 else 1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
db = lambda g: 10 ** (g / 20)
def biquad(kind, f0, g=0, q=.707):
    A, w0 = 10 ** (g / 40), 2 * np.pi * f0 / SR; c, s = np.cos(w0), np.sin(w0); al = s / (2 * q)
    if kind == 'peak': b = [1 + al * A, -2 * c, 1 - al * A]; a = [1 + al / A, -2 * c, 1 - al / A]
    elif kind == 'low':
        sq = 2 * np.sqrt(A) * al; b = [A * ((A + 1) - (A - 1) * c + sq), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - sq)]; a = [(A + 1) + (A - 1) * c + sq, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - sq]
    else:
        sq = 2 * np.sqrt(A) * al; b = [A * ((A + 1) + (A - 1) * c + sq), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - sq)]; a = [(A + 1) - (A - 1) * c + sq, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - sq]
    return np.array(b) / a[0], np.array(a) / a[0]
def eq(x, kind, f0, g=0, q=.707): b, a = biquad(kind, f0, g, q); return lfilter(b, a, x, axis=0)
def lp(x, f, o=2): return sosfilt(butter(o, f, 'low', fs=SR, output='sos'), x, axis=0)
def hp(x, f, o=2): return sosfilt(butter(o, f, 'high', fs=SR, output='sos'), x, axis=0)
def bp(x, f1, f2, o=2): return sosfilt(butter(o, [f1, f2], 'band', fs=SR, output='sos'), x, axis=0)
def env_follow(x, att, rel):
    a1, a2 = np.exp(-1 / (att * SR)), np.exp(-1 / (rel * SR)); y = np.zeros_like(x); v = 0.0
    for i, s in enumerate(x): v = a1 * v + (1 - a1) * s if s > v else a2 * v + (1 - a2) * s; y[i] = v
    return y
def env_fast(x, att, rel, dec=48):  # blok tabanlı hızlı zarf (dec örnekte bir)
    m = np.abs(x).reshape(-1, dec).max(1) if len(x) % dec == 0 else np.abs(np.pad(x, (0, dec - len(x) % dec))).reshape(-1, dec).max(1)
    sr2 = SR / dec; a1, a2 = np.exp(-1 / (att * sr2)), np.exp(-1 / (rel * sr2)); y = np.zeros_like(m); v = 0.0
    for i, s in enumerate(m): v = a1 * v + (1 - a1) * s if s > v else a2 * v + (1 - a2) * s; y[i] = v
    return np.repeat(y, dec)[:len(x)]
def kweight(x):
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1, -1.69065929318241, .73248077421585]
    b2, a2 = [1., -2., 1.], [1, -1.99004745483398, .99007225036621]
    return lfilter(b2, a2, lfilter(b1, a1, x, axis=0), axis=0)
def lufs(x):  # ITU-R BS.1770-4 bütünleşik ses yüksekliği
    x = x if x.ndim > 1 else x[:, None]; k = kweight(x); B, H = int(.4 * SR), int(.1 * SR)
    z = np.array([np.sum(np.mean(k[i:i + B] ** 2, 0)) for i in range(0, len(k) - B, H)]); l = -.691 + 10 * np.log10(z + 1e-12)
    z1 = z[l > -70]; g = -.691 + 10 * np.log10(z1.mean()) - 10; z2 = z[l > max(-70, g)]
    return -.691 + 10 * np.log10(z2.mean())
def tpeak(x): x = x if x.ndim > 1 else x[:, None]; return 20 * np.log10(np.max(np.abs(resample_poly(x, 4, 1, axis=0))) + 1e-12)
def limiter(x, ceil_db=-1.5, look=.005, rel=.08):
    c = db(ceil_db); x2 = x if x.ndim > 1 else x[:, None]
    pk = np.max(np.abs(resample_poly(x2, 4, 1, axis=0)), 1).reshape(-1, 4).max(1)[:len(x2)]
    need = np.minimum(1, c / np.maximum(pk, 1e-9)); L = int(look * SR)
    from scipy.ndimage import minimum_filter1d
    g = minimum_filter1d(np.concatenate([need[L:], np.ones(L)]), L * 2 + 1)
    a = np.exp(-1 / (rel * SR)); y = np.empty_like(g); v = 1.0
    for i, s in enumerate(g): v = s if s < v else a * v + (1 - a) * s; y[i] = v
    out = x2 * y[:, None]; return out if x.ndim > 1 else out[:, 0]
def place(buf, x, t, gain=1.0, pan=0.0):
    i = int(t * SR); n = max(0, min(len(x), len(buf) - i)); x = x[:n]
    if buf.ndim == 2 and x.ndim == 2: buf[i:i + n] += x * gain
    elif buf.ndim == 2: buf[i:i + n, 0] += x * gain * np.sqrt(1 - pan); buf[i:i + n, 1] += x * gain * np.sqrt(1 + pan)
    else: buf[i:i + n] += x * gain
def adsr(n, a, r, sus=1.0):
    e = np.full(n, sus); A, Rl = int(a * SR), int(r * SR); e[:A] = np.linspace(0, sus, A) if A else e[:A]
    if Rl: e[-Rl:] *= np.linspace(1, 0, Rl) ** 1.5
    return e
mtof = lambda m: 440 * 2 ** ((m - 69) / 12)
noise = lambda n: R.standard_normal(n).astype(np.float32)
def reverb_ir(rt=2.2, pre=.02, bright=4500):
    n = int(rt * SR); t = np.arange(n) / SR; ir = np.stack([noise(n), noise(n)], 1) * np.exp(-6.9 * t / rt)[:, None]
    ir = lp(ir, bright); ir[:int(pre * SR)] = 0; return ir / np.sqrt(np.sum(ir ** 2))
IR = reverb_ir()
def verb(x, wet=.3):
    x2 = x if x.ndim > 1 else np.stack([x, x], 1)
    w = np.stack([fftconvolve(x2[:, 0], IR[:, 0])[:len(x2)], fftconvolve(x2[:, 1], IR[:, 1])[:len(x2)]], 1)
    return x2 * (1 - wet * .5) + w * wet

# ---------------- 1) Seslendirme ----------------
segs = json.load(open(f'{ROOT}/voice/segs.json'))
V = np.zeros(N, np.float32)
for s in segs: place(V, rd(f"{ROOT}/voice/segs/{s['id']}.wav"), s['t'])
V = hp(V, 75); V = eq(V, 'low', 180, -2.0); V = eq(V, 'peak', 3200, 2.5, 1.0); V = eq(V, 'peak', 7000, 1.0, 1.2)
e = env_fast(V, .005, .12); thr = db(-24); gr = np.where(e > thr, (e / thr) ** (1 / 3 - 1), 1.0)  # 3:1 kompresör
V = V * gr
V *= db(-16 - lufs(V)); V = limiter(V, -1.5)
V *= db(-16 - lufs(V)); V = limiter(V, -1.6)
print(f'seslendirme: {lufs(V):.2f} LUFS, tepe {tpeak(V):.2f} dBTP')
wr(f'{D}/voice_track.wav', V)

# ---------------- 2) Müzik (özgün sentez) ----------------
M = np.zeros((N, 2), np.float32)
CH = [(0, 3.5, [50, 57, 64, 65, 72]), (3.5, 6.5, [50, 57, 62, 65]), (6.5, 9.6, [46, 53, 57, 62]), (9.6, 13.0, [43, 50, 55, 58, 62]), (13.0, 16.4, [45, 52, 57, 61, 64]),
      (16.4, 19.6, [41, 48, 53, 57, 60]), (19.6, 23.4, [48, 55, 60, 64, 67]), (23.4, 26.15, [38, 50, 51, 57]), (26.15, 30.6, [38, 45, 50, 53]), (30.6, 34.6, [46, 53, 58, 62, 65]),
      (34.6, 37.6, [45, 53, 57, 60, 65]), (37.6, 40.6, [43, 50, 55, 58, 62]), (40.6, 42.4, [45, 52, 57, 61, 64]), (42.4, 45.0, [50, 57, 62, 66, 69])]
def pad_note(f, n, cutoff, det=(-.11, 0, .1)):
    t = np.arange(n) / SR; out = np.zeros((n, 2), np.float32)
    for j, d in enumerate(det):
        ff = f * 2 ** (d / 12); ph = R.random() * 6.28; s = np.zeros(n, np.float32)
        for k in range(1, 40):
            amp = (1 / k) * np.exp(-k * ff / cutoff)
            if k * ff > 9000 or amp < .004: break
            s += np.sin(2 * np.pi * k * ff * t + ph * k) * amp
        pan = (j - 1) * .6; out[:, 0] += s * (1 - pan) * .5; out[:, 1] += s * (1 + pan) * .5
    return out
bright = lambda t: np.interp(t, [0, 3.4, 3.6, 9.5, 9.7, 16.3, 16.5, 23.3, 23.5, 30.5, 30.7, 37.5, 37.7, 45], [1600, 2400, 500, 700, 1500, 1800, 2200, 2600, 450, 500, 1200, 1600, 2000, 2600])
for t0, t1, notes in CH:
    a0, a1 = max(0, t0 - .35), min(DUR, t1 + .9); n = int((a1 - a0) * SR)
    cut = float(bright((t0 + t1) / 2)); e = adsr(n, .55 if t0 else 1.2, 1.1)
    for m in notes: place(M, pad_note(mtof(m), n, cut) * e[:, None], a0, .05)
lvl = np.interp(T, [0, .2, 3.3, 3.6, 9.4, 9.7, 23.3, 23.5, 26.1, 26.2, 26.7, 30.5, 37.6, 42.4, 44.4, 45], [.5, .8, 1.0, .7, .8, 1.0, 1.0, .9, 1.1, .2, .8, .8, 1.05, 1.15, .9, 0])
M *= lvl[:, None]
# Sub bas
sub = np.zeros(N, np.float32)
for t0, t1, notes in CH:
    i0, i1 = int(t0 * SR), int(min(DUR, t1) * SR); f = mtof(min(notes) - 12 if min(notes) > 40 else min(notes)); n = i1 - i0
    sub[i0:i1] += np.tanh(1.5 * np.sin(2 * np.pi * f * np.arange(n) / SR)) * adsr(n, .08, .2) * .5
puls = np.ones(N, np.float32)
for a, b, per in [(3.5, 9.6, .75), (9.6, 23.4, .5), (23.4, 26.15, .375), (30.6, 37.6, .5), (37.6, 42.4, .5)]:
    m = (T >= a) & (T < b); ph = ((T[m] - a) % per) / per; puls[m] = .35 + .65 * np.exp(-ph * 5)
place(M, np.stack([sub * puls, sub * puls], 1), 0, .45)
# Arpej (pluck)
def pluck(f, dur=.45):
    n = int(dur * SR); t = np.arange(n) / SR; s = (np.sin(2 * np.pi * f * t) + .35 * np.sin(4 * np.pi * f * t) + .12 * np.sin(6 * np.pi * f * t)) * np.exp(-t * 7)
    return s * np.minimum(1, t / .003)
step = .25
for a, b, g in [(9.6, 23.3, .11), (30.8, 37.5, .08), (37.6, 42.3, .1)]:
    k = 0; t = a
    while t < b - .05:
        notes = next(n for t0, t1, n in CH if t0 <= t < t1); pat = [0, 2, 1, 3, 2, 4, 1, 3]; m = sorted(notes)[pat[k % 8] % len(notes)] + 12
        place(M, pluck(mtof(m)), t, g * (1 if k % 2 == 0 else .7), pan=-.45 if k % 2 else .45); k += 1; t += step
# Perküsyon
def kick(g=1.0):
    n = int(.35 * SR); t = np.arange(n) / SR; f = 45 + 80 * np.exp(-t * 28); return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9) * g
def hat(): n = int(.05 * SR); return hp(noise(n), 7000) * np.exp(-np.arange(n) / SR * 90) * .4
def boom(g=1.0, L=2.5):
    n = int(L * SR); t = np.arange(n) / SR; f = 32 + 70 * np.exp(-t * 6)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6) + lp(noise(n), 600) * np.exp(-t * 7) * .5
    return np.tanh(s * 1.4) * g
def taiko(g=1.0):
    n = int(.8 * SR); t = np.arange(n) / SR; f = 55 + 40 * np.exp(-t * 20)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 5) + bp(noise(n), 80, 900) * np.exp(-t * 18) * .6) * g
for a, b, g in [(9.6, 16.4, .35), (16.4, 23.3, .3), (30.6, 37.5, .22), (37.6, 42.3, .3)]:
    t = a
    while t < b: place(M, np.stack([kick(g)] * 2, 1), t); t += .5
for a, b, g in [(9.85, 16.3, .05), (19.85, 23.3, .06), (35.85, 37.5, .05)]:
    t = a
    while t < b: place(M, hat(), t, g, pan=.3); t += .5
for t, g in [(23.6, .5), (24.2, .55), (24.7, .6), (25.1, .65), (25.45, .7), (25.75, .75), (26.0, .8)]: place(M, np.stack([taiko(g)] * 2, 1), t)
for t, g in [(0.0, .45), (3.5, 1.0), (9.6, .55), (16.4, .55), (19.6, .45), (23.4, .7), (26.15, 1.0), (30.6, .5), (34.6, .4), (37.6, .75), (42.38, .9)]: place(M, np.stack([boom(g)] * 2, 1), t, .8)
def riser(L, f0=200, f1=6000):
    n = int(L * SR); t = np.arange(n) / SR; x = noise(n); out = np.zeros(n, np.float32); B = 2048
    for i in range(0, n, B):
        fc = f0 * (f1 / f0) ** (i / n); out[i:i + B] = bp(x[i:i + B], fc * .7, min(fc * 1.4, 20000))
    return out * (t / L) ** 2
for t, L, g in [(3.5, 1.4, .5), (9.6, 1.0, .3), (16.4, 1.0, .3), (23.4, 1.2, .35), (37.6, 1.2, .4), (42.38, 1.0, .3)]: place(M, np.stack([riser(L)] * 2, 1), t - L, g)
M = verb(M, .32)

# ---------------- 3) Efektler ----------------
X = np.zeros((N, 2), np.float32)
def sweep_noise(L, f0, f1, q=.5):
    n = int(L * SR); x = noise(n); out = np.zeros(n, np.float32); B = 1024
    for i in range(0, n, B): fc = f0 * (f1 / f0) ** (i / n); out[i:i + B] = bp(x[i:i + B], fc * (1 - q), min(fc * (1 + q), 20000))
    return out
def bubble(f0):
    L = .05 + R.random() * .07; n = int(L * SR); t = np.arange(n) / SR; f = f0 * (1 + 2.2 * t / L)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 40) * np.minimum(1, t / .002)
def blip(f, L=.07, g=1.0): n = int(L * SR); t = np.arange(n) / SR; return np.sin(2 * np.pi * f * t) * np.exp(-t * 45) * np.minimum(1, t / .002) * g
def clink():
    n = int(.25 * SR); t = np.arange(n) / SR; fr = [1300, 2950, 4400, 6100]; s = sum(np.sin(2 * np.pi * f * (1 + .03 * R.standard_normal()) * t) / (i + 1) for i, f in enumerate(fr))
    return s * np.exp(-t * (25 + R.random() * 20)) * .5
# Uzay: alçak uğultu + hızlanan rüzgar/dalış
place(X, np.stack([lp(noise(int(3.6 * SR)), 140) * adsr(int(3.6 * SR), .3, .2) * 2.2] * 2, 1), 0, .5)
place(X, np.stack([sweep_noise(2.1, 250, 4200) * np.linspace(0, 1, int(2.1 * SR)) ** 2] * 2, 1), 1.45, .55)
for t, f in [(.55, 2800), (.85, 3300), (1.25, 2800), (1.6, 3700)]: place(X, blip(f, .06, .12), t, pan=.4)
# Suya giriş: sıçrama + kabarcıklar
n = int(1.2 * SR); place(X, np.stack([sweep_noise(1.2, 5000, 250, .6) * np.exp(-np.arange(n) / SR * 3.5)] * 2, 1), 3.48, .9)
for i in range(90):
    t = 3.5 + R.exponential(.45); place(X, bubble(350 + R.random() * 900), t, .09 * np.exp(-(t - 3.5) * .9), pan=R.uniform(-.7, .7))
# Su altı ambiyansı
amb = lp(np.cumsum(noise(N)) * .02, 320); amb -= lp(amb, 30); amb *= .6 + .4 * np.sin(2 * np.pi * .13 * T)
ambg = np.interp(T, [0, 3.45, 3.6, 9.5, 9.7, 23.3, 23.6, 34.5, 34.7, 45], [0, 0, 1, 1, 0, 0, .8, .8, 0, 0])
X += np.stack([amb * ambg, np.roll(amb, 2400) * ambg], 1) * 1.2
# Projektör tıkı + sonar
place(X, hp(noise(int(.02 * SR)), 1500) * .6, 4.55); place(X, blip(2100, .03, .3), 4.55)
n = int(2.2 * SR); tt = np.arange(n) / SR; place(X, verb(np.sin(2 * np.pi * 1150 * tt) * np.exp(-tt * 3.2) * np.minimum(1, tt / .005) * .2, .6), 5.7)
# Harita: güzergâh blipleri
from math import isfinite
RT = [0, .25, .45, .7, .85, 1.0, 1.1, 1.3, 1.5, 1.6, 1.7, 1.9, 2.1, 2.3, 2.4, 2.55, 2.7, 2.85]
for i, r in enumerate(RT): place(X, blip(1200 * 2 ** (i / 12 * .7), .08, .16), 9.6 + r * 1.25, pan=np.sin(i))
# Kablo kesiti: metalik parıltı + etiket tıkları
n = int(1.8 * SR); tt = np.arange(n) / SR; place(X, sum(np.sin(2 * np.pi * f * tt) for f in [1180, 2610, 3920, 5230]) * np.exp(-tt * 2.6) * .05, 16.45)
for t in [16.65, 17.0, 17.35, 17.7]: place(X, blip(1800, .05, .2), t)
# Fiber: ışık darbeleri "vınlama"
for i in range(22):
    t = 19.7 + i * .17 + R.random() * .05; place(X, np.stack([sweep_noise(.16, 2500, 7000, .3) * np.hanning(int(.16 * SR))] * 2, 1), t, .1, )
# Çapa: zincir tıkırtısı, sürtünme, gerilme, KOPMA
for i in range(60):
    t = 23.5 + R.random() * 3.0; place(X, clink(), t, .22, pan=R.uniform(-.3, .5))
n = int(3.2 * SR); place(X, np.stack([lp(noise(n), 260) * adsr(n, .4, .5) * .9] * 2, 1), 23.4, .6)
n = int(1.0 * SR); tt = np.arange(n) / SR; f = 70 + 110 * tt; cr = bp(np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)) * (1 + .3 * noise(n)), 150, 1400) * tt ** 2
place(X, cr, 25.15, .25)
n = int(.6 * SR); tt = np.arange(n) / SR
snap = hp(noise(n), 2500) * np.exp(-tt * 60) * 1.0 + np.sin(2 * np.pi * np.cumsum(60 + 90 * np.exp(-tt * 30)) / SR) * np.exp(-tt * 8) * .9 + sum(np.sin(2 * np.pi * f * tt) for f in [430, 1210, 2330]) * np.exp(-tt * 10) * .12
place(X, np.stack([snap] * 2, 1), 26.15, .9)
n = int(2.5 * SR); place(X, np.stack([lp(noise(n), 400) * np.exp(-np.arange(n) / SR * 1.2)] * 2, 1), 26.17, .5)
n = int(.5 * SR); tt = np.arange(n) / SR; al = np.sign(np.sin(2 * np.pi * np.cumsum(880 - 440 * tt / .5) / SR)) * np.exp(-tt * 4) * .08
place(X, lp(al, 3500), 26.25); place(X, lp(al, 3500), 26.85, .7)
# Onarım: vinç uğultusu + ROV iticileri
n = int(4.1 * SR); tt = np.arange(n) / SR; winch = lp(np.sign(np.sin(2 * np.pi * 92 * tt)) * (1 + .2 * np.sin(2 * np.pi * 3 * tt)), 420) * adsr(n, .5, .6)
place(X, np.stack([winch] * 2, 1), 30.6, .1); place(X, np.stack([bp(noise(n), 500, 1000) * adsr(n, .6, .6)] * 2, 1), 30.6, .05)
for i in range(25): t = 30.7 + R.random() * 3.6; place(X, bubble(300 + R.random() * 500), t, .06, pan=R.uniform(-.5, .5))
# Yeniden yönlendirme: başarı blipleri
for t, f in [(35.1, 1046.5), (35.35, 1318.5), (35.6, 1568), (35.85, 2093)]: place(X, blip(f, .12, .2), t)
# Final: geri çekilme + logo parıltısı
place(X, np.stack([sweep_noise(1.6, 3500, 200, .5) * np.hanning(int(1.6 * SR))] * 2, 1), 37.5, .5)
n = int(2.6 * SR); tt = np.arange(n) / SR; bell = sum(np.sin(2 * np.pi * f * tt) * np.exp(-tt * (1.2 + i * .6)) / (i + 1) for i, f in enumerate([1318.5, 1975.5, 2637, 3322]))
place(X, verb(bell * .12, .5), 42.38); place(X, blip(1568, .1, .2), 42.95); place(X, blip(2093, .14, .16), 43.05)
X = verb(X, .18)

# ---------------- 4) Miks ----------------
vo = env_fast(V, .05, .35); duck = 1 - .45 * np.clip(vo / (np.max(vo) * .35), 0, 1)
mus = M * duck[:, None] * db(-1.5); sfx = X * (1 - .25 * np.clip(vo / (np.max(vo) * .35), 0, 1))[:, None]
bed = mus + sfx
bed *= db(-25 - lufs(bed))  # yatak, konuşmadan ~9 dB aşağıda
mix = bed + np.stack([V, V], 1) * db(-3)
mix = hp(mix, 28)
fade = np.ones(N); f0, f1 = int(44.35 * SR), N; fade[f0:f1] = np.linspace(1, 0, f1 - f0) ** 2; fade[:int(.02 * SR)] = np.linspace(0, 1, int(.02 * SR))
mix *= fade[:, None]
for _ in range(3): mix *= db(-14 - lufs(mix)); mix = limiter(mix, -2.4)  # AAC aşımı için pay: kodlama sonrası ≈ -2 dBTP
print(f'yatak(müzik+efekt): {lufs(bed):.2f} LUFS | miks: {lufs(mix):.2f} LUFS, tepe {tpeak(mix):.2f} dBTP')
wr(f'{D}/mix.wav', mix); wr(f'{D}/music_stem.wav', mus * .5); wr(f'{D}/sfx_stem.wav', sfx * .5)
