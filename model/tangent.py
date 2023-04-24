import logging

from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..global_data import WpReq
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer, make_coincident, get_connection_point
from .categories import CURVE
from .line_2d import SlvsLine2D
from .arc import SlvsArc
from .circle import SlvsCircle

logger = logging.getLogger(__name__)


class SlvsTangent(GenericConstraint, PropertyGroup):
    """Forces two curves (arc/circle) or a curve and a line to be tangent."""

    type = "TANGENT"
    label = "Tangent"
    signature = (CURVE, (SlvsLine2D, *CURVE))

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2 = self.entity1, self.entity2
        wp = self.get_workplane()

        # check if entities share a point
        point = get_connection_point(e1, e2)
        if point and not isinstance(e2, SlvsCircle):
            if isinstance(e2, SlvsLine2D):
                return solvesys.addArcLineTangent(
                    e1.direction(point),
                    e1.py_data,
                    e2.py_data,
                    group=group,
                )
            elif isinstance(e2, SlvsArc):
                return solvesys.addCurvesTangent(
                    e1.direction(point),
                    e2.direction(point),
                    e1.py_data,
                    e2.py_data,
                    wrkpln=wp,
                    group=group,
                )

        elif isinstance(e2, SlvsLine2D):
            orig = e2.p1.co
            coords = (e1.ct.co - orig).project(e2.p2.co - orig) + orig
            params = [solvesys.addParamV(v, group) for v in coords]
            p = solvesys.addPoint2d(wp, *params, group=group)
            line = solvesys.addLineSegment(e1.ct.py_data, p, group=group)

            return (
                make_coincident(solvesys, p, e1, wp, group),
                make_coincident(solvesys, p, e2, wp, group),
                solvesys.addPerpendicular(e2.py_data, line, wrkpln=wp, group=group),
            )

        elif e2.is_curve():
            coords = (e1.ct.co + e2.ct.co) / 2
            params = [solvesys.addParamV(v, group) for v in coords]
            p = solvesys.addPoint2d(wp, *params, group=group)
            line = solvesys.addLineSegment(e1.ct.py_data, e2.ct.py_data, group=group)

            return (
                make_coincident(solvesys, p, e1, wp, group),
                make_coincident(solvesys, p, e2, wp, group),
                solvesys.addPointOnLine(p, line, group=group, wrkpln=wp),
            )

    def placements(self):
        point = get_connection_point(self.entity1, self.entity2)
        if point is None:
            return (self.entity1, self.entity2)
        return (point,)


slvs_entity_pointer(SlvsTangent, "entity1")
slvs_entity_pointer(SlvsTangent, "entity2")
slvs_entity_pointer(SlvsTangent, "sketch")

register, unregister = register_classes_factory((SlvsTangent,))
