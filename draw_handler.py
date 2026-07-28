import logging

import bpy
import gpu
from bpy.types import Context, Operator
from bpy.utils import register_class, unregister_class
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import global_data
from .utilities import preferences
from .utilities.preferences import get_prefs
from .shaders import Shaders
from .declarations import Operators

logger = logging.getLogger(__name__)



def _draw_curves_overlay(context: Context):
    """Draw native curve geometry as an overlay (cached, batched drawing system)."""
    from .drawing import overlay
    overlay.draw(context)


def draw_cb():
    context = bpy.context
    _draw_curves_overlay(context)


# Bounding-box edges (Blender's 8-corner order).
_BBOX_EDGES = (
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
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

    # Only while a hover tool is active; otherwise clear stale hover so the
    # highlight doesn't linger after switching tools.
    tool = context.workspace.tools.from_space_view3d_mode(context.mode)
    if tool is None or tool.widget != GizmoGroups.ObjectHover.value:
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
        return {"FINISHED"}


def register():
    register_class(View3D_OT_slvs_register_draw_cb)
    register_class(View3D_OT_slvs_unregister_draw_cb)


def unregister():
    unregister_class(View3D_OT_slvs_unregister_draw_cb)
    unregister_class(View3D_OT_slvs_register_draw_cb)
