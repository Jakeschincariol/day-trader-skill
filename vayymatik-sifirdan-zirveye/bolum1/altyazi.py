# Altyazılar: altyazi.json (kelime zamanlı) -> subs/ana.srt + subs/ana.ass (yatay, cümle bloklu)
#             kisa/kisaN_altyazi.json -> subs/kisaN.ass (dikey, kelime kelime vurgulu) + subs/kisaN.srt
import json, os, re, glob
D = os.path.dirname(os.path.abspath(__file__)); os.makedirs(f'{D}/subs', exist_ok=True)
TRU = lambda s: s.replace('i', 'İ').replace('ı', 'I').upper()  # Türkçe büyük harf
POP = '{\\fscx106\\fscy106\\t(0,90,\\fscx100\\fscy100)}'
def ts(t, ass=False):
    t = max(0, t); h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f'{h}:{m:02d}:{s:05.2f}' if ass else f'{h:02d}:{m:02d}:{int(s):02d},{int(round((s % 1) * 1000)) % 1000:03d}'
def bloklar(W, maks=80):  # cümle/virgül sınırlarında böl
    out, cur = [], []
    for i, w in enumerate(W):
        cur.append(w); n = len(' '.join(x['w'] for x in cur)); son = i == len(W) - 1
        cumle = re.search(r'[.?!…:]$', w['w']); virgul = re.search(r'[,;]$', w['w'])
        if son or (cumle and n > 18) or (virgul and n > 46) or n > maks - 12:
            if not son and n > maks - 12 and not (cumle or virgul) and len(cur) > 2: nx = cur.pop(); out.append(cur); cur = [nx]; continue
            out.append(cur); cur = []
    if cur: out.append(cur)
    return out
def iki_satir(s, mx=42):
    if len(s) <= mx: return s
    w = s.split(); best = min(range(1, len(w)), key=lambda k: abs(len(' '.join(w[:k])) - len(' '.join(w[k:]))))
    return ' '.join(w[:best]) + '\\N' + ' '.join(w[best:])
def ana(A, srt, ass, W=1920, H=1080):
    ev = []
    for a in A:
        for bl in bloklar(a['words']): ev.append([bl[0]['t0'], bl[-1]['t1'] + .3, ' '.join(x['w'] for x in bl), a['kon']])
    for i in range(len(ev) - 1): ev[i][1] = min(ev[i][1], ev[i + 1][0] - .04); ev[i][1] = max(ev[i][1], ev[i][0] + .9) if ev[i + 1][0] - ev[i][0] > .95 else ev[i][1]
    with open(srt, 'w', encoding='utf-8') as f:
        for i, (a, b, t, k) in enumerate(ev, 1): f.write(f'{i}\n{ts(a)} --> {ts(b)}\n{iki_satir(t).replace(chr(92) + "N", chr(10))}\n\n')
    with open(ass, 'w', encoding='utf-8') as f:
        f.write(f'[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
                'Style: N,Montserrat SemiBold,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H8C000000,0,0,0,0,100,100,0.3,0,1,3,1.2,2,120,120,46,1\n'
                'Style: K,Montserrat SemiBold,46,&H008BD9F5,&H008BD9F5,&H00000000,&H8C000000,0,0,0,0,100,100,0.3,0,1,3,1.2,2,120,120,46,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
        for a, b, t, k in ev: f.write(f'Dialogue: 0,{ts(a, 1)},{ts(b, 1)},{"N" if k == "N" else "K"},,0,0,0,,{iki_satir(t)}\n')
    return len(ev)
def kisa(A, ass, srt, W=1080, H=1920):  # 1-3 kelimelik gruplar, konuşulan kelime altın renkte
    G = []
    for a in A:
        W_ = a['words']; grp = []
        for w in W_:
            grp.append(w); n = len(' '.join(x['w'] for x in grp))
            if len(grp) == 3 or n > 16 or re.search(r'[.?!…:,;]$', w['w']): G.append(grp); grp = []
        if grp: G.append(grp)
    with open(ass, 'w', encoding='utf-8') as f:
        f.write(f'[Script Info]\nScriptType: v4.00+\nPlayResX: {W}\nPlayResY: {H}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n'
                'Style: C,Montserrat ExtraBold,76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0.5,0,1,6,3,2,70,70,600,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
        for gi, g in enumerate(G):
            g_end = min(g[-1]['t1'] + .25, G[gi + 1][0]['t0'] - .02) if gi + 1 < len(G) else g[-1]['t1'] + .4
            for wi, w in enumerate(g):
                a = w['t0'] if wi else min(w['t0'], g[0]['t0']); b = g[wi + 1]['t0'] if wi + 1 < len(g) else g_end
                if b - a < .03: continue
                txt = ' '.join(('{\\c&H4AC4E8&}' + TRU(x['w']) + '{\\c&HFFFFFF&}') if j == wi else TRU(x['w']) for j, x in enumerate(g))
                f.write(f'Dialogue: 0,{ts(a, 1)},{ts(b, 1)},C,,0,0,0,,{POP if wi == 0 else ""}{txt}\n')
    ev = []
    for a in A:
        for bl in bloklar(a['words'], 60): ev.append([bl[0]['t0'], bl[-1]['t1'] + .3, ' '.join(x['w'] for x in bl)])
    for i in range(len(ev) - 1): ev[i][1] = min(ev[i][1], ev[i + 1][0] - .04)
    with open(srt, 'w', encoding='utf-8') as f:
        for i, (a, b, t) in enumerate(ev, 1): f.write(f'{i}\n{ts(a)} --> {ts(b)}\n{iki_satir(t, 32).replace(chr(92) + "N", chr(10))}\n\n')
    return len(G)
print('ana altyazı:', ana(json.load(open(f'{D}/altyazi.json')), f'{D}/subs/ana.srt', f'{D}/subs/ana.ass'), 'blok')
for fn in sorted(glob.glob(f'{D}/kisa/kisa[0-9]_altyazi.json')):
    n = os.path.basename(fn)[4]; print(f'kısa {n}:', kisa(json.load(open(fn)), f'{D}/subs/kisa{n}.ass', f'{D}/subs/kisa{n}.srt'), 'grup')
