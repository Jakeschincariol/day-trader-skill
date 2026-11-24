# VAYYMATİK0 ses miksi — parçaları DOĞAL HIZDA yerleştirir (hızlandırma YOK), kelime zamanları + miks
# Kullanım: .venv-tts/bin/python ses_miks.py parca_klasoru SURE_sn muzik.wav efekt.wav cikti_klasoru
import json, sys, glob, numpy as np, soundfile as sf, pyloudnorm as pyln
from scipy.signal import resample_poly
from scipy.ndimage import minimum_filter1d
D, LEN, MUS, SFX, OUT = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]; SR = 48000; N = int(LEN * SR)
out = []
for f in sorted(glob.glob(f'{D}/p*.json')): o = json.load(open(f)); o['y'] = sf.read(f[:-5] + '.wav', dtype='float32')[0]; out.append(o)
end = 0; pl = []
for o in out: st = max(o['t'], end + o['gap']) if end else o['t']; pl.append(st); end = st + len(o['y']) / SR
print('konuşma bitişi', round(end, 2), 'sn' + ('  UYARI: video sonuna 1,5 sn kalmalı; araları kısalt veya final sahnesini uzat (HIZLANDIRMA YAPMA)' if end > LEN - 1.5 else ''))
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
json.dump(S, open(f'{OUT}/segs.json', 'w'), ensure_ascii=False, indent=1)
def limiter(x, ceil_db, look=.005, rel=.08):
    x2 = x if x.ndim > 1 else x[:, None]; c = 10 ** (ceil_db / 20)
    pk = np.max(np.abs(resample_poly(x2, 4, 1, axis=0)), 1).reshape(-1, 4).max(1)[:len(x2)]; need = np.minimum(1, c / np.maximum(pk, 1e-9)); L = int(look * SR)
    g = minimum_filter1d(np.concatenate([need[L:], np.ones(L)]), 2 * L + 1); a = np.exp(-1 / (rel * SR)); y = np.empty_like(g); v = 1.0
    for i, s in enumerate(g): v = s if s < v else a * v + (1 - a) * s; y[i] = v
    r = x2 * y[:, None]; return r if x.ndim > 1 else r[:, 0]
mt = pyln.Meter(SR)
for _ in range(2): VO *= 10 ** ((-16 - mt.integrated_loudness(VO)) / 20); VO = limiter(VO, -1.6)
sf.write(f'{OUT}/voice_track.wav', VO, SR)
bed = sf.read(MUS, dtype='float32')[0] * 2 + sf.read(SFX, dtype='float32')[0] * 2; bed = bed[:N]
env = np.convolve(np.convolve(np.abs(VO), np.ones(4800) / 4800, 'same'), np.ones(9600) / 9600, 'same'); bed *= (1 - .55 * np.clip(env / (env.max() * .3), 0, 1))[:, None]
bed *= 10 ** ((-27 - mt.integrated_loudness(bed)) / 20); mix = bed + np.stack([VO, VO], 1) * 10 ** (-3 / 20)
f0 = int((LEN - .7) * SR); mix[f0:] *= (np.linspace(1, 0, N - f0) ** 2)[:, None]
for _ in range(3): mix *= 10 ** ((-14 - mt.integrated_loudness(mix)) / 20); mix = limiter(mix, -3.2)
sf.write(f'{OUT}/mix.wav', mix, SR, subtype='PCM_16'); print('miks', round(mt.integrated_loudness(mix), 2), 'LUFS | ses', round(mt.integrated_loudness(VO), 2), 'LUFS')
