"""Read analytic IFC profiles from the current sketch model without mutation.

Endpoint identity and explicit point-coincidence constraints establish paths.
Construction geometry is excluded; unrelated nearby endpoints are never welded.
"""

import math
from collections import defaultdict
from numbers import Real
from typing import TYPE_CHECKING

from ..model.curve_ref import PointRef, curve_ref
from .curve_data import read_uuid_list
from .ifc_profile import IFC_PRECISION, Arc, Circle, Line, Profile, arrange_boundaries

if TYPE_CHECKING:
    from ..model.sketch_ref import Sketch


def sketch_profiles(sketch: "Sketch", *, unit_scale: float = 1.0) -> list[Profile]:
    """Return named local-plane profiles with their directly contained holes.

    Coordinates and radii retain scene units. The unit scale only supplies the
    corresponding IFC join precision; the writer performs the sole conversion.
    No sketch data, solver state or native point relationships are changed.
    """
    if sketch.is_3d:
        raise ValueError("IFC area profiles need a two-dimensional sketch")
    if not sketch.geometry_solved or sketch.solver_state not in {
        "OKAY",
        "REDUNDANT_OK",
    }:
        raise ValueError("Solve the sketch successfully before exporting its profiles")
    if (
        isinstance(unit_scale, bool)
        or not isinstance(unit_scale, Real)
        or not math.isfinite(unit_scale)
        or unit_scale <= 0
    ):
        raise ValueError("scene unit scale must be a finite positive number")

    # Received from SCOUT's dba04 integration: omitting a placement may omit
    # rotation and translation, but must not silently omit scale or shear.
    basis = sketch.plane_matrix.to_3x3()
    x_axis, y_axis = basis.col[0], basis.col[1]
    x_length, y_length = x_axis.length, y_axis.length
    xy_dot = x_axis.dot(y_axis)
    if (
        not all(math.isfinite(value) for value in (x_length, y_length, xy_dot))
        or abs(x_length - 1.0) > 1e-6
        or abs(y_length - 1.0) > 1e-6
        or abs(xy_dot) > 1e-6
    ):
        raise ValueError(
            "IFC profile export cannot omit workplane scale or shear; "
            "use an unscaled, orthogonal workplane"
        )

    data = sketch.data
    curve_ids = read_uuid_list(data, "curve_id")
    point_ids = {cid for cid in curve_ids if cid and curve_ref(sketch, cid).is_point()}
    parent = {cid: cid for cid in point_ids}

    def root(cid: str) -> str:
        while parent[cid] != cid:
            parent[cid] = parent[parent[cid]]
            cid = parent[cid]
        return cid

    for constraint in sketch.constraints.coincident:
        a, b = constraint.curve_id_1, constraint.curve_id_2
        if a in parent and b in parent:
            parent[root(b)] = root(a)

    edges = {}
    geometry = {}
    adjacent = defaultdict(list)
    coordinates = {}
    standalone = {}
    for cid in curve_ids:
        if not cid:
            continue
        ref = curve_ref(sketch, cid)
        if ref.is_point() or ref.construction:
            continue
        if ref.is_circle() or ref.is_arc():
            center = ref.ct
            if center is None or not center.valid or center.curve_id not in parent:
                raise ValueError("A profile circle or arc has a missing center")
            center_co = tuple(map(float, center.co))
            if ref.is_circle():
                standalone[cid] = Circle(center_co, float(ref.radius))
                continue
            geometry[cid] = Arc(
                center_co, float(ref.radius), float(ref.start_angle), float(ref.angle)
            )
        elif not ref.is_line():
            raise ValueError(
                "Only lines, circular arcs and circles can form IFC profiles"
            )
        start, end = ref.p1, ref.p2
        if start is None or end is None or not start.valid or not end.valid:
            raise ValueError("A profile segment has a missing endpoint")
        if start.curve_id not in parent or end.curve_id not in parent:
            raise ValueError("A profile segment endpoint does not reference a point")
        a, b = root(start.curve_id), root(end.curve_id)
        if a == b:
            raise ValueError("A profile segment starts and ends at the same point")
        edges[cid] = (a, b)
        adjacent[a].append(cid)
        adjacent[b].append(cid)
        for point_id in (a, b):
            coordinates.setdefault(
                point_id, tuple(map(float, PointRef(sketch, point_id).co))
            )
        if ref.is_line():
            geometry[cid] = Line(coordinates[a], coordinates[b])

    if not edges and not standalone:
        raise ValueError("The active sketch has no closed profile to export")
    if any(len(segments) != 2 for segments in adjacent.values()):
        raise ValueError(
            "Every profile must be closed and unbranched; join its endpoints "
            "or mark extra segments as construction"
        )

    remaining = set(edges)
    boundaries = []
    # Walk curve storage order so profile names remain stable; containment does
    # not depend on which boundary (outer or hole) was drawn first.
    for first_edge in curve_ids:
        if first_edge in standalone:
            boundaries.append(standalone[first_edge])
            continue
        if first_edge not in remaining:
            continue
        first_point = edges[first_edge][0]
        point, edge = first_point, first_edge
        loop = []
        while True:
            a, b = edges[edge]
            part = geometry[edge]
            forward = point == a
            if not forward:
                part = (
                    Line(part.end, part.start)
                    if isinstance(part, Line)
                    else part.reversed()
                )
            loop.append(part)
            remaining.remove(edge)
            point = b if forward else a
            if point == first_point:
                break
            edge = next((cid for cid in adjacent[point] if cid in remaining), None)
            if edge is None:
                raise ValueError("A profile path could not be closed")
        boundaries.append(tuple(loop))

    groups = arrange_boundaries(
        boundaries, join_tolerance=IFC_PRECISION / float(unit_scale)
    )
    return [
        Profile(
            sketch.name if len(groups) == 1 else f"{sketch.name} {i + 1}",
            boundaries[outer],
            tuple(boundaries[hole] for hole in holes),
        )
        for i, (outer, holes) in enumerate(groups)
    ]
