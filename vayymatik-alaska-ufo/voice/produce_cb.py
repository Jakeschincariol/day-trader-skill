# Chatterbox ile tam anlatım: net diksiyon ayarları + tiz netleştirme + Whisper doğrulama/kelime zamanları + miks
import json, re, difflib, numpy as np, torch, soundfile as sf, librosa, pyloudnorm as pyln
from scipy.signal import butter, sosfilt, lfilter, resample_poly
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
from transformers import pipeline
torch.set_num_threads(4); SR = 48000; V = 'voice'
P = [("s1", .30, 0, "Amerika'da, gökyüzünde ahtapota benzeyen gizemli bir cisim görüntülendi!", "Amerika'da gökyüzünde ahtapota benzeyen gizemli bir cisim görüntülendi!", .6),
 ("s2", 4.15, .3, "Ve bu görüntüler uzaylı tartışmalarını yeniden başlattı.", None, .5), ("s3", 7.40, .3, "On beş Haziran iki bin yirmi altı.", "15 Haziran 2026.", .45),
 ("s4", 9.85, .3, "Alaska'da bir kadın, gökkuşağını görüntülerken...", "Alaska'da bir kadın gökkuşağını görüntülerken,", .5), ("s4", 0, .25, "gökyüzünde tuhaf bir şey fark etti.", None, .6),
 ("s5", 14.55, .3, "Koyu renkli bir gövde...", "Koyu renkli bir gövde…", .55), ("s6", 0, .45, "Ve aşağıya doğru sarkan, sürekli hareket eden uzun kollar!", None, .65),
 ("s7", 22.65, .3, "Üstelik görüntüler bir Amerikan askeri üssünün yakınında kaydedilmişti.", "Üstelik görüntüler bir Amerikan askerî üssünün yakınında kaydedilmişti.", .5),
 ("s8", 0, .4, "Peki bu gerçekten dünya dışı bir araç mıydı?", None, .6), ("s9", 30.65, .3, "Eski Pentagon ufo araştırmacısı Şon Kırkpatrik...", "Eski Pentagon UFO araştırmacısı Sean Kirkpatrick,", .5),
 ("s9", 0, .2, "çok daha basit bir ihtimalden söz etti.", None, .5), ("s10", 0, .45, "Ahtapot şeklinde bir uçurtma!", None, .7),
 ("s11", 0, .4, "Ancak görüntüler cismin ne olduğunu kesin olarak belirlemeye yetmiyor.", None, .5), ("s12", 0, .4, "Yani uzaylı olduğuna dair hiçbir kanıt yok.", None, .55),
 ("s13", 0, .5, "Peki sen ne düşünüyorsun?", None, .6), ("s14", 0, .4, "Bu şey gerçekten neydi?", None, .65)]
def biq(kind, f0, g, q):
    A, w = 10 ** (g / 40), 2 * np.pi * f0 / SR; c, s = np.cos(w), np.sin(w); al = s / (2 * q)
    if kind == 'peak': b, a = [1 + al * A, -2 * c, 1 - al * A], [1 + al / A, -2 * c, 1 - al / A]
    else: sq = 2 * np.sqrt(A) * al; b = [A * ((A + 1) + (A - 1) * c + sq), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - sq)]; a = [(A + 1) - (A - 1) * c + sq, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - sq]
    return np.array(b) / a[0], np.array(a) / a[0]
F = lambda y, k, f, g, q=.8: lfilter(*biq(k, f, g, q), y)
def enhance(y):  # netlik: çamur kesimi, varlık, tiz uyarıcı (s/ş berraklığı), hava
    y = sosfilt(butter(2, 70, 'high', fs=SR, output='sos'), y); y = F(y, 'peak', 260, -2.5, .9); y = F(y, 'peak', 3600, 2.5, 1.0)
    hf = lambda x: sosfilt(butter(4, [5000, 11500], 'band', fs=SR, output='sos'), x); e0 = np.mean(hf(y) ** 2)
    ex = hf(np.tanh(sosfilt(butter(2, [2400, 5200], 'band', fs=SR, output='sos'), y) * 8)); k = np.sqrt(1.5 * e0 / (np.mean(ex ** 2) + 1e-12))
    return F(y + ex * k, 'high', 7500, 1.5, .7)
def tighten(y, mx=.3):
    iv = librosa.effects.split(y, top_db=40, frame_length=1024, hop_length=256); r = [y[:iv[0][0]]]
    for j, (a, b) in enumerate(iv):
        r.append(y[a:b])
        if j + 1 < len(iv): r.append(y[b:b + min(iv[j + 1][0] - b, int(mx * SR))])
    r.append(y[iv[-1][1]:]); return np.concatenate(r)
norm = lambda s: re.sub(r"[^a-zçğıöşüâî0-9 ]", "", s.replace('I', 'ı').replace('İ', 'i').lower())
# referans: onaylanan örnekten (doğal tını), netleştirilmiş
ref = np.concatenate([np.concatenate([sf.read(f'{V}/cb_sample/p0{k}.wav', dtype='float32')[0], np.zeros(9600, np.float32)]) for k in [0, 1, 3, 4]])
sf.write(f'{V}/ref_voice2.wav', resample_poly(enhance(ref), 1, 2).astype(np.float32), 24000)
m = ChatterboxMultilingualTTS.from_pretrained(device='cpu'); asr = pipeline('automatic-speech-recognition', model='openai/whisper-small', device='cpu')
out = []; import os
for i, (seg, t, gap, say, cap, ex) in enumerate(P):
    best = None; cf = f'{V}/cb_final/p{i:02d}'
    if os.path.exists(cf + '.json'):
        o = json.load(open(cf + '.json')); o['y'] = sf.read(cf + '.wav', dtype='float32')[0]; out.append(o); print(i, seg, 'önbellek', o['sim'], flush=True); continue
    for att in range(5):
        torch.manual_seed(100 + i * 10 + att)
        w = m.generate(say, language_id='tr', audio_prompt_path=f'{V}/ref_voice2.wav', exaggeration=min(ex, .5), cfg_weight=.68, temperature=.5)
        y = librosa.resample(w.squeeze(0).numpy().astype(np.float32), orig_sr=m.sr, target_sr=SR); idx = np.where(np.abs(y) > .01)[0]
        y = tighten(enhance(y[max(idx[0] - 960, 0):min(idx[-1] + 4800, len(y))]), .25)
        r = asr(librosa.resample(y, orig_sr=SR, target_sr=16000), return_timestamps='word', generate_kwargs={'language': 'turkish', 'task': 'transcribe'})
        if r['chunks']:
            a0 = max(0., r['chunks'][0]['timestamp'][0] - .06); a1 = min(len(y) / SR, (r['chunks'][-1]['timestamp'][1] or len(y) / SR) + .2); y = y[int(a0 * SR):int(a1 * SR)].copy()
            for c in r['chunks']: c['timestamp'] = (max(0., c['timestamp'][0] - a0), max(0., (c['timestamp'][1] or a1) - a0))
        f = int(.04 * SR); y[-f:] *= np.linspace(1, 0, f) ** 2
        sim = max(difflib.SequenceMatcher(None, norm(say), norm(r['text'])).ratio(), difflib.SequenceMatcher(None, norm(cap or say), norm(r['text'])).ratio())
        if best is None or sim > best[0]: best = (sim, y, r)
        if sim >= .95: break
    sim, y, r = best
    o = dict(seg=seg, t=t, gap=gap, cap=cap or say, chunks=[(c['timestamp'][0], c['timestamp'][1] or len(y) / SR) for c in r['chunks']], sim=round(sim, 3), tr=r['text'].strip()); json.dump(o, open(cf + '.json', 'w'), ensure_ascii=False); sf.write(cf + '.wav', y, SR); o['y'] = y; out.append(o)
    print(i, seg, f'{len(y) / SR:.2f}s', 'benzerlik', round(sim, 3), '|', r['text'].strip(), flush=True)
# zaman çizelgesi
end = 0; pl = []
for o in out: st = max(o['t'], end + o['gap']) if end else o['t']; pl.append(st); end = st + len(o['y']) / SR
rate = max(1.0, min(1.08, (end - .3) / (48.9 - .3)))
if rate > 1:
    for o in out: o['y'] = librosa.effects.time_stretch(o['y'], rate=rate); o['chunks'] = [(a / rate, b / rate) for a, b in o['chunks']]
    end = 0; pl = []
    for o in out: st = max(o['t'], end + o['gap']) if end else o['t']; pl.append(st); end = st + len(o['y']) / SR
print('hız', round(rate, 3), 'bitiş', round(end, 2), [round(x, 2) for x in pl])
N = int(51 * SR); VO = np.zeros(N, np.float32); segs = {}
for o, st in zip(out, pl):
    i0 = int(st * SR); n = max(0, min(len(o['y']), N - i0)); VO[i0:i0 + n] += o['y'][:n]
    toks = o['cap'].split(); ch = o['chunks']
    if len(ch) == len(toks): tm = [(st + a, st + b) for a, b in ch]
    else:
        a0, a1 = (ch[0][0], ch[-1][1]) if ch else (.02, len(o['y']) / SR - .1); L = [len(x) + 1 for x in toks]; acc = a0; tm = []
        for l in L: s0 = acc; acc += (a1 - a0) * l / sum(L); tm.append((st + s0, st + acc))
    sg = segs.setdefault(o['seg'], {'id': o['seg'], 'words': [], 'cap': ''})
    sg['words'] += [{'w': w, 't0': round(a, 3), 't1': round(b, 3)} for w, (a, b) in zip(toks, tm)]; sg['cap'] = (sg['cap'] + ' ' + o['cap']).strip()
S = list(segs.values())
for s in S: s['t'] = s['words'][0]['t0']; s['dur'] = round(s['words'][-1]['t1'] - s['t'], 3)
json.dump(S, open(f'{V}/segs.json', 'w'), ensure_ascii=False, indent=1)
mt = pyln.Meter(SR); VO *= 10 ** ((-16 - mt.integrated_loudness(VO)) / 20); VO *= min(1, 10 ** (-1.5 / 20) / np.max(np.abs(resample_poly(VO, 4, 1))))
sf.write('audio/voice_track.wav', VO, SR)
bed = (sf.read('audio/music_stem.wav', dtype='float32')[0] + sf.read('audio/sfx_stem.wav', dtype='float32')[0]) * 2; bed = bed[:N]
env = np.convolve(np.convolve(np.abs(VO), np.ones(4800) / 4800, 'same'), np.ones(9600) / 9600, 'same'); bed *= (1 - .55 * np.clip(env / (env.max() * .3), 0, 1))[:, None]
bed *= 10 ** ((-27 - mt.integrated_loudness(bed)) / 20); mix = bed + np.stack([VO, VO], 1) * 10 ** (-3 / 20)
mix *= 10 ** ((-14 - mt.integrated_loudness(mix)) / 20); f = int(.65 * SR); mix[-f:] *= np.linspace(1, 0, f)[:, None]
mix *= min(1, 10 ** (-2.0 / 20) / np.max(np.abs(resample_poly(mix, 4, 1, axis=0)))); sf.write('audio/mix.wav', mix, SR, subtype='PCM_16')
print('miks LUFS', round(mt.integrated_loudness(mix), 2), 'ses LUFS', round(mt.integrated_loudness(VO), 2))
