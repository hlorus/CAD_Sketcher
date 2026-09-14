import logging

from bpy.props import StringProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..curve_solver import Solver
from ..global_data import WpReq
from .arc import SlvsArc
from .base_constraint import GenericConstraint
from .categories import CURVE
from .circle import SlvsCircle
from .line_2d import SlvsLine2D
from .utilities import make_coincident, point_on_line, slvs_entity_pointer

logger = logging.getLogger(__name__)


def _curve_curve_tangent_seed(center1, center2, radius1, radius2):
    """Return the closest current axial contact point for two circles/arcs.

    The solver's auxiliary point may converge to either the external or the
    internal tangent branch.  Seeding it at the midpoint of the two centres
    biases unequal-radius curves toward a large jump.  Instead, compare the
    two radial points on each curve that lie on the centre line and seed from
    the pair that is already closest in the current geometry.
    """
    from mathutils import Vector

    c1 = Vector(center1[:2])
    c2 = Vector(center2[:2])
    axis = c2 - c1
    if axis.length_squared < 1e-12:
        return (c1 + c2) / 2

    direction = axis.normalized()
    points1 = (c1 + direction * radius1, c1 - direction * radius1)
    points2 = (c2 + direction * radius2, c2 - direction * radius2)
    p1, p2 = min(
        ((a, b) for a in points1 for b in points2),
        key=lambda pair: (pair[0] - pair[1]).length_squared,
    )
    return (p1 + p2) / 2


def _known_tangent_point(sketch, on_first, on_second):
    """A point curve already constrained onto both curves, or None.

    ``on_first``/``on_second`` are ``(curve_id, point_ids)`` pairs, the point ids
    being those that lie on the curve structurally (its own endpoints). Points put on a curve by a
    coincident constraint count too, and coincident points are interchangeable.
    Solving tangency through a separate helper point would duplicate those
    constraints at the tangent point, which solvespace reports as redundant.
    """
    from ..utilities.curve_data import get_curve_type
    from .constants import SketchCurveType

    first_id, first_points = on_first
    second_id, second_points = on_second
    first_points = {point_id for point_id in first_points if point_id}
    second_points = {point_id for point_id in second_points if point_id}

    sketch_obj = getattr(sketch, "target_object", None)
    data = getattr(sketch_obj, "data", None)
    constraints = getattr(data, "sketch_constraints", None)
    # Coincident points share one solver position; group them so a point on one
    # curve matches its partner on the other.
    partner = {}

    def root(point_id):
        while partner.get(point_id, point_id) != point_id:
            point_id = partner[point_id]
        return point_id

    if constraints is not None:
        for c in constraints.all:
            if getattr(c, "type", "") != "COINCIDENT":
                continue
            a, b = c.curve_id_1, c.curve_id_2
            if not a or not b:
                continue
            if b == first_id:
                first_points.add(a)
            elif b == second_id:
                second_points.add(a)
            elif get_curve_type(sketch, b) == SketchCurveType.POINT:
                partner[root(a)] = root(b)

    second_roots = {root(point_id) for point_id in second_points}
    for point_id in sorted(first_points):
        if root(point_id) in second_roots:
            return point_id
    return None


class SlvsTangent(GenericConstraint, PropertyGroup):
    """Forces two curves (arc/circle) or a curve and a line to be tangent."""

    type = "TANGENT"
    label = "Tangent"
    signature = (CURVE, (SlvsLine2D, *CURVE))

    curve_id_1: StringProperty(name="Curve ID 1", default="")
    curve_id_2: StringProperty(name="Curve ID 2", default="")

    def create_slvs_data_from_curves(self, solvesys, handle_map, wp, group):

        from ..model.constants import SketchCurveType
        from ..utilities.curve_data import get_curve_data, get_curve_position, get_uuid

        h1 = handle_map.get(self.curve_id_1)
        h2 = handle_map.get(self.curve_id_2)
        if h1 is None or h2 is None:
            return None

        sketch = self._get_sketch()
        cd1, idx1, _ = get_curve_data(sketch, self.curve_id_1)
        cd2, idx2, _ = get_curve_data(sketch, self.curve_id_2)
        if cd1 is None or cd2 is None:
            return None

        type_attr = cd1.attributes.get("sketch_type")

        t1 = type_attr.data[idx1].value
        t2 = type_attr.data[idx2].value

        is_curve1 = t1 in (SketchCurveType.ARC, SketchCurveType.CIRCLE)
        is_curve2 = t2 in (SketchCurveType.ARC, SketchCurveType.CIRCLE)
        is_line2 = t2 == SketchCurveType.LINE

        def endpoints(curve_data, idx):
            return (
                get_uuid(curve_data, "start_point_id", idx),
                get_uuid(curve_data, "end_point_id", idx),
            )

        # An arc's own endpoints lie on it; a circle has none.
        on_curve1 = endpoints(cd1, idx1) if t1 == SketchCurveType.ARC else ()

        if is_curve1 and is_line2:
            # Curve-line tangent
            ct_id = get_uuid(cd1, "center_point_id", idx1)
            ct_handle = handle_map.get(ct_id)
            sp_id, ep_id = endpoints(cd2, idx2)

            ct_pos = get_curve_position(sketch, ct_id)
            sp_pos = get_curve_position(sketch, sp_id)
            ep_pos = get_curve_position(sketch, ep_id)
            if not all((ct_handle, ct_pos, sp_pos, ep_pos)):
                return None

            # A point already on both (e.g. a fillet's shared endpoint) is the
            # tangent point: the radius to it must be perpendicular to the line.
            tangent_id = _known_tangent_point(
                sketch,
                (self.curve_id_1, on_curve1),
                (self.curve_id_2, (sp_id, ep_id)),
            )
            tangent_handle = handle_map.get(tangent_id) if tangent_id else None
            if tangent_handle:
                radius = solvesys.add_line_2d(group, ct_handle, tangent_handle, wp)
                return solvesys.perpendicular(group, h2, radius, workplane=wp)

            from mathutils import Vector

            orig = Vector(sp_pos[:2])
            coords = (Vector(ct_pos[:2]) - orig).project(
                Vector(ep_pos[:2]) - orig
            ) + orig
            p = solvesys.add_point_2d(group, coords.x, coords.y, wp)
            line = solvesys.add_line_2d(group, ct_handle, p, wp)
            return (
                solvesys.coincident(group, p, h1, wp),
                point_on_line(solvesys, group, p, h2, wp, sp_pos, ep_pos),
                solvesys.perpendicular(group, h2, line, workplane=wp),
            )

        elif is_curve1 and is_curve2:
            # Curve-curve tangent
            ct1_id = get_uuid(cd1, "center_point_id", idx1)
            ct2_id = get_uuid(cd2, "center_point_id", idx2)
            ct1_handle = handle_map.get(ct1_id)
            ct2_handle = handle_map.get(ct2_id)
            ct1_pos = get_curve_position(sketch, ct1_id)
            ct2_pos = get_curve_position(sketch, ct2_id)
            if not all((ct1_handle, ct2_handle, ct1_pos, ct2_pos)):
                return None

            line = solvesys.add_line_2d(group, ct1_handle, ct2_handle, wp)

            # A point already on both curves is the tangent point, which then
            # only has to lie on the line through the centres.
            on_curve2 = endpoints(cd2, idx2) if t2 == SketchCurveType.ARC else ()
            tangent_id = _known_tangent_point(
                sketch, (self.curve_id_1, on_curve1), (self.curve_id_2, on_curve2)
            )
            tangent_handle = handle_map.get(tangent_id) if tangent_id else None
            if tangent_handle:
                return point_on_line(
                    solvesys, group, tangent_handle, line, wp, ct1_pos, ct2_pos
                )

            from mathutils import Vector

            curve1 = cd1.curves[idx1]
            curve2 = cd2.curves[idx2]
            edge1 = Vector(cd1.points[curve1.points[0].index].position[:2])
            edge2 = Vector(cd2.points[curve2.points[0].index].position[:2])
            radius1 = (edge1 - Vector(ct1_pos[:2])).length
            radius2 = (edge2 - Vector(ct2_pos[:2])).length
            coords = _curve_curve_tangent_seed(ct1_pos, ct2_pos, radius1, radius2)
            p = solvesys.add_point_2d(group, coords.x, coords.y, wp)
            return (
                solvesys.coincident(group, p, h1, wp),
                solvesys.coincident(group, p, h2, wp),
                point_on_line(solvesys, group, p, line, wp, ct1_pos, ct2_pos),
            )

        # Simple tangent
        return solvesys.tangent(group, h2, h1, wp)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2 = self.entity1, self.entity2
        wp = self.get_workplane()

        CIRCLE_ARC = (SlvsCircle, SlvsArc)
        if type(e1) in CIRCLE_ARC and e2.is_line():
            orig = e2.p1.co
            coords = (e1.ct.co - orig).project(e2.p2.co - orig) + orig
            p = solvesys.add_point_2d(group, *coords, wp)
            line = solvesys.add_line_2d(group, e1.ct.py_data, p, wp)
            return (
                make_coincident(solvesys, p, e1, wp, group),
                make_coincident(solvesys, p, e2, wp, group),
                solvesys.perpendicular(group, e2.py_data, line, workplane=wp),
            )
        elif type(e1) in CIRCLE_ARC and type(e2) in CIRCLE_ARC:
            coords = (e1.ct.co + e2.ct.co) / 2
            p = solvesys.add_point_2d(group, *coords, wp)
            line = solvesys.add_line_2d(group, e1.ct.py_data, e2.ct.py_data, wp)

            return (
                make_coincident(solvesys, p, e1, wp, group),
                make_coincident(solvesys, p, e2, wp, group),
                solvesys.coincident(group, p, line, wp),
            )

        return solvesys.tangent(group, e2.py_data, e1.py_data, wp)

    def placements(self):
        return (self.ref(1), self.ref(2))

    def curve_id_placements(self):
        """Show a single tangent marker at the tangent point.

        The default would draw an icon on every referenced curve (line *and*
        arc), giving two markers. Place it once at the curved side, whose
        placement is its start point -- the tangent point when the two share a
        coincident endpoint.
        """
        from ..utilities.curve_data import get_curve_type
        from .constants import SketchCurveType

        ids = [
            cid
            for cid in (
                getattr(self, "curve_id_1", ""),
                getattr(self, "curve_id_2", ""),
                getattr(self, "curve_id_3", ""),
            )
            if cid
        ]
        if not ids:
            return []
        sketch = self._get_sketch()
        if sketch:
            for cid in ids:
                if get_curve_type(sketch, cid) in (
                    SketchCurveType.ARC,
                    SketchCurveType.CIRCLE,
                ):
                    return [cid]
        return ids[:1]

    def marker_position(self, sketch):
        """Tangent point of a line + arc/circle: the foot of the perpendicular
        from the curved element's center onto the line (drawing-direction
        independent). Returns None for other combinations."""
        from mathutils import Vector

        r1, r2 = self.ref(1), self.ref(2)
        if not r1 or not r2:
            return None

        # The curved element (arc/circle) exposes a center point as `ct`; the
        # line does not. Arc refs also alias p1/p2, so identify the line by the
        # *absence* of a center.
        curved = next((r for r in (r1, r2) if getattr(r, "ct", None) is not None), None)
        line = next(
            (
                r
                for r in (r1, r2)
                if r is not curved
                and getattr(r, "ct", None) is None
                and getattr(r, "p1", None) is not None
            ),
            None,
        )
        if curved is None or line is None:
            return None

        p1, p2, center = line.p1, line.p2, curved.ct
        if p1 is None or p2 is None or center is None:
            return None

        a = Vector(p1.co[:2])
        b = Vector(p2.co[:2])
        c = Vector(center.co[:2])
        ab = b - a
        if ab.length_squared < 1e-12:
            return None
        t = (c - a).dot(ab) / ab.length_squared
        foot = a + t * ab  # perpendicular foot on the (infinite) line = tangent point
        return sketch.target_object.matrix_world @ foot.to_3d()


slvs_entity_pointer(SlvsTangent, "entity1")
slvs_entity_pointer(SlvsTangent, "entity2")
slvs_entity_pointer(SlvsTangent, "sketch")

register, unregister = register_classes_factory((SlvsTangent,))
