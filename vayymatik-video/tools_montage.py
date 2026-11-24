import sys, glob, os
from PIL import Image, ImageDraw
d, out, cols = sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 6
fs = sorted(glob.glob(d + '/*.jpg')); ims = [Image.open(f) for f in fs]; w, h = 270, 480
rows = (len(ims) + cols - 1) // cols; M = Image.new('RGB', (cols * w, rows * h))
for i, (f, im) in enumerate(zip(fs, ims)):
    im = im.resize((w, h)); ImageDraw.Draw(im).text((6, 4), f"{int(os.path.basename(f)[:5])/30:.1f}s", fill=(255, 255, 0)); M.paste(im, ((i % cols) * w, (i // cols) * h))
M.save(out, quality=85)
