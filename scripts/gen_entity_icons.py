"""Regenerate the entity-type icons in `resources/icons/ENTITY_*.png`.

The panel list shows one small icon per curve so the entity type (and whether it
is construction geometry) is readable at a glance. The shapes are simple enough
to draw programmatically, which keeps them consistent and easy to tweak.

Usage: python scripts/gen_entity_icons.py   (requires Pillow)
"""

from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw

# Rendered large and downsampled, since PIL has no anti-aliased drawing.
SS = 8
SIZE = 64
S = SIZE * SS

# Blender's active orange, the colour selected entities already use in the
# viewport. Readable on both light and dark themes, which matters because
# preview icons are blitted untinted.
COLOR: Tuple[int, int, int, int] = (255, 152, 66, 255)

STROKE = 6 * SS  # line weight of the drawn shapes
MARGIN = 12 * SS
DASH = 9 * SS  # dash length used for construction variants
GAP = 7 * SS


def _new() -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _save(img: Image.Image, name: str, folder: Path) -> None:
    img.resize((SIZE, SIZE), Image.LANCZOS).save(folder / f"{name}.png")


def _dashed_polyline(draw: ImageDraw.ImageDraw, pts, dash: int, gap: int) -> None:
    """Stroke a polyline as dashes of `dash` px separated by `gap` px."""
    carry = 0.0  # distance already walked inside the current dash/gap cycle
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        if length == 0:
            continue
        walked = 0.0
        while walked < length:
            period = dash + gap
            pos = (carry + walked) % period
            if pos < dash:
                step = min(dash - pos, length - walked)
                t0, t1 = walked / length, (walked + step) / length
                draw.line(
                    [
                        (x0 + (x1 - x0) * t0, y0 + (y1 - y0) * t0),
                        (x0 + (x1 - x0) * t1, y0 + (y1 - y0) * t1),
                    ],
                    fill=COLOR,
                    width=STROKE,
                )
            else:
                step = min(period - pos, length - walked)
            walked += step
        carry = (carry + length) % (dash + gap)


def _arc_points(box, start_deg: float, end_deg: float, steps: int = 96):
    from math import cos, radians, sin

    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    return [
        (
            cx + rx * cos(radians(start_deg + (end_deg - start_deg) * i / steps)),
            cy + ry * sin(radians(start_deg + (end_deg - start_deg) * i / steps)),
        )
        for i in range(steps + 1)
    ]


def draw_point(construction: bool) -> Image.Image:
    img, draw = _new()
    r = 13 * SS
    c = S / 2
    box = [c - r, c - r, c + r, c + r]
    if construction:
        draw.ellipse(box, outline=COLOR, width=int(STROKE * 0.8))
    else:
        draw.ellipse(box, fill=COLOR)
    return img


def draw_line(construction: bool) -> Image.Image:
    img, draw = _new()
    pts = [(MARGIN, S - MARGIN), (S - MARGIN, MARGIN)]
    if construction:
        _dashed_polyline(draw, pts, DASH, GAP)
    else:
        draw.line(pts, fill=COLOR, width=STROKE)
    return img


def draw_arc(construction: bool) -> Image.Image:
    img, draw = _new()
    # Upper half of a tall ellipse: a shallow "cap" that reads as an arc at 16 px.
    box = [MARGIN, 0.28 * S, S - MARGIN, 1.16 * S]
    if construction:
        _dashed_polyline(draw, _arc_points(box, 180, 360), DASH, GAP)
    else:
        draw.arc(box, 180, 360, fill=COLOR, width=STROKE)
    return img


def draw_circle(construction: bool) -> Image.Image:
    img, draw = _new()
    box = [MARGIN, MARGIN, S - MARGIN, S - MARGIN]
    if construction:
        _dashed_polyline(draw, _arc_points(box, 0, 360), DASH, GAP)
    else:
        draw.ellipse(box, outline=COLOR, width=STROKE)
    return img


def main() -> None:
    folder = Path(__file__).resolve().parent.parent / "resources" / "icons"
    builders = {
        "POINT": draw_point,
        "LINE": draw_line,
        "ARC": draw_arc,
        "CIRCLE": draw_circle,
    }
    for name, build in builders.items():
        _save(build(False), f"ENTITY_{name}", folder)
        _save(build(True), f"ENTITY_{name}_CONSTRUCTION", folder)
    print(f"wrote {2 * len(builders)} icons to {folder}")


if __name__ == "__main__":
    main()
