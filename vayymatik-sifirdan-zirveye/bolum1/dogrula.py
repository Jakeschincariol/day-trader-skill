# Çıktı doğrulama: açılıyor mu (tam kod çözme), çözünürlük, fps, süre, ses akışı, A/V süre farkı, ses yüksekliği (EBU R128)
import json, subprocess, sys, os, re
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cikti'); hata = []
def bilgi(f):
    p = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', f], capture_output=True, text=True).stdout)
    v = next(s for s in p['streams'] if s['codec_type'] == 'video'); a = [s for s in p['streams'] if s['codec_type'] == 'audio']
    return v, a, float(p['format']['duration']), int(p['format']['size'])
def coz(f):  # tam kod çözme + yükseklik ölçümü
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', f, '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True); e = r.stderr
    hatalar = [l for l in e.splitlines() if l.strip() and not l.startswith(('[Parsed_ebur128', '  ', 'Summary')) and 'ebur128' not in l and not re.match(r'^\s*(Integrated|I:|Threshold|LRA|Loudness range|True peak|Peak|LRA low|LRA high)', l)]
    I = re.findall(r'I:\s+(-?[\d.]+) LUFS', e); P = re.findall(r'Peak:\s+(-?[\d.]+) dBFS', e)
    return r.returncode, hatalar, float(I[-1]) if I else None, float(P[-1]) if P else None
BEK = [('Sifirdan_Zirveye_Bolum1.mp4', 1920, 1080, 24, 12 * 60, 15 * 60)] + [(f'Shorts_0{n}.mp4', 1080, 1920, 30, 30, 55) for n in range(1, 7)]
for ad, W, H, fps, s0, s1 in BEK:
    f = os.path.join(D, ad)
    if not os.path.exists(f): hata.append(f'{ad}: YOK'); print(f'✘ {ad}: dosya yok'); continue
    v, a, sure, boy = bilgi(f); vs = float(v.get('duration', sure)); as_ = float(a[0].get('duration', sure)) if a else 0; fr = eval(v['avg_frame_rate'])
    rc, hl, I, P = coz(f)
    ok = [v['width'] == W and v['height'] == H, abs(fr - fps) < .01, s0 <= sure <= s1, bool(a), abs(vs - as_) < .15, rc == 0 and not hl, I is not None and -15.5 <= I <= -12.5, P is not None and P <= -1.0]
    print(('✔' if all(ok) else '✘'), f'{ad}: {v["width"]}x{v["height"]} {fr:g} fps {v["codec_name"]}/{a[0]["codec_name"] if a else "-"} | {int(sure // 60)}:{sure % 60:04.1f} | video {vs:.2f}s ses {as_:.2f}s | {I} LUFS, tepe {P} dBFS | {boy / 1e6:.1f} MB | kod çözme {"temiz" if rc == 0 and not hl else "HATA " + str(hl[:2])}')
    if not all(ok): hata.append(ad)
print('TÜM ÇIKTILAR DOĞRULANDI' if not hata else f'SORUNLU: {hata}'); sys.exit(1 if hata else 0)
