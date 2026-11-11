"""Export closed 2D sketch loops as IFC4 profile definitions.

IfcOpenShell is optional. The addon does not import it at load time, so this
module can be imported without it. Only the functions that write IFC need it,
and they raise IfcOpenShellMissing when it is not installed.
"""

import math
from collections.abc import Sequence
from fractions import Fraction

Point2D = tuple[float, float]


class IfcOpenShellMissing(RuntimeError):
    """Raised when an IFC export is requested without the ifcopenshell package."""


def _ifcopenshell():
    try:
        import ifcopenshell
    except ImportError as exc:
        raise IfcOpenShellMissing(
            "IFC export needs the 'ifcopenshell' Python package"
        ) from exc
    return ifcopenshell


def is_available() -> bool:
    """Return True when ifcopenshell can be imported."""
    try:
        _ifcopenshell()
    except IfcOpenShellMissing:
        return False
    return True


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


def add_arbitrary_profile(ifc_file, name: str, points: Sequence[Point2D]):
    """Add an IfcArbitraryClosedProfileDef (AREA) to an open ifcopenshell file."""
    loop = closed_loop_points(points)
    cartesian = [ifc_file.createIfcCartesianPoint(p) for p in loop]
    cartesian.append(cartesian[0])
    polyline = ifc_file.createIfcPolyline(cartesian)
    return ifc_file.createIfcArbitraryClosedProfileDef("AREA", name, polyline)


def write_profiles(path: str, profiles: Sequence[tuple[str, Sequence[Point2D]]]) -> str:
    """Write one IFC4 file holding a profile definition per (name, points) pair."""
    ifc = _ifcopenshell()
    ifc_file = ifc.file(schema="IFC4")
    for name, points in profiles:
        add_arbitrary_profile(ifc_file, name, points)
    ifc_file.write(path)
    return path
