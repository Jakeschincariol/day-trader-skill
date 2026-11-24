# Prosedürel dokular: Dünya (Natural Earth kara verisi), bulut, stilize harita, deniz tabanı.
import json, sys, numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import gaussian_filter, binary_dilation, binary_erosion
D = sys.path[0]; R = np.random.default_rng(7)
topo = json.load(open(f"{D}/../node_modules/world-atlas/land-50m.json"))
sc, tr = topo["transform"]["scale"], topo["transform"]["translate"]
arcs = []
for a in topo["arcs"]:
    x = y = 0; pts = []
    for dx, dy in a: x += dx; y += dy; pts.append((x * sc[0] + tr[0], y * sc[1] + tr[1]))
    arcs.append(pts)
def ring(ids):
    out = []
    for i in ids:
        p = arcs[i] if i >= 0 else arcs[~i][::-1]
        out += p if not out else p[1:]
    return out
polys = []
for g in topo["objects"]["land"]["geometries"]:
    ps = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
    for p in ps: polys.append([ring(r) for r in p])
def mask(W, H):
    S = 2; im = Image.new("L", (W * S, H * S), 0); dr = ImageDraw.Draw(im)
    for p in polys:
        for k, r in enumerate(p):
            r = np.array(r)
            if r[:, 1].min() < -85: offs = [0]
            else:
                d = np.diff(r[:, 0]); r[1:, 0] -= 360 * np.cumsum(np.round(d / 360)); offs = [-360, 0, 360]
            for o in offs:
                dr.polygon([((lo + o + 180) / 360 * W * S, (90 - la) / 180 * H * S) for lo, la in r], fill=0 if k else 255)
    return np.asarray(im.resize((W, H), Image.LANCZOS), np.float32) / 255
def vnoise3(p, seed):
    perm = np.random.default_rng(seed).permutation(256); perm = np.concatenate([perm, perm])
    i = np.floor(p).astype(np.int64); f = p - i; u = f * f * (3 - 2 * f); i &= 255
    def h(dx, dy, dz): return perm[perm[perm[i[..., 0] + dx] + i[..., 1] + dy] + i[..., 2] + dz] / 255.0
    l = lambda a, b, t: a + (b - a) * t
    return l(l(l(h(0,0,0), h(1,0,0), u[...,0]), l(h(0,1,0), h(1,1,0), u[...,0]), u[...,1]),
             l(l(h(0,0,1), h(1,0,1), u[...,0]), l(h(0,1,1), h(1,1,1), u[...,0]), u[...,1]), u[...,2])
def fbm(p, oct, seed, g=0.5):
    s, a, n = 0, 1, 0
    for o in range(oct): s += a * vnoise3(p * 2 ** o + o * 17.3, seed + o); n += a; a *= g
    return s / n
def sphere(W, H):
    lon = (np.arange(W) + .5) / W * 2 * np.pi - np.pi; lat = np.pi / 2 - (np.arange(H) + .5) / H * np.pi
    LO, LA = np.meshgrid(lon, lat)
    return np.stack([np.cos(LA) * np.cos(LO), np.sin(LA), np.cos(LA) * np.sin(LO)], -1), np.degrees(LO), np.degrees(LA)
sm = lambda a, b, x: np.clip((x - a) / (b - a), 0, 1) ** 2 * (3 - 2 * np.clip((x - a) / (b - a), 0, 1))
# ---------- Dünya gündüz dokusu ----------
W, H = 4096, 2048
L = mask(W, H); P, LO, LA = sphere(W, H)
n1 = fbm(P * 3, 6, 1); n2 = fbm(P * 9, 5, 2); ridge = 1 - np.abs(fbm(P * 6, 6, 3) * 2 - 1)
box = lambda la0, la1, lo0, lo1, e=4: sm(la0 - e, la0 + e, LA) * sm(-la1 - e, -la1 + e, -LA) * sm(lo0 - e, lo0 + e, LO) * sm(-lo1 - e, -lo1 + e, -LO)
des = np.maximum.reduce([box(15, 31, -15, 32, 7), box(15, 31, 37, 57, 7), box(26, 35, 52, 68, 7) * .7, box(38, 46, 88, 110, 8) * .75, box(-29, -21, 120, 140, 8),
                         box(-26, -20, 14, 22, 6) * .7, box(28, 36, -116, -106, 6) * .7, box(39, 45, 54, 66, 7) * .5])
des = sm(0.3, 0.8, des * (0.45 + 0.9 * n1) + (n2 - 0.5) * 0.35)
ice = np.clip(sm(-62, -66, LA) + box(60, 84, -72, -14, 7) * sm(0.3, 0.5, n1 + 0.2) + sm(74, 82, LA) * sm(0.35, 0.6, n1 + 0.1), 0, 1)
absl = np.abs(LA)
c_rain, c_temp, c_sav, c_des, c_tun, c_ice = [np.array(c, np.float32) / 255 for c in [(24,50,20),(50,70,34),(104,98,56),(196,164,112),(92,86,64),(236,240,246)]]
veg = c_rain[None, None] * sm(16, 6, absl)[..., None] + c_temp[None, None] * (1 - sm(16, 6, absl))[..., None]
veg = veg * (1 - sm(52, 62, absl))[..., None] + c_tun * sm(52, 62, absl)[..., None]
sav = sm(0.45, 0.7, n1) * sm(6, 14, absl) * sm(40, 28, absl)
land = veg * (1 - sav[..., None]) + c_sav * sav[..., None]
land = land * (1 - des[..., None]) + c_des * des[..., None]
land *= (0.78 + 0.45 * n2)[..., None]
land *= (0.82 + 0.35 * ridge ** 2)[..., None]
land = land * (1 - ice[..., None]) + c_ice * (0.9 + 0.1 * n2[..., None]) * ice[..., None]
sh1 = gaussian_filter(L, 4); sh2 = gaussian_filter(L, 22)
deep, mid, shal = [np.array(c, np.float32) / 255 for c in [(6,20,46),(10,40,80),(26,92,118)]]
t1 = np.clip(sh2 * 2.2, 0, 1); t2 = np.clip(sh1 * 2.5, 0, 1) ** 1.5
oc = deep + (mid - deep) * t1[..., None]; oc = oc + (shal - oc) * t2[..., None] * 0.8
oc *= (0.92 + 0.16 * n2[..., None])
img = oc * (1 - L[..., None]) + land * L[..., None]
Image.fromarray((np.clip(img, 0, 1) ** (1 / 1.05) * 255).astype(np.uint8)).save(f"{D}/earth_day.jpg", quality=92)
Image.fromarray(((1 - L) * 255).astype(np.uint8)).resize((2048, 1024)).save(f"{D}/earth_spec.png")
# ---------- Bulutlar ----------
W2, H2 = 2048, 1024; P2, _, LA2 = sphere(W2, H2)
warp = np.stack([fbm(P2 * 2 + 5, 4, 11), fbm(P2 * 2 + 9, 4, 12), fbm(P2 * 2 + 13, 4, 13)], -1)
c = fbm(P2 * 2.6 + warp * 1.6, 7, 21) * 0.75 + fbm(P2 * 11, 4, 22) * 0.25
a2 = np.abs(LA2)
bias = 0.07 * np.exp(-(LA2 / 8) ** 2) - 0.07 * np.exp(-((a2 - 24) / 9) ** 2) + 0.08 * np.exp(-((a2 - 55) / 12) ** 2) - 0.05 * sm(70, 88, a2)
cl = sm(0.50, 0.74, c + bias)
Image.fromarray((cl * 255).astype(np.uint8)).save(f"{D}/earth_clouds.png")
# ---------- Stilize harita (nokta matrisi) ----------
LM = L > 0.5
img = np.zeros((H, W, 3), np.float32) + np.array([3, 9, 20], np.float32) / 255
yy, xx = np.mgrid[0:H, 0:W]
grid = ((xx % (W // 24)) < 2) | ((yy % (H // 12)) < 2)
img[grid] += np.array([8, 20, 34]) / 255
img[LM] = np.array([9, 26, 44]) / 255
st = 9; cy, cx = (yy % st) - st / 2 + .5, (xx % st) - st / 2 + .5
cen = L[(yy // st) * st + st // 2, np.minimum((xx // st) * st + st // 2, W - 1)] > 0.5
dot = np.clip(2.9 - np.sqrt(cx ** 2 + cy ** 2), 0, 1) * cen
img += dot[..., None] * np.array([46, 128, 168], np.float32) / 255
edge = binary_dilation(LM, iterations=2) & ~binary_erosion(LM, iterations=1)
glow = gaussian_filter(edge.astype(np.float32), 3)
img += edge[..., None] * np.array([40, 150, 190]) / 255 * 0.9 + glow[..., None] * np.array([20, 90, 140]) / 255
Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(f"{D}/map_style.jpg", quality=93)
# ---------- Deniz tabanı (döşenebilir) ----------
N = 1024
def fftn(beta, seed):
    f = np.fft.fftfreq(N); k = np.sqrt(f[None] ** 2 + f[:, None] ** 2); k[0, 0] = 1
    z = np.fft.ifft2(np.fft.fft2(np.random.default_rng(seed).standard_normal((N, N))) / k ** beta).real
    return (z - z.min()) / (z.max() - z.min())
h = fftn(1.6, 31); h2 = fftn(1.1, 32); h3 = fftn(0.6, 33)
y, x = np.mgrid[0:N, 0:N] / N
rip = 0.5 + 0.5 * np.sin(2 * np.pi * (14 * x + 5 * y) + 6 * (h - 0.5) * 2 * np.pi * 0.35)
hh = h * 0.6 + rip * 0.12 * (0.4 + h2) + h3 * 0.08
gy, gx = np.roll(hh, -1, 0) - np.roll(hh, 1, 0), np.roll(hh, -1, 1) - np.roll(hh, 1, 1)
nrm = np.stack([-gx * 40, -gy * 40, np.ones_like(gx)], -1); nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
Image.fromarray(((nrm * 0.5 + 0.5) * 255).astype(np.uint8)).save(f"{D}/seabed_normal.png")
alb = np.array([0.55, 0.52, 0.45]) * (0.72 + 0.35 * h2[..., None] + 0.12 * h3[..., None])
spk = (h3 > 0.78)[..., None] * -0.15
Image.fromarray((np.clip(alb + spk, 0, 1) * 255).astype(np.uint8)).save(f"{D}/seabed_albedo.jpg", quality=92)
print("ok")
