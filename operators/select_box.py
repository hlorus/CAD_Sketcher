import bpy, gpu
from bpy.types import Operator, Context, Event
from bpy.utils import register_classes_factory
from mathutils import Vector
from gpu_extras.batch import batch_for_shader

from .. import global_data
from ..declarations import Operators
from ..utilities.index import rgb_to_index
from ..utilities.view import refresh
from ..utilities.select import mode_property, deselect_all


def get_start_dist(value1, value2, invert: bool = False):
    values = [value1, value2]
    values.sort(reverse=invert)
    start = values[0]
    return int(start), int(abs(value2 - value1))


def draw_callback_px(self, context):
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    gpu.state.line_width_set(2.0)

    start = self.start_coords
    end = self.mouse_pos

    box_path = (start, (end.x, start.y), end, (start.x, end.y), start)
    batch = batch_for_shader(shader, "LINE_STRIP", {"pos": box_path})
    shader.bind()
    shader.uniform_float("color", (0.0, 0.0, 0.0, 0.5))
    batch.draw(shader)

    # restore opengl defaults
    gpu.state.line_width_set(1.0)
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

        start_x, width = get_start_dist(self.start_coords.x, self.end_coords.x)
        start_y, height = get_start_dist(self.start_coords.y, self.end_coords.y)

        offscreen = global_data.offscreen
        if not offscreen:
            return False
        with offscreen.bind():
            fb = gpu.state.active_framebuffer_get()
            buffer = fb.read_color(start_x, start_y, width, height, 4, 0, "FLOAT")

        if not width or not height:
            return False

        buffer.dimensions = (width * height, 4)

        # Filter out empty pixels
        pixels = [p for p in buffer if p[3] > 0]

        # Remove duplicates
        unique_pixels = []
        [unique_pixels.append(p[:-1]) for p in pixels if p[:-1] not in unique_pixels]

        entities = []
        for pixel in unique_pixels:
            r, g, b = pixel

            index = rgb_to_index(r, g, b)
            entity = context.scene.sketcher.entities.get(index)
            entities.append(entity)

        mode = self.mode
        if mode == "SET":
            deselect_all(context)

        value = True
        toggle = mode == "TOGGLE"
        if mode == "SUBTRACT":
            value = False

        for e in entities:
            if toggle:
                e.selected = not e.selected
                continue
            e.selected = value

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
