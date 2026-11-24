# Anchorage bölgesi stilize harita (Natural Earth 1:10m kara verisi)
import json, sys, numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter, binary_dilation, binary_erosion
D = sys.path[0]; LAT0, LON0 = 61.25, -149.75; LA = (61.05, 61.45); LO = (-150.15, -149.35)
W = 2048; KX = np.cos(np.radians(LAT0)) * 111.32; KY = 110.57
wkm, hkm = (LO[1] - LO[0]) * KX, (LA[1] - LA[0]) * KY; H = int(W * hkm / wkm)
topo = json.load(open(f'{D}/../node_modules/world-atlas/land-10m.json')); sc, tr = topo['transform']['scale'], topo['transform']['translate']
arcs = []
for a in topo['arcs']:
    x = y = 0; pts = []
    for dx, dy in a: x += dx; y += dy; pts.append((x * sc[0] + tr[0], y * sc[1] + tr[1]))
    arcs.append(pts)
def ring(ids):
    out = []
    for i in ids: p = arcs[i] if i >= 0 else arcs[~i][::-1]; out += p if not out else p[1:]
    return out
px = lambda lo, la: ((lo - LO[0]) / (LO[1] - LO[0]) * W * 2, (LA[1] - la) / (LA[1] - LA[0]) * H * 2)
im = Image.new('L', (W * 2, H * 2), 0); dr = ImageDraw.Draw(im)
for g in topo['objects']['land']['geometries']:
    for p in (g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']]):
        rs = [ring(r) for r in p]; r0 = np.array(rs[0])
        if r0[:, 0].max() < LO[0] - 1 or r0[:, 0].min() > LO[1] + 1 or r0[:, 1].max() < LA[0] - 1 or r0[:, 1].min() > LA[1] + 1: continue
        for k, r in enumerate(rs): dr.polygon([px(lo, la) for lo, la in r], fill=0 if k else 255)
L = np.asarray(im.resize((W, H), Image.LANCZOS), np.float32) / 255
yy, xx = np.mgrid[0:H, 0:W]; lon = LO[0] + xx / W * (LO[1] - LO[0]); lat = LA[1] - yy / H * (LA[1] - LA[0])
r = np.random.default_rng(1); n = gaussian_filter(r.standard_normal((H, W)), 40) * 22 + gaussian_filter(r.standard_normal((H, W)), 12) * 4
sm = lambda a, b, x: np.clip((x - a) / (b - a), 0, 1) ** 2 * (3 - 2 * np.clip((x - a) / (b - a), 0, 1))
elev = sm(-149.78, -149.55, lon + n * .01) * (0.6 + n * .5) + sm(-149.62, -149.4, lon) * 1.2
gy, gx = np.gradient(gaussian_filter(elev, 6)); shade = np.clip(.85 - (gx * -1 + gy * 1) * 160, .45, 1.35)
img = np.zeros((H, W, 3), np.float32) + np.array([3, 12, 28]) / 255
land = (np.array([34, 48, 58]) / 255)[None, None] * shade[..., None] * (1 + sm(.6, 1.6, elev)[..., None] * .5)
img = img * (1 - L[..., None]) + land * L[..., None]
grid = (((lon * 20) % 1) < .012) | (((lat * 40) % 1) < .024)
img[grid] += np.array([12, 30, 48]) / 255
LM = L > .5; edge = binary_dilation(LM, iterations=2) & ~binary_erosion(LM, iterations=1); glow = gaussian_filter(edge.astype(np.float32), 4)
img += edge[..., None] * np.array([40, 150, 200]) / 255 * .8 + glow[..., None] * np.array([20, 90, 150]) / 255
Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(f'{D}/anc_map.jpg', quality=92)
json.dump({'W': wkm, 'H': hkm, 'LAT0': LAT0, 'LON0': LON0, 'LA': LA, 'LO': LO}, open(f'{D}/anc_map.json', 'w'))
print('harita', W, H, round(wkm, 1), 'x', round(hkm, 1), 'km')
