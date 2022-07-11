from collections import deque
import math
from math import pi, cos, sin, tau
import subprocess
import re
import site
from importlib import reload
from typing import Any, List, Tuple, Union

import bpy
import bmesh
from bpy.types import Context, RegionView3D, Object
from bpy_extras.view3d_utils import (
    location_3d_to_region_2d,
    region_2d_to_location_3d,
    region_2d_to_vector_3d,
    region_2d_to_origin_3d,
)
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

from . import global_data


def get_prefs():
    return bpy.context.preferences.addons[__package__].preferences


def install_pip():
    """ Subprocess call ensurepip module"""
    cmd = [global_data.PYPATH, "-m", "ensurepip", "--upgrade"]
    return not subprocess.call(cmd)


def update_pip():
    cmd = [global_data.PYPATH, "-m", "pip", "install", "--upgrade", "pip"]
    return not subprocess.call(cmd)


def refresh_path():
    """ refresh path to packages found after install """
    reload(site)


def install_package(package: str, no_deps: bool = True):
    update_pip()
    base_call = [global_data.PYPATH, "-m", "pip", "install"]
    args = ["--upgrade"]
    if no_deps:
        args += ["--no-deps"]
    cmd = base_call + args + package.split(" ")
    ret_val = subprocess.call(cmd)
    refresh_path()
    return ret_val == 0


def ensure_pip():
    if subprocess.call([global_data.PYPATH, "-m", "pip", "--version"]):
        return install_pip()
    return True


def show_package_info(package: str):
    try:
        subprocess.call([global_data.PYPATH, "-m", "pip", "show", package])
    except Exception as e:
        print(e)
        pass


def show_ui_message_popup(
    message: str = "", title: str = "Sketcher Warning", icon: str = "INFO"
):
    """
    Trigger a ui popup message
    NOTE: Perhaps better located in ui.py, but would currently require circular
          dependency with operators.py
    """

    def draw(self, context: Context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def add_new_empty(context, location: Vector, name="") -> Object:
    """ NOTE: No used """
    data = bpy.data
    empty = data.objects.new(name, None)
    empty.location = location
    context.collection.objects.link(empty)
    return empty


def draw_circle_2d(cx: float, cy: float, r: float, num_segments: int):
    """ NOTE: Not used?"""
    # circle outline
    # NOTE: also see gpu_extras.presets.draw_circle_2d
    theta = 2 * pi / num_segments

    # precalculate the sine and cosine
    c = math.cos(theta)
    s = math.sin(theta)

    # start at angle = 0
    x = r
    y = 0
    coords = []
    for _ in range(num_segments):
        coords.append((x + cx, y + cy))
        # apply the rotation matrix
        t = x
        x = c * x - s * y
        y = s * t + c * y
    coords.append(coords[0])
    return coords


def draw_rect_2d(cx: float, cy: float, width: float, height: float):
    # NOTE: this currently returns xyz coordinates, might make sense to return 2d coords
    ox = cx - (width / 2)
    oy = cy - (height / 2)
    cz = 0
    return (
        (ox, oy, cz),
        (ox + width, oy, cz),
        (ox + width, oy + height, cz),
        (ox, oy + height, cz),
    )


def draw_rect_3d(origin: Vector, orientation: Vector, width: float) -> List[Vector]:
    mat_rot = global_data.Z_AXIS.rotation_difference(orientation).to_matrix()
    mat = Matrix.Translation(origin) @ mat_rot.to_4x4()
    coords = draw_rect_2d(0, 0, width, width)
    coords = [(mat @ Vector(co))[:] for co in coords]
    return coords


def draw_quad_3d(cx: float, cy: float, cz: float, width: float):
    half_width = width / 2
    coords = (
        (cx - half_width, cy - half_width, cz),
        (cx + half_width, cy - half_width, cz),
        (cx + half_width, cy + half_width, cz),
        (cx - half_width, cy + half_width, cz),
    )
    indices = ((0, 1, 2), (2, 3, 0))
    return coords, indices


def tris_from_quad_ids(id0: int, id1: int, id2: int, id3: int):
    return (id0, id1, id2), (id1, id2, id3)


def draw_cube_3d(cx: float, cy: float, cz: float, width: float):
    half_width = width / 2
    coords = []
    for x in (cx - half_width, cx + half_width):
        for y in (cy - half_width, cy + half_width):
            for z in (cz - half_width, cz + half_width):
                coords.append((x, y, z))
    # order: ((-x, -y, -z), (-x, -y, +z), (-x, +y, -z), ...)
    indices = (
        *tris_from_quad_ids(0, 1, 2, 3),
        *tris_from_quad_ids(0, 1, 4, 5),
        *tris_from_quad_ids(1, 3, 5, 7),
        *tris_from_quad_ids(2, 3, 6, 7),
        *tris_from_quad_ids(0, 2, 4, 6),
        *tris_from_quad_ids(4, 5, 6, 7),
    )

    return coords, indices


def coords_circle_2d(x: float, y: float, radius: float, segments: int):
    coords = []
    m = (1.0 / (segments - 1)) * (pi * 2)

    for p in range(segments):
        p1 = x + cos(m * p) * radius
        p2 = y + sin(m * p) * radius
        coords.append((p1, p2))
    return coords


def coords_arc_2d(
    x: float,
    y: float,
    radius: float,
    segments: int,
    angle=tau,
    offset: float = 0.0,
    type="LINE_STRIP",
):
    coords = deque()
    segments = max(segments, 1)

    m = (1.0 / segments) * angle

    prev_point = None
    for p in range(segments + 1):
        co_x = x + cos(m * p + offset) * radius
        co_y = y + sin(m * p + offset) * radius
        if type == "LINES":
            if prev_point:
                coords.append(prev_point)
                coords.append((co_x, co_y))
            prev_point = co_x, co_y
        else:
            coords.append((co_x, co_y))
    return coords


def range_2pi(angle: float) -> float:
    """Map angle range -Pi/+Pi to 0/2*Pi"""
    return (angle + tau) % tau


def pol2cart(radius: float, angle: float) -> Vector:
    x = radius * cos(angle)
    y = radius * sin(angle)
    return Vector((x, y))


def index_to_rgb(i: int):
    r = (i & int("0x000000FF", 16)) / 255
    g = ((i & int("0x0000FF00", 16)) >> 8) / 255
    b = ((i & int("0x00FF0000", 16)) >> 16) / 255
    return r, g, b


def rgb_to_index(r: int, g: int, b: int) -> int:
    i = int(r * 255 + g * 255 * 256 + b * 255 * 256 * 256)
    return i


def get_picking_origin_dir(context: Context, coords: Vector) -> Tuple[Vector, Vector]:
    scene = context.scene
    region = context.region
    rv3d = context.region_data
    viewlayer = context.view_layer

    # get the ray from the viewport and mouse
    view_vector = region_2d_to_vector_3d(region, rv3d, coords)
    ray_origin = region_2d_to_origin_3d(region, rv3d, coords)
    return ray_origin, view_vector


def get_picking_origin_end(context: Context, coords: Vector) -> Tuple[Vector, Vector]:
    scene = context.scene
    region = context.region
    rv3d = context.region_data
    viewlayer = context.view_layer

    # get the ray from the viewport and mouse
    view_vector = region_2d_to_vector_3d(region, rv3d, coords)
    ray_origin = region_2d_to_origin_3d(region, rv3d, coords)

    # view vector needs to be scaled and translated
    end_point = view_vector * context.space_data.clip_end + ray_origin
    return ray_origin, end_point


def nearest_point_line_line(p1: Vector, d1: Vector, p2: Vector, d2: Vector) -> Vector:
    n = d1.cross(d2)
    n2 = d2.cross(n)
    return p1 + ((p2 - p1).dot(n2) / d1.dot(n2)) * d1


def get_placement_pos(context: Context, coords: Vector) -> Vector:
    region = context.region
    rv3d = context.region_data
    view_vector = region_2d_to_vector_3d(region, rv3d, coords)
    return region_2d_to_location_3d(region, rv3d, coords, view_vector)


def get_2d_coords(context, pos: Vector) -> Vector:
    region = context.region
    rv3d = context.space_data.region_3d
    return location_3d_to_region_2d(region, rv3d, pos)


def line_abc_form(p1: Vector, p2: Vector) -> Tuple[float, float, float]:
    a = p2.y - p1.y
    b = p1.x - p2.x
    return a, b, a * p1.x + b * p1.y


def get_line_intersection(a1, b1, c1, a2, b2, c2) -> Vector:
    det = a1 * b2 - a2 * b1
    if det == 0:
        # Parallel lines
        return Vector((math.inf, math.inf))
    else:
        x = (b2 * c1 - b1 * c2) / det
        y = (a1 * c2 - a2 * c1) / det
        return Vector((x, y))


def get_scale_from_pos(co: Vector, rv3d: RegionView3D) -> Vector:
    if rv3d.view_perspective == "ORTHO":
        scale = rv3d.view_distance
    else:
        scale = (rv3d.perspective_matrix @ co.to_4d())[3]
    return scale


def refresh(context: Context):
    """ Update gizmos """
    if context.space_data and context.space_data.type == "VIEW_3D":
        context.space_data.show_gizmo = True

    if context.area and context.area.type == "VIEW_3D":
        context.area.tag_redraw()


def update_cb(self, context: Context):
    if not context.space_data:
        return
    # update gizmos!
    if context.space_data.type == "VIEW_3D":
        context.space_data.show_gizmo = True


class bpyEnum:
    """
    Helper class to interact with bpy enums

    NOTE: this is currently based on the enum_items list,
    alternatively this could also work on registered EnumProperties
    """

    def __init__(
        self, data, index: Union[int, None] = None, identifier: Union[None, str] = None
    ):
        self.data = data

        if not identifier:
            self.identifier = self._get_identifier(index)
        else:
            self.identifier = identifier
        item = self._get_active_item()

        self.name = item[1]
        self.description = item[2]
        self.index = item[-1]
        if len(item) == 5:
            icon = item[3]
        else:
            icon = None
        self.icon = icon

    def _get_active_item(self):
        i = [item[0] for item in self.data].index(self.identifier)
        return self.data[i]

    def _get_item_index(self, item):
        if len(item) > 3:
            return item[-1]
        return self.data.index(item)

    def _get_identifier(self, index):
        i = [self._get_item_index(item) for item in self.data].index(index)
        return self.data[i][0]


# custom __setattr__ to allow unique attributes in collections,
# use with PropertyGroups which are stored in a collection
# define class attribute "unique_names = ["", ...]" to define what attributes should be handled
# https://blender.stackexchange.com/questions/15122/collectionproperty-avoid-duplicate-names
# cls.__setattr__ = functions.unique_attribute_setter


def unique_attribute_setter(self, name: str, value: Any):
    def collection_from_element(self):
        """ Get the collection containing the element """
        path = self.path_from_id()
        match = re.match("(.*)\[\d*\]", path)
        parent = self.id_data
        try:
            coll_path = match.group(1)
        except AttributeError:
            raise TypeError("Property not element in a collection.")
        else:
            return parent.path_resolve(coll_path)

    def new_val(stem, nbr):
        """ Simply for formatting """
        return "{st}.{nbr:03d}".format(st=stem, nbr=nbr)

    property_func = getattr(self.__class__, name, None)
    if property_func and isinstance(property_func, property):
        # check if name is a property
        super(self.__class__, self).__setattr__(name, value)
        return
    if name not in self.unique_names:
        # don't handle
        self[name] = value
        return
    if value == getattr(self, name):
        # check for assignment of current value
        return

    coll = collection_from_element(self)
    if value not in coll:
        # if value is not in the collection, just assign
        self[name] = value
        return

    # see if value is already in a format like 'name.012'
    match = re.match(r"(.*)\.(\d{3,})", value)
    if match is None:
        stem, nbr = value, 1
    else:
        stem, nbr = match.groups()

    # check for each value if in collection
    new_value = new_val(stem, nbr)
    while new_value in coll:
        nbr += 1
        new_value = new_val(stem, nbr)
    self[name] = new_value


def breakdown_index(index: int):
    # See SlvsEntities._set_index for the reverse operation
    type_index = index >> 20
    local_index = index & 0xFFFFF
    return type_index, local_index


def bvhtree_from_object(object: Context) -> BVHTree:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    object_eval = object.evaluated_get(depsgraph)
    mesh = object_eval.to_mesh()

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.transform(object.matrix_world)

    bvhtree = BVHTree.FromBMesh(bm)
    object_eval.to_mesh_clear()
    bm.free()
    return bvhtree
