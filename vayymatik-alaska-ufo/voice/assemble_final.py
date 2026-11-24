# Önbellekteki Chatterbox parçalarını zaman çizelgesine yerleştirir, kelime zamanlarını yazar, sınırlayıcılı miks yapar
import json, numpy as np, soundfile as sf, librosa, pyloudnorm as pyln
from scipy.signal import resample_poly
from scipy.ndimage import minimum_filter1d
SR, N = 48000, 52 * 48000; TGT = {'s7': 0, 's9': 0}
out = []
for i in range(16):
    o = json.load(open(f'voice/cb_final/p{i:02d}.json')); o['y'] = sf.read(f'voice/cb_final/p{i:02d}.wav', dtype='float32')[0]
    if o['t']: o['t'] = TGT.get(o['seg'], o['t'])
    f = int(.012 * SR); o['y'][:f] *= np.linspace(0, 1, f); o['gap'] = min(o['gap'], .32); out.append(o)
def place(stretch):
    end = 0; pl = []
    for o in out: L = len(o['y']) / SR / stretch; st = max(o['t'], end + o['gap']) if end else o['t']; pl.append(st); end = st + L
    return pl, end
pl, end = place(1.0); sp = sum(len(o['y']) for o in out) / SR; rate = 1.0
while False: rate = min(1.08, rate * (1 + (end - 49.5) / sp)); pl, end = place(rate)
if rate > 1:
    for o in out: o['y'] = librosa.effects.time_stretch(o['y'], rate=rate); o['chunks'] = [(a / rate, b / rate) for a, b in o['chunks']]
    pl, end = place(1.0)
print('hız', round(rate, 3), 'bitiş', round(end, 2))
VO = np.zeros(N, np.float32); segs = {}
for o, st in zip(out, pl):
    i0 = int(st * SR); n = max(0, min(len(o['y']), N - i0)); VO[i0:i0 + n] += o['y'][:n]
    toks, ch = o['cap'].split(), o['chunks']
    if len(ch) == len(toks): tm = [(st + a, st + b) for a, b in ch]
    else:
        a0, a1 = (ch[0][0], ch[-1][1]) if ch else (.02, len(o['y']) / SR - .1); L = [len(x) + 1 for x in toks]; acc = a0; tm = []
        for l in L: s0 = acc; acc += (a1 - a0) * l / sum(L); tm.append((st + s0, st + acc))
    g = segs.setdefault(o['seg'], {'id': o['seg'], 'words': [], 'cap': ''}); g['words'] += [{'w': w, 't0': round(a, 3), 't1': round(b, 3)} for w, (a, b) in zip(toks, tm)]; g['cap'] = (g['cap'] + ' ' + o['cap']).strip()
S = list(segs.values())
for g in S: g['t'] = g['words'][0]['t0']; g['dur'] = round(g['words'][-1]['t1'] - g['t'], 3)
json.dump(S, open('voice/segs.json', 'w'), ensure_ascii=False, indent=1)
def limiter(x, ceil_db, look=.005, rel=.08):
    x2 = x if x.ndim > 1 else x[:, None]; c = 10 ** (ceil_db / 20)
    pk = np.max(np.abs(resample_poly(x2, 4, 1, axis=0)), 1).reshape(-1, 4).max(1)[:len(x2)]; need = np.minimum(1, c / np.maximum(pk, 1e-9)); L = int(look * SR)
    g = minimum_filter1d(np.concatenate([need[L:], np.ones(L)]), 2 * L + 1); a = np.exp(-1 / (rel * SR)); y = np.empty_like(g); v = 1.0
    for i, s in enumerate(g): v = s if s < v else a * v + (1 - a) * s; y[i] = v
    r = x2 * y[:, None]; return r if x.ndim > 1 else r[:, 0]
mt = pyln.Meter(SR)
for _ in range(2): VO *= 10 ** ((-16 - mt.integrated_loudness(VO)) / 20); VO = limiter(VO, -1.6)
sf.write('audio/voice_track.wav', VO, SR)
bed = (sf.read('audio/music_stem.wav', dtype='float32')[0] + sf.read('audio/sfx_stem.wav', dtype='float32')[0]) * 2; bed = bed[:N]
env = np.convolve(np.convolve(np.abs(VO), np.ones(4800) / 4800, 'same'), np.ones(9600) / 9600, 'same'); bed *= (1 - .55 * np.clip(env / (env.max() * .3), 0, 1))[:, None]
bed *= 10 ** ((-27 - mt.integrated_loudness(bed)) / 20); mix = bed + np.stack([VO, VO], 1) * 10 ** (-3 / 20)
f0 = int(51.3 * SR); mix[f0:] *= (np.linspace(1, 0, N - f0) ** 2)[:, None]
for _ in range(3): mix *= 10 ** ((-14 - mt.integrated_loudness(mix)) / 20); mix = limiter(mix, -3.2)
sf.write('audio/mix.wav', mix, SR, subtype='PCM_16'); print('miks LUFS', round(mt.integrated_loudness(mix), 2), '| ses LUFS', round(mt.integrated_loudness(VO), 2))
print([(g['id'], g['t'], round(g['t'] + g['dur'], 2)) for g in S][-4:])
