from pathlib import Path

import gpu
import bpy.utils.previews
from gpu_extras.batch import batch_for_shader
from bpy.app import background

from .shaders import Shaders
from .operators.add_angle import VIEW3D_OT_slvs_add_angle
from .operators.add_diameter import VIEW3D_OT_slvs_add_diameter
from .operators.add_distance import VIEW3D_OT_slvs_add_distance
from .operators.add_geometric_constraints import constraint_operators

icons = {}
constraint_icons = None
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


def coords_from_icon(data, range_x=255, range_y=255):
    length = len(data)
    # Take the 1st third of the data
    geometry_data = data[: length // 3]
    # Cut geometry_data into chunks of 6 bytes
    tris = [geometry_data[i * 6 : (i + 1) * 6] for i in range(len(geometry_data) // 6)]

    coords = []
    indices = []
    for i, tri in enumerate(tris):
        # split the 6 Byte chunk into 2 Byte chunks
        # Each 2 Byte chunk represent the xy coordinates
        # of triangles to render for the icon
        verts = [tri[i * 2 : (i + 1) * 2] for i in range(3)]

        indices.append([])

        for v in verts:

            x = (int.from_bytes(v[0], "little") / range_x) - 0.5
            y = (int.from_bytes(v[1], "little") / range_y) - 0.5
            co = (x, y)

            if co not in coords:
                coords.append(co)
                index = len(coords) - 1
            else:
                index = coords.index(co)

            indices[i].append(index)

    return coords, indices


def read_icon(fp):
    data = []

    with open(fp, "rb") as icon:
        identifier = icon.read(3)
        _version, size_x, size_y, _start_x, _start_y = icon.read(5)

        while True:
            val = icon.read(1)
            if not val:
                break
            data.append(val)

    return data, size_x, size_y


def load_icon(path):
    data, size_x, size_y = read_icon(path)
    coords, indices = coords_from_icon(data, range_x=size_x, range_y=size_y)
    batch = batch_from_coords(coords, indices)
    icons[path.stem] = batch


def batch_from_coords(coords, indices):
    shader = Shaders.uniform_color_2d()
    return batch_for_shader(shader, "TRIS", {"pos": coords}, indices=indices)


def load():
    if background:
        return
    # Read icons from filepath and store as python data(batch?) for easy access
    filepath = get_folder_path()

    for icon in filepath.glob("*.dat"):
        load_icon(icon)


def load_constraint_icons():
    global constraint_icons

    if constraint_icons:
        return

    constraint_icons = bpy.utils.previews.new()

    for operator, type in _operator_types.items():
        icon_path = get_folder_path() / f"{type}.png"

        if not icon_path.exists():
            continue

        constraint_icons.load(operator, str(icon_path), 'IMAGE')


def unload_constraint_icons():
    global constraint_icons

    if not constraint_icons:
        return

    constraint_icons.clear()
    bpy.utils.previews.remove(constraint_icons)
    constraint_icons = None


def get_constraint_icon(operator: str):
    if not constraint_icons:
        return -1

    icon = constraint_icons.get(operator)

    if not icon:
        return -1

    return icon.icon_id


def draw(id, color):
    batch = icons.get(id)

    if not batch:
        batch = icons.get("none")
    if not batch:
        print('Icon with name: "{}" not found!'.format(id))
        return

    gpu.state.blend_set("ALPHA")

    shader = Shaders.uniform_color_2d()
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

    gpu.state.blend_set("NONE")
