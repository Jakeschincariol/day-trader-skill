# Shorts senaryoları (kisa/kisaN.txt) -> kisa/kisaN_beats.json. Ana bölümdeki aynı (konuşan, metin) satırı varsa o ses parçası
# yeniden kullanılır; yeni satırlar ses/kisa_parcalar.json'a yazılır (ortak/ses_uret.py ile ses/kisa_parca/ içine üretilir).
import json, re, os, glob
D = os.path.dirname(os.path.abspath(__file__)); O = os.path.join(D, '..', 'ortak')
EX = {'N': .45, 'E': .5, 'K': .4, 'H': .45, 'B': .5, 'R': .5, 'Y': .4, 'M': .4, 'C': .4}
ana = {(b['kon'], b['say']): b['parca'] for b in json.load(open(f'{D}/beats.json')) if b['kon'] != '-'}
yeni, yeni_idx = [], {}
for f in sorted(glob.glob(f'{D}/kisa/kisa[0-9].txt')):
    n = int(re.search(r'(\d)\.txt$', f).group(1)); meta, beats = {}, []
    for ln in open(f, encoding='utf-8'):
        if not ln.strip() or ln.startswith('#'): continue
        if ln.startswith('@'): k, *v = ln[1:].rstrip('\n').split('|'); meta[k] = v; continue
        sah, kon, met, cek, pan, ara = re.split(r'\|(?![^{]*\})', ln.rstrip('\n'))
        cap = re.sub(r'\{([^|}]*)\|([^}]*)\}', r'\1', met); say = re.sub(r'\{([^|}]*)\|([^}]*)\}', r'\2', met)
        b = dict(i=len(beats), sahne=int(sah), kon=kon, cek=cek, panel=pan, ara=float(ara), cap=cap, say=say)
        if (kon, say) in ana: b['wav'] = f"ses/parca/p{ana[(kon, say)]:02d}"
        else:
            if (kon, say) not in yeni_idx: yeni_idx[(kon, say)] = len(yeni); yeni.append(dict(seg=f'k{n}_{len(beats):02d}', t=0, gap=0, say=say, cap=cap, ex=EX[kon], ref=f'{O}/sesler/{kon}.wav'))
            b['wav'] = f"ses/kisa_parca/p{yeni_idx[(kon, say)]:02d}"
        beats.append(b)
    json.dump(dict(baslik=meta['baslik'][0], kanca=meta['kanca'], son=meta['son'], beats=beats), open(f'{D}/kisa/kisa{n}_beats.json', 'w'), ensure_ascii=False, indent=1)
    print(f'kısa {n}: {len(beats)} satır, yeniden kullanılan {sum(b["wav"].startswith("ses/parca/") for b in beats)}, yeni {sum(b["wav"].startswith("ses/kisa") for b in beats)}')
json.dump(yeni, open(f'{D}/ses/kisa_parcalar.json', 'w'), ensure_ascii=False, indent=1); print('yeni TTS parçası:', len(yeni), '|', sum(len(p['say'].split()) for p in yeni), 'kelime')
