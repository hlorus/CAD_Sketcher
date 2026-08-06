"""Shared viewport marker for the current geometry snap target.

Draws a small screen-space glyph at the point the cursor is snapped to, so it's
clear when locked onto external geometry -- the glyph shape encodes the snap type
(issue #577). One renderer is shared by both feedback paths:

- while a draw tool is *active but idle*, the preselection gizmo computes and
  draws the snap (``gizmos.preselection``),
- while a draw *operator* runs (which suspends gizmos), the operator draws it
  from a POST_PIXEL handler it owns (``operators.base_2d.Operator2d``).

Each owner just holds its own ``_snap`` (dict from ``get_blender_snap_info`` or
None); this module owns the drawing. It sets up a region-pixel matrix itself, so
the same code renders correctly from a POST_PIXEL handler or a gizmo ``draw()``.
"""

import gpu
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from ..shaders import Shaders
from ..utilities.preferences import get_prefs, get_scale

# Half-extent of the marker in pixels, before UI scaling.
_SIZE = 7.0


def _glyph(snap_type: str, center, s: float):
    """Line-segment endpoints (flat list, taken in pairs) for a snap type's
    marker.

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


def _region_pixel_projection(region):
    """Ortho projection mapping region pixels (origin bottom-left) to clip space.

    Lets the marker draw in screen space from any GPU context (POST_PIXEL already
    sets this up; a gizmo ``draw()`` does not).
    """
    w = max(region.width, 1)
    h = max(region.height, 1)
    return Matrix(
        (
            (2.0 / w, 0.0, 0.0, -1.0),
            (0.0, 2.0 / h, 0.0, -1.0),
            (0.0, 0.0, -1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )


def draw_snap_marker(owner, context):
    """Draw ``owner._snap``'s marker, if any. Safe from a POST_PIXEL handler or a
    gizmo ``draw()`` (sets up its own region-pixel matrix)."""
    snap = getattr(owner, "_snap", None)
    if not snap or "world_point" not in snap:
        return
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return
    p = location_3d_to_region_2d(region, rv3d, Vector(snap["world_point"]))
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
    with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
        gpu.matrix.load_identity()
        gpu.matrix.load_projection_matrix(_region_pixel_projection(region))
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
