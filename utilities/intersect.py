from enum import Enum
from typing import Callable, Tuple

from mathutils.geometry import (
    intersect_line_line_2d as intersect_segment_segment_2d,
    intersect_line_sphere_2d as intersect_segment_sphere_2d,
    intersect_sphere_sphere_2d,
)

from ..model.identifiers import is_line
from .geometry import intersect_line_line_2d, intersect_line_sphere_2d
from ..model.base_entity import SlvsGenericEntity
from .data_handling import to_list


class ElementTypes(str, Enum):
    Line = "LINE"
    Sphere = "Sphere"


def _get_intersection_func(type_a, type_b, segment=False):
    if all([t == ElementTypes.Line for t in (type_a, type_b)]):
        return intersect_line_line_2d if not segment else intersect_segment_segment_2d
    if all([t == ElementTypes.Sphere for t in (type_a, type_b)]):
        return intersect_sphere_sphere_2d
    return intersect_line_sphere_2d if not segment else intersect_segment_sphere_2d


def _order_intersection_args(arg1, arg2):
    if arg1[0] == ElementTypes.Sphere and arg2[0] == ElementTypes.Line:
        return arg2, arg1
    return arg1, arg2


# TODO: Move to entity classes
# -> entity.get_offset_props()


def _get_offset_line(line, offset):
    normal = line.normal()
    offset_vec = normal * offset
    return (line.p1.co + offset_vec, line.p2.co + offset_vec)


def _get_offset_sphere(arc, offset):
    """Return sphere_co and sphere_radius of offset sphere"""
    return arc.ct.co, arc.radius + offset


# create versions which directly accept the entity's props
def _get_offset_line_props(offset, args):
    normal, p1, p2 = args
    offset_vec = normal * offset
    return (p1 + offset_vec, p2 + offset_vec)


def _get_offset_sphere_props(offset, args):
    """Return sphere_co and sphere_radius of offset sphere"""
    ct, radius = args
    return ct, radius + offset


def get_offset_args(entity):
    """Returns the entity's arguments that are used to create an offset element"""
    if is_line(entity):
        return entity.normal().copy(), entity.p1.co.copy(), entity.p2.co.copy()
    return entity.ct.co.copy(), entity.radius


def get_offset_elements_args(
    t: ElementTypes, offset: float, args: tuple
) -> Tuple[ElementTypes, Callable]:
    """Returns the elements of a new offsetted element"""
    func = (
        _get_offset_sphere_props if t == ElementTypes.Sphere else _get_offset_line_props
    )
    return (t, func(offset, args))


# Note: for arcs the radius might increse or decrease depending of the curvature


def get_offset_elements(
    entity: SlvsGenericEntity, offset: float
) -> Tuple[ElementTypes, Callable]:
    t = ElementTypes.Line if entity.type == "SlvsLine2D" else ElementTypes.Sphere
    func = _get_offset_sphere if t == ElementTypes.Sphere else _get_offset_line
    return (t, func(entity, offset))


def _get_offset_line_cb(entity):
    def func(
        offset,
        normal=entity.normal().copy(),
        p1=entity.p1.co.copy(),
        p2=entity.p2.co.copy(),
    ):
        offset_vec = normal * offset
        return (ElementTypes.Line, (p1 + offset_vec, p2 + offset_vec))

    return func


def _get_offset_sphere_cb(entity):
    def func(offset, ct=entity.ct.co.copy(), radius=entity.radius):
        return (ElementTypes.Sphere, (ct, radius + offset))

    return func


def get_offset_cb(entity: SlvsGenericEntity):
    """Create a callback to generate an offset element from a given offset"""

    t = ElementTypes.Line if entity.type == "SlvsLine2D" else ElementTypes.Sphere
    func = _get_offset_sphere_cb if t == ElementTypes.Sphere else _get_offset_line_cb

    return func(entity)


def get_intersections(*element_list, segment=False):
    """Find all intersections between all combinations of elements, (type, element)"""
    intersections = []
    lenght = len(element_list)

    for i, elem_a in enumerate(element_list):
        if i + 1 == lenght:
            break
        for elem_b in element_list[i + 1 :]:
            a, b = _order_intersection_args(elem_a, elem_b)
            func = _get_intersection_func(a[0], b[0], segment=segment)

            retval = to_list(func(*a[1], *b[1]))

            for intr in retval:
                if not intr:
                    continue
                intersections.append(intr)
    return intersections
