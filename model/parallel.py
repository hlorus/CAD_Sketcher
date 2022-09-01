import logging

from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..global_data import WpReq
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer
from .line_2d import SlvsLine2D

logger = logging.getLogger(__name__)


class SlvsParallel(GenericConstraint, PropertyGroup):
    """Forces two lines to be parallel. Applies only in 2D."""

    type = "PARALLEL"
    label = "Parallel"
    signature = ((SlvsLine2D,), (SlvsLine2D,))

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        return solvesys.addParallel(
            self.entity1.py_data,
            self.entity2.py_data,
            wrkpln=self.get_workplane(),
            group=group,
        )

    def placements(self):
        return (self.entity1, self.entity2)


slvs_entity_pointer(SlvsParallel, "entity1")
slvs_entity_pointer(SlvsParallel, "entity2")
slvs_entity_pointer(SlvsParallel, "sketch")

register, unregister = register_classes_factory((SlvsParallel,))
