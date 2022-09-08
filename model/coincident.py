import logging

from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..global_data import WpReq
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer, make_coincident
from .categories import POINT, LINE
from .workplane import SlvsWorkplane
from .arc import SlvsArc
from .circle import SlvsCircle

logger = logging.getLogger(__name__)


class SlvsCoincident(GenericConstraint, PropertyGroup):
    """Forces two points to be coincident,
    or a point to lie on a curve, or a point to lie on a plane.

    The point-coincident constraint is available in both 3d and projected versions.
    The 3d point-coincident constraint restricts three degrees of freedom;
    the projected version restricts only two. If two points are drawn in a workplane,
    and then constrained coincident in 3d, then an error will result–they are already
    coincident in one dimension (the dimension normal to the plane),
    so the third constraint equation is redundant.
    """

    type = "COINCIDENT"
    label = "Coincident"
    signature = (POINT, (*POINT, *LINE, SlvsWorkplane, SlvsCircle, SlvsArc))
    # NOTE: Coincident between 3dPoint and Workplane currently doesn't seem to work

    def needs_wp(self):
        if isinstance(self.entity2, SlvsWorkplane):
            return WpReq.FREE
        return WpReq.OPTIONAL

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return make_coincident(
            solvesys, self.entity1.py_data, self.entity2, self.get_workplane(), group
        )

    def placements(self):
        return (self.entity1,)


slvs_entity_pointer(SlvsCoincident, "entity1")
slvs_entity_pointer(SlvsCoincident, "entity2")
slvs_entity_pointer(SlvsCoincident, "sketch")

register, unregister = register_classes_factory((SlvsCoincident,))
