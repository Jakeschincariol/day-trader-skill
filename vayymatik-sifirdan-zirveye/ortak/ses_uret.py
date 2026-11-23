# VAYYMATİK0 seslendirme üretici — Chatterbox Multilingual (MIT) + Whisper doğrulama
# Kullanım: .venv-tts/bin/python ses_uret.py metin.json cikti_klasoru [ref_ses.wav]
# metin.json: [{"seg":"s1","t":0.3,"gap":0.3,"say":"TTS metni","cap":"altyazı metni","ex":0.5}, ...]  (t=0: öncekinin ardından)
import json, re, os, sys, difflib, numpy as np, torch, soundfile as sf, librosa
from scipy.signal import butter, sosfilt, lfilter
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
from transformers import pipeline
torch.set_num_threads(os.cpu_count() or 4); SR = 48000
P = json.load(open(sys.argv[1])); OUT = sys.argv[2]; REF = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ref_ses.wav'); os.makedirs(OUT, exist_ok=True)
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
SAYI = set("bir iki üç dört beş altı yedi sekiz dokuz on yirmi otuz kırk elli altmış yetmiş seksen doksan yüz bin milyon buçuk".split())
norm = lambda s: " ".join(w for w in re.sub(r"[^a-zçğıöşüâî ]", " ", s.replace('I', 'ı').replace('İ', 'i').lower()).split() if w not in SAYI and not re.match(r"^(bin|yüz|milyon|on|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|yirmi|otuz|kırk|elli|altmış|yetmiş|seksen|doksan)\w*$", w))
m = ChatterboxMultilingualTTS.from_pretrained(device='cpu'); asr = pipeline('automatic-speech-recognition', model='openai/whisper-small', device='cpu')
for i, p in enumerate(P):
    cf = f'{OUT}/p{i:02d}'
    if os.path.exists(cf + '.json'): print(i, 'önbellek'); continue
    say, cap = p['say'], p.get('cap') or p['say']; best = None
    for att in range(3):
        torch.manual_seed(100 + i * 10 + att)
        w = m.generate(say, language_id='tr', audio_prompt_path=p.get('ref', REF), exaggeration=min(p.get('ex', .5), .5), cfg_weight=.68, temperature=.5)
        y = librosa.resample(w.squeeze(0).numpy().astype(np.float32), orig_sr=m.sr, target_sr=SR); idx = np.where(np.abs(y) > .01)[0]
        y = tighten(enhance(y[max(idx[0] - 960, 0):min(idx[-1] + 4800, len(y))]), .25)
        r = asr(librosa.resample(y, orig_sr=SR, target_sr=16000), return_timestamps='word', generate_kwargs={'language': 'turkish', 'task': 'transcribe'})
        if r['chunks']:
            a0 = max(0., r['chunks'][0]['timestamp'][0] - .06); a1 = min(len(y) / SR, (r['chunks'][-1]['timestamp'][1] or len(y) / SR) + .2); y = y[int(a0 * SR):int(a1 * SR)].copy()
            for c in r['chunks']: c['timestamp'] = (max(0., c['timestamp'][0] - a0), max(0., (c['timestamp'][1] or a1) - a0))
        f = int(.04 * SR); y[-f:] *= np.linspace(1, 0, f) ** 2; f = int(.012 * SR); y[:f] *= np.linspace(0, 1, f)
        sim = max(difflib.SequenceMatcher(None, norm(say), norm(r['text'])).ratio(), difflib.SequenceMatcher(None, norm(cap), norm(r['text'])).ratio())
        if best is None or sim > best[0]: best = (sim, y, r)
        if sim >= .92: break
    sim, y, r = best; sf.write(cf + '.wav', y, SR)
    json.dump(dict(seg=p['seg'], t=p.get('t', 0), gap=p.get('gap', .3), cap=cap, chunks=[(c['timestamp'][0], c['timestamp'][1] or len(y) / SR) for c in r['chunks']], sim=round(sim, 3), tr=r['text'].strip()), open(cf + '.json', 'w'), ensure_ascii=False)
    print(i, p['seg'], f'{len(y) / SR:.2f}s', 'benzerlik', round(sim, 3), '|', r['text'].strip(), flush=True)
