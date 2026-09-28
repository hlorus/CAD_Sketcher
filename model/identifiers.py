from typing import Type, Union

from .categories import CURVE, ELEMENT_2D, LINE, POINT, SEGMENT
from .group_entities import type_from_index
from .types import SlvsCircle, SlvsGenericEntity, SlvsSketch

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


def is_circle(entity: EntityRef) -> bool:
    return _get_type(entity) == SlvsCircle


# Legacy entity classes still spell the accepted types of every constraint
# (``signature``), while picked geometry is a CurveRef. One mapping serves both
# the interactive picker and the MCP layer, so they cannot disagree about what a
# constraint accepts.
_CURVE_REF_TYPES = {
    "PointRef": "SlvsPoint2D",
    "LineRef": "SlvsLine2D",
    "ArcRef": "SlvsArc",
    "CircleRef": "SlvsCircle",
}

# What each accepted entity class is called in agent-facing text.
_KIND_LABELS = {
    "SlvsPoint2D": "point",
    "SlvsPoint3D": "point",
    "SlvsLine2D": "line",
    "SlvsLine3D": "line",
    "SlvsArc": "arc",
    "SlvsCircle": "circle",
}


def legacy_type(element) -> Type[SlvsGenericEntity]:
    """The entity class a picked element counts as, or None when it isn't one."""
    from . import types as model_types
    from .curve_ref import CurveRef

    if isinstance(element, SlvsGenericEntity):
        return type(element)
    if not isinstance(element, CurveRef):
        return None
    name = _CURVE_REF_TYPES.get(type(element).__name__)
    return getattr(model_types, name) if name else None


def matches_types(element, types) -> bool:
    """Whether ``element`` is one of ``types``, for entities and CurveRefs alike."""
    if type(element) in types:
        return True
    mapped = legacy_type(element)
    return mapped in types if mapped else False


def kind_labels(types) -> list:
    """Agent-facing names ("point", "line", ...) for a signature's accepted types."""
    labels = []
    for entity_type in types:
        label = _KIND_LABELS.get(getattr(entity_type, "__name__", ""))
        if label and label not in labels:
            labels.append(label)
    return labels
