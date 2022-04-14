import gpu
from gpu_extras.batch import batch_for_shader
from bpy.app import background

from functools import cache
from pathlib import Path

from . import functions

icons = {}

@cache
def get_shader():
    # Avoid access in background mode
    return gpu.shader.from_builtin("2D_UNIFORM_COLOR")

def coords_from_icon(data, range_x=255, range_y=255):
    length = len(data)
    geometry_data = data[:length // 3]
    tris = [geometry_data[i*6:(i+1)*6] for i in range(len(geometry_data) // 6)]

    coords = []
    indices = []
    for i, tri in enumerate(tris):
        v1 = tri[0:2]
        verts = [tri[i*2:(i+1)*2] for i in range(3)]

        indices.append([])

        for v in verts:

            x = (int.from_bytes(v[0], "little") / range_x) -0.5
            y = (int.from_bytes(v[1], "little") / range_y) -0.5
            co = (x,y)

            if not co in coords:
                coords.append(co)
                index = len(coords) - 1
            else:
                index = coords.index(co)

            indices[i].append(index)

    return coords, indices

def read_icon(fp):
    data = []
    name = fp.stem

    with open(fp, "rb") as icon:
        identifier = icon.read(3)
        _version, size_x, size_y, _start_x, _start_y = icon.read(5)

        while True:
            val = icon.read(1)
            if not val:
                break
            data.append(val)

    coords, indices = coords_from_icon(data, range_x=size_x, range_y=size_y)
    batch = batch_from_coords(coords, indices)
    icons[name] = batch


def batch_from_coords(coords, indices):

    return batch_for_shader(
        get_shader(), "TRIS", {"pos": coords}, indices=indices
    )


def load():
    if background:
        return
    # Read icons from filepath and store as python data(batch?) for easy access
    filepath = Path(Path(__file__).parent, "icons")

    for icon in filepath.iterdir():
        read_icon(icon)


def draw(id, color):
    batch = icons.get(id)

    if not batch:
        batch = icons.get("none")
    if not batch:
        print("Icon with name: \"{}\" not found!".format(id))
        return

    gpu.state.blend_set('ALPHA')

    shader = get_shader()
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)

    gpu.state.blend_set('NONE')
