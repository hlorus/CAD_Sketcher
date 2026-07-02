import logging

from bpy.types import PropertyGroup
from bpy.props import IntProperty
from bpy.utils import register_classes_factory

from ..curve_solver import Solver
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


    curve_id_1: IntProperty(name="Curve ID 1", default=0)
    curve_id_2: IntProperty(name="Curve ID 2", default=0)

    def create_slvs_data_from_curves(self, solvesys, handle_map, wp, group):
        h1 = handle_map.get(self.curve_id_1)
        h2 = handle_map.get(self.curve_id_2)
        if h1 is None or h2 is None:
            return None
        kwargs = {}
        if wp:
            kwargs['workplane'] = wp
        return solvesys.parallel(group, h1, h2, **kwargs)

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        wp = self.get_workplane()
        kwargs = {}
        if wp:
            kwargs['workplane'] = wp

        return solvesys.parallel(
            group,
            self.entity1.py_data,
            self.entity2.py_data,
            **kwargs,
        )

    def placements(self):
        return (self.ref(1), self.ref(2))


slvs_entity_pointer(SlvsParallel, "entity1")
slvs_entity_pointer(SlvsParallel, "entity2")
slvs_entity_pointer(SlvsParallel, "sketch")

register, unregister = register_classes_factory((SlvsParallel,))
