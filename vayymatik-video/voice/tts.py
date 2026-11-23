# Piper (tr_TR-fahrettin-medium, CC0) ile cümle cümle seslendirme üretir.
import json, wave, sys, numpy as np
from piper import PiperVoice, SynthesisConfig
from scipy.signal import resample_poly
D = sys.path[0]
cfg = SynthesisConfig(length_scale=1.0, noise_scale=0.667, noise_w_scale=0.8)
v = PiperVoice.load(f"{D}/models/tr_TR-fahrettin-medium.onnx")
segs = json.load(open(f"{D}/metin.json"))
for s in segs:
    pcm = np.concatenate([np.frombuffer(c.audio_int16_bytes, np.int16) for c in v.synthesize(s["text"], syn_config=cfg)]).astype(np.float32) / 32768
    sr = v.config.sample_rate
    x = resample_poly(pcm, 160, 147 * (sr // 22050)) if sr == 22050 else pcm  # -> 24000? fixed below
    x = resample_poly(pcm, 320, 147)  # 22050 -> 48000
    env = np.abs(x) > 0.01; idx = np.where(env)[0]
    a, b = max(idx[0] - 960, 0), min(idx[-1] + 4800, len(x))  # 20 ms önce, 100 ms sonra
    x = x[a:b]; fade = int(0.04 * 48000); x[-fade:] *= np.linspace(1, 0, fade) ** 2
    s["dur"] = round(len(x) / 48000, 3)
    with wave.open(f"{D}/segs/{s['id']}.wav", "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    print(s["id"], s["dur"], round(s["t"] + s["dur"], 2), "|", "".join(v.phonemize(s["text"])[0])[:90])
json.dump(segs, open(f"{D}/segs.json", "w"), ensure_ascii=False, indent=1)
