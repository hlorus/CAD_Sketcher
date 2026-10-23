import logging
from math import cos, sin

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
from .utilities.constants import QUARTER_TURN
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


# Breathing room around a value box, in text heights: the gap from its anchor,
# the padding inside it, and the step between boxes that would overlap.
_BOX_GAP = 0.7
_BOX_PADDING = 0.35
_BOX_STEP = 1.9
# Corner radius of a value box, in text heights, and the segments drawing one.
_BOX_RADIUS = 0.3
_BOX_CORNER_STEPS = 4
# How far a box's fill is taken from the colour the value is written in, and
# how solid it sits over the viewport.
_BOX_FILL_MIX = 0.1
_BOX_FILL_ALPHA = 0.85

# The live dimension drawn along the stretch a value measures, in text heights:
# how far off the geometry the dimension line sits, where an extension line
# starts and ends, and the size of an arrowhead.
_DIM_OFFSET = 1.6
_WITNESS_GAP = 0.4
_WITNESS_OVERSHOOT = 0.5
_ARROW_LENGTH = 0.9
_ARROW_WIDTH = 0.5
# A stretch shorter than this many pixels leaves no room to dimension it, so
# only its value is written there.
_MIN_SPAN = 14.0


def _box_rect(x, y, width, height, pad, radius=0.0):
    """A value box's outline in screen pixels, with rounded corners.

    Counter-clockwise from the bottom right, so the points serve as both a
    triangle fan and a line loop.
    """
    left, right = x - pad, x + width + pad
    bottom, top = y - pad, y + height + pad
    radius = min(radius, (right - left) / 2, (top - bottom) / 2)
    if radius <= 0:
        return ((left, bottom), (right, bottom), (right, top), (left, top))

    corners = (
        (right - radius, bottom + radius, -QUARTER_TURN),
        (right - radius, top - radius, 0.0),
        (left + radius, top - radius, QUARTER_TURN),
        (left + radius, bottom + radius, 2 * QUARTER_TURN),
    )
    points = []
    for centre_x, centre_y, start in corners:
        for step in range(_BOX_CORNER_STEPS + 1):
            angle = start + QUARTER_TURN * step / _BOX_CORNER_STEPS
            points.append(
                (centre_x + radius * cos(angle), centre_y + radius * sin(angle))
            )
    return tuple(points)


def _box_colors(color):
    """The fill and border of a value box, from the constraint theme.

    The border is the colour the value is written in; the fill is that colour
    taken to the far end of its own range, so the number keeps its contrast
    whatever the viewport is showing and however the theme is set.
    """
    luminance = 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]
    if luminance > 0.5:
        fill = [channel * _BOX_FILL_MIX for channel in color[:3]]
    else:
        fill = [1.0 - (1.0 - channel) * _BOX_FILL_MIX for channel in color[:3]]
    return (*fill, _BOX_FILL_ALPHA), tuple(color)


def _draw_box(rect, fill, border):
    """Outline a value box, over a fill when it has one."""
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    shader.bind()
    if fill is not None:
        shader.uniform_float("color", fill)
        batch_for_shader(shader, "TRI_FAN", {"pos": rect}).draw(shader)
    shader.uniform_float("color", border)
    batch_for_shader(shader, "LINE_LOOP", {"pos": rect}).draw(shader)
    gpu.state.blend_set("NONE")


def _draw_pixel_lines(region, coords, color, width):
    """Draw screen-space ``LINES`` at a given pixel width.

    The same polyline shader the dimension gizmos use, because
    ``line_width_set`` alone is ignored on some backends.
    """
    if len(coords) < 2:
        return
    shader = Shaders.polyline_color_3d()
    batch = batch_for_shader(
        shader, "LINES", {"pos": [(point[0], point[1], 0.0) for point in coords]}
    )
    gpu.state.blend_set("ALPHA")
    shader.bind()
    shader.uniform_float("color", color)
    gpu.state.line_width_set(width)
    if bpy.app.version >= (4, 5):
        shader.uniform_float("viewportSize", (region.width, region.height))
        shader.uniform_float("lineWidth", width)
    batch.draw(shader)
    gpu.shader.unbind()
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")


def _dimension_normal(start, end, away_from):
    """The side of a stretch its dimension line goes on, as a unit vector.

    Away from the middle of everything being drawn, so a rectangle dimensions
    its width below itself and its height beside itself rather than across its
    own face. With nothing to be away from, it goes above the stretch.
    """
    direction = (end - start).normalized()
    normal = Vector((-direction.y, direction.x))
    inward = away_from - (start + end) / 2
    if inward.length_squared > 1e-9:
        return -normal if normal.dot(inward) > 0 else normal
    return normal if (normal.y, normal.x) > (0.0, 0.0) else -normal


def live_dimension_text_height(context: Context) -> float:
    """Height in pixels of the text a live dimension is labelled with."""
    from .drawing import frame_cache

    # The interface scale reads as zero with no interface at all.
    blf.size(_FONT_ID, frame_cache.text_size() * (frame_cache.ui_scale(context) or 1.0))
    return blf.dimensions(_FONT_ID, "0")[1]


def live_dimension_gap(context: Context) -> float:
    """How far off the geometry a live dimension line is drawn, in pixels."""
    return live_dimension_text_height(context) * _DIM_OFFSET


def live_dimension_placement(start, end, away_from, height):
    """Where a live dimension sits: a unit normal, and pixels along it.

    Shared so a dimension created on commit can be placed where its preview was
    drawn, rather than at the default offset (see
    ``Operator2d._place_dimension``).
    """
    return _dimension_normal(start, end, away_from), height * _DIM_OFFSET


def _dimension_shape(start, end, normal, height):
    """A stretch's dimension line, arrowheads and extension lines, in pixels.

    Built from the same helper the distance gizmo draws its arrows with, so a
    value being dragged looks like the dimension it can become.
    """
    from .gizmos.utilities import draw_arrow_shape

    direction = (end - start).normalized()
    offset = normal * (height * _DIM_OFFSET)
    tip_1, tip_2 = (start + offset).to_3d(), (end + offset).to_3d()

    arrow = height * _ARROW_LENGTH
    width = height * _ARROW_WIDTH
    # Arrowheads point inwards, unless the stretch is too short to hold them.
    step = (direction * arrow).to_3d()
    if (tip_2 - tip_1).length < arrow * 3:
        step = -step

    leader = [
        *draw_arrow_shape(tip_1, tip_1 + step, width, is_3d=True),
        tip_1,
        tip_2,
        *draw_arrow_shape(tip_2, tip_2 - step, width, is_3d=True),
    ]
    if step.dot(tip_2 - tip_1) < 0:
        # Arrows sit outside: run the dimension line out to meet them.
        leader += [tip_1, tip_1 + step, tip_2, tip_2 - step]

    gap = normal * (height * _WITNESS_GAP)
    over = normal * (height * (_DIM_OFFSET + _WITNESS_OVERSHOOT))
    witness = [
        (start + gap).to_3d(),
        (start + over).to_3d(),
        (end + gap).to_3d(),
        (end + over).to_3d(),
    ]
    return leader, witness


def draw_state_value():
    """POST_PIXEL: dimension the stretch the running tool's live value measures.

    The same numbers are in the status bar, but the eye is on what is being
    drawn rather than on the bottom of the window, so they are shown again
    where the work is. Each value is drawn as a dimension on the leg it
    measures, with the dimension line, arrowheads and extension lines a
    finished dimension has. The value a typed digit would land in is outlined,
    and filled once it is being typed into. The
    operator publishes them (see
    ``StatefulOperatorLogic._publish_state_value``) along with the region the
    mouse was in, so they are not drawn in every other 3D view at once.
    """
    published = global_data.state_value
    region = bpy.context.region
    if not published or region is None:
        return
    boxes, region_ptr = published
    if region.as_pointer() != region_ptr:
        return

    from .drawing import frame_cache
    from .gizmos.utilities import Color, dimension_line_widths

    size = frame_cache.text_size() * frame_cache.ui_scale(bpy.context)
    blf.size(_FONT_ID, size)
    text_color = frame_cache.constraint_color(Color.Text, False)
    focus_color = frame_cache.constraint_color(Color.Text, True)
    leader_width, witness_width = dimension_line_widths()

    # The middle of everything on screen, so each dimension goes on the outside.
    ends = [point for _text, p1, p2, _focus in boxes for point in (p1, p2)]
    middle = sum(ends, Vector((0.0, 0.0))) / len(ends)

    drawn = []
    for text, p1, p2, focus in boxes:
        if not text:
            continue
        width, height = blf.dimensions(_FONT_ID, text)
        gap = height * _BOX_GAP
        pad = height * _BOX_PADDING
        color = focus_color if focus else text_color

        if (p2 - p1).length >= _MIN_SPAN:
            normal = _dimension_normal(p1, p2, middle)
            leader, witness = _dimension_shape(p1, p2, normal, height)
            _draw_pixel_lines(region, witness, color, witness_width)
            _draw_pixel_lines(region, leader, color, leader_width)
            # Centred just beyond the dimension line, where a label sits.
            centre = (p1 + p2) / 2 + normal * (height * (_DIM_OFFSET + 0.9))
            x, y = centre.x - width / 2, centre.y - height / 2
        else:
            # No stretch to dimension: the value goes up and to the right of it.
            x, y = p1.x + gap, p1.y + gap

        # Pulled back inside the region when that would put it past an edge,
        # and stepped down off any box already drawn on top of it.
        x = min(max(gap, x), region.width - width - gap)
        y = min(max(gap, y), region.height - height - gap)
        while any(
            abs(x - other_x) < width + pad and abs(y - other_y) < height * _BOX_STEP
            for other_x, other_y in drawn
        ):
            y -= height * _BOX_STEP
        drawn.append((x, y))

        if focus:
            # Outlined to say a value can be typed here, filled once one is
            # being typed: the box says where the digits go either way.
            fill, border = _box_colors(color)
            _draw_box(
                _box_rect(x, y, width, height, pad, height * _BOX_RADIUS),
                fill if focus == global_data.BOX_EDITING else None,
                border,
            )
        blf.color(_FONT_ID, *color)
        blf.position(_FONT_ID, x, y, 0.0)
        blf.draw(_FONT_ID, text)


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


def _draw_text_block(plane_mat, lines, dims, gap, size, scale, x, y, align):
    """Draw a measured block in the plane's own frame, sitting on ``y``.

    ``x`` is the block's left edge, centre or right edge in that frame, per
    ``align`` ("left", "center", "right"). Nothing here looks at the view: the
    text lies in the plane like a label painted on a surface, so it stays put
    however the plane is turned.
    """
    width = max(w for w, _h in dims)
    height = sum(h for _w, h in dims) + gap * (len(dims) - 1)
    span = width * scale
    origin_x = x - {"left": 0.0, "center": span / 2.0, "right": span}[align]
    mat = plane_mat @ Matrix.Translation((origin_x, y, 0.0)) @ Matrix.Scale(scale, 4)
    with gpu.matrix.push_pop():
        gpu.matrix.multiply_matrix(mat)
        blf.size(_FONT_ID, size)
        cursor = height
        for line, (line_w, line_h) in zip(lines, dims):
            cursor -= line_h
            offset = {
                "left": 0.0,
                "center": (width - line_w) / 2.0,
                "right": width - line_w,
            }[align]
            blf.position(_FONT_ID, offset, cursor, 0.0)
            blf.draw(_FONT_ID, line)
            cursor -= gap


def draw_origin_labels():
    """POST_VIEW: name each workplane, lying in its plane.

    Drawn in the 3D pass so ``blf`` is transformed by the plane's matrix and the
    text tilts with it in perspective. Visibility mirrors the workplane gizmo:
    only while the Add Sketch tool is active, and ``iter_wp_empties`` already
    respects ``show_origin``.

    A base plane says the axis, large and in the middle where the eye lands, and
    whose plane it is in smaller text in the plane's top-right corner. Both sit
    at fixed places in the plane's own frame, so they stay put as the view turns
    and read from the plane's front like any label painted on a surface. The glyph raster is
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

        margin = side * _LABEL_CORNER_MARGIN
        usable = side - 2.0 * margin

        # Axis-tinted, lightened toward white so the text reads a bit softer
        # than the plane fill, brighter still while hovered.
        hovered = selection.hover == pick_id
        tint = workplane_color(pick_id)
        lift = 0.55 if hovered else 0.35
        blf.color(_FONT_ID, *(tuple(c + (1.0 - c) * lift for c in tint) + (1.0,)))

        middle_x = (min_x + max_x) / 2.0
        middle_y = (min_y + max_y) / 2.0

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
                    middle_x,
                    middle_y - height * scale / 2.0,
                    "center",
                )

        if name_lines:
            size = raster_for(side * _NAME_HEIGHT_FACTOR)
            if size is not None:
                dims, gap, width, height = _text_block(name_lines, size)
                line_h = max(h for _w, h in dims)
                scale = (side * _NAME_HEIGHT_FACTOR) / line_h
                if width > 0.0 and width * scale > usable:
                    scale = usable / width
                # Right-aligned into the plane's own top-right corner: a fixed
                # place in the plane's frame, so it stays put whatever the view.
                _draw_text_block(
                    plane_mat,
                    name_lines,
                    dims,
                    gap,
                    size,
                    scale,
                    max_x - margin,
                    max_y - margin - height * scale,
                    "right",
                )

    gpu.state.depth_test_set("LESS_EQUAL")
    gpu.state.blend_set("NONE")


def draw_axis_candidates():
    """POST_VIEW: draw the axes a revolve can be picked around.

    An axis is a base plane's own direction (see utilities.workplane), so these
    are the frame of the part in focus, or the world's. Tinted like Blender's
    own axes, since that is what they are; the one under the cursor is brighter.
    """
    if not global_data.axis_picker:
        return

    from .utilities.workplane import AXIS_COLOR, axis_endpoints, iter_axis_candidates

    context = bpy.context
    if context.region is None or context.region_data is None:
        return

    scale = preferences.get_scale()
    for plane, index, pick_id in iter_axis_candidates(context):
        # The same two ends the hit test uses, so what is drawn is what picks.
        start, end = axis_endpoints(plane, index, context)
        hovered = global_data.hover_axis == pick_id
        base = AXIS_COLOR[pick_id]
        lift = 0.5 if hovered else 0.0
        color = tuple(c + (1.0 - c) * lift for c in base) + (1.0,)
        _draw_lines_hover([start[:], end[:]], color, scale, width=3 if hovered else 2)


# Viewport draw handlers, keyed by their global_data attribute. Order matches
# the passes: geometry/hover/origin labels in the 3D view, constraint icons in
# screen space (batched from one atlas).
_DRAW_HANDLERS = (
    ("draw_handle", draw_cb, "POST_VIEW"),
    ("hover_draw_handle", draw_hover_element, "POST_VIEW"),
    ("origin_label_draw_handle", draw_origin_labels, "POST_VIEW"),
    ("axis_draw_handle", draw_axis_candidates, "POST_VIEW"),
    ("state_value_draw_handle", draw_state_value, "POST_PIXEL"),
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
