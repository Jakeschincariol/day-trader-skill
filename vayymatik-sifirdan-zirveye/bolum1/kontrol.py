# Otomatik tutarlılık kontrolleri (senaryo + Shorts + finans + render çekim listesi). Hata varsa çıkış kodu 1.
# 1) {altyazı|okunuş} çiftlerinde rakam = okunan sayı   2) altyazıdaki her ≥1.000 TL rakamı finans.json'da (veya izinli türev listesinde) var
# 3) kullanılan her çekim kodu render/bolum1.js'te, her panel anahtarı finans/HUD'da tanımlı   4) Shorts: ilk vuruşta panel yok (kanca), süre 30–55 sn
import json, re, os, glob, sys
D = os.path.dirname(os.path.abspath(__file__)); F = json.load(open(f'{D}/finans.json')); hata, uyari = [], []
BIR = dict(bir=1, iki=2, üç=3, dört=4, beş=5, altı=6, yedi=7, sekiz=8, dokuz=9); ON = dict(on=10, yirmi=20, otuz=30, kırk=40, elli=50, altmış=60, yetmiş=70, seksen=80, doksan=90)
KOK = sorted(list(BIR) + list(ON) + ['yüz', 'bin', 'milyon', 'buçuk'], key=len, reverse=True)
low = lambda s: s.replace('I', 'ı').replace('İ', 'i').lower()
def kok(w):
    w = re.sub(r'[^a-zçğıöşüâî]', '', low(w)); return next((k for k in KOK if w.startswith(k)), None)
def kelime_sayi(toks):
    top = cur = 0.; var = False
    for t in toks:
        k = kok(t)
        if k is None: continue
        var = True
        if k in BIR: cur += BIR[k]
        elif k in ON: cur += ON[k]
        elif k == 'buçuk': cur += .5
        elif k == 'yüz': cur = (cur or 1) * 100
        elif k == 'bin': top += (cur or 1) * 1000; cur = 0
        elif k == 'milyon': top += (cur or 1) * 1e6; cur = 0
    return top + cur if var else None
def karisik_sayi(toks):
    v = None
    for t in toks:
        if re.match(r'^\d[\d.,]*', t): v = float(re.match(r'^\d[\d.,]*', t).group().rstrip('.,').replace('.', '').replace(',', '.'))
        elif v is not None and kok(t) == 'milyon': v *= 1e6
        elif v is not None and kok(t) == 'bin': v *= 1000
    return v if v is not None else kelime_sayi(toks)
CARPAN = re.compile(r'^(milyon|bin)', re.I)
def cift_kontrol(met, yer):
    for m in re.finditer(r'((?:\{[^}]*\}\s*)+)(\S+)?', met):
        grup, sonraki = m.group(1), m.group(2) or ''
        caps = ' '.join(re.findall(r'\{([^|}]*)\|', grup)); says = ' '.join(re.findall(r'\|([^}]*)\}', grup))
        ek = [sonraki] if CARPAN.match(low(sonraki)) else []
        a, b = karisik_sayi(caps.split() + ek), kelime_sayi(says.split() + ek)
        if a is None and b is None: continue  # sayı içermeyen çift (ör. tırnaklı ifade)
        if a is None or b is None or abs(a - b) > 1e-6: hata.append(f'{yer}: "{caps}" ({a}) okunuşu "{says}" ({b}) ile uyuşmuyor')
def duz(o, out):
    if isinstance(o, dict): [duz(v, out) for v in o.values()]
    elif isinstance(o, list): [duz(v, out) for v in o]
    elif isinstance(o, (int, float)) and not isinstance(o, bool): out.add(round(abs(o)))
    return out
BILINEN = duz(F, set())  # ekranda/seste geçen her ≥1.000 TL rakam finans.json'dan gelmeli
def rakam_kontrol(cap, yer):
    for m in re.finditer(r'(\d[\d.,]*)\s*(milyon|bin)?', cap):
        v = float(m.group(1).rstrip('.,').replace('.', '').replace(',', '.')) * (1e6 if m.group(2) == 'milyon' else 1000 if m.group(2) == 'bin' else 1)
        if v >= 1000 and round(v) not in BILINEN: hata.append(f'{yer}: {m.group(0)} finans verisinde yok')
JS = open(f'{D}/../render/bolum1.js', encoding='utf-8').read()
CEK = set(re.findall(r"'([A-Z]\.[a-z0-9_]+)':\s*\{", JS)) | {f'H.{h}' for h in re.findall(r"for \(const h of \[([^\]]*)\]\) S\['H\.'", JS)[0].replace("'", '').replace(' ', '').split(',')} | {f'X.{h}' for h in re.findall(r"for \(const x of \[([^\]]*)\]\) S\['X\.'", JS)[0].replace("'", '').replace(' ', '').split(',')}
PANEL = set(F['anlar']) | {'-', 'yil_sonu', 'kaynak1', 'kaynak2', 'kaynak3', 'kaynak4', 'kaynak_toplam', 'kullanim1', 'kullanim2', 'kullanim3', 'emanet', 'siparis', 'kriz', 'yatirimci', 'belirsiz', 'takvim', 'kullanilabilir', 'yil_ciro', 'yil_gider', 'yil_net', 'kopru', 'final1', 'final2', 'final3'}
def satirlar(fn):
    for k, ln in enumerate(open(fn, encoding='utf-8'), 1):
        if ln.strip() and not ln.startswith(('#', '@')): yield k, re.split(r'\|(?![^{]*\})', ln.rstrip('\n'))
for fn in [f'{D}/senaryo.txt'] + sorted(glob.glob(f'{D}/kisa/kisa[0-9].txt')):
    ad = os.path.basename(fn); ilk = True
    for k, (sah, kon, met, cek, pan, ara) in satirlar(fn):
        yer = f'{ad}:{k}'
        if cek not in CEK: hata.append(f'{yer}: çekim kodu tanımsız: {cek}')
        if pan not in PANEL: hata.append(f'{yer}: panel tanımsız: {pan}')
        if kon != '-': cift_kontrol(met, yer); rakam_kontrol(re.sub(r'\{([^|}]*)\|([^}]*)\}', r'\1', met), yer)
        if ad.startswith('kisa') and ilk and pan != '-': hata.append(f'{yer}: Shorts kancasında panel olmamalı')
        ilk = False
for fn in sorted(glob.glob(f'{D}/kisa[0-9].json')):
    T = json.load(open(fn)); t = [b for b in T['beats'] if b.get('tahmin')]
    if not 30 <= T['sure'] <= 55: hata.append(f'{os.path.basename(fn)}: süre {T["sure"]} sn (30–55 olmalı)')
    if t: uyari.append(f'{os.path.basename(fn)}: {len(t)} vuruş henüz tahmini süreli (ses üretimi bitmedi)')
T = json.load(open(f'{D}/timeline.json'))
if not 12 * 60 <= T['sure'] <= 15 * 60: hata.append(f'timeline.json: süre {T["sure"]:.0f} sn (12–15 dk olmalı)')
if any(b.get('tahmin') for b in T['beats']): uyari.append('timeline.json: tahmini süreli vuruşlar var (ses üretimi bitmedi)')
print('finans kontrolleri:', len(F.get('kontroller', [])), '| çekim kodu:', len(CEK), '| bilinen rakam:', len(BILINEN))
for u in uyari: print('UYARI', u)
for h in hata: print('HATA ', h)
print('TAMAM' if not hata else f'{len(hata)} hata'); sys.exit(1 if hata else 0)
