from typing import Union, Type

from .group_entities import type_from_index
from .categories import POINT, SEGMENT, LINE, CURVE, ELEMENT_2D
from .types import SlvsSketch, SlvsCircle, SlvsGenericEntity

EntityRef = Union[SlvsGenericEntity, int]


def _get_type(value: EntityRef) -> Type[SlvsGenericEntity]:
    index = value if isinstance(value, int) else value.slvs_index
    return type_from_index(index)


def is_2d(entity: EntityRef) -> bool:
    return _get_type(entity) in ELEMENT_2D


def is_3d(entity: EntityRef) -> bool:
    return not is_2d(entity)


def is_point(entity: EntityRef) -> bool:
    return _get_type(entity) in POINT


def is_line(entity: EntityRef) -> bool:
    return _get_type(entity) in LINE


def is_curve(entity: EntityRef) -> bool:
    return _get_type(entity) in CURVE


def is_segment(entity: EntityRef) -> bool:
    return _get_type(entity) in SEGMENT


def is_path(entity: EntityRef) -> bool:
    return _get_type(entity) in (*SEGMENT, SlvsCircle)


def is_closed(entity: EntityRef) -> bool:
    return _get_type(entity) == SlvsCircle


def is_sketch(entity: EntityRef) -> bool:
    return _get_type(entity) == SlvsSketch
