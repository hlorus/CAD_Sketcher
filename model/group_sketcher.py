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

# Prefix for all constraint driver target custom properties on the scene.
_EP_PREFIX = "slvs:c:"


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
    auto_axis_constraints: BoolProperty(
        name="Auto Constraints",
        description="Automatically add inferred constraints (for example auto axis alignment and auto coincident)",
        default=True,
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

    def create_constraint_value_endpoint(self, constraint) -> str | None:
        uid = getattr(constraint, "constraint_uid", "")
        if not uid:
            return None
        scene = self.id_data
        key = f"{_EP_PREFIX}{uid}"
        if key not in scene:
            if (
                hasattr(constraint, "value_store")
                and constraint.is_property_set("value_store")
            ):
                init_value = float(constraint.value_store)
            else:
                init_value = 0.0

            scene[key] = init_value
            try:
                rna_prop = type(constraint).bl_rna.properties.get("value_store")
                subtype = rna_prop.subtype if rna_prop else "NONE"
                scene.id_properties_ui(key).update(subtype=subtype, min=0.0, soft_min=0.0)
            except Exception:
                pass
        return key

    def get_constraint_value_endpoint(self, constraint) -> str | None:
        uid = getattr(constraint, "constraint_uid", "")
        if not uid:
            return None
        key = f"{_EP_PREFIX}{uid}"
        scene = self.id_data
        return key if key in scene else None

    def remove_constraint_value_endpoint(self, constraint_uid: str):
        """Delete the scene custom property for a constraint that is being removed."""
        if not constraint_uid:
            return
        scene = self.id_data
        key = f"{_EP_PREFIX}{constraint_uid}"
        if key in scene:
            del scene[key]

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
