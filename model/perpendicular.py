import logging

from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..global_data import WpReq
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer
from .line_2d import SlvsLine2D
from .utilities import get_connection_point

logger = logging.getLogger(__name__)


class SlvsPerpendicular(GenericConstraint, PropertyGroup):
    """Forces two lines to be perpendicular, applies only in 2D. This constraint
    is equivalent to an angle constraint for ninety degrees.
    """

    type = "PERPENDICULAR"
    label = "Perpendicular"
    signature = ((SlvsLine2D,), (SlvsLine2D,))

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addPerpendicular(
            self.entity1.py_data,
            self.entity2.py_data,
            wrkpln=self.get_workplane(),
            group=group,
        )

    def placements(self):
        point = get_connection_point(self.entity1, self.entity2)
        if point:
            return (point,)
        return (self.entity1, self.entity2)


slvs_entity_pointer(SlvsPerpendicular, "entity1")
slvs_entity_pointer(SlvsPerpendicular, "entity2")
slvs_entity_pointer(SlvsPerpendicular, "sketch")

register, unregister = register_classes_factory((SlvsPerpendicular,))
