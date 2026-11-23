# Parçaları zaman çizelgesine yerleştirir: iç duraklamaları kısaltır, mevcut müzik/efekt yatağıyla miksler (konuşma önde)
import json, sys, numpy as np, soundfile as sf, librosa, pyloudnorm as pyln
from scipy.signal import resample_poly
D = 'voice'; SR = 48000; parts = json.load(open(sys.argv[1])); LEN = float(sys.argv[2]); out = sys.argv[3]; pdir = sys.argv[1].rsplit('/', 1)[0]
def tighten(y, mx=.3):
    iv = librosa.effects.split(y, top_db=38, frame_length=1024, hop_length=256); res = [y[:iv[0][0]]]
    for k, (a, b) in enumerate(iv):
        res.append(y[a:b])
        if k + 1 < len(iv): g = iv[k + 1][0] - b; res.append(y[b:b + min(g, int(mx * SR))])
    res.append(y[iv[-1][1]:]); return np.concatenate(res)
V = np.zeros(int(LEN * SR), np.float32); t_end = 0; times = []
for p in parts:
    y, _ = sf.read(f"{pdir}/{p['file']}", dtype='float32'); y = tighten(y)
    st = max(p['t'] if p['t'] else 0, t_end + (p.get('gap', .3) if t_end else 0)); i = int(st * SR); n = min(len(y), len(V) - i)
    V[i:i + n] += y[:n]; t_end = st + len(y) / SR; times.append((p['seg'], round(st, 2), round(t_end, 2)))
print(times)
meter = pyln.Meter(SR); V *= 10 ** ((-16 - meter.integrated_loudness(V)) / 20)
bed = (sf.read('audio/music_stem.wav', dtype='float32')[0] + sf.read('audio/sfx_stem.wav', dtype='float32')[0]) * 2; bed = bed[:len(V)]
env = np.convolve(np.abs(V), np.ones(4800) / 4800, 'same'); env = np.convolve(env, np.ones(9600) / 9600, 'same'); duck = 1 - .55 * np.clip(env / (env.max() * .3), 0, 1)
bed = bed * duck[:, None]; bed *= 10 ** ((-27 - meter.integrated_loudness(bed)) / 20)
mix = bed + np.stack([V, V], 1) * 10 ** (-3 / 20)
mix *= 10 ** ((-14 - meter.integrated_loudness(mix)) / 20); f = int(.6 * SR); mix[-f:] *= np.linspace(1, 0, f)[:, None]
pk = np.max(np.abs(resample_poly(mix, 4, 1, axis=0))); mix *= min(1, 10 ** (-1.5 / 20) / pk)
sf.write(out + '_miks.wav', mix, SR); sf.write(out + '_ses.wav', V * min(1, 10 ** (-1.5 / 20) / np.max(np.abs(V))), SR)
print('miks LUFS', round(meter.integrated_loudness(mix), 1))
