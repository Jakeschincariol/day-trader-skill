# Chatterbox Multilingual (Resemble AI, MIT) ile doğal Türkçe anlatım. Ses kimliği: Piper fahrettin (CC0) referansı.
import json, sys, os, numpy as np, torch, soundfile as sf, librosa
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
D = os.path.dirname(os.path.abspath(__file__)); torch.set_num_threads(4); torch.manual_seed(7)
parts = json.load(open(sys.argv[1])); out = sys.argv[2]; SR = 48000
ref = f'{D}/ref_voice.wav'
if not os.path.exists(ref):  # fahrettin sesinden ~10 sn referans
    x = np.concatenate([librosa.load(f'{D}/segs/{k}.wav', sr=24000)[0] for k in ['s4', 's9', 's11']]); sf.write(ref, x[:24000 * 12], 24000)
m = ChatterboxMultilingualTTS.from_pretrained(device='cpu')
os.makedirs(out, exist_ok=True); res = []
for i, p in enumerate(parts):
    w = m.generate(p['text'], language_id='tr', audio_prompt_path=ref, exaggeration=p['ex'], cfg_weight=p['cfg'], temperature=.75)
    y = librosa.resample(w.squeeze(0).numpy().astype(np.float32), orig_sr=m.sr, target_sr=SR)
    idx = np.where(np.abs(y) > .01)[0]; y = y[max(idx[0] - 960, 0):min(idx[-1] + 4800, len(y))]; f = int(.03 * SR); y[-f:] *= np.linspace(1, 0, f)
    sf.write(f'{out}/p{i:02d}.wav', y, SR); res.append({**p, 'dur': round(len(y) / SR, 3), 'file': f'p{i:02d}.wav'}); print(i, p['seg'], res[-1]['dur'], flush=True)
json.dump(res, open(f'{out}/parts.json', 'w'), ensure_ascii=False, indent=1)
