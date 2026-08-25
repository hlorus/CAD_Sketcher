import logging

import blf
import bpy
import gpu
from bpy.types import Context, Operator
from bpy.utils import register_class, unregister_class
from bpy_extras.view3d_utils import location_3d_to_region_2d
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

from . import global_data
from .declarations import Operators
from .shaders import Shaders
from .utilities import preferences
from .utilities.preferences import get_prefs

logger = logging.getLogger(__name__)

# Blender's built-in default font.
_FONT_ID = 0
# Label height as a fraction of the origin plane's drawn side length.
_LABEL_HEIGHT_FACTOR = 0.22
# Inset of the label from the plane's outer corner, as a fraction of its side.
_LABEL_CORNER_MARGIN = 0.08


def _draw_curves_overlay(context: Context):
    """Draw native curve geometry as an overlay (cached, batched drawing system)."""
    from .drawing import overlay

    overlay.draw(context)


def draw_cb():
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


def draw_origin_labels():
    """POST_VIEW: name each origin workplane (XY/XZ/YZ), lying in its plane.

    Drawn in the 3D pass so ``blf`` is transformed by the plane's matrix and the
    text tilts with it in perspective. Visibility mirrors the workplane gizmo:
    only while the Add Sketch tool is active, and ``iter_wp_empties`` already
    respects ``show_origin``. The glyph raster is sized to the label's on-screen
    height so it stays crisp instead of being magnified; the text sits in the
    plane's outer corner, uses the themed constraint-text color, is mirrored
    when seen from behind so it never reads backwards, and skips the depth test
    so it stays legible over geometry.
    """
    from .declarations import GizmoGroups
    from .drawing import selection
    from .utilities.workplane import (
        ORIGIN_AXIS_COLOR,
        ORIGIN_LABEL,
        iter_wp_empties,
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
        label = ORIGIN_LABEL.get(pick_id)
        if not label:
            continue

        min_x, min_y, max_x, max_y = wp_plane_bounds(context, pick_id)
        side = max_x - min_x
        target_h = side * _LABEL_HEIGHT_FACTOR

        plane_mat = wp_obj.matrix_world
        up_world = plane_mat.to_3x3().col[1].normalized()
        corner = plane_mat @ Vector((max_x, max_y, 0.0))

        # Raster the glyphs at their on-screen pixel height so they stay sharp:
        # magnifying a small raster into world space is what made them blurry.
        s0 = location_3d_to_region_2d(region, rv3d, corner)
        s1 = location_3d_to_region_2d(region, rv3d, corner + up_world * target_h)
        if s0 is None or s1 is None:  # behind the view plane
            continue
        blf.size(_FONT_ID, max(8, min(round((s1 - s0).length), 256)))

        w, h = blf.dimensions(_FONT_ID, label)
        if h <= 0.0:
            continue
        scale = target_h / h

        # Anchor the text box's outer corner a margin in from the plane's outer
        # corner, so it reads as a corner label rather than filling the plane.
        margin = side * _LABEL_CORNER_MARGIN
        box_cx = max_x - margin - (w * scale) / 2
        box_cy = max_y - margin - (h * scale) / 2

        normal = plane_mat.to_3x3().col[2].normalized()
        # Flip in-plane X when looking at the plane's back so the glyphs read
        # left-to-right from the viewer's side instead of mirrored.
        sx = -1.0 if normal.dot(view_forward) > 0.0 else 1.0

        # Right-to-left: center the glyph box, mirror if needed, scale to world,
        # move to the corner anchor, then into the plane's frame.
        mat = (
            plane_mat
            @ Matrix.Translation((box_cx, box_cy, 0.0))
            @ Matrix.Scale(scale, 4)
            @ Matrix.Diagonal((sx, 1.0, 1.0, 1.0))
            @ Matrix.Translation((-w / 2, -h / 2, 0.0))
        )

        # Axis-tinted, lightened toward white so the text reads a bit softer
        # than the plane fill, brighter still while hovered.
        axis = ORIGIN_AXIS_COLOR[pick_id]
        lift = 0.55 if selection.hover == pick_id else 0.35
        color = tuple(c + (1.0 - c) * lift for c in axis) + (1.0,)
        blf.color(_FONT_ID, *color)

        with gpu.matrix.push_pop():
            gpu.matrix.multiply_matrix(mat)
            blf.position(_FONT_ID, 0.0, 0.0, 0.0)
            blf.draw(_FONT_ID, label)

    gpu.state.depth_test_set("LESS_EQUAL")
    gpu.state.blend_set("NONE")


class View3D_OT_slvs_register_draw_cb(Operator):
    bl_idname = Operators.RegisterDrawCB
    bl_label = "Register Draw Callback"

    def execute(self, context: Context):
        from .drawing import constraint_icons

        global_data.draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_cb, (), "WINDOW", "POST_VIEW"
        )
        global_data.hover_draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_hover_element, (), "WINDOW", "POST_VIEW"
        )
        # Constraint icons draw in screen space, batched from one atlas.
        global_data.icon_draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            constraint_icons.draw, (), "WINDOW", "POST_PIXEL"
        )
        # Origin-plane labels are drawn in the plane, so they need the 3D pass.
        global_data.origin_label_draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_origin_labels, (), "WINDOW", "POST_VIEW"
        )

        return {"FINISHED"}


class View3D_OT_slvs_unregister_draw_cb(Operator):
    bl_idname = Operators.UnregisterDrawCB
    bl_label = ""

    def execute(self, context: Context):
        global_data.draw_handler.remove_handle()
        if global_data.hover_draw_handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(
                global_data.hover_draw_handle, "WINDOW"
            )
            global_data.hover_draw_handle = None
        if getattr(global_data, "icon_draw_handle", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(
                global_data.icon_draw_handle, "WINDOW"
            )
            global_data.icon_draw_handle = None
        if getattr(global_data, "origin_label_draw_handle", None) is not None:
            bpy.types.SpaceView3D.draw_handler_remove(
                global_data.origin_label_draw_handle, "WINDOW"
            )
            global_data.origin_label_draw_handle = None
        return {"FINISHED"}


def register():
    register_class(View3D_OT_slvs_register_draw_cb)
    register_class(View3D_OT_slvs_unregister_draw_cb)


def unregister():
    unregister_class(View3D_OT_slvs_unregister_draw_cb)
    unregister_class(View3D_OT_slvs_register_draw_cb)
