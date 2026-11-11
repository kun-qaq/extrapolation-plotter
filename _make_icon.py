# -*- coding: utf-8 -*-
"""Generate the sakura (cherry blossom) icon for the app window and the exe.

Run with the project venv:
    .venv\\Scripts\\python.exe _make_icon.py

Outputs sakura.png (512px preview) and sakura.ico (16..256 px, alpha).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
S = 1024                      # supersampled canvas
C = S / 2
R = S * 0.425                 # petal length in pixels
TAU = math.tau


def bezier(p0, p1, p2, p3, n=56):
    """Cubic Bezier sampling in local petal space (unit = R, +y = tip)."""
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]
        out.append((x, y))
    return out


def quad(p0, p1, p2, n=22):
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
        y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        out.append((x, y))
    return out


def petal_outline():
    """One sakura petal: narrow base, wide middle, tips with a V-shaped notch."""
    left = bezier((0.0, 0.04), (-0.22, 0.10), (-0.53, 0.42), (-0.335, 0.885))
    notch_l = quad((-0.335, 0.885), (-0.145, 0.775), (0.0, 0.705), n=18)[1:]
    notch_r = quad((0.0, 0.705), (0.145, 0.775), (0.335, 0.885), n=18)[1:]
    right = bezier((0.335, 0.885), (0.53, 0.42), (0.22, 0.10), (0.0, 0.04), n=56)[1:]
    return left + notch_l + notch_r + right


def rotate_to_screen(pt, angle):
    """Local (+y up) -> screen (+y down), rotated clockwise by angle."""
    x, y = pt
    ca, sa = math.cos(angle), math.sin(angle)
    return (C + R * (x * ca + y * sa), C + R * (x * sa - y * ca))


def radial_gradient():
    yy, xx = np.mgrid[0:S, 0:S]
    t = np.sqrt((xx - C) ** 2 + (yy - C) ** 2) / R
    t = np.clip(t, 0.0, 1.0)
    # centre: near-white blush -> middle: soft pink -> tip: saturated rose
    stops = [
        (0.00, (255, 249, 251)),
        (0.30, (255, 226, 238)),
        (0.62, (255, 186, 212)),
        (0.88, (250, 137, 180)),
        (1.00, (238, 108, 156)),
    ]
    arr = np.zeros((S, S, 3), dtype=np.float32)
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        w = np.clip((t - t0) / (t1 - t0), 0, 1)[..., None]
        seg = np.array(c0, dtype=np.float32) * (1 - w) + np.array(c1, dtype=np.float32) * w
        arr = np.where((t[..., None] >= t0) & (t[..., None] < t1), seg, arr)
    arr = np.where(t[..., None] >= 1.0, np.array(stops[-1][1], dtype=np.float32), arr)
    return Image.fromarray(arr.astype(np.uint8), "RGB").convert("RGBA")


def main():
    local = petal_outline()
    petals = []
    for k in range(5):
        a = k * TAU / 5 - 0.02      # tiny tilt so it does not look mechanical
        petals.append([rotate_to_screen(p, a) for p in local])

    # 1. petal mask
    mask = Image.new("L", (S, S), 0)
    dm = ImageDraw.Draw(mask)
    for pts in petals:
        dm.polygon(pts, fill=255)

    # 2. gradient clipped to petals
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(radial_gradient(), (0, 0), mask)

    # 3. edges + veins on their own layer so alpha composites correctly
    edge = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    de = ImageDraw.Draw(edge)
    for pts in petals:
        de.line(pts + [pts[0]], fill=(214, 78, 130, 165), width=5, joint="curve")
    for k in range(5):
        a = k * TAU / 5 - 0.02
        for off in (-0.14, 0.0, 0.14):
            p0 = rotate_to_screen((off * 0.35, 0.10), a)
            p1 = rotate_to_screen((off, 0.62), a)
            de.line([p0, p1], fill=(222, 110, 155, 70), width=4)
    img = Image.alpha_composite(img, edge)

    # 4. stamens: warm centre, radiating filaments, tiny anthers
    st = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ds = ImageDraw.Draw(st)
    cr = R * 0.115
    for i in range(14):
        a = i * TAU / 14 + 0.11
        x0, y0 = C + math.cos(a) * cr * 0.72, C + math.sin(a) * cr * 0.72
        x1, y1 = C + math.cos(a) * R * 0.245, C + math.sin(a) * R * 0.245
        ds.line([(x0, y0), (x1, y1)], fill=(243, 168, 92, 235), width=6)
        rr = R * 0.021
        ds.ellipse([x1 - rr, y1 - rr, x1 + rr, y1 + rr], fill=(255, 226, 138, 255))
    ds.ellipse([C - cr, C - cr, C + cr, C + cr], fill=(255, 214, 126, 255))
    ds.ellipse([C - cr * 0.62, C - cr * 0.62, C + cr * 0.62, C + cr * 0.62],
               fill=(255, 238, 176, 255))
    img = Image.alpha_composite(img, st)

    # 5. export
    png = ROOT / "sakura.png"
    img.resize((512, 512), Image.LANCZOS).save(png)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    ico = ROOT / "sakura.ico"
    img.resize((256, 256), Image.LANCZOS).save(
        ico, format="ICO", sizes=[(n, n) for n in sizes]
    )
    print("OK", png.name, ico.name, "sizes:", sizes, "bytes:", ico.stat().st_size)


if __name__ == "__main__":
    main()
