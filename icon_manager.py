from pathlib import Path

import bpy
import bpy.utils.previews
import gpu
import numpy as np
from bpy.app import background

from .declarations import Operators
from .model.constants import SketchCurveType

preview_icons = None
# Custom preview icons are blitted as-is (Blender never themes them), so the white
# icons vanish on light UI themes. Keep a dark-tinted copy and pick the set that
# contrasts the panel: Blender guarantees the widget text colour contrasts the
# panel background, so matching the icon lightness to the text colour works.
preview_icons_dark = None
_DARK_TINT = 0.15

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


# The constraint list draws by type, the tool grid by operator; the icons are
# stored per operator, so keep the reverse lookup next to the forward one.
_constraint_operators = {type: operator for operator, type in _operator_types.items()}

# Entity-type icons for the entities list, one per sketch_type with a dashed
# variant for construction geometry. Drawn in the selected-entity orange, which
# reads on light and dark themes alike (preview icons are blitted untinted).
_entity_types = {
    SketchCurveType.POINT: "POINT",
    SketchCurveType.LINE: "LINE",
    SketchCurveType.ARC: "ARC",
    SketchCurveType.CIRCLE: "CIRCLE",
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
    _build_dark_previews()
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

    for type in _entity_types.values():
        for construction in (False, True):
            name = _entity_icon_name_for(type, construction)
            icon_path = get_folder_path() / f"{name}.png"

            if not icon_path.exists():
                continue

            preview_icons.load(name, str(icon_path), 'IMAGE')


def _build_dark_previews():
    """Derive a dark-tinted copy of each icon for use on light UI themes."""
    global preview_icons_dark

    if preview_icons_dark or not preview_icons:
        return

    preview_icons_dark = bpy.utils.previews.new()
    for name in preview_icons.keys():
        light = preview_icons.get(name)
        if not light:
            continue
        w, h = light.icon_size
        if w == 0 or h == 0:
            continue
        pixels = np.asarray(light.icon_pixels_float, dtype=np.float32).reshape(-1, 4)
        pixels[:, :3] *= _DARK_TINT  # darken the shape, keep the alpha (edges)
        dark = preview_icons_dark.new(name)
        dark.icon_size = (w, h)
        dark.icon_pixels_float.foreach_set(pixels.ravel())


def unload_preview_icons():
    global preview_icons, preview_icons_dark

    if preview_icons_dark:
        preview_icons_dark.clear()
        bpy.utils.previews.remove(preview_icons_dark)
        preview_icons_dark = None

    if not preview_icons:
        return

    preview_icons.clear()
    bpy.utils.previews.remove(preview_icons)
    preview_icons = None


def _use_dark_icons():
    """True on a light theme -- decided by the widget text colour, which Blender
    keeps contrasting with the panel background (dark text => light panel)."""
    try:
        text = bpy.context.preferences.themes[0].user_interface.wcol_regular.text
        return (0.2126 * text[0] + 0.7152 * text[1] + 0.0722 * text[2]) < 0.5
    except Exception:
        return False


def _themed_icons():
    """The icon set that contrasts the current theme, or None when unloaded."""
    if preview_icons_dark and _use_dark_icons():
        return preview_icons_dark
    return preview_icons


def get_constraint_icon(operator: str):
    icons = _themed_icons()
    if not icons:
        return -1

    icon = icons.get(operator)

    if not icon:
        return -1

    return icon.icon_id


def _entity_icon_name_for(type: str, construction: bool) -> str:
    return f"ENTITY_{type}_CONSTRUCTION" if construction else f"ENTITY_{type}"


def get_entity_icon_name(curve_type: int, construction: bool = False) -> str:
    """Icon name for a sketch entity type, empty when the type has none."""
    type = _entity_types.get(curve_type)

    return _entity_icon_name_for(type, construction) if type else ""


def get_entity_icon(curve_type: int, construction: bool = False) -> int:
    """Preview icon id for a sketch entity type, 0 when there is none.

    0 is Blender's "no icon", so the result can be passed to icon_value as is.
    """
    name = get_entity_icon_name(curve_type, construction)
    icons = _themed_icons()

    if not icons or not name:
        return 0

    icon = icons.get(name)

    return icon.icon_id if icon else 0


def get_constraint_icon_name(type: str) -> str:
    """Icon name for a constraint type ("DISTANCE", ...), empty when it has none."""
    return type if type in _constraint_operators else ""


def get_constraint_icon_for_type(type: str) -> int:
    """Preview icon id for a constraint type, 0 when there is none.

    0 is Blender's "no icon", so the result can be passed to icon_value as is.
    """
    operator = _constraint_operators.get(type)

    if not operator:
        return 0

    return max(get_constraint_icon(operator), 0)
