# senaryo.txt -> beats.json + TTS parça listesi; konuşmacı başına referans ses (anlatıcı sesinden formant kaydırma, gerçek kişi klonlanmaz)
import json, re, os, numpy as np, soundfile as sf
from scipy.signal import resample_poly
D = os.path.dirname(os.path.abspath(__file__)); O = os.path.join(D, '..', 'ortak')
KAT = {'N': 1.0, 'E': 1.07, 'K': .84, 'H': .95, 'B': .9, 'R': 1.13, 'Y': .88, 'M': 1.04, 'C': 1.0}
EX = {'N': .45, 'E': .5, 'K': .4, 'H': .45, 'B': .5, 'R': .5, 'Y': .4, 'M': .4, 'C': .4}
os.makedirs(f'{O}/sesler', exist_ok=True); y, sr = sf.read(f'{O}/ref_ses.wav', dtype='float32')
for k, f in KAT.items():
    p = f'{O}/sesler/{k}.wav'
    if not os.path.exists(p): sf.write(p, (y if f == 1 else resample_poly(y, 1000, int(1000 * f))).astype(np.float32), sr)
beats = []; PJ = f'{D}/ses/parcalar.json'; parts = json.load(open(PJ)) if os.path.exists(PJ) else []  # mevcut parça sırası korunur (ses önbelleği indeksle eşleşir)
idx = {(os.path.basename(p['ref'])[0], p['say']): i for i, p in enumerate(parts)}
for ln in open(f'{D}/senaryo.txt', encoding='utf-8'):
    if not ln.strip() or ln.startswith('#'): continue
    sah, kon, met, cek, pan, ara = re.split(r'\|(?![^{]*\})', ln.rstrip('\n'))
    b = dict(i=len(beats), sahne=int(sah), kon=kon, cek=cek, panel=pan, ara=float(ara))
    if kon != '-':
        cap = re.sub(r'\{([^|}]*)\|([^}]*)\}', r'\1', met); say = re.sub(r'\{([^|}]*)\|([^}]*)\}', r'\2', met)
        if (kon, say) not in idx: idx[(kon, say)] = len(parts); parts.append(dict(seg=f'b{b["i"]:03d}', t=0, gap=0, say=say, cap=cap, ex=EX[kon], ref=f'{O}/sesler/{kon}.wav'))
        b.update(cap=cap, say=say, parca=idx[(kon, say)])
    else: b['sure'] = float(ara); b['etiket'] = met
    beats.append(b)
json.dump(beats, open(f'{D}/beats.json', 'w'), ensure_ascii=False, indent=1); json.dump(parts, open(f'{D}/ses/parcalar.json', 'w'), ensure_ascii=False, indent=1)
kul = {b['parca'] for b in beats if 'parca' in b}; print(len(beats), 'vuruş,', len(kul), 'kullanılan parça (listede', len(parts), '),', sum(len(parts[i]['say'].split()) for i in kul), 'kelime')
