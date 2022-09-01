import logging

from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..global_data import WpReq
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer
from .point_2d import SlvsPoint2D
from .line_2d import SlvsLine2D

logger = logging.getLogger(__name__)


class SlvsVertical(GenericConstraint, PropertyGroup):
    """Forces a line segment to be vertical. It applies in 2D Space only because
    the meaning of horizontal or vertical is defined by the workplane.
    """

    type = "VERTICAL"
    label = "Vertical"
    signature = ((SlvsLine2D, SlvsPoint2D), (SlvsPoint2D,))

    @classmethod
    def get_types(cls, index, entities):
        if index == 1:
            # return None if first entity is line
            if entities[0] and entities[0].is_line():
                return None

        return cls.signature[index]

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        wp = self.get_workplane()
        if self.entity1.is_point():
            return solvesys.addPointsVertical(
                self.entity1.py_data, self.entity2.py_data, wp, group=group
            )
        return solvesys.addLineVertical(self.entity1.py_data, wrkpln=wp, group=group)

    def placements(self):
        return (self.entity1,)


slvs_entity_pointer(SlvsVertical, "entity1")
slvs_entity_pointer(SlvsVertical, "entity2")
slvs_entity_pointer(SlvsVertical, "sketch")

register, unregister = register_classes_factory((SlvsVertical,))
