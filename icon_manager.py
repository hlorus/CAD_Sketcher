from pathlib import Path

import gpu
import bpy
import bpy.utils.previews
import numpy as np
from bpy.app import background

from .declarations import Operators

preview_icons = None

# Single texture atlas holding every constraint icon, so all icons render in one
# batched draw (one sampler bind) instead of one textured draw per constraint.
_atlas = None            # GPUTexture
_atlas_uvs = {}          # type -> (u0, v0, u1, v1)
_ATLAS_CELL = 128        # each icon is resized into a CELL x CELL cell
_operator_types = {
    Operators.AddDistance: "DISTANCE",
    Operators.AddDiameter: "DIAMETER",
    Operators.AddAngle: "ANGLE",
    Operators.AddCoincident: "COINCIDENT",
    Operators.AddEqual: "EQUAL",
    Operators.AddVertical: "VERTICAL",
    Operators.AddHorizontal: "HORIZONTAL",
    Operators.AddParallel: "PARALLEL",
    Operators.AddPerpendicular: "PERPENDICULAR",
    Operators.AddTangent: "TANGENT",
    Operators.AddMidPoint: "MIDPOINT",
    Operators.AddRatio: "RATIO",
    Operators.AddSymmetry: "SYMMETRY",
}


def get_folder_path():
    return Path(__file__).parent / "resources" / "icons"


def get_icon(name: str):
    return str(get_folder_path() / name)


def _resize_nearest(pixels, w, h, cell):
    """Nearest-neighbour resize an (h, w, 4) icon to (cell, cell, 4)."""
    img = np.asarray(pixels, dtype=np.float32).reshape(h, w, 4)
    ys = (np.arange(cell) * h // cell).clip(0, h - 1)
    xs = (np.arange(cell) * w // cell).clip(0, w - 1)
    return img[ys][:, xs]


def _build_atlas():
    """Composite every icon into one horizontal-strip texture + record UVs."""
    global _atlas, _atlas_uvs

    cells = []
    valid_types = []
    for operator, type in _operator_types.items():
        icon = preview_icons.get(operator)
        if not icon:
            continue
        w, h = icon.icon_size
        if w == 0 or h == 0:
            continue
        cells.append(_resize_nearest(icon.icon_pixels_float, w, h, _ATLAS_CELL))
        valid_types.append(type)

    if not cells:
        return

    # Horizontal strip: (CELL, CELL * n, 4). Rows preserved so the atlas matches
    # the per-icon draw's pixel order.
    strip = np.concatenate(cells, axis=1)
    n = len(cells)
    _atlas_uvs = {
        type: (i / n, 0.0, (i + 1) / n, 1.0) for i, type in enumerate(valid_types)
    }

    height, width = strip.shape[0], strip.shape[1]
    buffer = gpu.types.Buffer("FLOAT", width * height * 4, strip.ravel().tolist())
    _atlas = gpu.types.GPUTexture(size=(width, height), data=buffer)


def get_atlas():
    """(atlas_texture, {type: uv_rect}) or (None, {}) when unavailable."""
    return _atlas, _atlas_uvs


def load():
    global preview_icons

    if preview_icons:
        return

    if background:
        return

    load_preview_icons()
    _build_atlas()


def unload():
    global _atlas, _atlas_uvs
    unload_preview_icons()
    _atlas = None
    _atlas_uvs = {}


def load_preview_icons():
    global preview_icons

    if preview_icons:
        return

    preview_icons = bpy.utils.previews.new()

    for operator, type in _operator_types.items():
        icon_path = get_folder_path() / f"{type}.png"

        if not icon_path.exists():
            continue

        preview_icons.load(operator, str(icon_path), 'IMAGE')


def unload_preview_icons():
    global preview_icons

    if not preview_icons:
        return

    preview_icons.clear()
    bpy.utils.previews.remove(preview_icons)
    preview_icons = None


def get_constraint_icon(operator: str):
    if not preview_icons:
        return -1

    icon = preview_icons.get(operator)

    if not icon:
        return -1

    return icon.icon_id
