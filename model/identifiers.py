from .group_entities import type_from_index
from .categories import POINT, SEGMENT, LINE, CURVE, ELEMENT_2D
from .types import SlvsSketch, SlvsCircle


def _get_type(value):
    index = value if isinstance(value, int) else value.slvs_index
    return type_from_index(index)


def is_2d(entity):
    return _get_type(entity) in ELEMENT_2D


def is_3d(entity):
    return not is_2d(entity)


def is_point(entity):
    return _get_type(entity) in POINT


def is_line(entity):
    return _get_type(entity) in LINE


def is_curve(entity):
    return _get_type(entity) in CURVE


def is_segment(entity):
    return _get_type(entity) in SEGMENT


def is_path(entity):
    return _get_type(entity) in (*SEGMENT, SlvsCircle)


def is_closed(entity):
    return _get_type(entity) == SlvsCircle


def is_sketch(entity):
    return _get_type(entity) == SlvsSketch
