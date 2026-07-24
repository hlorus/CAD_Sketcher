import logging

from bpy.types import PropertyGroup
from bpy.props import StringProperty
from bpy.utils import register_classes_factory

from ..curve_solver import Solver
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


    curve_id_1: StringProperty(name="Curve ID 1", default="")
    curve_id_2: StringProperty(name="Curve ID 2", default="")

    def create_slvs_data_from_curves(self, solvesys, handle_map, wp, group):
        h1 = handle_map.get(self.curve_id_1)
        h2 = handle_map.get(self.curve_id_2)
        if h1 is None or h2 is None:
            return None
        kwargs = {}
        if wp:
            kwargs['workplane'] = wp
        return solvesys.perpendicular(group, h1, h2, **kwargs)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        wp = self.get_workplane()
        kwargs = {}
        if wp:
            kwargs['workplane'] = wp

        return solvesys.perpendicular(
            group,
            self.entity1.py_data,
            self.entity2.py_data,
            **kwargs,
        )

    def placements(self):
        return (self.ref(1), self.ref(2))


slvs_entity_pointer(SlvsPerpendicular, "entity1")
slvs_entity_pointer(SlvsPerpendicular, "entity2")
slvs_entity_pointer(SlvsPerpendicular, "sketch")

register, unregister = register_classes_factory((SlvsPerpendicular,))
