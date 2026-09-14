import logging
import math

import bpy
from bpy.props import IntProperty
from bpy.types import Context
from mathutils import Matrix, Vector

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
    spline: bpy.types.CurveSlice,
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

    attributes = spline.id_data.attributes

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

        attributes["handle_right"].data[b1.index].vector = coords[0]
        attributes["handle_left"].data[b2.index].vector = coords[1]
        b2.position = loc2.to_3d()

        # For non-cyclic curves, set both handles for endpoints
        if not cyclic:
            # Set handle_left for the first point (only for the first segment)
            if index == 0:
                pos = loc1 - center
                angle = math.atan2(pos[1], pos[0])
                offset = base_offset.copy()

                # Use opposite direction compared to handle_right
                if not invert:
                    offset[1] *= -1

                offset.rotate(Matrix.Rotation(angle, 2))
                attributes["handle_left"].data[b1.index].vector = (
                    center + offset
                ).to_3d()

            # Set handle_right for the last point (only for the last segment)
            if index == segment_count - 1:
                pos = loc2 - center
                angle = math.atan2(pos[1], pos[0])
                offset = base_offset.copy()

                # Use opposite direction compared to handle_left
                if invert:
                    offset[1] *= -1

                offset.rotate(Matrix.Rotation(angle, 2))
                attributes["handle_right"].data[b2.index].vector = (
                    center + offset
                ).to_3d()


def create_bezier_curve_attributes(spline, segment_count, point_indices):
    pass


# NOTE: When tweaking, it's necessary to constrain a point that is only temporary available
# and has no SlvsPoint representation
def make_coincident(solvesys, point_handle, e2, wp, group, entity_type=None):

    kwargs = {}
    if wp:
        kwargs["workplane"] = wp

    return solvesys.coincident(group, point_handle, e2.py_data, **kwargs)


def line_endpoint_positions(sketch, curve_id: str):
    """Local start/end positions of a LINE curve, or None if it is not a line."""
    from ..model.constants import SketchCurveType
    from ..utilities.curve_data import get_curve_data, get_curve_position, get_uuid

    if sketch is None or not curve_id:
        return None
    curve_data, idx, _ = get_curve_data(sketch, curve_id)
    if curve_data is None:
        return None
    type_attr = curve_data.attributes.get("sketch_type")
    if not type_attr or type_attr.data[idx].value != SketchCurveType.LINE:
        return None
    start = get_curve_position(sketch, get_uuid(curve_data, "start_point_id", idx))
    end = get_curve_position(sketch, get_uuid(curve_data, "end_point_id", idx))
    if start is None or end is None:
        return None
    return start, end


def point_on_line(solvesys, group, point, line, wp, line_start, line_end):
    """Constrain ``point`` to lie on the (infinite) ``line`` in the workplane.

    Solvespace's PT_ON_LINE (what ``coincident`` makes for a point and a line)
    carries a hidden line parameter the library always starts at 0, so every
    fresh solve pulls the point towards the line's start and moves geometry
    that already satisfies the constraint (solvespace/solvespace#1775). A
    zero point-line distance removes the same degree of freedom without that
    parameter. It divides by the line's length though, so a line that is
    degenerate when the system is built keeps PT_ON_LINE.
    """
    start, end = Vector(line_start[:2]), Vector(line_end[:2])
    if wp != solvesys.E_FREE_IN_3D and (end - start).length > 1e-6:
        return solvesys.distance(group, point, line, 0.0, wp)
    return solvesys.coincident(group, point, line, wp)


def update_pointers(scene, index_old, index_new):
    """Replaces all references to an entity index with its new index"""
    logger.debug("Update references {} -> {}".format(index_old, index_new))
    # NOTE: this should go through all entity pointers and update them if necessary.
    # It might be possible to use the msgbus to notify and update the IntProperty pointers

    for o in scene.sketcher.all:
        if not hasattr(o, "update_pointers"):
            continue
        o.update_pointers(index_old, index_new)

    scene.sketcher.purge_stale_data()
