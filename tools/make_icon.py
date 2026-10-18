#!/usr/bin/env python3
"""Generuje ikony integracji (kropla wody z wykresem godzinowym) do custom_components/.../brand/.

Wymaga: pip install pillow
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 2048  # rysujemy w dużej rozdzielczości i zmniejszamy - gładkie krawędzie
TOP = (79, 195, 247)  # #4FC3F7
BOTTOM = (2, 119, 189)  # #0277BD
OUT = Path(__file__).resolve().parent.parent / "custom_components" / "licznik_wody_wroclaw" / "brand"


def drop_polygon(cx: float, cy: float, r: float, tip_dist: float) -> list[tuple[float, float]]:
    """Kropla: koło o środku (cx, cy) i szpic tip_dist nad środkiem, połączone stycznymi."""
    theta = math.asin(r / tip_dist)
    # punkty styczności leżą pod kątem (90° - theta) od pionu w górę
    start = -math.pi / 2 + (math.pi / 2 - theta)
    end = -math.pi / 2 - (math.pi / 2 - theta) + 2 * math.pi
    points = [(cx, cy - tip_dist)]
    steps = 400
    for i in range(steps + 1):
        a = start + (end - start) * i / steps
        points.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return points


def render() -> Image.Image:
    r = SIZE * 0.36
    cx, cy = SIZE / 2, SIZE * 0.615
    tip = r * 1.62

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).polygon(drop_polygon(cx, cy, r, tip), fill=255)

    gradient = Image.new("RGBA", (SIZE, SIZE))
    top_y, bottom_y = cy - tip, cy + r
    gd = ImageDraw.Draw(gradient)
    for y in range(SIZE):
        t = min(max((y - top_y) / (bottom_y - top_y), 0), 1)
        gd.line([(0, y), (SIZE, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)) + (255,))

    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    img.paste(gradient, (0, 0), mask)

    # rysujemy na osobnej warstwie i nakładamy, żeby półprzezroczystość nie "przebijała" kropli
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # słupki wykresu godzinowego na linii bazowej
    heights = [0.28, 0.45, 0.85, 0.62, 0.36, 0.55]
    bar_w, gap = SIZE * 0.052, SIZE * 0.026
    total_w = len(heights) * bar_w + (len(heights) - 1) * gap
    base_y = cy + r * 0.50
    max_h = r * 0.95
    x = cx - total_w / 2
    for h in heights:
        draw.rounded_rectangle(
            [x, base_y - max_h * h, x + bar_w, base_y],
            radius=bar_w * 0.3,
            fill=(255, 255, 255, 255),
        )
        x += bar_w + gap
    line_h = SIZE * 0.018
    draw.rounded_rectangle(
        [cx - total_w / 2 - gap, base_y + gap * 0.6, cx + total_w / 2 + gap, base_y + gap * 0.6 + line_h],
        radius=line_h / 2,
        fill=(255, 255, 255, 255),
    )

    # odblask: łuk wzdłuż lewej krawędzi kropli
    rr = r * 0.78
    draw.arc([cx - rr, cy - rr, cx + rr, cy + rr], start=192, end=232, fill=(255, 255, 255, 120), width=round(SIZE * 0.03))

    img = Image.alpha_composite(img, overlay)
    img.putalpha(Image.composite(img.getchannel("A"), mask, mask))  # nic poza kroplą
    return img.crop(img.getbbox())


def save(img: Image.Image, name: str, size: int) -> None:
    # kwadrat z przezroczystym tłem, kropla wyśrodkowana
    w, h = img.size
    side = max(w, h)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(img, ((side - w) // 2, (side - h) // 2))
    square.resize((size, size), Image.LANCZOS).save(OUT / name, optimize=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    icon = render()
    save(icon, "icon.png", 256)
    save(icon, "icon@2x.png", 512)
    print(f"Zapisano ikony w {OUT}")
