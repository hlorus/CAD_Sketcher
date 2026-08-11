import logging

from bpy.types import PropertyGroup
from .sketch_ref import get_active_sketch
from bpy.props import StringProperty
from bpy.utils import register_classes_factory

from ..curve_solver import Solver
from ..global_data import WpReq
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer, make_coincident, get_connection_point
from .categories import CURVE
from .line_2d import SlvsLine2D
from .arc import SlvsArc
from .circle import SlvsCircle

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


class SlvsTangent(GenericConstraint, PropertyGroup):
    """Forces two curves (arc/circle) or a curve and a line to be tangent."""

    type = "TANGENT"
    label = "Tangent"
    signature = (CURVE, (SlvsLine2D, *CURVE))

    curve_id_1: StringProperty(name="Curve ID 1", default="")
    curve_id_2: StringProperty(name="Curve ID 2", default="")

    def create_slvs_data_from_curves(self, solvesys, handle_map, wp, group):
        from ..utilities.curve_data import get_curve_data, get_curve_position, get_uuid
        from ..model.constants import SketchCurveType
        import bpy

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

        if is_curve1 and is_line2:
            # Curve-line tangent
            ct_id = get_uuid(cd1, "center_point_id", idx1)
            ct_handle = handle_map.get(ct_id)
            sp_id = get_uuid(cd2, "start_point_id", idx2)
            ep_id = get_uuid(cd2, "end_point_id", idx2)

            ct_pos = get_curve_position(sketch, ct_id)
            sp_pos = get_curve_position(sketch, sp_id)
            ep_pos = get_curve_position(sketch, ep_id)
            if not all((ct_handle, ct_pos, sp_pos, ep_pos)):
                return None

            from mathutils import Vector
            orig = Vector(sp_pos[:2])
            coords = (Vector(ct_pos[:2]) - orig).project(Vector(ep_pos[:2]) - orig) + orig
            p = solvesys.add_point_2d(group, coords.x, coords.y, wp)
            line = solvesys.add_line_2d(group, ct_handle, p, wp)
            return (
                solvesys.coincident(group, p, h1, wp),
                solvesys.coincident(group, p, h2, wp),
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

            from mathutils import Vector
            curve1 = cd1.curves[idx1]
            curve2 = cd2.curves[idx2]
            edge1 = Vector(cd1.points[curve1.points[0].index].position[:2])
            edge2 = Vector(cd2.points[curve2.points[0].index].position[:2])
            radius1 = (edge1 - Vector(ct1_pos[:2])).length
            radius2 = (edge2 - Vector(ct2_pos[:2])).length
            coords = _curve_curve_tangent_seed(
                ct1_pos, ct2_pos, radius1, radius2
            )
            p = solvesys.add_point_2d(group, coords.x, coords.y, wp)
            line = solvesys.add_line_2d(group, ct1_handle, ct2_handle, wp)
            return (
                solvesys.coincident(group, p, h1, wp),
                solvesys.coincident(group, p, h2, wp),
                solvesys.coincident(group, p, line, wp),
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
                solvesys.coincident(group, p, line, wp)
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
            cid for cid in (getattr(self, "curve_id_1", ""),
                            getattr(self, "curve_id_2", ""),
                            getattr(self, "curve_id_3", "")) if cid
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
        curved = next(
            (r for r in (r1, r2) if getattr(r, "ct", None) is not None), None
        )
        line = next(
            (r for r in (r1, r2)
             if r is not curved
             and getattr(r, "ct", None) is None
             and getattr(r, "p1", None) is not None),
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
