import logging
from typing import List

import bpy
from bpy.types import PropertyGroup
from bpy.props import EnumProperty, BoolProperty, IntProperty, PointerProperty
from bpy.utils import register_classes_factory

from .. import global_data
from ..curve_solver import Solver, solve_system
from .base_entity import SlvsGenericEntity
from .utilities import slvs_entity_pointer
from ..utilities.bpy import bpyEnum

logger = logging.getLogger(__name__)

class SlvsSketch(SlvsGenericEntity, PropertyGroup):
    """A sketch groups 2 dimensional entities together.

    Entities that belong to a sketch can only be edited as long as the sketch is active.
    """

    solver_state: EnumProperty(
        name="Solver Status", items=global_data.solver_state_items
    )
    dof: IntProperty(name="Degrees of Freedom", max=6)
    target_mesh: PointerProperty(type=bpy.types.Mesh)
    target_object: PointerProperty(type=bpy.types.Object)
    curve_resolution: IntProperty(
        name="Mesh Curve Resolution", default=12, min=1, soft_max=25
    )
    next_curve_id: IntProperty(
        name="Next Curve ID",
        description="Counter for generating unique curve IDs within this sketch",
        default=1,
    )
    workplane_object: PointerProperty(
        type=bpy.types.Object,
        name="Workplane Object",
        description="Empty object whose transform defines the workplane",
    )

    def dependencies(self) -> List[SlvsGenericEntity]:
        return [
            self.wp,
        ]

    def sketch_entities(self, context):
        for e in context.scene.sketcher.entities.all:
            if not hasattr(e, "sketch"):
                continue
            if e.sketch != self:
                continue
            yield e

    def update(self):
        self.is_dirty = False

    def draw(self, context):
        pass

    def draw_id(self, context):
        pass

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        pass

    def remove_objects(self):
        if self.target_object:
            bpy.data.objects.remove(self.target_object)

    def is_visible(self, context):
        if context.scene.sketcher.active_sketch_i == self.slvs_index:
            return True
        return self.visible

    def get_solver_state(self):
        return bpyEnum(global_data.solver_state_items, identifier=self.solver_state)

    def solve(self, context):
        return solve_system(context, sketch=self)

    @classmethod
    def is_sketch(cls):
        return True


slvs_entity_pointer(SlvsSketch, "wp")

register, unregister = register_classes_factory((SlvsSketch,))
