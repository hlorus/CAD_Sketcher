# NOTE: This currently doesn't get registered because of a bug in the solver module

import logging

from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..global_data import WpReq
from .base_constraint import GenericConstraint
from .utilities import slvs_entity_pointer
from .categories import POINT
from .workplane import SlvsWorkplane
from .line_2d import SlvsLine2D

logger = logging.getLogger(__name__)


class SlvsSymmetry(GenericConstraint, PropertyGroup):
    """Forces two points to be symmetric about a plane.

    The symmetry plane may be a workplane when used in 3D. Or, the symmetry plane
    may be specified as a line in a workplane; the symmetry plane is then through
    that line, and normal to the workplane.

    """

    type = "SYMMETRY"
    label = "Symmetry"

    # TODO: not all combinations are possible!
    signature = (
        POINT,
        POINT,
        (SlvsLine2D, SlvsWorkplane),
    )

    def needs_wp(self):
        if isinstance(self.entity3, SlvsLine2D):
            return WpReq.NOT_FREE
        return WpReq.FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        e1, e2, e3 = self.entity1, self.entity2, self.entity3

        wp = self.get_workplane()
        kwargs = {}
        if wp:
            kwargs['workplane'] = wp

        return solvesys.symmetric(
            group,
            e1.py_data,
            e2.py_data,
            e3.py_data,
            **kwargs,
        )

    def placements(self):
        return (self.entity1, self.entity2, self.entity3)


slvs_entity_pointer(SlvsSymmetry, "entity1")
slvs_entity_pointer(SlvsSymmetry, "entity2")
slvs_entity_pointer(SlvsSymmetry, "entity3")
slvs_entity_pointer(SlvsSymmetry, "sketch")

register, unregister = register_classes_factory((SlvsSymmetry,))
