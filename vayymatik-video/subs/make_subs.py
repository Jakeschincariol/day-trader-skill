# Seslendirme zamanlamasından SRT ve stilize ASS (anahtar kelime vurgulu) altyazı üretir.
import json, os, re
D = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(D)
segs = json.load(open(f'{ROOT}/voice/segs.json'))
FIX = {'[[ onaɾˈɯm ]]': 'Onarım', '[[ denizˈɪn ]]': 'denizin'}
KEY = ['uzaydan', 'okyanus', 'dibinde', 'fiber', 'optik', 'uluslararası', 'yüzde', 'doksan', 'dokuzundan', 'ışık', 'iki', 'yüz', 'bin', 'kilometre',
       'gemi', 'çapası', 'koparırsa', 'üçte', 'ikisine', 'balıkçılık', 'çapalar', 'onarım', 'yüzeye', 'diğer', 'kablolara', 'kıtalar', 'denizin', 'altından', 'takip']
low = lambda w: w.replace('I', 'ı').replace('İ', 'i').lower()
def chunks(text):
    out, cur = [], []
    for w in text.split():
        if cur and (len(' '.join(cur + [w])) > 22 or len(cur) >= 4): out.append(cur); cur = []
        cur.append(w)
        if re.search(r'[,.?!:;]$', w) and len(cur) >= 2: out.append(cur); cur = []
    if cur: out.append(cur)
    return out
ev = []  # (başlangıç, bitiş, kelimeler, cümle no)
for k, s in enumerate(segs):
    txt = s['text']
    for a, b in FIX.items(): txt = txt.replace(a, b)
    cs = chunks(txt); wts = [len(' '.join(c)) + 5 * sum(bool(re.search(r'[,:;]$', w)) for w in c) + 3 for c in cs]
    t0, t1 = s['t'] + .03, s['t'] + s['dur'] - .1; tot = sum(wts); acc = t0
    nxt = segs[k + 1]['t'] - .05 if k + 1 < len(segs) else 44.9
    for i, (c, w) in enumerate(zip(cs, wts)):
        st = acc; acc += (t1 - t0) * w / tot
        en = acc if i < len(cs) - 1 else min(acc + .35, nxt)
        ev.append((st, en, c, k))
def ts(t, sep=','): h, m = divmod(t, 3600); m, s = divmod(m, 60); return f'{int(h):02d}:{int(m):02d}:{s:06.3f}'.replace('.', sep)
# SRT: cümle bazlı, en çok 2 satır x 42 karakter
srt = []
for k in range(len(segs)):
    g = [e for e in ev if e[3] == k]; ln = lambda x: len(' '.join(sum([e[2] for e in x], [])))
    if ln(g) <= 90: srt.append(g); continue
    b = min(range(1, len(g)), key=lambda i: abs(ln(g[:i]) - ln(g[i:]))); srt += [g[:b], g[b:]]
def two(ws):
    s = ' '.join(ws)
    if len(s) <= 42: return s
    best = min(range(1, len(ws)), key=lambda i: abs(len(' '.join(ws[:i])) - len(' '.join(ws[i:]))))
    return ' '.join(ws[:best]) + '\n' + ' '.join(ws[best:])
with open(f'{ROOT}/altyazi.srt', 'w', encoding='utf-8') as f:
    for i, g in enumerate(srt, 1): f.write(f"{i}\n{ts(g[0][0])} --> {ts(g[-1][1])}\n{two(sum([x[2] for x in g], []))}\n\n")
# ASS
Y, C, G = '&H003FD2FF&', '&H00FFE34F&', '&H00B8C4CC&'
hdr = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Montserrat ExtraBold,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,6,3,5,70,70,10,1
Style: Big,Montserrat Black,200,&H00FFE34F,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,40,40,10,1
Style: Sub,Montserrat ExtraBold,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,4,2,5,60,60,10,1
Style: Src,Montserrat SemiBold,30,&H00C4CCD4,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,3,0,5,60,60,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
L = []
for st, en, ws, _ in ev:
    txt = ' '.join(('{\\c' + Y + '}' + w + '{\\c&H00FFFFFF&}') if any(low(re.sub(r'[^\wçğıöşüÇĞİÖŞÜ]', '', w)).startswith(k) for k in KEY) else w for w in ws)
    L.append(f"Dialogue: 2,{ts(st, '.')[1:-1]},{ts(en, '.')[1:-1]},Cap,,0,0,0,,{{\\an5\\pos(540,1300)\\fad(60,40)\\fscx86\\fscy86\\t(0,110,\\fscx100\\fscy100)}}{txt}")
def big(st, en, main, size, sub, src, y=380):
    a = '\\fad(150,250)\\fscx70\\fscy70\\t(0,180,\\fscx100\\fscy100)'
    L.append(f"Dialogue: 0,{ts(st, '.')[1:-1]},{ts(en, '.')[1:-1]},Big,,0,0,0,,{{\\an5\\pos(540,{y})\\fs{size}\\blur14\\alpha&H70&{a}}}{main}")
    L.append(f"Dialogue: 1,{ts(st, '.')[1:-1]},{ts(en, '.')[1:-1]},Big,,0,0,0,,{{\\an5\\pos(540,{y})\\fs{size}\\bord3\\3c&H00301808&{a}}}{main}")
    L.append(f"Dialogue: 1,{ts(st + .15, '.')[1:-1]},{ts(en, '.')[1:-1]},Sub,,0,0,0,,{{\\an5\\pos(540,{y + size * .62 + 10:.0f})\\fad(200,250)}}{sub}")
    if src: L.append(f"Dialogue: 1,{ts(st + .3, '.')[1:-1]},{ts(en, '.')[1:-1]},Src,,0,0,0,,{{\\an5\\pos(540,{y + size * .62 + 66:.0f})\\fad(200,250)}}{src}")
big(11.05, 16.25, '%99+', 210, 'uluslararası veri trafiği', 'Kaynak: ITU')
big(19.15, 23.15, '≈200.000 km/sn', 116, 'ışığın cam lifteki hızı', '')
big(27.45, 30.45, '2/3', 210, 'arızanın nedeni: balıkçılık ve çapa', 'Kaynak: TeleGeography (ICPC verisi)')
open(f'{D}/captions.ass', 'w', encoding='utf-8').write(hdr + '\n'.join(L) + '\n')
print(len(ev), 'altyazı parçası,', len(srt), 'SRT girdisi')
