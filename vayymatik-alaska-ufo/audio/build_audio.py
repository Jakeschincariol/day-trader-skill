# VAYYMATİK0 – ses tasarımı: seslendirme işleme, özgün (sentezlenmiş) müzik, efektler, miks ve mastering.
# Tüm müzik ve efektler bu betikte sıfırdan sentezlenir: telif sorunu yoktur.
import json, sys, os, wave, numpy as np
from scipy.signal import butter, sosfilt, lfilter, resample_poly, fftconvolve
D = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(D)
SR, DUR = 48000, 52.0
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
CH = [(0, 6.0, [38, 50, 53, 57, 58]), (6.0, 13.5, [41, 48, 53, 57, 60]), (13.5, 22.5, [38, 45, 50, 51, 57]), (22.5, 30.5, [43, 50, 55, 58, 62]),
      (30.5, 35.8, [46, 53, 58, 62, 65]), (35.8, 41.6, [48, 55, 60, 64, 67]), (41.6, 47.0, [38, 45, 50, 53, 57]), (47.0, 52.0, [34, 46, 50, 53, 58])]
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
bright = lambda t: np.interp(t, [0, 6, 6.2, 13.4, 13.6, 22.4, 22.6, 30.4, 30.6, 35.7, 35.9, 41.5, 41.7, 51], [1200, 1600, 1800, 2200, 700, 900, 1300, 1500, 1500, 1800, 2200, 2400, 700, 900])
for t0, t1, notes in CH:
    a0, a1 = max(0, t0 - .35), min(DUR, t1 + .9); n = int((a1 - a0) * SR)
    cut = float(bright((t0 + t1) / 2)); e = adsr(n, .55 if t0 else 1.2, 1.1)
    for m in notes: place(M, pad_note(mtof(m), n, cut) * e[:, None], a0, .05)
lvl = np.interp(T, [0, .05, 5.9, 6.1, 13.4, 13.6, 22.4, 22.6, 30.4, 30.6, 41.5, 41.7, 48.3, 51.2, 52], [.9, 1, 1.05, .8, .9, 1.0, 1.05, .9, .95, .85, .95, .9, 1.1, .9, 0])
M *= lvl[:, None]
# Sub bas
sub = np.zeros(N, np.float32)
for t0, t1, notes in CH:
    i0, i1 = int(t0 * SR), int(min(DUR, t1) * SR); f = mtof(min(notes) - 12 if min(notes) > 40 else min(notes)); n = i1 - i0
    sub[i0:i1] += np.tanh(1.5 * np.sin(2 * np.pi * f * np.arange(n) / SR)) * adsr(n, .08, .2) * .5
puls = np.ones(N, np.float32)
for a, b, per in [(0, 6.0, .5), (13.5, 22.5, .75), (22.5, 30.5, .5), (41.6, 48.3, .75)]:
    m = (T >= a) & (T < b); ph = ((T[m] - a) % per) / per; puls[m] = .35 + .65 * np.exp(-ph * 5)
place(M, np.stack([sub * puls, sub * puls], 1), 0, .45)
# Arpej (pluck)
def pluck(f, dur=.45):
    n = int(dur * SR); t = np.arange(n) / SR; s = (np.sin(2 * np.pi * f * t) + .35 * np.sin(4 * np.pi * f * t) + .12 * np.sin(6 * np.pi * f * t)) * np.exp(-t * 7)
    return s * np.minimum(1, t / .003)
step = .25
for a, b, g in [(6.2, 13.4, .08), (22.6, 30.4, .09), (35.9, 41.5, .1)]:
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
for a, b, g in [(0, 5.8, .4), (22.5, 30.3, .3), (35.8, 41.4, .25)]:
    t = a
    while t < b: place(M, np.stack([kick(g)] * 2, 1), t); t += .5
for a, b, g in [(.25, 5.8, .05), (22.75, 30.3, .05)]:
    t = a
    while t < b: place(M, hat(), t, g, pan=.3); t += .5
for t, g in [(19.8, .45), (20.6, .5), (21.3, .55), (21.9, .65)]: place(M, np.stack([taiko(g)] * 2, 1), t)
for t, g in [(0.0, 1.0), (.4, .9), (6.0, .5), (13.5, .7), (22.5, .6), (30.5, .5), (35.85, .7), (41.6, .6), (44.9, .7), (48.4, .9)]: place(M, np.stack([boom(g)] * 2, 1), t, .8)
def riser(L, f0=200, f1=6000):
    n = int(L * SR); t = np.arange(n) / SR; x = noise(n); out = np.zeros(n, np.float32); B = 2048
    for i in range(0, n, B):
        fc = f0 * (f1 / f0) ** (i / n); out[i:i + B] = bp(x[i:i + B], fc * .7, min(fc * 1.4, 20000))
    return out * (t / L) ** 2
for t, L, g in [(6.0, 1.0, .3), (13.5, 1.4, .45), (22.5, 1.0, .3), (35.85, 1.0, .35), (44.9, 1.2, .35), (48.4, 1.0, .3)]: place(M, np.stack([riser(L)] * 2, 1), t - L, g)
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
# 0-6: gerilim: tekinsiz "theremin" tonu + rüzgâr + BU ŞEY NE?! darbesi
n = int(6.2 * SR); tt = np.arange(n) / SR; ther = np.sin(2 * np.pi * np.cumsum(740 + 60 * np.sin(2 * np.pi * 5.5 * tt) + 120 * np.sin(2 * np.pi * .35 * tt)) / SR) * adsr(n, .3, .8) * .05
place(X, verb(ther, .6), 0); place(X, np.stack([windn(n, 200, 1500), windn(n, 220, 1600)], 1) * adsr(n, .05, .6)[:, None], 0, .3)
n = int(1.6 * SR); tt = np.arange(n) / SR; slam = np.sin(2 * np.pi * np.cumsum(40 + 90 * np.exp(-tt * 18)) / SR) * np.exp(-tt * 3) + hp(noise(n), 1500) * np.exp(-tt * 25) * .5
place(X, np.stack([slam, slam], 1), .38, .7)
# 6-13.5: Alaska akşamı: hafif rüzgâr + çisenti
n = int(7.8 * SR); place(X, np.stack([windn(n, 150, 900), windn(n, 160, 950)], 1) * adsr(n, .6, .8)[:, None], 5.9, .25)
place(X, np.stack([hp(noise(n), 3500) * (.6 + .4 * noise(n) ** 2 * 0)] * 2, 1) * adsr(n, 1.0, 1.0)[:, None], 5.9, .025)
# 13.5-22.5 ve 41.6-51: cismin tekinsiz uğultusu (kol dalgalanmasıyla titreşen)
for t0, L, g in [(13.4, 9.3, .16), (41.5, 9.5, .12), (0, 6.0, .08)]:
    n = int(L * SR); tt = np.arange(n) / SR; war = (np.sin(2 * np.pi * 62 * tt) + .4 * np.sin(2 * np.pi * 93.7 * tt)) * (.6 + .4 * np.sin(2 * np.pi * 1.7 * tt)) * adsr(n, .8, 1.0)
    place(X, np.stack([war, war], 1), t0, g); place(X, np.stack([lp(noise(n), 500) * (.5 + .5 * np.sin(2 * np.pi * 1.1 * tt)), lp(noise(n), 520) * (.5 + .5 * np.sin(2 * np.pi * 1.1 * tt + 1))], 1) * adsr(n, .8, 1.0)[:, None], t0, g * .9)
# 22.5-30.5: harita blipleri ve sonar
for t, f in [(22.75, 900), (24.0, 1200), (25.0, 1400), (26.4, 1600)]: place(X, blip(f, .08, .2), t)
n = int(2.2 * SR); tt = np.arange(n) / SR; place(X, verb(np.sin(2 * np.pi * 1050 * tt) * np.exp(-tt * 3.5) * np.minimum(1, tt / .005) * .18, .6), 26.4)
# 30.5-41.6: alıntı kartı vuuşu + uçurtma kumaşı çırpınması
n = int(.7 * SR); place(X, np.stack([sweep_noise(.7, 800, 4000) * np.hanning(n)] * 2, 1), 30.55, .3)
n = int(7.4 * SR); tt = np.arange(n) / SR; flap = bp(noise(n), 300, 2500) * (.4 + .6 * np.abs(np.sin(2 * np.pi * 5.2 * tt + 2 * np.sin(2 * np.pi * .7 * tt)))) * adsr(n, .3, .8)
place(X, np.stack([flap, np.roll(flap, 900)], 1), 34.4, .3)
# 48.4: logo parıltısı
n = int(2.6 * SR); tt = np.arange(n) / SR; bell = sum(np.sin(2 * np.pi * f * tt) * np.exp(-tt * (1.1 + i * .5)) / (i + 1) for i, f in enumerate([880, 1318.5, 1760, 2637]))
place(X, verb(bell * .12, .5), 48.4); place(X, blip(1568, .1, .2), 48.95); place(X, blip(2093, .14, .16), 49.05)
X = verb(X, .15)

# ---------------- 4) Miks ----------------
vo = env_fast(V, .05, .35); duck = 1 - .45 * np.clip(vo / (np.max(vo) * .35), 0, 1)
mus = M * duck[:, None] * db(-1.5); sfx = X * (1 - .25 * np.clip(vo / (np.max(vo) * .35), 0, 1))[:, None]
bed = mus + sfx
bed *= db(-25 - lufs(bed))  # yatak, konuşmadan ~9 dB aşağıda
mix = bed + np.stack([V, V], 1) * db(-3)
mix = hp(mix, 28)
fade = np.ones(N); f0, f1 = int(51.35 * SR), N; fade[f0:f1] = np.linspace(1, 0, f1 - f0) ** 2  # son 0,65 sn yumuşak çıkış; fade[:int(.02 * SR)] = np.linspace(0, 1, int(.02 * SR))
mix *= fade[:, None]
for _ in range(3): mix *= db(-14 - lufs(mix)); mix = limiter(mix, -2.4)  # AAC aşımı için pay: kodlama sonrası ≈ -2 dBTP
print(f'yatak(müzik+efekt): {lufs(bed):.2f} LUFS | miks: {lufs(mix):.2f} LUFS, tepe {tpeak(mix):.2f} dBTP')
wr(f'{D}/mix.wav', mix); wr(f'{D}/music_stem.wav', M * db(-1.5) * .5); wr(f'{D}/sfx_stem.wav', X * .5)  # konuşmaya göre kısma, yeni seste ayrıca yapılır
