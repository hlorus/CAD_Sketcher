"""Read closed straight-sided IFC profiles from the current sketch model.

This reader does not create curves, run the solver, or change the sketch. It
uses endpoint identity and explicit point-coincidence constraints, never a
distance-based weld that could join unrelated geometry at a different scale.
"""

from collections import defaultdict
from fractions import Fraction
from typing import TYPE_CHECKING

from ..model.curve_ref import PointRef, curve_ref
from .curve_data import read_uuid_list
from .ifc_export import Point2D, _segments_intersect, closed_loop_points

if TYPE_CHECKING:
    from ..model.sketch_ref import Sketch


def _contains(loop, p) -> bool:
    inside = False
    for a, b in zip(loop, loop[1:] + loop[:1]):
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if p[0] < x:
                inside = not inside
    return inside


def _check_separate_profiles(loops: list[list[Point2D]]) -> None:
    # Each loop is a separate solid profile. Nested rings would require
    # IfcArbitraryProfileDefWithVoids; exporting each as solid loses the hole.
    exact = [
        [(Fraction.from_float(x), Fraction.from_float(y)) for x, y in loop]
        for loop in loops
    ]
    for i, first in enumerate(exact):
        for second in exact[i + 1 :]:
            if any(
                _segments_intersect(a, b, c, d)
                for a, b in zip(first, first[1:] + first[:1])
                for c, d in zip(second, second[1:] + second[:1])
            ):
                raise ValueError(
                    "Profile outlines intersect or touch; separate them before export"
                )
            if _contains(first, second[0]) or _contains(second, first[0]):
                raise ValueError(
                    "Profiles with holes are not supported by this straight-profile export"
                )


def sketch_profiles(sketch: "Sketch") -> list[tuple[str, list[Point2D]]]:
    """Return named, disjoint closed line profiles in the sketch's local frame.

    Construction geometry and standalone points are ignored. Reject unsupported
    geometry before returning anything, so an export never silently omits part
    of the active sketch. Coordinates retain Blender scene units; the file
    writer is responsible for assigning and converting the IFC length unit.
    """
    if sketch.is_3d:
        raise ValueError("IFC area profiles need a two-dimensional sketch")
    if not sketch.geometry_solved or sketch.solver_state != "OKAY":
        raise ValueError("Solve the sketch successfully before exporting its profiles")
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
    adjacent = defaultdict(list)
    coordinates = {}
    for cid in curve_ids:
        if not cid:
            continue
        ref = curve_ref(sketch, cid)
        if ref.is_point() or ref.construction:
            continue
        if not ref.is_line():
            raise ValueError(
                "Only straight-line profiles are supported; arcs and circles need a curved-profile exporter"
            )
        start, end = ref.p1, ref.p2
        if start is None or end is None or not start.valid or not end.valid:
            raise ValueError("A profile line has a missing endpoint")
        if start.curve_id not in parent or end.curve_id not in parent:
            raise ValueError("A profile line endpoint does not reference a point")
        a, b = root(start.curve_id), root(end.curve_id)
        if a == b:
            raise ValueError("A profile line starts and ends at the same point")
        edges[cid] = (a, b)
        adjacent[a].append(cid)
        adjacent[b].append(cid)
        for point_id in (a, b):
            coordinates.setdefault(point_id, tuple(PointRef(sketch, point_id).co))

    if not edges:
        raise ValueError("The active sketch has no straight-line profile to export")
    if any(len(segments) != 2 for segments in adjacent.values()):
        raise ValueError(
            "Every profile must be closed and unbranched; join its endpoints or mark extra lines as construction"
        )

    remaining = set(edges)
    loops = []
    # Curve storage order gives stable profile names even though UUID values are
    # unrelated to drawing order.
    for first_edge in edges:
        if first_edge not in remaining:
            continue
        first_point = edges[first_edge][0]
        point, edge = first_point, first_edge
        loop = []
        while True:
            loop.append(coordinates[point])
            remaining.remove(edge)
            a, b = edges[edge]
            point = b if point == a else a
            if point == first_point:
                break
            edge = next((cid for cid in adjacent[point] if cid in remaining), None)
            if edge is None:
                raise ValueError("A profile path could not be closed")
        loops.append(closed_loop_points(loop))

    _check_separate_profiles(loops)
    return [
        (sketch.name if len(loops) == 1 else f"{sketch.name} {i + 1}", loop)
        for i, loop in enumerate(loops)
    ]
