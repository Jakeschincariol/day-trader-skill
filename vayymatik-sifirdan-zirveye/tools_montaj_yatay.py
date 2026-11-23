import sys, glob, os
from PIL import Image, ImageDraw
d, out, cols, fps = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4]) if len(sys.argv) > 4 else 24
fs = sorted(glob.glob(d + '/*.jpg'))[:int(sys.argv[5]) if len(sys.argv) > 5 else 999]; w, h = 384, 216; rows = (len(fs) + cols - 1) // cols; M = Image.new('RGB', (cols * w, rows * h))
for i, f in enumerate(fs):
    im = Image.open(f).resize((w, h)); n = int(os.path.basename(f)[:5]); ImageDraw.Draw(im).text((5, 3), f"{int(n / fps // 60)}:{n / fps % 60:04.1f}", fill=(255, 255, 0)); M.paste(im, ((i % cols) * w, (i // cols) * h))
M.save(out, quality=82)
