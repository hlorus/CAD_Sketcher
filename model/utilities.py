import logging

import bpy
from bpy.props import IntProperty
from bpy.types import Context
import math
from mathutils import Vector, Matrix

logger = logging.getLogger(__name__)


def slvs_entity_pointer(cls, name, **kwargs):
    index_prop = name + "_i"
    annotations = {}
    if hasattr(cls, "__annotations__"):
        annotations = cls.__annotations__.copy()
    annotations[index_prop] = IntProperty(name=name + " index", default=-1, **kwargs)
    setattr(cls, "__annotations__", annotations)

    @property
    def func(self):
        index = getattr(self, index_prop)
        return None if index == -1 else bpy.context.scene.sketcher.entities.get(index)
    setattr(cls, name, func)

    @func.setter
    def setter(self, entity):
        index = entity.slvs_index if entity else -1
        setattr(self, index_prop, index)

    setattr(cls, name, setter)


def tag_update(self, context: Context):
    self.tag_update()


def round_v(vec, ndigits=None):
    values = []
    for v in vec:
        values.append(round(v, ndigits=ndigits))
    return Vector(values)


def get_connection_point(seg_1, seg_2):
    points = seg_1.connection_points()
    for p in seg_2.connection_points():
        if p in points:
            return p


def get_bezier_curve_midpoint_positions(
    curve_element, segment_count, midpoints, angle, cyclic=False
):
    positions = []
    if segment_count == 1:
        return []

    if cyclic:
        point_count = segment_count
    else:
        point_count = segment_count - 1

    a = angle / segment_count
    for i in range(point_count):
        pos = curve_element.point_on_curve(a * (i + 1))
        positions.append(pos)
    return positions


def create_bezier_curve(
    segment_count,
    bezier_points,
    locations,
    center,
    base_offset,
    invert=False,
    cyclic=False,
):
    if cyclic:
        bezier_points.append(bezier_points[0])
        locations.append(locations[0])

    for index in range(segment_count):
        loc1, loc2 = locations[index], locations[index + 1]
        b1, b2 = bezier_points[index], bezier_points[index + 1]

        coords = []
        for i, loc in enumerate((loc1, loc2)):
            pos = loc - center
            angle = math.atan2(pos[1], pos[0])
            offset = base_offset.copy()

            if i == 0 and invert or i == 1 and not invert:
                offset[1] *= -1

            offset.rotate(Matrix.Rotation(angle, 2))
            coords.append((center + offset).to_3d())

        b1.handle_right = coords[0]
        b2.handle_left = coords[1]
        b2.co = loc2.to_3d()


# NOTE: When tweaking, it's necessary to constrain a point that is only temporary available
# and has no SlvsPoint representation
def make_coincident(solvesys, point_handle, e2, wp, group, entity_type=None):
    from .categories import LINE, CURVE, POINT
    from .workplane import SlvsWorkplane

    func = None
    set_wp = False

    if entity_type:
        handle = e2
    else:
        entity_type = type(e2)
        handle = e2.py_data

    if entity_type in LINE:
        func = solvesys.addPointOnLine
        set_wp = True
    elif entity_type in CURVE:
        func = solvesys.addPointOnCircle
    elif entity_type == SlvsWorkplane:
        func = solvesys.addPointInPlane
    elif entity_type in POINT:
        func = solvesys.addPointsCoincident
        set_wp = True

    kwargs = {
        "group": group,
    }

    if set_wp:
        kwargs["wrkpln"] = wp

    return func(point_handle, handle, **kwargs)


def update_pointers(scene, index_old, index_new):
    """Replaces all references to an entity index with its new index"""
    logger.debug("Update references {} -> {}".format(index_old, index_new))
    # NOTE: this should go through all entity pointers and update them if necessary.
    # It might be possible to use the msgbus to notify and update the IntProperty pointers

    if scene.sketcher.active_sketch_i == index_old:
        logger.debug(
            "Update reference {} of {} to {}: ".format(
                "active_sketch", scene.sketcher, index_new
            )
        )
        scene.sketcher.active_sketch_i = index_new

    for o in scene.sketcher.all:
        if not hasattr(o, "update_pointers"):
            continue
        o.update_pointers(index_old, index_new)

    scene.sketcher.purge_stale_data()
