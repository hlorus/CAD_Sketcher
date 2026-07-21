import logging
import math

import bpy
import gpu
from bpy import app
from bpy.types import Context, Operator
from bpy.utils import register_class, unregister_class
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import global_data
from .utilities import preferences
from .utilities.preferences import get_prefs
from .utilities.curve_data import sync_curve_selection
from .model.constants import SketchCurveType
from .shaders import Shaders
from .declarations import Operators

logger = logging.getLogger(__name__)


def _draw_curves_id_buffer(context: Context):
    """Draw curve-based ID buffer using sequential pick indices for picking."""
    from .utilities.index import index_to_rgb
    from .utilities.curve_data import get_uuid, has_uuid_field

    # Reset pick map each frame
    global_data.pick_map = {}
    pick_idx = 1  # Start at 1 (0 = background)

    # Only the active sketch is pickable; other sketches are read-only reference.
    active_obj = context.scene.sketcher.active_sketch_object

    from .model.sketch_ref import get_sketches
    for sketch in get_sketches(context):
        if sketch.target_object != active_obj:
            continue
        if not sketch.is_visible(context):
            continue

        curve_data = sketch.data
        n_curves = len(curve_data.curves)
        if n_curves == 0:
            continue

        cid_attr = has_uuid_field(curve_data, "curve_id")
        vis_attr = curve_data.attributes.get("visible")
        type_attr = curve_data.attributes.get("sketch_type")
        cyc_attr = curve_data.attributes.get("cyclic")
        if not cid_attr:
            continue

        mat = sketch.target_object.matrix_world
        scale = preferences.get_scale()

        for curve_idx in range(n_curves):
            if vis_attr and not vis_attr.data[curve_idx].value:
                continue

            cid = get_uuid(curve_data, "curve_id", curve_idx)
            if not cid:
                continue
            if cid in global_data.ignore_list:
                continue

            global_data.pick_map[pick_idx] = cid
            curve_slice = curve_data.curves[curve_idx]
            ctype = type_attr.data[curve_idx].value if type_attr else -1
            is_cyclic = cyc_attr.data[curve_idx].value if cyc_attr else False
            color = (*index_to_rgb(pick_idx), 1.0)
            pick_idx += 1

            if ctype == SketchCurveType.POINT:
                pt_idx = curve_slice.points[0].index
                world_pos = mat @ Vector(curve_data.points[pt_idx].position)

                shader = Shaders.id_shader_3d()
                shader.bind()
                gpu.state.point_size_set(20 * scale)
                shader.uniform_float("color", color)
                batch = batch_for_shader(shader, "POINTS", {"pos": (world_pos[:],)})
                batch.draw(shader)
                gpu.shader.unbind()
                gpu.state.point_size_set(1)

            elif curve_slice.points_length >= 2:
                shader = Shaders.id_line_3d()
                shader.bind()
                line_width = 8 * scale
                gpu.state.line_width_set(line_width)
                if app.version >= (4, 5):
                    shader.uniform_float("lineWidth", line_width)
                    shader.uniform_float(
                        "viewportSize", (context.region.width, context.region.height)
                    )
                shader.uniform_float("color", color)
                _draw_bezier_curve(shader, curve_data, curve_slice, mat, is_cyclic)
                gpu.shader.unbind()
                gpu.state.line_width_set(1)


def draw_selection_buffer(context: Context):
    """Draw elements offscreen"""
    region = context.region

    # create offscreen
    width, height = region.width, region.height
    offscreen = global_data.offscreen = gpu.types.GPUOffScreen(width, height)

    with offscreen.bind():

        fb = gpu.state.active_framebuffer_get()
        fb.clear(color=(0.0, 0.0, 0.0, 0.0), depth=1.0)

        gpu.state.depth_test_set('LESS_EQUAL')
        gpu.state.depth_mask_set(True)

        _draw_curves_id_buffer(context)

        gpu.state.depth_test_set('NONE')
        gpu.state.depth_mask_set(False)


def ensure_selection_texture(context: Context):
    if not global_data.redraw_selection_buffer:
        return

    draw_selection_buffer(context)
    global_data.redraw_selection_buffer = False


def _arc_points(center, radius, start_angle, arc_angle, segments, mat):
    """Generate world-space points along an arc."""
    points = []
    for i in range(segments + 1):
        a = start_angle + arc_angle * i / segments
        x = center.x + radius * math.cos(a)
        y = center.y + radius * math.sin(a)
        world = mat @ Vector((x, y, 0))
        points.append(world[:])
    return points


def _curve_color(ts, selected, hover, fixed, active=True):
    """Resolve color from curve attributes and theme settings."""
    if not active:
        # Non-active sketches are drawn dimmed as read-only reference.
        return ts.inactive_selected if selected else ts.inactive
    if selected:
        if hover:
            return ts.selected_highlight
        return ts.selected
    if hover:
        return ts.highlight
    if fixed:
        return ts.fixed
    return ts.default


def _bezier_evaluate(p0, h0_right, h1_left, p1, steps):
    """Evaluate a cubic bezier segment into a list of world-space points.

    Args:
        p0: Start point position (Vector).
        h0_right: Right handle of start point (Vector).
        h1_left: Left handle of end point (Vector).
        p1: End point position (Vector).
        steps: Number of subdivisions.

    Returns:
        List of Vector positions along the curve.
    """
    points = []
    for i in range(steps + 1):
        t = i / steps
        t2 = t * t
        t3 = t2 * t
        mt = 1 - t
        mt2 = mt * mt
        mt3 = mt2 * mt
        pt = mt3 * p0 + 3 * mt2 * t * h0_right + 3 * mt * t2 * h1_left + t3 * p1
        points.append(pt)
    return points



def _draw_bezier_curve(shader, curve_data, curve_slice, mat, is_cyclic, steps=12):
    """Tessellate and draw a bezier curve."""
    n_points = curve_slice.points_length
    first = curve_slice.points[0].index

    hl_attr = curve_data.attributes.get("handle_left")
    hr_attr = curve_data.attributes.get("handle_right")

    positions = []
    handles_right = []
    handles_left = []
    for i in range(n_points):
        idx = first + i
        positions.append(Vector(curve_data.points[idx].position))
        handles_right.append(Vector(hr_attr.data[idx].vector) if hr_attr else Vector(curve_data.points[idx].position))
        handles_left.append(Vector(hl_attr.data[idx].vector) if hl_attr else Vector(curve_data.points[idx].position))

    # Determine segment count
    n_segments = n_points if is_cyclic else n_points - 1

    # Tessellate all segments
    all_points = []
    for seg in range(n_segments):
        i0 = seg
        i1 = (seg + 1) % n_points

        seg_points = _bezier_evaluate(
            positions[i0], handles_right[i0],
            handles_left[i1], positions[i1],
            steps,
        )

        # Avoid duplicate points at segment joins
        if all_points:
            seg_points = seg_points[1:]
        all_points.extend(seg_points)

    # Transform to world space
    world_points = [mat @ p for p in all_points]

    # Build LINES pairs from the point strip
    lines = []
    for i in range(len(world_points) - 1):
        lines.append(world_points[i][:])
        lines.append(world_points[i + 1][:])

    # Close cyclic
    if is_cyclic and len(world_points) > 1:
        lines.append(world_points[-1][:])
        lines.append(world_points[0][:])

    if lines:
        batch = batch_for_shader(shader, "LINES", {"pos": lines})
        batch.draw(shader)


def _draw_curves_overlay(context: Context):
    """Draw native curve geometry as an overlay."""
    from .utilities.curve_data import get_uuid, has_uuid_field

    if context.scene.sketcher.active_sketch_object is None:
        return

    from .utilities.curve_data import get_curve_data as _gcd

    ts = get_prefs().theme_settings.entity
    scale = preferences.get_scale()
    line_shader = Shaders.polyline_color_3d()
    dashed_shader = Shaders.uniform_color_line_3d()
    point_shader = Shaders.point_color_3d()

    active_obj = context.scene.sketcher.active_sketch_object
    from .model.sketch_ref import get_sketches
    for sketch in get_sketches(context):
        if not sketch.is_visible(context):
            continue

        is_active = sketch.target_object == active_obj

        curve_data = sketch.data
        n_curves = len(curve_data.curves)
        if n_curves == 0:
            continue

        sel_attr = curve_data.attributes.get("selected")
        hov_attr = curve_data.attributes.get("hover")
        con_attr = curve_data.attributes.get("construction")
        fix_attr = curve_data.attributes.get("fixed")
        vis_attr = curve_data.attributes.get("visible")
        cyc_attr = curve_data.attributes.get("cyclic")
        type_attr = curve_data.attributes.get("sketch_type")
        sp_attr = has_uuid_field(curve_data, "start_point_id")
        ep_attr = has_uuid_field(curve_data, "end_point_id")
        cp_attr = has_uuid_field(curve_data, "center_point_id")

        mat = sketch.target_object.matrix_world
        point_coords = []
        point_colors = []

        for curve_idx in range(n_curves):
            curve_slice = curve_data.curves[curve_idx]

            if vis_attr and not vis_attr.data[curve_idx].value:
                continue

            selected = sel_attr.data[curve_idx].value if sel_attr else False
            hover = hov_attr.data[curve_idx].value if hov_attr else False
            construction = con_attr.data[curve_idx].value if con_attr else False
            fixed = fix_attr.data[curve_idx].value if fix_attr else False
            is_cyclic = cyc_attr.data[curve_idx].value if cyc_attr else False
            ctype = type_attr.data[curve_idx].value if type_attr else -1

            col = _curve_color(ts, selected, hover, fixed, active=is_active)

            if ctype == SketchCurveType.POINT:
                # 1-point curve — collect for batch drawing
                pt_idx = curve_slice.points[0].index
                world_pos = mat @ Vector(curve_data.points[pt_idx].position)
                point_coords.append(world_pos[:])
                point_colors.append(col)

            elif ctype == SketchCurveType.LINE and sp_attr and ep_attr:
                # Line — draw from point curves
                sp_cid = get_uuid(curve_data, "start_point_id", curve_idx)
                ep_cid = get_uuid(curve_data, "end_point_id", curve_idx)
                _, _, sp_slice = _gcd(sketch, sp_cid)
                _, _, ep_slice = _gcd(sketch, ep_cid)
                if sp_slice and ep_slice:
                    p1 = mat @ Vector(curve_data.points[sp_slice.points[0].index].position)
                    p2 = mat @ Vector(curve_data.points[ep_slice.points[0].index].position)

                    line_width = (1.5 if construction else 2) * scale
                    shader = dashed_shader if construction else line_shader
                    shader.bind()
                    gpu.state.blend_set("ALPHA")
                    shader.uniform_float("color", col)
                    gpu.state.line_width_set(line_width)
                    if construction:
                        shader.uniform_bool("dashed", (True,))
                        shader.uniform_float("dash_width", 0.05)
                        shader.uniform_float("dash_factor", 0.3)
                    elif app.version >= (4, 5):
                        shader.uniform_float("lineWidth", line_width)
                        shader.uniform_float(
                            "viewportSize", (context.region.width, context.region.height)
                        )
                    batch = batch_for_shader(shader, "LINES", {"pos": (p1[:], p2[:])})
                    batch.draw(shader)
                    gpu.shader.unbind()
                    gpu.state.line_width_set(1)
                    gpu.state.blend_set("NONE")

            elif ctype in (SketchCurveType.ARC, SketchCurveType.CIRCLE) and cp_attr:
                # Arc/circle — resolve from point curves and draw arc
                cp_cid = get_uuid(curve_data, "center_point_id", curve_idx)
                _, _, cp_slice = _gcd(sketch, cp_cid)
                if cp_slice:
                    center = Vector(curve_data.points[cp_slice.points[0].index].position[:2])
                    if is_cyclic:
                        # Circle: use first edge point for radius
                        edge = Vector(curve_data.points[curve_slice.points[0].index].position[:2])
                        radius = (edge - center).length
                        arc_points = _arc_points(center, radius, 0, math.tau, 48, mat)
                    else:
                        sp_cid = get_uuid(curve_data, "start_point_id", curve_idx)
                        ep_cid = get_uuid(curve_data, "end_point_id", curve_idx)
                        _, _, s_slice = _gcd(sketch, sp_cid) if sp_cid else (None, None, None)
                        _, _, e_slice = _gcd(sketch, ep_cid) if ep_cid else (None, None, None)
                        if s_slice and e_slice:
                            start = Vector(curve_data.points[s_slice.points[0].index].position[:2])
                            end = Vector(curve_data.points[e_slice.points[0].index].position[:2])
                            radius = (start - center).length
                            from .utilities.math import range_2pi
                            s_angle = math.atan2((start - center).y, (start - center).x)
                            e_angle = math.atan2((end - center).y, (end - center).x)
                            arc_angle = range_2pi(e_angle - s_angle)
                            segments = max(int(arc_angle / math.tau * 48), 4)
                            arc_points = _arc_points(center, radius, s_angle, arc_angle, segments, mat)
                        else:
                            arc_points = None

                    if arc_points and len(arc_points) >= 2:
                        line_width = (1.5 if construction else 2) * scale
                        shader = dashed_shader if construction else line_shader
                        shader.bind()
                        gpu.state.blend_set("ALPHA")
                        shader.uniform_float("color", col)
                        gpu.state.line_width_set(line_width)
                        if construction:
                            shader.uniform_bool("dashed", (True,))
                            shader.uniform_float("dash_width", 0.05)
                            shader.uniform_float("dash_factor", 0.3)
                        elif app.version >= (4, 5):
                            shader.uniform_float("lineWidth", line_width)
                            shader.uniform_float(
                                "viewportSize", (context.region.width, context.region.height)
                            )
                        lines = []
                        for j in range(len(arc_points) - 1):
                            lines.append(arc_points[j])
                            lines.append(arc_points[j + 1])
                        if is_cyclic and len(arc_points) > 1:
                            lines.append(arc_points[-1])
                            lines.append(arc_points[0])
                        batch = batch_for_shader(shader, "LINES", {"pos": lines})
                        batch.draw(shader)
                        gpu.shader.unbind()
                        gpu.state.line_width_set(1)
                        gpu.state.blend_set("NONE")

                gpu.shader.unbind()
                gpu.state.line_width_set(1)
                gpu.state.blend_set("NONE")

        # Draw all points (grouped by color for fewer draw calls)
        if point_coords:
            point_shader.bind()
            gpu.state.blend_set("ALPHA")
            # Inactive sketches draw smaller (and dimmer) as reference.
            gpu.state.point_size_set((5 if is_active else 3) * scale)

            # Group by color
            color_groups = {}
            for pos, col in zip(point_coords, point_colors):
                key = tuple(col)
                color_groups.setdefault(key, []).append(pos)

            for col, positions in color_groups.items():
                # Keep the color's alpha so inactive-sketch points dim like lines.
                point_shader.uniform_float("color", col)
                batch = batch_for_shader(point_shader, "POINTS", {"pos": positions})
                batch.draw(point_shader)

            gpu.shader.unbind()
            gpu.state.point_size_set(1)
            gpu.state.blend_set("NONE")


def draw_cb():
    context = bpy.context

    sync_curve_selection(context.scene)
    _draw_curves_overlay(context)

    global_data.redraw_selection_buffer = True


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
        global_data.draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_cb, (), "WINDOW", "POST_VIEW"
        )
        global_data.hover_draw_handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_hover_element, (), "WINDOW", "POST_VIEW"
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
        return {"FINISHED"}


def register():
    register_class(View3D_OT_slvs_register_draw_cb)
    register_class(View3D_OT_slvs_unregister_draw_cb)


def unregister():
    unregister_class(View3D_OT_slvs_unregister_draw_cb)
    unregister_class(View3D_OT_slvs_register_draw_cb)
