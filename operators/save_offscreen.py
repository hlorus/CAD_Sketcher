import bpy
import gpu
from bpy.types import Operator, Context
from bpy.utils import register_classes_factory

from .. import global_data
from ..declarations import Operators


def write_selection_buffer_image(image_name: str):
    offscreen = global_data.offscreen
    width, height = offscreen.width, offscreen.height

    with offscreen.bind():
        fb = gpu.state.active_framebuffer_get()
        buffer = fb.read_color(0, 0, width, height, 4, 0, "FLOAT")
        buffer.dimensions = width * height * 4

    if image_name not in bpy.data.images:
        bpy.data.images.new(image_name, width, height)
    image = bpy.data.images[image_name]
    image.scale(width, height)
    image.pixels = buffer
    return image


class VIEW3D_OT_slvs_write_selection_texture(Operator):
    """Write selection texture to image for debugging"""

    bl_idname = Operators.WriteSelectionTexture
    bl_label = "Write selection texture"

    def execute(self, context: Context):
        if context.area.type != "VIEW_3D":
            self.report({"WARNING"}, "View3D not found, cannot run operator")
            return {"CANCELLED"}

        if not global_data.offscreen:
            self.report({"WARNING"}, "Selection texture is not available")
            return {"CANCELLED"}

        image = write_selection_buffer_image("selection_buffer")
        self.report({"INFO"}, "Wrote buffer to image: {}".format(image.name))

        return {"FINISHED"}


register, unregister = register_classes_factory(
    (VIEW3D_OT_slvs_write_selection_texture,)
)
