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
CH = [(0, 5.2, [48, 55, 60, 63, 67]), (5.2, 9.4, [44, 51, 56, 60, 63]), (9.4, 12.4, [41, 48, 53, 56, 60]), (12.4, 16.3, [39, 46, 51, 55, 58]),
      (16.3, 20.4, [46, 53, 58, 62, 65]), (20.4, 24.9, [36, 48, 55, 60, 63]), (24.9, 29.4, [43, 50, 55, 59, 62]), (29.4, 33.3, [44, 51, 56, 60, 63]),
      (33.3, 37.2, [46, 53, 58, 62, 65]), (37.2, 41.0, [39, 51, 55, 58, 63]), (41.0, 45.0, [48, 55, 60, 64, 67])]
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
bright = lambda t: np.interp(t, [0, 5.1, 5.3, 9.3, 9.5, 16.2, 16.4, 20.3, 20.5, 29.3, 29.5, 37.1, 37.3, 45], [2200, 2600, 1800, 2000, 900, 1300, 1600, 1800, 1200, 1700, 1400, 1700, 2000, 2800])
for t0, t1, notes in CH:
    a0, a1 = max(0, t0 - .35), min(DUR, t1 + .9); n = int((a1 - a0) * SR)
    cut = float(bright((t0 + t1) / 2)); e = adsr(n, .55 if t0 else 1.2, 1.1)
    for m in notes: place(M, pad_note(mtof(m), n, cut) * e[:, None], a0, .05)
lvl = np.interp(T, [0, .05, 5.0, 9.3, 9.45, 16.3, 20.3, 20.5, 29.3, 29.5, 37.1, 39.8, 44.3, 45], [.9, 1.0, 1.0, .9, .6, .85, .9, 1.05, 1.05, .8, .85, 1.15, 1.0, 0])
M *= lvl[:, None]
# Sub bas
sub = np.zeros(N, np.float32)
for t0, t1, notes in CH:
    i0, i1 = int(t0 * SR), int(min(DUR, t1) * SR); f = mtof(min(notes) - 12 if min(notes) > 40 else min(notes)); n = i1 - i0
    sub[i0:i1] += np.tanh(1.5 * np.sin(2 * np.pi * f * np.arange(n) / SR)) * adsr(n, .08, .2) * .5
puls = np.ones(N, np.float32)
for a, b, per in [(0, 5.2, .5), (9.4, 16.3, .75), (16.3, 20.4, .5), (20.4, 29.4, .6), (29.4, 37.2, .6), (37.2, 42.0, .5)]:
    m = (T >= a) & (T < b); ph = ((T[m] - a) % per) / per; puls[m] = .35 + .65 * np.exp(-ph * 5)
place(M, np.stack([sub * puls, sub * puls], 1), 0, .45)
# Arpej (pluck)
def pluck(f, dur=.45):
    n = int(dur * SR); t = np.arange(n) / SR; s = (np.sin(2 * np.pi * f * t) + .35 * np.sin(4 * np.pi * f * t) + .12 * np.sin(6 * np.pi * f * t)) * np.exp(-t * 7)
    return s * np.minimum(1, t / .003)
step = .25
for a, b, g in [(5.2, 9.3, .1), (12.4, 20.3, .09), (29.6, 37.0, .08), (37.3, 41.5, .1)]:
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
for a, b, g in [(0, 5.0, .4), (16.3, 20.3, .25), (20.4, 29.3, .35), (37.2, 41.5, .3)]:
    t = a
    while t < b: place(M, np.stack([kick(g)] * 2, 1), t); t += .5
for a, b, g in [(.25, 5.0, .05), (5.45, 9.3, .04), (20.65, 29.3, .05)]:
    t = a
    while t < b: place(M, hat(), t, g, pan=.3); t += .5
for t, g in [(24.9, .45), (25.5, .5), (26.1, .55), (26.65, .6), (27.0, .7)]: place(M, np.stack([taiko(g)] * 2, 1), t)
for t, g in [(0.0, .9), (.35, 1.0), (5.2, .45), (9.4, .8), (16.3, .45), (20.4, .6), (27.2, .6), (29.4, .55), (37.2, .6), (39.8, .9)]: place(M, np.stack([boom(g)] * 2, 1), t, .8)
def riser(L, f0=200, f1=6000):
    n = int(L * SR); t = np.arange(n) / SR; x = noise(n); out = np.zeros(n, np.float32); B = 2048
    for i in range(0, n, B):
        fc = f0 * (f1 / f0) ** (i / n); out[i:i + B] = bp(x[i:i + B], fc * .7, min(fc * 1.4, 20000))
    return out * (t / L) ** 2
for t, L, g in [(5.2, 1.0, .3), (9.4, 1.4, .45), (20.4, 1.0, .3), (29.4, 1.0, .3), (37.2, 1.2, .35), (39.8, 1.0, .3)]: place(M, np.stack([riser(L)] * 2, 1), t - L, g)
M = verb(M, .32)

# ---------------- 3) Efektler ----------------
X = np.zeros((N, 2), np.float32)
def sweep_noise(L, f0, f1, q=.5):
    n = int(L * SR); x = noise(n); out = np.zeros(n, np.float32); B = 1024
    for i in range(0, n, B): fc = f0 * (f1 / f0) ** (i / n); out[i:i + B] = bp(x[i:i + B], fc * (1 - q), min(fc * (1 + q), 20000))
    return out
def blip(f, L=.07, g=1.0): n = int(L * SR); t = np.arange(n) / SR; return np.sin(2 * np.pi * f * t) * np.exp(-t * 45) * np.minimum(1, t / .002) * g
def clink():
    n = int(.25 * SR); t = np.arange(n) / SR; s_ = sum(np.sin(2 * np.pi * f * (1 + .03 * R.standard_normal()) * t) / (i + 1) for i, f in enumerate([1300, 2950, 4400, 6100])); return s_ * np.exp(-t * 35) * .5
def windn(n, f0, f1):
    t = np.arange(n) / SR; return bp(noise(n), f0, f1) * (.55 + .45 * np.sin(2 * np.pi * (.3 + .2 * R.random()) * t + R.random() * 6))
WT = {w['w'].strip(',.!?:'): w['t0'] for g in segs for w in g['words']}
# 0-5.2: şehir uğultusu, yükselen kamera rüzgârı, "660 TON!" darbesi
n = int(5.4 * SR); place(X, np.stack([lp(noise(n), 300) * adsr(n, .02, .4)] * 2, 1), 0, .5)
n = int(4.6 * SR); place(X, np.stack([sweep_noise(4.6, 300, 5000) * np.linspace(.4, 1, n) * np.hanning(n) ** .3] * 2, 1), 0, .4)
n = int(1.6 * SR); tt = np.arange(n) / SR; slam = np.sin(2 * np.pi * np.cumsum(40 + 90 * np.exp(-tt * 18)) / SR) * np.exp(-tt * 3) + hp(noise(n), 1500) * np.exp(-tt * 25) * .5
place(X, np.stack([slam, slam], 1), .32, .7)
# 5.2-9.4: yüksek irtifa rüzgârı; 9.4: cama dalış
n = int(4.4 * SR); place(X, np.stack([windn(n, 300, 1800), windn(n, 280, 1700)], 1) * adsr(n, .4, .6)[:, None], 5.1, .35)
n = int(1.4 * SR); tt = np.arange(n) / SR; gl = sum(np.sin(2 * np.pi * f * tt) * np.exp(-tt * (3 + i)) for i, f in enumerate([2350, 3170, 4420, 5870, 7300])) * .05
place(X, verb(gl, .5), 9.38); n = int(.9 * SR); place(X, np.stack([sweep_noise(.9, 6000, 600, .6) * np.hanning(n)] * 2, 1), 9.0, .5)
# 9.4-16.3: iç mekân metalik uğultu + halat tıkırtıları
n = int(7.2 * SR); tt = np.arange(n) / SR; hum = (np.sin(2 * np.pi * 55 * tt) + .5 * np.sin(2 * np.pi * 110.6 * tt) + .25 * np.sin(2 * np.pi * 165.3 * tt)) * (.8 + .2 * np.sin(2 * np.pi * .3 * tt)) * adsr(n, .6, .8)
place(X, np.stack([hum, hum], 1), 9.3, .12)
for t in [10.6, 12.1, 13.8, 15.2]: place(X, lp(clink(), 2500), t, .12, pan=R.uniform(-.4, .4))
# 16.3-20.4: kat etiketleri
for i in range(6): place(X, blip(900 + i * 120, .05, .12), 16.55 + i * .07)
for w, f in [("87'nci", 1400), ("92'nci", 1800)]:
    if w in WT: place(X, blip(f, .12, .25), WT[w])
# 20.4-29.4: güçlü rüzgâr, bina gıcırtısı, hidrolik tıslama, kürenin ağır salınımı
n = int(9.2 * SR); tt = np.arange(n) / SR; gust = np.clip(tt / 1.8, 0, 1) * adsr(n, .1, .8)
wl = windn(n, 180, 2400) + .5 * bp(noise(n), 900, 1300) * (.5 + .5 * np.sin(2 * np.pi * .4 * tt)); wr_ = windn(n, 160, 2200) + .5 * bp(noise(n), 950, 1350) * (.5 + .5 * np.sin(2 * np.pi * .37 * tt + 1))
place(X, np.stack([wl * gust, wr_ * gust], 1), 20.3, .55)
for k in range(1, 8):
    t = 20.4 + k * 1.2; n = int(.6 * SR); tt = np.arange(n) / SR
    place(X, hp(noise(n), 2500) * np.minimum(1, tt / .12) * np.exp(-tt * 6), t - .05, .06, pan=.2)
    n = int(1.1 * SR); tt = np.arange(n) / SR; place(X, np.stack([lp(noise(n), 260) * np.hanning(n)] * 2, 1), t - .55, .28)
    n = int(.9 * SR); tt = np.arange(n) / SR; cr = bp(np.sign(np.sin(2 * np.pi * np.cumsum(58 + 18 * tt) / SR)) * (1 + .3 * noise(n)), 90, 700) * np.hanning(n); place(X, cr, t + .25, .05)
# 29.4-37.2: rüzgâr darbesi + grafik blipleri
n = int(1.0 * SR); place(X, np.stack([sweep_noise(1.0, 400, 2500) * np.hanning(n)] * 2, 1), 29.55, .35)
for k in range(11): place(X, blip(1500, .04, .06), 29.9 + k * .6, pan=-.5); place(X, blip(1700, .04, .06), 30.2 + k * .6, pan=.5)
# 37.2-45: geri çekilme + logo parıltısı
n = int(2.0 * SR); place(X, np.stack([sweep_noise(2.0, 3500, 250, .5) * np.hanning(n)] * 2, 1), 37.1, .45)
n = int(2.8 * SR); tt = np.arange(n) / SR; bell = sum(np.sin(2 * np.pi * f * tt) * np.exp(-tt * (1.1 + i * .5)) / (i + 1) for i, f in enumerate([1046.5, 1568, 2093, 2637]))
place(X, verb(bell * .12, .5), 39.8); place(X, blip(1568, .1, .2), 40.4); place(X, blip(2093, .14, .16), 40.5)
X = verb(X, .15)

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
