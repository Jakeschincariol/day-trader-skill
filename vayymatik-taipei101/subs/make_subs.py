# Kelime kelime senkronize altyazı: karaoke ASS (videoya gömülür) + SRT (cümle) + SRT (kelime)
import json, os, re
D = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(D)
segs = json.load(open(f'{ROOT}/voice/segs.json'))
def ts(t, sep=','): h, m = divmod(t, 3600); m, s = divmod(m, 60); return f'{int(h):02d}:{int(m):02d}:{s:06.3f}'.replace('.', sep)
ass = lambda t: ts(t, '.')[1:-1]
chunks = []
for k, g in enumerate(segs):
    cur = []
    for w in g['words']:
        if cur and (len(' '.join(x['w'] for x in cur + [w])) > 22 or len(cur) >= 4): chunks.append((k, cur)); cur = []
        cur.append(w)
        if re.search(r'[,.?!:;]$', w['w']) and len(cur) >= 2: chunks.append((k, cur)); cur = []
    if cur: chunks.append((k, cur))
Y, Wc = '&H003FD2FF&', '&H00FFFFFF&'
L = []
for i, (k, c) in enumerate(chunks):
    nxt = chunks[i + 1][1][0]['t0'] if i + 1 < len(chunks) else 44.9
    end = min(c[-1]['t1'] + .3, nxt - .02) if i + 1 < len(chunks) and chunks[i + 1][0] == k else min(c[-1]['t1'] + .45, nxt - .02)
    for j, w in enumerate(c):
        st = c[0]['t0'] if j == 0 else w['t0']; en = c[j + 1]['t0'] if j + 1 < len(c) else end
        txt = ' '.join((f'{{\\c{Y}\\3c&H00101010&}}' + x['w'] + f'{{\\c{Wc}}}') if q == j else (('{\\alpha&H70&}' + x['w'] + '{\\alpha&H00&}') if q > j else x['w']) for q, x in enumerate(c))
        pop = '\\fscx86\\fscy86\\t(0,110,\\fscx100\\fscy100)' if j == 0 else ''
        L.append(f"Dialogue: 2,{ass(st)},{ass(en)},Cap,,0,0,0,,{{\\an5\\pos(540,1300){pop}}}{txt}")
def big(st, en, lines, size, y, sub=None, col='&H003CC9FF&'):
    a = '\\fad(120,250)\\fscx175\\fscy175\\t(0,160,\\fscx100\\fscy100)'
    for k, ln in enumerate(lines):
        yy = y + k * size * .95
        L.append(f"Dialogue: 0,{ass(st)},{ass(en)},Big,,0,0,0,,{{\\an5\\pos(540,{yy:.0f})\\fs{size}\\1c{col}\\blur16\\alpha&H66&{a}}}{ln}")
        L.append(f"Dialogue: 1,{ass(st)},{ass(en)},Big,,0,0,0,,{{\\an5\\pos(540,{yy:.0f})\\fs{size}\\1c{col}\\bord4\\3c&H00101010&{a}}}{ln}")
    if sub: L.append(f"Dialogue: 1,{ass(st + .2)},{ass(en)},Src,,0,0,0,,{{\\an5\\pos(540,{y + len(lines) * size * .95 - size * .25:.0f})\\fad(200,250)}}{sub}")
big(.35, 4.65, ['660 TON!'], 230, 470)
big(27.25, 29.35, ['AYARLI KÜTLE', 'SÖNÜMLEYİCİ'], 112, 420, 'Tuned Mass Damper (TMD)', '&H003AC2FF&')
hdr = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Montserrat ExtraBold,74,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,6,3,5,60,60,10,1
Style: Big,Montserrat Black,200,&H003CC9FF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,40,40,10,1
Style: Src,Montserrat SemiBold,38,&H00D8E0E6,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,3,0,5,60,60,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
open(f'{D}/captions.ass', 'w', encoding='utf-8').write(hdr + '\n'.join(L) + '\n')
def two(s):
    if len(s) <= 42: return s
    ws = s.split(); b = min(range(1, len(ws)), key=lambda i: abs(len(' '.join(ws[:i])) - len(' '.join(ws[i:])))); return ' '.join(ws[:b]) + '\n' + ' '.join(ws[b:])
with open(f'{ROOT}/altyazi.srt', 'w', encoding='utf-8') as f:
    n = 0
    for g in segs:
        ws = g['words']; parts = [ws] if len(g['cap']) <= 90 else [ws[:len(ws) // 2], ws[len(ws) // 2:]]
        for p in parts: n += 1; f.write(f"{n}\n{ts(p[0]['t0'])} --> {ts(p[-1]['t1'] + .3)}\n{two(' '.join(x['w'] for x in p))}\n\n")
with open(f'{ROOT}/altyazi_kelime.srt', 'w', encoding='utf-8') as f:
    for i, w in enumerate([w for g in segs for w in g['words']], 1): f.write(f"{i}\n{ts(w['t0'])} --> {ts(w['t1'])}\n{w['w']}\n\n")
print(len(chunks), 'parça,', len(L), 'ASS olayı')
