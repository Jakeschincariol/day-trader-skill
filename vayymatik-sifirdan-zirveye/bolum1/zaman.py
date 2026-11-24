# Zaman çizelgesi: vuruşlar + konuşma parçaları -> timeline.json (render), altyazi.json, ses yerleşimi.
# python zaman.py            ana bölüm      | python zaman.py --kisa   6 Shorts (kisa/kisaN_beats.json -> kisaN.json)
# --tahmin: ses yokken kelime sayısından süre (henüz üretilmemiş parçalar da tahminle doldurulur)
import json, os, sys, glob, numpy as np, soundfile as sf
D = os.path.dirname(os.path.abspath(__file__)); TAH = '--tahmin' in sys.argv; SR = 48000; ENV = 24
def zaman(B, wav, bas, sahne_ara, ek=0.):  # ek: her konuşmadan sonra ek nefes payı (sn)
    out, alt, ses, cur = [], [], [], bas
    for b in B:
        if out and b['sahne'] != out[-1]['sahne']: cur += sahne_ara
        e = dict(i=b['i'], sahne=b['sahne'], kon=b['kon'], cek=b['cek'], panel=b['panel'], t0=round(cur, 3))
        if b['kon'] == '-': cur += b['sure']; e['t1'] = round(cur, 3); out.append(e); continue
        w = f"{D}/{wav(b)}"
        if TAH or not os.path.exists(w + '.json'): dur = len(b['say'].split()) / 2.6; env = [round(abs(np.sin(i * .9)) * .7, 2) for i in range(int(dur * ENV))]; ch = []; e['tahmin'] = 1
        else:
            y, _ = sf.read(w + '.wav', dtype='float32'); dur = len(y) / SR; ch = json.load(open(w + '.json'))['chunks']
            n = SR // ENV; r = np.sqrt(np.mean(y[:len(y) // n * n].reshape(-1, n) ** 2, 1)); r = r / (np.percentile(r, 95) + 1e-6); env = [round(float(min(1, v * .9)), 2) for v in np.convolve(r, [.25, .5, .25], 'same')]
            ses.append(dict(t=round(cur + .05, 3), wav=w + '.wav', kon=b['kon'], cek=b['cek']))
        ks = cur + .05; e.update(ks=round(ks, 3), agiz=env); cur = ks + dur + b['ara'] + ek; e['t1'] = round(cur, 3); out.append(e)
        toks = b['cap'].split(); a0, a1 = (ch[0][0], ch[-1][1]) if len(ch) else (.02, dur - .1)
        tm = [(ks + x, ks + y) for x, y in ch] if len(ch) == len(toks) else None
        if tm is None:
            L = [len(x) + 1 for x in toks]; acc = a0; tm = []
            for l in L: s0 = acc; acc += (a1 - a0) * l / sum(L); tm.append((ks + s0, ks + acc))
        alt.append(dict(kon=b['kon'], cek=b['cek'], cap=b['cap'], words=[dict(w=w_, t0=round(x, 3), t1=round(y, 3)) for w_, (x, y) in zip(toks, tm)]))
    return out, alt, ses, cur
fmt = lambda s: f'{int(s // 60)}:{int(s % 60):02d}'
if '--kisa' not in sys.argv:
    B = json.load(open(f'{D}/beats.json')); out, alt, ses, cur = zaman(B, lambda b: f"ses/parca/p{b['parca']:02d}", .3, .5, .2)
    sure = round(cur + .6, 2); s2 = next(e['t0'] for e in out if e['sahne'] == 2)
    json.dump(dict(sure=sure, sahne2=s2, beats=out), open(f'{D}/timeline.json', 'w'), ensure_ascii=False)
    json.dump(alt, open(f'{D}/altyazi.json', 'w'), ensure_ascii=False, indent=0); json.dump(ses, open(f'{D}/ses/yerlesim.json', 'w'), indent=0)
    sah = {}; [sah.setdefault(e['sahne'], e['t0']) for e in out]
    print('süre', sure, 's =', fmt(sure), '| tahmini vuruş', sum('tahmin' in e for e in out), '| sahne başları:', {k: fmt(v) for k, v in sah.items()})
else:
    for f in sorted(glob.glob(f'{D}/kisa/kisa[0-9]_beats.json')):
        K = json.load(open(f)); n = int(os.path.basename(f)[4]); out, alt, ses, cur = zaman(K['beats'], lambda b: b['wav'], .08, 0)
        son = round(cur, 3); sure = round(son + 2.4, 2)  # son 2,4 sn: harekete çağrı kartı
        json.dump(dict(sure=sure, son=son, kisa=n, baslik=K['baslik'], kanca=K['kanca'], sonyazi=K['son'], beats=out), open(f'{D}/kisa{n}.json', 'w'), ensure_ascii=False)
        json.dump(alt, open(f'{D}/kisa/kisa{n}_altyazi.json', 'w'), ensure_ascii=False, indent=0); json.dump(ses, open(f'{D}/kisa/kisa{n}_yerlesim.json', 'w'), indent=0)
        print(f'kısa {n}: {sure:.1f} sn', '| tahmini vuruş', sum('tahmin' in e for e in out), ('' if 30 <= sure <= 55 else '  UYARI: 30–55 sn dışında'))
