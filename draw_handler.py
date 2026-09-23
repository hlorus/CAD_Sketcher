import logging

import blf
import bpy
import gpu
from bpy.types import Context
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from . import global_data
from .shaders import Shaders
from .utilities import preferences
from .utilities.preferences import get_prefs

logger = logging.getLogger(__name__)

# Blender's built-in default font.
_FONT_ID = 0
# Label height as a fraction of the origin plane's drawn side length.
_LABEL_HEIGHT_FACTOR = 0.22
# A plane that is not a base plane is a lesser thing to pick, so its name is
# drawn smaller.
_NAME_HEIGHT_FACTOR = 0.10
# Space between those lines, as a fraction of one line's height.
_LABEL_LINE_GAP = 0.2
# Inset of the label from the plane's outer corner, as a fraction of its side.
_LABEL_CORNER_MARGIN = 0.08


def _draw_curves_overlay(context: Context):
    """Draw native curve geometry as an overlay (cached, batched drawing system)."""
    from .drawing import overlay

    overlay.draw(context)


def draw_cb():
    from .drawing import frame_cache

    # First callback of each 3D view redraw: reset the per-redraw memo that the
    # constraint gizmos and icons drawn later in this redraw read from.
    frame_cache.begin_frame()
    context = bpy.context
    _draw_curves_overlay(context)


# Bounding-box edges (Blender's 8-corner order).
_BBOX_EDGES = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 0),
    (4, 5),
    (5, 6),
    (6, 7),
    (7, 4),
    (0, 4),
    (1, 5),
    (2, 6),
    (3, 7),
)


def _draw_lines_hover(lines, col, scale, width=2):
    if not lines:
        return
    shader = Shaders.uniform_color_3d()
    shader.bind()
    gpu.state.blend_set("ALPHA")
    gpu.state.line_width_set(width * scale)
    shader.uniform_float("color", col)
    batch = batch_for_shader(shader, "LINES", {"pos": lines})
    batch.draw(shader)
    gpu.shader.unbind()
    gpu.state.line_width_set(1)
    gpu.state.blend_set("NONE")


def _draw_bbox_hover(ob, col, scale):
    """Highlight an object by its (modifier-aware) bounding box."""
    mw = ob.matrix_world
    corners = [mw @ Vector(c) for c in ob.bound_box]
    lines = []
    for a, b in _BBOX_EDGES:
        lines.append(corners[a][:])
        lines.append(corners[b][:])
    _draw_lines_hover(lines, col, scale, width=2)


def _draw_edge_hover(context, ob, index, col, scale):
    # Curves have no evaluated mesh edges; the index is a control-point index
    # (segment = points [i, i+1]), resolved from the original curve data.
    if ob.type in {"CURVE", "CURVES"}:
        cd = ob.original.data
        pts = getattr(cd, "points", None)
        if pts is None or index + 1 >= len(pts):
            return
        mw = ob.matrix_world
        lines = [
            (mw @ Vector(pts[index].position))[:],
            (mw @ Vector(pts[index + 1].position))[:],
        ]
        _draw_lines_hover(lines, col, scale, width=3)
        return

    eval_ob = ob.evaluated_get(context.evaluated_depsgraph_get())
    me = eval_ob.data
    if not hasattr(me, "edges") or index >= len(me.edges):
        return
    mw = eval_ob.matrix_world
    a, b = me.edges[index].vertices
    lines = [(mw @ me.vertices[a].co)[:], (mw @ me.vertices[b].co)[:]]
    _draw_lines_hover(lines, col, scale, width=3)


def _draw_face_hover(context, ob, index, col, scale):
    eval_ob = ob.evaluated_get(context.evaluated_depsgraph_get())
    me = eval_ob.data
    if not hasattr(me, "polygons") or index >= len(me.polygons):
        return
    mw = eval_ob.matrix_world
    verts = list(me.polygons[index].vertices)
    lines = []
    for i in range(len(verts)):
        lines.append((mw @ me.vertices[verts[i]].co)[:])
        lines.append((mw @ me.vertices[verts[(i + 1) % len(verts)]].co)[:])
    _draw_lines_hover(lines, col, scale, width=3)


def _draw_vertex_hover(context, ob, index, col, scale):
    eval_ob = ob.evaluated_get(context.evaluated_depsgraph_get())
    me = eval_ob.data
    if not hasattr(me, "vertices") or index >= len(me.vertices):
        return
    pos = (eval_ob.matrix_world @ me.vertices[index].co)[:]
    shader = Shaders.point_color_3d()
    shader.bind()
    gpu.state.blend_set("ALPHA")
    gpu.state.point_size_set(8 * scale)
    shader.uniform_float("color", col)
    batch = batch_for_shader(shader, "POINTS", {"pos": (pos,)})
    batch.draw(shader)
    gpu.shader.unbind()
    gpu.state.point_size_set(1)
    gpu.state.blend_set("NONE")


def _draw_curve_element_hover(ob, key, col, scale):
    """Highlight one hovered curve element: its segments and/or its point.

    A line highlights its segment, an arc/circle its tessellated segments, a
    point its position -- so the whole element under the cursor lights up.
    """
    from .drawing.reference_pick import element_geometry

    points, segments = element_geometry(ob, key)
    if segments:
        lines = []
        for a, b in segments:
            lines += [a, b]
        _draw_lines_hover(lines, col, scale, width=3)
    if points:
        shader = Shaders.point_color_3d()
        shader.bind()
        gpu.state.blend_set("ALPHA")
        gpu.state.point_size_set(8 * scale)
        shader.uniform_float("color", col)
        batch = batch_for_shader(shader, "POINTS", {"pos": points})
        batch.draw(shader)
        gpu.shader.unbind()
        gpu.state.point_size_set(1)
        gpu.state.blend_set("NONE")


def draw_hover_element():
    """POST_VIEW: highlight the hovered element per its type.

    OBJECT -> bounding box; EDGE/FACE/VERTEX -> the element on the evaluated
    mesh. The element type follows the active state's accepted pick types.
    """
    from .declarations import GizmoGroups

    context = bpy.context

    # While a hover tool is active, or any pick is in progress (the redo-panel
    # eyedropper re-pick publishes hover_types without switching tools).
    # Otherwise clear stale hover so the highlight doesn't linger after switching.
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    tool_active = tool is not None and tool.widget == GizmoGroups.ObjectHover.value
    if not tool_active and global_data.hover_types is None:
        global_data.hover_element = None
        return

    element = global_data.hover_element
    if not element or context.region is None:
        return

    kind, name, index = element
    ob = bpy.data.objects.get(name)
    if ob is None:
        return

    scale = preferences.get_scale()
    col = (*get_prefs().theme_settings.entity.highlight[:3], 1.0)

    if kind == "OBJECT":
        _draw_bbox_hover(ob, col, scale)
    elif kind == "EDGE":
        _draw_edge_hover(context, ob, index, col, scale)
    elif kind == "FACE":
        _draw_face_hover(context, ob, index, col, scale)
    elif kind == "VERTEX":
        _draw_vertex_hover(context, ob, index, col, scale)
    elif kind == "CURVE_ELEM":
        # ``index`` is the element key (a curve_id or index tuple).
        _draw_curve_element_hover(ob, index, col, scale)


def _text_block(lines, size):
    """Measure ``lines`` at ``size``: per-line dims, total width and height."""
    dims = []
    for line in lines:
        blf.size(_FONT_ID, size)
        dims.append(blf.dimensions(_FONT_ID, line))
    line_h = max(h for _w, h in dims)
    gap = line_h * _LABEL_LINE_GAP
    width = max(w for w, _h in dims)
    height = sum(h for _w, h in dims) + gap * (len(dims) - 1)
    return dims, gap, width, height


def _draw_text_block(plane_mat, lines, dims, gap, size, scale, sx, x, y, centered):
    """Draw a measured block in plane space, anchored at its bottom-left.

    ``x``/``y`` are that corner in the plane's own coordinates, ``sx`` mirrors
    the glyphs when the plane is seen from behind, and ``centered`` centres each
    line on ``x`` instead of starting there.
    """
    width = max(w for w, _h in dims)
    height = sum(h for _w, h in dims) + gap * (len(dims) - 1)
    # Mirroring flips the direction text grows in, so the anchor moves with it.
    origin_x = x - (width * scale / 2.0 if centered else 0.0) * (
        1.0 if sx > 0 else -1.0
    )
    mat = (
        plane_mat
        @ Matrix.Translation((origin_x, y, 0.0))
        @ Matrix.Scale(scale, 4)
        @ Matrix.Diagonal((sx, 1.0, 1.0, 1.0))
    )
    with gpu.matrix.push_pop():
        gpu.matrix.multiply_matrix(mat)
        blf.size(_FONT_ID, size)
        cursor = height
        for line, (_line_w, line_h) in zip(lines, dims):
            cursor -= line_h
            blf.position(_FONT_ID, 0.0, cursor, 0.0)
            blf.draw(_FONT_ID, line)
            cursor -= gap


def draw_origin_labels():
    """POST_VIEW: name each workplane, lying in its plane.

    Drawn in the 3D pass so ``blf`` is transformed by the plane's matrix and the
    text tilts with it in perspective. Visibility mirrors the workplane gizmo:
    only while the Add Sketch tool is active, and ``iter_wp_empties`` already
    respects ``show_origin``.

    A base plane says the axis, large and in the middle where the eye lands, and
    adds whose plane it is in the outer corner while it is hovered -- the planes
    cross on screen, so naming them all at once puts one plane's name over
    another's axis. A plane that has only a name shows it always, since that is
    all it has to say. The glyph raster is
    sized to the on-screen height so it stays crisp instead of being magnified,
    the text is mirrored when seen from behind so it never reads backwards, and
    it skips the depth test so it stays legible over geometry.
    """
    from .declarations import GizmoGroups
    from .drawing import selection
    from .utilities.workplane import (
        is_base_plane,
        iter_wp_empties,
        label_lines,
        workplane_color,
        workplane_label,
        wp_plane_bounds,
    )

    context = bpy.context
    region, rv3d = context.region, context.region_data
    if region is None or rv3d is None:
        return

    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    if tool is None or tool.widget != GizmoGroups.Workplane.value:
        return

    # Direction the view looks along, in world space, to detect back-facing text.
    view_forward = rv3d.view_rotation @ Vector((0.0, 0.0, -1.0))

    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")

    for wp_obj, pick_id in iter_wp_empties(context):
        label = workplane_label(wp_obj, pick_id)
        if not label:
            continue

        min_x, min_y, max_x, max_y = wp_plane_bounds(context, pick_id)
        side = max_x - min_x
        base = is_base_plane(pick_id)
        lines = label_lines(label)
        # On a base plane the last line is the axis; the rest name the owner.
        axis_line = lines[-1] if base else None
        name_lines = lines[:-1] if base else lines

        plane_mat = wp_obj.matrix_world
        up_world = plane_mat.to_3x3().col[1].normalized()
        center = plane_mat @ Vector(((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, 0.0))

        def raster_for(height):
            """Glyph size in pixels for ``height`` world units at this plane."""
            s0 = location_3d_to_region_2d(region, rv3d, center)
            s1 = location_3d_to_region_2d(region, rv3d, center + up_world * height)
            if s0 is None or s1 is None:  # behind the view plane
                return None
            return max(8, min(round((s1 - s0).length), 256))

        normal = plane_mat.to_3x3().col[2].normalized()
        # Flip in-plane X when looking at the plane's back so the glyphs read
        # left-to-right from the viewer's side instead of mirrored.
        sx = -1.0 if normal.dot(view_forward) > 0.0 else 1.0
        margin = side * _LABEL_CORNER_MARGIN
        usable = side - 2.0 * margin

        # Axis-tinted, lightened toward white so the text reads a bit softer
        # than the plane fill, brighter still while hovered.
        hovered = selection.hover == pick_id
        tint = workplane_color(pick_id)
        lift = 0.55 if hovered else 0.35
        blf.color(_FONT_ID, *(tuple(c + (1.0 - c) * lift for c in tint) + (1.0,)))

        if axis_line is not None:
            size = raster_for(side * _LABEL_HEIGHT_FACTOR)
            if size is not None:
                dims, gap, width, height = _text_block([axis_line], size)
                scale = (side * _LABEL_HEIGHT_FACTOR) / height
                if width > 0.0 and width * scale > usable:
                    scale = usable / width
                _draw_text_block(
                    plane_mat,
                    [axis_line],
                    dims,
                    gap,
                    size,
                    scale,
                    sx,
                    (min_x + max_x) / 2.0,
                    (min_y + max_y) / 2.0 - height * scale / 2.0,
                    "center",
                )

        # Whose plane it is only matters for the one you are about to pick, and
        # the planes cross on screen: a name drawn on every plane at once lands
        # on another plane's axis as often as not.
        if name_lines and (hovered or axis_line is None):
            size = raster_for(side * _NAME_HEIGHT_FACTOR)
            if size is not None:
                dims, gap, width, height = _text_block(name_lines, size)
                line_h = max(h for _w, h in dims)
                scale = (side * _NAME_HEIGHT_FACTOR) / line_h
                if width > 0.0 and width * scale > usable:
                    scale = usable / width
                # The outer corner, and right-aligned into it: the planes are
                # drawn in their positive quadrant, so it is the only corner
                # where all three names land in different places (XY and XZ
                # share the bottom-right one, and their names collide there).
                # Seen from behind, the plane's own -X corner is on the right.
                x = max_x - margin if sx > 0 else min_x + margin
                _draw_text_block(
                    plane_mat,
                    name_lines,
                    dims,
                    gap,
                    size,
                    scale,
                    sx,
                    x,
                    max_y - margin - height * scale,
                    "right",
                )

    gpu.state.depth_test_set("LESS_EQUAL")
    gpu.state.blend_set("NONE")


# Viewport draw handlers, keyed by their global_data attribute. Order matches
# the passes: geometry/hover/origin labels in the 3D view, constraint icons in
# screen space (batched from one atlas).
_DRAW_HANDLERS = (
    ("draw_handle", draw_cb, "POST_VIEW"),
    ("hover_draw_handle", draw_hover_element, "POST_VIEW"),
    ("origin_label_draw_handle", draw_origin_labels, "POST_VIEW"),
    ("icon_draw_handle", None, "POST_PIXEL"),  # callback resolved in register()
)


def register():
    from .drawing import constraint_icons

    callbacks = {"icon_draw_handle": constraint_icons.draw}
    for attr, cb, pass_type in _DRAW_HANDLERS:
        cb = cb or callbacks[attr]
        handle = bpy.types.SpaceView3D.draw_handler_add(cb, (), "WINDOW", pass_type)
        setattr(global_data, attr, handle)


def unregister():
    for attr, _cb, _pass in _DRAW_HANDLERS:
        handle = getattr(global_data, attr, None)
        if handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(handle, "WINDOW")
            setattr(global_data, attr, None)
