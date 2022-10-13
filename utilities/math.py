from mathutils import Vector

from math import sin, cos

from .constants import FULL_TURN


def range_2pi(angle: float) -> float:
    """Map angle range -Pi/+Pi to 0/2*Pi"""
    return (angle + FULL_TURN) % FULL_TURN


def pol2cart(radius: float, angle: float) -> Vector:
    x = radius * cos(angle)
    y = radius * sin(angle)
    return Vector((x, y))
