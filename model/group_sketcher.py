import logging
from typing import Union, Generator

import bpy
from bpy.types import PropertyGroup, Context
from bpy.utils import register_class, unregister_class
from bpy.props import IntProperty, BoolProperty, PointerProperty, IntVectorProperty

from .. import global_data
from ..solver import solve_system
from .utilities import slvs_entity_pointer
from .base_entity import SlvsGenericEntity
from .group_entities import SlvsEntities
from .group_constraints import SlvsConstraints
from ..utilities.view import update_cb

logger = logging.getLogger(__name__)


class SketcherProps(PropertyGroup):
    """The base structure for CAD Sketcher"""

    entities: PointerProperty(type=SlvsEntities)
    constraints: PointerProperty(type=SlvsConstraints)
    show_origin: BoolProperty(name="Show Origin Entities")
    use_construction: BoolProperty(
        name="Construction Mode",
        description="Draw all subsequent entities in construction mode",
        default=False,
        options={"SKIP_SAVE"},
        update=update_cb,
    )
    selectable_constraints: BoolProperty(
        name="Constraints Selectability",
        default=True,
        options={"SKIP_SAVE"},
        update=update_cb,
    )

    version: IntVectorProperty(
        name="Extension Version",
        description="CAD Sketcher extension version this scene was saved with",
    )

    # This is needed for the sketches ui list
    ui_active_sketch: IntProperty()

    @property
    def all(self) -> Generator[Union[SlvsGenericEntity, SlvsConstraints], None, None]:
        """Iterate over entities and constraints of every type"""
        for entity in self.entities.all:
            yield entity
        for constraint in self.constraints.all:
            yield constraint

    def solve(self, context: Context):
        return solve_system(context)

    def purge_stale_data(self):
        global_data.hover = -1
        global_data.selected.clear()
        global_data.batches.clear()
        for e in self.entities.all:
            e.dirty = True


slvs_entity_pointer(SketcherProps, "active_sketch", update=update_cb)


# register, unregister = register_classes_factory((SketcherProps,))


def register():
    register_class(SketcherProps)
    bpy.types.Scene.sketcher = PointerProperty(type=SketcherProps)
    bpy.types.Object.sketch_index = IntProperty(name="Parent Sketch", default=-1)


def unregister():
    del bpy.types.Object.sketch_index
    del bpy.types.Scene.sketcher
    unregister_class(SketcherProps)
