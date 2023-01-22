import logging

from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..global_data import WpReq
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer
from .categories import POINT, LINE

logger = logging.getLogger(__name__)


class SlvsMidpoint(GenericConstraint, PropertyGroup):
    """Forces a point to lie on the midpoint of a line."""

    type = "MIDPOINT"
    label = "Midpoint"
    signature = (POINT, LINE)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys):
        wp = self.get_workplane()
        return solvesys.midpoint(
            self.entity1.py_data,
            self.entity2.py_data,
            wp,
        )

    def placements(self):
        return (self.entity2,)


slvs_entity_pointer(SlvsMidpoint, "entity1")
slvs_entity_pointer(SlvsMidpoint, "entity2")
slvs_entity_pointer(SlvsMidpoint, "sketch")


register, unregister = register_classes_factory((SlvsMidpoint,))
