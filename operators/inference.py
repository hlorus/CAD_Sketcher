"""Constraints inferred from how a new segment meets the ones it joins.

Drawing a chain leaves segments connected but free to pivot: the arc that
continues a line smoothly stays smooth only by accident, and the line drawn
square to the last one is square only until something moves. What the joint looks
like is read here and turned into the constraint it suggests -- tangent where a
curve continues smoothly, parallel or perpendicular between two lines.

Only proposals come out of this module. The caller offers each to
``add_auto_constraint``, which keeps one only while it both solves and takes a
degree of freedom away, so nothing here can over-constrain a sketch.
"""

import math
from typing import Iterator, Optional, Tuple

from ..model.curve_ref import ArcRef, CircleRef, CurveRef
from ..utilities.topology import SketchTopology

# As wide as the axis alignment's tolerance (see add_line_2d._alignment): what
# reads on screen as meant to line up rather than nearly doing so.
THRESHOLD = 0.1
_ALIGNED = math.cos(THRESHOLD)
_SQUARE = math.sin(THRESHOLD)

TANGENT = "TANGENT"
PARALLEL = "PARALLEL"
PERPENDICULAR = "PERPENDICULAR"


def _is_curved(ref: CurveRef) -> bool:
    return isinstance(ref, (ArcRef, CircleRef))


def relation_for(ref: CurveRef, other: CurveRef, alignment: float) -> Optional[str]:
    """The constraint an ``alignment`` between two segments suggests, or None.

    ``alignment`` is ``abs(cos)`` between the directions the two run in at their
    shared point, so it says how aligned they are without caring which way along
    either of them that is.
    """
    if alignment >= _ALIGNED:
        # A curve carrying on smoothly is a tangency; two lines running the same
        # way are parallel (sharing a point, that makes them collinear).
        return TANGENT if _is_curved(ref) or _is_curved(other) else PARALLEL
    if alignment <= _SQUARE and not (_is_curved(ref) or _is_curved(other)):
        # Perpendicular is a line-to-line constraint; a curve has none.
        return PERPENDICULAR
    return None


def ordered_for(relation: str, ref: CurveRef, other: CurveRef) -> Tuple[str, str]:
    """The two curve ids in the order that constraint takes them.

    A tangency is declared on the curve first (``SlvsTangent.signature``), so a
    line tangent to an arc is stored as the arc and then the line. Solvespace
    aborts the whole of Blender on a constraint whose arguments are of the wrong
    kind, so this is not a cosmetic detail.
    """
    if relation == TANGENT and not _is_curved(ref) and _is_curved(other):
        return other.curve_id, ref.curve_id
    return ref.curve_id, other.curve_id


def joint_relations(sketch, ref: CurveRef) -> Iterator[Tuple[str, CurveRef]]:
    """What the joints of ``ref`` suggest, as ``(relation, other segment)``.

    Only segments that share a point with ``ref`` are considered: a joint is what
    makes the relation obvious, and it is what the user just drew.
    """
    if ref is None or not ref.valid or not sketch:
        return
    topology = SketchTopology(sketch)
    seen = set()
    for point in topology.connection_points(ref):
        point_id = point.curve_id
        direction = topology.direction_at_point(ref, point_id)
        if direction.length < 1e-9:
            continue
        for other, _end in topology.get_connected_segments(point_id):
            if other.curve_id == ref.curve_id or not other.valid:
                continue
            other_direction = topology.direction_at_point(other, point_id)
            if other_direction.length < 1e-9:
                continue
            relation = relation_for(
                ref,
                other,
                abs(direction.normalized().dot(other_direction.normalized())),
            )
            if relation is None or (relation, other.curve_id) in seen:
                continue
            seen.add((relation, other.curve_id))
            yield relation, other


def relation_adders(constraints) -> dict:
    """Map a relation to the collection's adder for it."""
    return {
        TANGENT: constraints.add_tangent,
        PARALLEL: constraints.add_parallel,
        PERPENDICULAR: constraints.add_perpendicular,
    }
