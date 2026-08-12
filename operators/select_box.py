import bpy, gpu
from bpy.types import Operator, Context, Event
from bpy.utils import register_classes_factory
from mathutils import Vector
from gpu_extras.batch import batch_for_shader

from ..drawing import selection
from ..declarations import Operators
from ..utilities.view import refresh
from ..utilities.select import mode_property, deselect_all


def get_start_dist(value1, value2, invert: bool = False):
    values = [value1, value2]
    values.sort(reverse=invert)
    start = values[0]
    return int(start), int(abs(value2 - value1))


def _append_quad(vertices, left, bottom, right, top):
    vertices.extend(
        (
            (left, bottom),
            (right, bottom),
            (right, top),
            (left, bottom),
            (right, top),
            (left, top),
        )
    )


def _box_outline_vertices(start, end, line_width=2.0):
    """Return screen-space triangles for a fixed-width rectangular outline.

    GPU line widths are not consistently supported across Blender backends
    (notably Metal on macOS). Building the outline from triangles keeps the
    marquee thickness stable without relying on ``gpu.state.line_width_set``.
    """
    half_width = line_width / 2.0
    left = min(start.x, end.x)
    right = max(start.x, end.x)
    bottom = min(start.y, end.y)
    top = max(start.y, end.y)

    vertices = []

    # Horizontal edges. Extend them by half a line width so their corners meet
    # the vertical edges cleanly.
    _append_quad(
        vertices,
        left - half_width,
        bottom - half_width,
        right + half_width,
        bottom + half_width,
    )
    _append_quad(
        vertices,
        left - half_width,
        top - half_width,
        right + half_width,
        top + half_width,
    )

    # Vertical edges.
    _append_quad(
        vertices,
        left - half_width,
        bottom - half_width,
        left + half_width,
        top + half_width,
    )
    _append_quad(
        vertices,
        right - half_width,
        bottom - half_width,
        right + half_width,
        top + half_width,
    )

    return vertices


def draw_callback_px(self, context):
    """Draw a backend-independent 2 px selection-box outline."""
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    gpu.state.blend_set("ALPHA")

    vertices = _box_outline_vertices(self.start_coords, self.mouse_pos, 2.0)
    batch = batch_for_shader(shader, "TRIS", {"pos": vertices})

    shader.bind()
    shader.uniform_float("color", (0.0, 0.0, 0.0, 0.5))
    batch.draw(shader)

    gpu.state.blend_set("NONE")


class View3D_OT_slvs_select_box(Operator):
    """Select entities by drawing a box"""

    bl_idname = Operators.SelectBox
    bl_label = "Box Select"
    bl_options = {"UNDO"}

    mode: mode_property
    _handle = None

    def invoke(self, context: Context, event):
        self.start_coords = Vector((event.mouse_region_x, event.mouse_region_y))
        self.mouse_pos = self.start_coords

        context.window.cursor_modal_set("CROSSHAIR")
        context.window_manager.modal_handler_add(self)

        args = (self, context)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            draw_callback_px, args, "WINDOW", "POST_PIXEL"
        )
        return {"RUNNING_MODAL"}

    def main(self, context: Context):
        if self.start_coords == self.end_coords:
            return False

        from ..drawing import picking
        curve_ids = picking.pick_box(context, self.start_coords, self.end_coords)

        mode = self.mode
        if mode == "SET":
            deselect_all(context)

        for cid in curve_ids:
            if mode == "TOGGLE":
                if cid in selection.selected:
                    selection.selected.remove(cid)
                else:
                    selection.selected.append(cid)
            elif mode == "SUBTRACT":
                if cid in selection.selected:
                    selection.selected.remove(cid)
            else:
                if cid not in selection.selected:
                    selection.selected.append(cid)

        refresh(context)
        return True

    def modal(self, context: Context, event: Event):
        if event.type in ("RIGHTMOUSE", "ESC"):
            return self.end(context, False)

        if event.type == "MOUSEMOVE":
            context.area.tag_redraw()
            self.mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))

        if event.type == "LEFTMOUSE":
            self.end_coords = Vector((event.mouse_region_x, event.mouse_region_y))
            return self.end(context, self.main(context))
        return {"RUNNING_MODAL"}

    def end(self, context, succeede):
        context.window.cursor_modal_restore()

        if self._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")

        retval = {"FINISHED"} if succeede else {"CANCELLED"}
        context.area.tag_redraw()
        return retval


register, unregister = register_classes_factory((View3D_OT_slvs_select_box,))
