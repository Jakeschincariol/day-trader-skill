# Ses akışını orijinal miksten (audio/*.wav) güvenli AAC ayarlarıyla yeniden kodlar; görüntü akışı kopyalanır (kalite değişmez).
# Neden: ffmpeg AAC'nin PNS / yoğunluk stereo / TNS araçları bazı geçişlerde gerçek tepe sıçramaları (+0,3 dBTP'ye kadar) üretiyordu;
# bu araçlar kapalıyken kaynak tepesi (-3,2 dBTP) korunuyor. Kullanım: python ses_tepe_duzelt.py [dosya.mp4 ...]
import subprocess, sys, re, os
D = os.path.dirname(os.path.abspath(__file__))
AAC = ['-c:a', 'aac', '-aac_coder', 'twoloop', '-b:a', '256k', '-aac_pns', '0', '-aac_is', '0', '-aac_tns', '0', '-aac_ms', '0', '-ar', '48000']
ESLE = {'Sifirdan_Zirveye_Bolum1.mp4': 'ana_mix.wav', **{f'Shorts_0{n}.mp4': f'kisa{n}_mix.wav' for n in range(1, 7)}}
def olc(f):
    e = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', f, '-vn', '-af', 'ebur128=peak=true', '-f', 'null', '-'], capture_output=True, text=True).stderr
    return float(re.findall(r'Peak:\s+(-?[\d.]+) dBFS', e)[-1]), float(re.findall(r'I:\s+(-?[\d.]+) LUFS', e)[-1])
for ad in (sys.argv[1:] or list(ESLE)):
    mp4, tm = f'{D}/cikti/{ad}', f'{D}/cikti/_tmp.mp4'
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', mp4, '-i', f'{D}/audio/{ESLE[ad]}', '-map', '0:v', '-map', '1:a', '-c:v', 'copy', *AAC, '-movflags', '+faststart', '-shortest', tm], check=True)
    os.replace(tm, mp4); p, I = olc(mp4); print(ad, f'{p} dBTP, {I} LUFS')
