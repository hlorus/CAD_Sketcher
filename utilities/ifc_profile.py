"""Analytic local-plane profile boundaries, containment and IFC curve creation.

Circles and arcs retain their native centre, radius and angular span. Geometry
is never tessellated to classify holes or write IFC. Endpoint connectivity is
established by the sketch reader, not by this module's numerical comparisons.
"""

import math
from dataclasses import dataclass
from fractions import Fraction
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import ifcopenshell

from .ifc_export import Point2D, _on_segment, closed_loop_points

IFC_PRECISION = 1e-8


@dataclass(frozen=True)
class Line:
    """An oriented straight segment in the profile's local coordinate frame."""

    start: Point2D
    end: Point2D


@dataclass(frozen=True)
class Circle:
    """A complete circular boundary with its original center and radius."""

    center: Point2D
    radius: float


@dataclass(frozen=True)
class Arc:
    """An oriented circular arc; positive sweep is counterclockwise."""

    center: Point2D
    radius: float
    start_angle: float
    sweep: float

    def point(self, fraction: float) -> Point2D:
        """Evaluate the analytic arc at a fraction of its signed sweep."""
        angle = self.start_angle + fraction * self.sweep
        return (
            self.center[0] + self.radius * math.cos(angle),
            self.center[1] + self.radius * math.sin(angle),
        )

    @property
    def start(self) -> Point2D:
        """Return the analytic point at the start angle."""
        return self.point(0.0)

    @property
    def end(self) -> Point2D:
        """Return the analytic point at the end of the signed sweep."""
        return self.point(1.0)

    def reversed(self) -> "Arc":
        """Return the same geometric arc with its traversal direction reversed."""
        return Arc(self.center, self.radius, self.start_angle + self.sweep, -self.sweep)


Segment = Line | Arc
Boundary = Circle | tuple[Segment, ...]


@dataclass(frozen=True)
class Profile:
    """A named area boundary and its directly contained void boundaries."""

    name: str
    outer: Boundary
    holes: tuple[Boundary, ...] = ()


def _parts(boundary: Boundary) -> tuple[Line | Arc | Circle, ...]:
    return (boundary,) if isinstance(boundary, Circle) else boundary


def _point(boundary: Boundary) -> Point2D:
    if isinstance(boundary, Circle):
        return (boundary.center[0] + boundary.radius, boundary.center[1])
    return boundary[0].start


def _epsilon(*parts: Line | Arc | Circle) -> float:
    # Roundoff allowance only, never a weld or a user-coordinate snapping rule.
    values = []
    for part in parts:
        if isinstance(part, Line):
            values.extend((*part.start, *part.end))
        else:
            values.extend((*part.center, part.radius))
    return 64 * max(math.ulp(abs(value)) for value in values)


def _arc_has_angle(arc: Arc, angle: float, *, strict: bool = False) -> bool:
    distance = (
        (angle - arc.start_angle) % math.tau
        if arc.sweep > 0
        else (arc.start_angle - angle) % math.tau
    )
    epsilon = 64 * math.ulp(math.tau)
    if math.tau - distance <= epsilon:
        distance = 0.0
    if strict:
        return epsilon < distance < abs(arc.sweep) - epsilon
    return distance <= abs(arc.sweep) + epsilon


def _on_curve(part: Arc | Circle, point: Point2D) -> bool:
    return isinstance(part, Circle) or _arc_has_angle(
        part, math.atan2(point[1] - part.center[1], point[0] - part.center[0])
    )


def _line_intersections(first: Line, second: Line) -> tuple[list[Point2D], bool]:
    # Preserve exact binary-float topology for the existing polygon course.
    a, b, c, d = [
        tuple(Fraction.from_float(float(value)) for value in point)
        for point in (first.start, first.end, second.start, second.end)
    ]
    dx, dy = b[0] - a[0], b[1] - a[1]
    ex, ey = d[0] - c[0], d[1] - c[1]
    denominator = dx * ey - dy * ex
    if denominator:
        t = ((c[0] - a[0]) * ey - (c[1] - a[1]) * ex) / denominator
        u = ((c[0] - a[0]) * dy - (c[1] - a[1]) * dx) / denominator
        if 0 <= t <= 1 and 0 <= u <= 1:
            return [(float(a[0] + t * dx), float(a[1] + t * dy))], False
        return [], False
    points = set()
    for point in (a, b, c, d):
        if _on_segment(a, b, point) and _on_segment(c, d, point):
            points.add((float(point[0]), float(point[1])))
    return list(points), len(points) > 1


def _line_circle(line: Line, curve: Arc | Circle) -> list[Point2D]:
    dx, dy = line.end[0] - line.start[0], line.end[1] - line.start[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    cx, cy = curve.center[0] - line.start[0], curve.center[1] - line.start[1]
    along = cx * ux + cy * uy
    perpendicular = cx * uy - cy * ux
    clearance = curve.radius - abs(perpendicular)
    epsilon = _epsilon(line, curve)
    if clearance < -epsilon:
        return []
    half_chord = math.sqrt(max(0.0, clearance * (curve.radius + abs(perpendicular))))
    points = []
    for distance in (along - half_chord, along + half_chord):
        if -epsilon <= distance <= length + epsilon:
            point = (line.start[0] + distance * ux, line.start[1] + distance * uy)
            if _on_curve(curve, point):
                points.append(point)
    return points


def _circle_intersections(
    first: Arc | Circle, second: Arc | Circle
) -> tuple[list[Point2D], bool]:
    dx, dy = second.center[0] - first.center[0], second.center[1] - first.center[1]
    distance = math.hypot(dx, dy)
    epsilon = _epsilon(first, second)
    if distance <= epsilon and abs(first.radius - second.radius) <= epsilon:
        if isinstance(first, Circle) or isinstance(second, Circle):
            return [], True
        # Coincident arc bases can share endpoints, but no interior interval.
        for a, b in ((first, second), (second, first)):
            if any(
                _arc_has_angle(
                    b,
                    math.atan2(point[1] - b.center[1], point[0] - b.center[0]),
                    strict=True,
                )
                for point in (a.start, a.point(0.5), a.end)
            ):
                return [], True
        return [
            point for point in (first.start, first.end) if _on_curve(second, point)
        ], False
    if (
        distance > first.radius + second.radius + epsilon
        or distance < abs(first.radius - second.radius) - epsilon
        or distance == 0
    ):
        return [], False
    along = (
        (first.radius - second.radius) * (first.radius + second.radius)
        + distance * distance
    ) / (2 * distance)
    height_squared = (first.radius - along) * (first.radius + along)
    if height_squared < -epsilon * max(first.radius, second.radius):
        return [], False
    height = math.sqrt(max(0.0, height_squared))
    ux, uy = dx / distance, dy / distance
    base = (first.center[0] + along * ux, first.center[1] + along * uy)
    points = [
        (base[0] - height * uy, base[1] + height * ux),
        (base[0] + height * uy, base[1] - height * ux),
    ]
    return [
        point
        for point in points
        if _on_curve(first, point) and _on_curve(second, point)
    ], False


def _intersections(
    first: Line | Arc | Circle, second: Line | Arc | Circle
) -> tuple[list[Point2D], bool]:
    if isinstance(first, Line):
        if isinstance(second, Line):
            return _line_intersections(first, second)
        return _line_circle(first, second), False
    if isinstance(second, Line):
        return _line_circle(second, first), False
    return _circle_intersections(first, second)


def _validate_part(part: Line | Arc | Circle) -> None:
    if isinstance(part, Line):
        if not all(
            math.isfinite(value) for point in (part.start, part.end) for value in point
        ):
            raise ValueError("profile points must be finite numbers")
        if part.start == part.end:
            raise ValueError("a profile segment has zero length")
        return
    if not all(math.isfinite(value) for value in (*part.center, part.radius)):
        raise ValueError("profile circle coordinates and radii must be finite")
    if part.radius <= 0:
        raise ValueError("a profile circle must have a positive radius")
    if not math.isfinite(part.radius * part.radius) or part.radius * part.radius == 0:
        raise ValueError("profile radius is outside the supported numerical range")
    if not all(
        math.isfinite(value + offset)
        for value in part.center
        for offset in (-part.radius, part.radius)
    ):
        raise ValueError("profile circle bounds must be finite")
    if isinstance(part, Arc) and (
        not math.isfinite(part.start_angle)
        or not math.isfinite(part.sweep)
        or not 0 < abs(part.sweep) < math.tau
    ):
        raise ValueError(
            "a profile arc must have a finite, nonzero span below one turn"
        )


def _validate_boundary(boundary: Boundary, join_tolerance: float) -> None:
    parts = _parts(boundary)
    if not parts:
        raise ValueError("a profile boundary cannot be empty")
    for part in parts:
        _validate_part(part)
    if isinstance(boundary, Circle):
        return
    for first, second in zip(parts, parts[1:] + parts[:1]):
        # Topological joins have already been established by point identity.
        # A native float32 arc endpoint can differ from its analytic circle by
        # roundoff. The writer permits at most the IFC context precision.
        if math.dist(first.end, second.start) > join_tolerance:
            raise ValueError(
                "connected profile segments do not meet within IFC precision"
            )
    if all(isinstance(part, Line) for part in parts):
        closed_loop_points([part.start for part in parts])
        return
    origin = parts[0].start
    terms = []
    for part in parts:
        sx, sy = part.start[0] - origin[0], part.start[1] - origin[1]
        ex, ey = part.end[0] - origin[0], part.end[1] - origin[1]
        if isinstance(part, Line):
            terms.append(sx * ey - ex * sy)
        else:
            cx, cy = part.center[0] - origin[0], part.center[1] - origin[1]
            terms.append(cx * (ey - sy) - cy * (ex - sx) + part.radius**2 * part.sweep)
    area = math.fsum(terms) / 2
    if not math.isfinite(area) or abs(area) <= max(_epsilon(*parts) ** 2, 0.0):
        raise ValueError("a closed profile must bound a finite nonzero area")
    for i, first in enumerate(parts):
        for j in range(i + 1, len(parts)):
            second = parts[j]
            allowed = []
            if j == i + 1:
                allowed.append(first.end)
            if i == 0 and j == len(parts) - 1:
                allowed.append(first.start)
            points, overlap = _intersections(first, second)
            if overlap or any(
                not any(math.dist(point, join) <= join_tolerance for join in allowed)
                for point in points
            ):
                raise ValueError("profile boundary intersects or overlaps itself")


def _contains(boundary: Boundary, point: Point2D) -> bool:
    if isinstance(boundary, Circle):
        return math.dist(boundary.center, point) < boundary.radius
    if all(isinstance(part, Line) for part in boundary):
        # Keep the original exact polygon containment course as well as the
        # exact polygon intersection and area checks.
        x, y = map(Fraction.from_float, point)
        inside = False
        for part in boundary:
            ax, ay = map(Fraction.from_float, part.start)
            bx, by = map(Fraction.from_float, part.end)
            if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
                inside = not inside
        return inside
    # Rotate the ray away from vertices and tangent events. Intersections are
    # analytic line/circle roots; no sampled polygon changes the hole topology.
    for angle in (0.0, 0.371, 0.839, 1.213, 1.731, 2.117, 2.659, 2.971):
        co, si = math.cos(angle), math.sin(angle)

        def rotate(p: Point2D) -> Point2D:
            x, y = p[0] - point[0], p[1] - point[1]
            return (x * co + y * si, y * co - x * si)

        epsilon = _epsilon(*boundary)
        if any(
            abs(rotate(p)[1]) <= epsilon
            for part in boundary
            for p in (part.start, part.end)
        ):
            continue
        if any(
            isinstance(part, Arc)
            and abs(abs(rotate(part.center)[1]) - part.radius) <= epsilon
            for part in boundary
        ):
            continue
        crossings = 0
        for part in boundary:
            if isinstance(part, Line):
                a, b = rotate(part.start), rotate(part.end)
                if (a[1] > 0) != (b[1] > 0):
                    x = a[0] - a[1] * (b[0] - a[0]) / (b[1] - a[1])
                    crossings += x > 0
            else:
                cx, cy = rotate(part.center)
                ratio = -cy / part.radius
                if -1 < ratio < 1:
                    root = math.asin(ratio)
                    for theta in (root, math.pi - root):
                        if cx + part.radius * math.cos(theta) > 0 and _arc_has_angle(
                            part, theta + angle
                        ):
                            crossings += 1
        return bool(crossings % 2)
    raise ValueError("profile containment is numerically ambiguous")


def arrange_boundaries(
    boundaries: list[Boundary], *, join_tolerance: float = IFC_PRECISION
) -> list[tuple[int, tuple[int, ...]]]:
    """Validate analytic boundaries and return outer/direct-hole index groups.

    Odd nesting depth is empty space; an island inside a hole is a separate
    profile. Crossing, touching and coincident boundaries are rejected.
    """
    for boundary in boundaries:
        _validate_boundary(boundary, join_tolerance)
    containers = [set() for _ in boundaries]
    for i, first in enumerate(boundaries):
        for j in range(i + 1, len(boundaries)):
            second = boundaries[j]
            for a in _parts(first):
                for b in _parts(second):
                    points, overlap = _intersections(a, b)
                    if points or overlap:
                        raise ValueError(
                            "profile boundaries intersect, touch or overlap"
                        )
            if _contains(first, _point(second)):
                containers[j].add(i)
            if _contains(second, _point(first)):
                containers[i].add(j)
    depth = [len(parents) for parents in containers]
    return [
        (
            i,
            tuple(
                j
                for j, parents in enumerate(containers)
                if i in parents and depth[j] == depth[i] + 1
            ),
        )
        for i in range(len(boundaries))
        if depth[i] % 2 == 0
    ]


def scale_boundary(boundary: Boundary, scale: float) -> Boundary:
    """Scale coordinates and radii once, leaving arc angles unchanged."""

    def point(p: Point2D) -> Point2D:
        return (float(p[0]) * scale, float(p[1]) * scale)

    def part(curve: Line | Arc | Circle) -> Line | Arc | Circle:
        if isinstance(curve, Line):
            return Line(point(curve.start), point(curve.end))
        if isinstance(curve, Arc):
            return Arc(
                point(curve.center),
                curve.radius * scale,
                curve.start_angle,
                curve.sweep,
            )
        return Circle(point(curve.center), curve.radius * scale)

    return (
        part(boundary) if isinstance(boundary, Circle) else tuple(map(part, boundary))
    )


def add_profile(
    document: "ifcopenshell.file", profile: Profile
) -> "ifcopenshell.entity_instance":
    """Add one analytic IFC4 area profile, including all direct voids."""

    def circle(curve: Arc | Circle):
        center = document.createIfcCartesianPoint(tuple(map(float, curve.center)))
        position = document.createIfcAxis2Placement2D(center, None)
        return document.createIfcCircle(position, float(curve.radius))

    def polyline(points):
        return document.createIfcPolyline(
            [
                document.createIfcCartesianPoint(tuple(map(float, point)))
                for point in points
            ]
        )

    def boundary_curve(boundary: Boundary):
        if isinstance(boundary, Circle):
            return circle(boundary)
        if all(isinstance(part, Line) for part in boundary):
            return polyline([part.start for part in boundary] + [boundary[0].start])
        segments = []
        for part in boundary:
            if isinstance(part, Line):
                curve = polyline([part.start, part.end])
            else:
                curve = document.createIfcTrimmedCurve(
                    circle(part),
                    [
                        document.createIfcParameterValue(
                            float(part.start_angle % math.tau)
                        )
                    ],
                    [
                        document.createIfcParameterValue(
                            float((part.start_angle + part.sweep) % math.tau)
                        )
                    ],
                    part.sweep > 0,
                    "PARAMETER",
                )
            segments.append(
                document.createIfcCompositeCurveSegment("CONTINUOUS", True, curve)
            )
        return document.createIfcCompositeCurve(segments, False)

    outer = boundary_curve(profile.outer)
    if profile.holes:
        return document.createIfcArbitraryProfileDefWithVoids(
            "AREA",
            profile.name,
            outer,
            [boundary_curve(hole) for hole in profile.holes],
        )
    return document.createIfcArbitraryClosedProfileDef("AREA", profile.name, outer)
