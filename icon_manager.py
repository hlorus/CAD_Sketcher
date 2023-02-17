from pathlib import Path

import gpu
import bpy
import bpy.utils.previews
from gpu_extras.batch import batch_for_shader
from bpy.app import background

from .shaders import Shaders
from .operators.add_angle import VIEW3D_OT_slvs_add_angle
from .operators.add_diameter import VIEW3D_OT_slvs_add_diameter
from .operators.add_distance import VIEW3D_OT_slvs_add_distance
from .operators.add_geometric_constraints import constraint_operators

icons = {}
_icon_shader = Shaders.uniform_color_image_2d()
_icon_batch = batch_for_shader(_icon_shader, "TRI_FAN", {
    "pos": ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5)),
    "texCoord": ((0, 0), (1, 0), (1, 1), (0, 1)),
})
preview_icons = None
_operator_types = {
    operator.bl_idname: operator.type
    for operator in (
        VIEW3D_OT_slvs_add_angle,
        VIEW3D_OT_slvs_add_diameter,
        VIEW3D_OT_slvs_add_distance,
        *constraint_operators,
    )
}


def get_folder_path():
    return Path(__file__).parent / "ressources" / "icons"


def get_icon(name: str):
    return str(get_folder_path() / name)


def load_icon(type, icon):
    size, pixels = icon.icon_size, icon.icon_pixels_float
    buffer = gpu.types.Buffer('FLOAT', (1, len(pixels)), [pixels])
    texture = gpu.types.GPUTexture(size=size, data=buffer)
    icons[type] = texture


def load():
    global preview_icons

    if preview_icons:
        return

    if background:
        return

    load_preview_icons()

    for operator, icon in preview_icons.items():
        load_icon(_operator_types[operator], icon)


def load_preview_icons():
    global preview_icons

    if preview_icons:
        return

    preview_icons = bpy.utils.previews.new()

    for operator, type in _operator_types.items():
        icon_path = get_folder_path() / f"{type}.png"

        if not icon_path.exists():
            continue

        preview_icons.load(operator, str(icon_path), 'IMAGE')


def unload_preview_icons():
    global preview_icons

    if not preview_icons:
        return

    preview_icons.clear()
    bpy.utils.previews.remove(preview_icons)
    preview_icons = None


def get_constraint_icon(operator: str):
    if not preview_icons:
        return -1

    icon = preview_icons.get(operator)

    if not icon:
        return -1

    return icon.icon_id


def draw(id, color):
    texture = icons.get(id)

    if not texture:
        return

    gpu.state.blend_set("ALPHA")

    shader, batch = _icon_shader, _icon_batch
    shader.bind()
    shader.uniform_float("color", color)
    shader.uniform_sampler("image", texture)
    batch.draw(shader)

    gpu.state.blend_set("NONE")
