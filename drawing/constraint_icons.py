"""Batched constraint-icon rendering.

The constraint gizmos used to draw their icon in each gizmo's ``draw()`` -- one
textured (sampler-bound) draw per constraint, which on the Vulkan backend
exhausted the descriptor pool (``VK_ERROR_OUT_OF_POOL_MEMORY``) once a sketch had
many constraints. Here every geometric constraint's icon is drawn in a *single*
batched call from one texture atlas, so there is exactly one sampler bind.

The gizmos keep ``test_select`` (clicking a constraint) and positioning; only the
icon rendering moved here. Positions are computed with the same formula the
gizmo uses so the icon stays under its clickable marker.
"""

import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import selection
from .. import icon_manager
from ..shaders import Shaders
from ..utilities.preferences import get_prefs
from ..utilities.view import get_2d_coords, get_scale_from_pos
from ..utilities.curve_data import get_curve_placement
from ..model.sketch_ref import get_active_sketch

# Matches gizmos.constraint.GIZMO_OFFSET (kept local to avoid importing the
# gizmo module into the drawing layer).
_GIZMO_OFFSET = Vector((1.0, 1.0))


def _iter_icons(context, sketch):
    """Yield (center_2d, size, constraint_type, color) for each geometric
    constraint icon, mirroring the gizmo group's placement + stacking."""
    from ..model.base_constraint import DimensionalConstraint
    from ..gizmos.utilities import get_constraint_color_type, get_color

    rv3d = context.region_data
    ui_scale = context.preferences.system.ui_scale
    size = get_prefs().gizmo_scale * ui_scale

    # Group constraints by the curve their marker sits on (for stacking offset).
    mapping = {}
    for c in sketch.constraints.all:
        if isinstance(c, DimensionalConstraint) or not c.visible:
            continue
        for cid in c.curve_id_placements():
            mapping.setdefault(cid, []).append(c)

    for cid, constrs in mapping.items():
        for i, c in enumerate(constrs):
            world = None
            if hasattr(c, "marker_position"):
                try:
                    world = c.marker_position(sketch)
                except Exception:
                    world = None
            if world is None:
                world = get_curve_placement(sketch, cid)
            if world is None:
                continue

            pos = get_2d_coords(context, world)
            if not pos:
                continue

            scale_3d = max(1, get_scale_from_pos(pos, rv3d) / 500)
            offset = Vector((size, 0.0)) * i * ui_scale
            center = pos + _GIZMO_OFFSET * size / scale_3d + offset

            is_highlight = c == selection.highlight_constraint
            color = get_color(get_constraint_color_type(c), is_highlight)
            yield center, size, c.type, color


def draw():
    """POST_PIXEL handler: draw every constraint icon in one atlas-batched call."""
    import bpy

    context = bpy.context
    if context.scene.sketcher.active_sketch_object is None:
        return
    sketch = get_active_sketch(context)
    if not sketch or context.region_data is None:
        return

    atlas, uvs = icon_manager.get_atlas()
    if atlas is None or not uvs:
        return

    verts, texco, colors = [], [], []
    for center, size, ctype, color in _iter_icons(context, sketch):
        uv = uvs.get(ctype)
        if uv is None:
            continue
        u0, v0, u1, v1 = uv
        h = size / 2.0
        cx, cy = center.x, center.y
        verts += [
            (cx - h, cy - h), (cx + h, cy - h), (cx + h, cy + h),
            (cx - h, cy - h), (cx + h, cy + h), (cx - h, cy + h),
        ]
        texco += [(u0, v0), (u1, v0), (u1, v1), (u0, v0), (u1, v1), (u0, v1)]
        colors += [tuple(color)] * 6

    if not verts:
        return

    shader = Shaders.atlas_icon_2d()
    gpu.state.blend_set("ALPHA")
    shader.bind()
    shader.uniform_sampler("image", atlas)
    batch = batch_for_shader(
        shader, "TRIS", {"pos": verts, "texCoord": texco, "color": colors}
    )
    batch.draw(shader)
    gpu.state.blend_set("NONE")
