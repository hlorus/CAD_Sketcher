"""Viewport marker for the current geometry snap target while drawing.

Draws a small screen-space glyph at the point the cursor is snapped to, so the
user gets clear feedback when locked onto external geometry — with the glyph
shape encoding the snap type (issue #577). Rendered by a POST_PIXEL draw handler
the placement operator owns for the lifetime of its modal (see
``operators.base_2d.Operator2d``), so nothing lingers past the draw.
"""

import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from ..shaders import Shaders
from ..utilities.preferences import get_prefs, get_scale
from ..utilities.view import get_2d_coords

# Half-extent of the marker in pixels, before UI scaling.
_SIZE = 7.0


def _glyph(snap_type: str, center, s: float):
    """Line-segment endpoints (flat list of points, taken in pairs) for a snap
    type's marker.

    Square = vertex/endpoint, down-triangle = a midpoint (edge or face centre),
    X = a point on an edge. Anything else falls back to the square.
    """
    x, y = center
    if snap_type in ("EDGE_MIDPOINT", "FACE_MIDPOINT"):
        a, b, c = (x, y + s), (x - s, y - s), (x + s, y - s)
        return [a, b, b, c, c, a]
    if snap_type == "EDGE":
        return [(x - s, y - s), (x + s, y + s), (x - s, y + s), (x + s, y - s)]
    a, b, c, d = (x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)
    return [a, b, b, c, c, d, d, a]


def draw_snap_marker(operator, context):
    """POST_PIXEL callback: mark the operator's current snap point, if any."""
    snap = getattr(operator, "_snap", None)
    if not snap or "world_point" not in snap:
        return
    if context.region is None or context.region_data is None:
        return
    p = get_2d_coords(context, Vector(snap["world_point"]))
    if p is None:
        return

    coords = _glyph(snap.get("type", ""), (p.x, p.y), _SIZE * get_scale())
    col = (*get_prefs().theme_settings.entity.highlight[:3], 1.0)

    try:
        is_vk_metal = gpu.platform.backend_type_get() in ("VULKAN", "METAL")
    except Exception:
        is_vk_metal = False
    shader = (
        gpu.shader.from_builtin("UNIFORM_COLOR")
        if is_vk_metal
        else Shaders.uniform_color_line_2d()
    )

    gpu.state.blend_set("ALPHA")
    gpu.state.line_width_set(2.0)
    shader.bind()
    shader.uniform_float("color", col)
    if not is_vk_metal:
        try:
            shader.uniform_float("lineWidth", 2.0)
        except Exception:
            pass
    batch_for_shader(shader, "LINES", {"pos": coords}).draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")
