# Piper (tr_TR-fahrettin-medium, CC0) seslendirme + kelime zamanlaması (sessizlik tespiti + izole kelime süreleri)
import json, re, wave, sys, numpy as np
from piper import PiperVoice, SynthesisConfig
from scipy.signal import resample_poly
D = sys.path[0]; SR = 48000
cfg = SynthesisConfig(length_scale=1.0, noise_scale=0.667, noise_w_scale=0.8)
v = PiperVoice.load(f"{D}/models/tr_TR-fahrettin-medium.onnx")
def synth(text):
    pcm = np.concatenate([np.frombuffer(c.audio_int16_bytes, np.int16) for c in v.synthesize(text, syn_config=cfg)]).astype(np.float32) / 32768
    return resample_poly(pcm, 320, 147)
def trim(x, pre=.02, post=.1):
    idx = np.where(np.abs(x) > .01)[0]; return x[max(idx[0] - int(pre * SR), 0):min(idx[-1] + int(post * SR), len(x))]
def toks(text):  # [(altyazı, söylenen)]
    out = []
    for m in re.finditer(r'\{([^|}]*)\|([^}]*)\}|(\S+)', text): out.append((m.group(1), m.group(2)) if m.group(1) is not None else (m.group(3), m.group(3)))
    return out
wdur = {}
def wlen(w):
    k = re.sub(r"[^\wçğıöşüâÇĞİÖŞÜÂ' ]", '', w).strip()
    if k not in wdur: x = synth(k); idx = np.where(np.abs(x) > .01)[0]; wdur[k] = (idx[-1] - idx[0]) / SR if len(idx) else .1
    return wdur[k]
segs = json.load(open(f"{D}/metin.json"))
for s in segs:
    T = toks(s["text"]); say = ' '.join(b for a, b in T)
    x = trim(synth(say)); fade = int(.04 * SR); x[-fade:] *= np.linspace(1, 0, fade) ** 2
    s["dur"] = round(len(x) / SR, 3)
    with wave.open(f"{D}/segs/{s['id']}.wav", "wb") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    # konuşma adaları (>=90 ms sessizlikle ayrılmış)
    e = np.convolve(np.abs(x), np.ones(480) / 480, 'same') > .012; isl = []; i = 0; n = len(e)
    while i < n:
        if e[i]:
            j = i
            while j < n and (e[j] or (j + 4320 < n and e[j:j + 4320].any())): j += 1
            isl.append((i / SR, j / SR)); i = j
        else: i += 1
    groups = [[]]
    for k, (a, b) in enumerate(T):
        groups[-1].append(k)
        if re.search(r'[,:;]$', b) and k < len(T) - 1: groups.append([])
    if len(isl) != len(groups): isl = [(isl[0][0], isl[-1][1])]; groups = [list(range(len(T)))]
    words = []
    for (a0, a1), g in zip(isl, groups):
        L = [sum(wlen(p) for p in T[k][1].split()) for k in g]; acc = a0
        for k, l in zip(g, L): t0 = acc; acc += (a1 - a0) * l / sum(L); words.append({"w": T[k][0], "t0": round(s["t"] + t0, 3), "t1": round(s["t"] + acc, 3)})
    s["words"] = words; s["cap"] = ' '.join(a for a, b in T)
    print(s["id"], s["dur"], round(s["t"] + s["dur"], 2), len(isl), "ada |", "".join(v.phonemize(say)[0])[:80])
json.dump(segs, open(f"{D}/segs.json", "w"), ensure_ascii=False, indent=1)
