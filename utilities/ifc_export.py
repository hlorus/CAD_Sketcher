"""Exact polygon validation and the optional IFC export dependency.

IfcOpenShell is optional. The addon does not import it at load time, so this
module can be imported without it. The file writer loads the dependency only
when an export is requested.
"""

import math
from collections.abc import Sequence
from fractions import Fraction
from types import ModuleType

Point2D = tuple[float, float]


class IfcOpenShellMissing(RuntimeError):
    """Raised when an IFC export is requested without the ifcopenshell package."""


def require_ifcopenshell() -> ModuleType:
    """Load IfcOpenShell lazily, or raise an actionable export error."""
    try:
        import ifcopenshell
    except ImportError as exc:
        raise IfcOpenShellMissing(
            "IFC export needs the 'ifcopenshell' Python package"
        ) from exc
    return ifcopenshell


def _cross(a, b, c):
    """Exact orientation of the three captured floating-point coordinates."""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, p):
    return (
        _cross(a, b, p) == 0
        and min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
        and min(a[1], b[1]) <= p[1] <= max(a[1], b[1])
    )


def _segments_intersect(a, b, c, d):
    ab_c, ab_d = _cross(a, b, c), _cross(a, b, d)
    cd_a, cd_b = _cross(c, d, a), _cross(c, d, b)
    if ((ab_c > 0 and ab_d < 0) or (ab_c < 0 and ab_d > 0)) and (
        (cd_a > 0 and cd_b < 0) or (cd_a < 0 and cd_b > 0)
    ):
        return True
    return (
        (ab_c == 0 and _on_segment(a, b, c))
        or (ab_d == 0 and _on_segment(a, b, d))
        or (cd_a == 0 and _on_segment(c, d, a))
        or (cd_b == 0 and _on_segment(c, d, b))
    )


def _validate_simple_area(loop):
    # Fraction.from_float represents the supplied binary floats exactly. This
    # avoids overflow or an arbitrary model-unit tolerance in topology checks.
    points = [(Fraction.from_float(x), Fraction.from_float(y)) for x, y in loop]
    count = len(points)
    if len(set(points)) != count:
        raise ValueError("profile boundary repeats a point")
    for i in range(count):
        a, b, c = points[i - 1], points[i], points[(i + 1) % count]
        # Adjacent collinear segments may share their endpoint, but reversing
        # direction makes them overlap.
        if (
            _cross(a, b, c) == 0
            and ((b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1])) < 0
        ):
            raise ValueError("profile boundary overlaps itself")

    twice_area = sum(
        points[i][0] * points[(i + 1) % count][1]
        - points[(i + 1) % count][0] * points[i][1]
        for i in range(count)
    )
    if twice_area == 0:
        raise ValueError("a closed profile must bound a nonzero area")

    for i in range(count):
        a, b = points[i], points[(i + 1) % count]
        for j in range(i + 1, count):
            # Adjacent edges share exactly one vertex; overlap was checked
            # above. Every other intersection or touch is invalid.
            if j == i + 1 or (i == 0 and j == count - 1):
                continue
            c, d = points[j], points[(j + 1) % count]
            if _segments_intersect(a, b, c, d):
                raise ValueError("profile boundary intersects itself")


def closed_loop_points(points: Sequence[Point2D]) -> list[Point2D]:
    """Return the loop without a repeated closing point.

    Raises ValueError for non-finite coordinates or fewer than three distinct
    points, a repeated boundary vertex, overlapping or crossing edges, or zero
    area. Checks apply to the exact converted floats, with no snapping tolerance.
    """
    loop = [(float(x), float(y)) for x, y in points]
    for x, y in loop:
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("profile points must be finite numbers")
    if len(loop) > 1 and loop[0] == loop[-1]:
        loop.pop()
    if len(set(loop)) < 3:
        raise ValueError("a closed profile needs at least three distinct points")
    _validate_simple_area(loop)
    return loop
