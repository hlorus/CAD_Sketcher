import logging

from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..global_data import WpReq
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer, get_connection_point
from .categories import CURVE
from .line_2d import SlvsLine2D
from .arc import SlvsArc
from .circle import SlvsCircle
from .utilities import make_coincident

logger = logging.getLogger(__name__)


class SlvsTangent(GenericConstraint, PropertyGroup):
    """Forces two curves (arc/circle) or a curve and a line to be tangent."""

    type = "TANGENT"
    label = "Tangent"
    signature = (CURVE, (SlvsLine2D, *CURVE))

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys):
        e1, e2 = self.entity1, self.entity2
        wp = self.get_workplane()

        point = get_connection_point(e1, e2)
        if point and not isinstance(e2, SlvsCircle):
            if isinstance(e2, (SlvsLine2D, SlvsArc)):
                return solvesys.tangent(e1.py_data, e2.py_data, wp)
        elif isinstance(e2, SlvsLine2D):
            orig = e2.p1.co
            coords = (e1.ct.co - orig).project(e2.p2.co - orig) + orig
            p = solvesys.add_point_2d(*tuple(coords), wp)
            l = solvesys.add_line_2d(e1.ct.py_data, p, wp=wp)
            return (
                make_coincident(solvesys, p, e1, wp),
                make_coincident(solvesys, p, e2, wp),
                solvesys.perpendicular(e2.py_data, l, wp=wp),
            )

    def placements(self):
        point = get_connection_point(self.entity1, self.entity2)
        return (point,)


slvs_entity_pointer(SlvsTangent, "entity1")
slvs_entity_pointer(SlvsTangent, "entity2")
slvs_entity_pointer(SlvsTangent, "sketch")

register, unregister = register_classes_factory((SlvsTangent,))
