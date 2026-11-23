# Bölüm 1 ses miksi: seslendirme (doğal hız, hızlandırma YOK) + sahne müziği + efektler -> audio/ana_mix.wav | audio/kisaN_mix.wav
# python miks.py          ana bölüm   |   python miks.py --kisa   6 Shorts
import json, os, re, sys, numpy as np, soundfile as sf, pyloudnorm as pyln
D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(D, '..', 'ortak'))
import ses_tasarim as S
SR = S.SR; MT = pyln.Meter(SR); os.makedirs(f'{D}/audio', exist_ok=True)
RUH = {1: 'gerilim', 2: 'melankoli', 3: 'umut', 4: 'tedirgin', 5: 'kriz', 6: 'suspense', 7: 'yukselis', 8: 'tefekkur', 9: 'final'}
HEDEF = {'gerilim': -28, 'melankoli': -27, 'umut': -26, 'tedirgin': -27, 'kriz': -26.5, 'suspense': -28, 'yukselis': -24.5, 'tefekkur': -27, 'final': -27.5}
KALEM = {'V.gece_hesap', 'D.kalem', 'D.gece_hesap', 'D.defter', 'D.defter2', 'D.tasarim'}
lufs = lambda x: MT.integrated_loudness(x) if len(x) > SR else -70
def norm(x, hedef):
    l = lufs(x); return x * 10 ** ((hedef - l) / 20) if np.isfinite(l) and l > -69 else x
def aile(p): return re.sub(r'[0-9]+$|_.*$', '', p, count=1) if re.match(r'^(kaynak|final|yil_)', p) else 'kullanim' if p in ('kullanim1', 'kullanim2') else p
def planla(B):
    P = []
    for b in B:
        if P and P[-1]['cek'] == b['cek'] and P[-1]['sahne'] == b['sahne']: P[-1]['t1'] = b['t1']; P[-1]['beats'].append(b)
        else: P.append(dict(cek=b['cek'], sahne=b['sahne'], t0=b['t0'], t1=b['t1'], beats=[b]))
    return P
def ses_izi(yer, N):
    V = np.zeros(N, np.float32)
    for e in yer:
        y = sf.read(e['wav'], dtype='float32')[0]; y = norm(y, -17) if len(y) > .5 * SR else y
        if e['kon'] == 'H' and e['cek'] == 'D.tel_yakin': y = S.telefon_filtre(y) * .9  # Hasan Usta telefonda
        i = int(e['t'] * SR); n = min(len(y), N - i); V[i:i + n] += y[:n]
    for _ in range(2): V = norm(V, -16); V = S.limiter(V, -1.5)
    return V
def efektler(B, N, kisa=False):
    X = np.zeros((N, 2), np.float32); P = planla(B); onceki = None; kep = False; kasa = False
    for p in P:
        c, t0, d, s = p['cek'], p['t0'], p['t1'] - p['t0'], p['sahne']
        if c.startswith('G.') and s in (1, 9): S.ekle(X, S.yagmur(d + .6, ic=c not in ('G.dis_yagmur', 'G.emir_yansima')), t0 - .3, SR, .5 if c == 'G.dis_yagmur' else .35)
        if c.startswith(('C.', 'O.')) or c == 'D.acilis_kapi': S.ekle(X, S.sokak(d + .6), t0 - .3, SR, .55)
        elif c.startswith('V.'): S.ekle(X, S.oda(d + .4, saat=True), t0 - .2, SR, .8)
        elif c.startswith('F.'): S.ekle(X, S.oda(d + .4, klima=True), t0 - .2, SR, .8)
        elif c.startswith('D.') or c.startswith('G.'): S.ekle(X, S.oda(d + .4, saat=c in ('D.kasa_gece', 'G.emir_yalniz')), t0 - .2, SR, .6)
        if c in ('D.kapi_musteri', 'D.kapi_murat'): S.ekle(X, S.kapi_zili(), t0 + .45, SR, .55)
        if c == 'D.murat_cikis': S.ekle(X, S.kapi_zili(), t0 + .8 * d, SR, .5)
        if c == 'D.acilis_kapi' and s == 3 and not kep: kep = True; S.ekle(X, S.kepenk(2.4), t0 + .05, SR, .7)
        if c == 'D.tadilat': [S.ekle(X, S.matkap(), t0 + o, SR, .6) for o in (.2, max(.2, d * .55))]
        if c == 'D.kasa' and not kasa: kasa = True; S.ekle(X, S.yazarkasa(), t0 + .35, SR, .6)
        if c == 'D.tezgah_satis': S.ekle(X, S.bozuk_para(), t0 + d * .6, SR, .55)
        if c in ('D.montaj1', 'D.montaj3'): S.ekle(X, S.bozuk_para(4), t0 + d * .3, SR, .35)
        if c == 'D.telefon': S.ekle(X, S.telefon_cal(2), t0 + .05, SR, .5)
        if c == 'X.takvim':
            for k, x in enumerate(np.arange(0, d, .5)): S.ekle(X, S.pan(S.davul('tik' if k % 2 else 'tak', .5, SR), 0), t0 + x, SR)
            for x in np.arange(.2, d, .9): S.ekle(X, S.pan(S.davul('kalp', .7, SR), 0), t0 + x, SR)
        if c in KALEM: S.ekle(X, S.kalem(min(d - .5, 3.2)), t0 + .5, SR, .5)
        if c == 'O.satis': S.ekle(X, S.araba_kapi(), t0 + .8, SR, .6)
        if c == 'D.atolye': S.ekle(X, S.alev(d), t0, SR, .7)
        if c in ('X.12ay', 'X.biryil'): S.ekle(X, S.whoosh(1.0, True, .45), t0 - .6, SR); S.ekle(X, S.vurus(3.5, .55), t0 + .25, SR)
        if c == 'X.bolum2': S.ekle(X, S.vurus(4.5, 1.0), t0 + .1, SR)
        if c == 'G.kenan_yakin' and s == 1: S.ekle(X, S.vurus(3, .45), p['t1'] - 1.2, SR)
        if c == 'G.emir_push' and s == 1 and not kisa: S.ekle(X, S.vurus(4, .85), p['t1'] - 2.4, SR)  # bölüm başlığı
        if c == 'G.emir_push' and s == 9 and not kisa:
            for x in (.3, 1.2, 2.1): S.ekle(X, S.pan(S.davul('kalp', .8, SR), 0), t0 + x, SR)
    for b in B:  # HUD paneli girişleri
        pnl = b['panel'] if b['panel'] != '-' else None
        if pnl and (onceki is None or aile(pnl) != aile(onceki)): S.ekle(X, S.whoosh(.55, True, .22), b['t0'] - .15, SR); S.ekle(X, S.hud_tik(5, .1), b['t0'] + .25, SR)
        onceki = pnl
    return X
def muzik_ana(T, N):
    B = T['beats']; bas = {}; [bas.setdefault(b['sahne'], b['t0']) for b in B]; sh = sorted(bas); M = np.zeros((N, 2), np.float32)
    ben = next((b for b in B if b['sahne'] == 9 and b['kon'] == 'E' and b['cek'] == 'G.emir_push'), None); b2 = next(b for b in B if b['cek'] == 'X.bolum2')
    for i, s in enumerate(sh):
        t0 = bas[s]; t1 = bas[sh[i + 1]] if i + 1 < len(sh) else (ben['t0'] if ben else T['sure']); r = RUH[s]
        cu = S.srm_to_sr(S.cue(r, t1 - t0 + 1.6)); cu = norm(cu, HEDEF[r]); S.ekle(M, cu, max(0, t0 - .5), SR)
    son = S.srm_to_sr(S.cue('gerilim', T['sure'] - b2['t0'] + .5)); S.ekle(M, norm(son, -29), b2['t0'], SR)
    return M
def miksle(V, M, X, sure, ad):
    N = len(V); e = S.zarf_takip(V); M = M[:N] * (1 - .55 * e)[:, None]; X = X[:N] * (1 - .25 * e)[:, None]
    X = norm(X, -31); mix = M + X + np.stack([V, V], 1) * 10 ** (-3 / 20)
    f0 = int((sure - .5) * SR); mix[f0:] *= (np.linspace(1, 0, N - f0) ** 2)[:, None]
    for _ in range(3): mix = norm(mix, -14); mix = S.limiter(mix, -3.2)
    sf.write(f'{D}/audio/{ad}.wav', mix, SR, subtype='PCM_16')
    print(ad, '| miks', round(lufs(mix), 2), 'LUFS | ses', round(lufs(V), 1), '| müzik', round(lufs(M), 1), '| efekt', round(lufs(X), 1), '| tepe', round(20 * np.log10(np.abs(mix).max()), 2), 'dBFS')
if '--kisa' not in sys.argv:
    T = json.load(open(f'{D}/timeline.json')); N = int(T['sure'] * SR); yer = json.load(open(f'{D}/ses/yerlesim.json'))
    V = ses_izi(yer, N); son = max(e['t'] + sf.info(e['wav']).duration for e in yer); print('konuşma bitişi', round(son, 2), '/ video', T['sure'])
    miksle(V, muzik_ana(T, N), efektler(T['beats'], N), T['sure'], 'ana_mix')
else:
    KR = {1: 'umut', 2: 'tedirgin', 3: 'kriz', 4: 'suspense', 5: 'tefekkur', 6: 'final'}
    for n in range(1, 7):
        T = json.load(open(f'{D}/kisa{n}.json')); N = int(T['sure'] * SR); yer = json.load(open(f'{D}/kisa/kisa{n}_yerlesim.json'))
        V = ses_izi(yer, N); M = np.zeros((N, 2), np.float32); S.ekle(M, norm(S.srm_to_sr(S.cue(KR[n], T['sure'] + .5)), HEDEF[KR[n]] + 1.5), 0, SR)
        X = efektler(T['beats'], N, kisa=True); S.ekle(X, S.vurus(3, .9), 0, SR); S.ekle(X, S.whoosh(.6, True, .4), T['son'] - .3, SR); S.ekle(X, S.vurus(2.5, .5), T['son'] + .2, SR)
        miksle(V, M, X, T['sure'], f'kisa{n}_mix')
