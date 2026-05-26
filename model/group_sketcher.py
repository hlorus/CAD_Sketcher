import json
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

_OBJ_PROP = "slvs_pre_sketch_hidden"
_SK_PROP = "slvs_pre_sketch_visible"
_WP_PROP = "slvs_pre_sketch_wp_visible"


def _update_show_objects(self, context):
    """Toggle visibility of all Blender objects while inside a sketch."""
    if self.sketch_show_objects:
        # Restore pre-sketch object visibility
        state_str = context.scene.get(_OBJ_PROP)
        if state_str:
            try:
                state = json.loads(state_str)
                for obj in context.view_layer.objects:
                    obj.hide_set(state.get(obj.name, False))
                return
            except (json.JSONDecodeError, TypeError):
                pass
        # Fallback: show everything
        for obj in context.view_layer.objects:
            obj.hide_set(False)
    else:
        # Re-hide all objects
        for obj in context.view_layer.objects:
            obj.hide_set(True)


def _update_show_sketches(self, context):
    """Toggle visibility of other sketches while inside a sketch."""
    active_index = self.active_sketch_i
    sketches = self.entities.sketches
    if self.sketch_show_sketches:
        # Restore pre-sketch sketch visibility
        state_str = context.scene.get(_SK_PROP)
        if state_str:
            try:
                state = json.loads(state_str)
                for i, sketch in enumerate(sketches):
                    sketch.visible = state.get(str(i), sketch.visible)
                return
            except (json.JSONDecodeError, TypeError):
                pass
        # Fallback: show all
        for sketch in sketches:
            sketch.visible = True
    else:
        # Re-hide other sketches
        for sketch in sketches:
            if sketch.slvs_index != active_index:
                sketch.visible = False


def _update_show_workplanes(self, context):
    """Toggle visibility of global 3D entities (workplanes, 3D points/lines/normals) while inside a sketch."""
    entities = self.entities
    global_cols = (
        entities.points3D,
        entities.lines3D,
        entities.normals3D,
        entities.workplanes,
    )
    if self.sketch_show_workplanes:
        state_str = context.scene.get(_WP_PROP)
        if state_str:
            try:
                state = json.loads(state_str)
                for col in global_cols:
                    for ent in col:
                        ent.visible = state.get(str(ent.slvs_index), ent.visible)
                return
            except (json.JSONDecodeError, TypeError):
                pass
        # Fallback: show all
        for col in global_cols:
            for ent in col:
                ent.visible = True
    else:
        for col in global_cols:
            for ent in col:
                ent.visible = False


def _update_ui_active_sketch(self, context):
    if context is None:
        return

    sketches = self.entities.sketches
    index = self.ui_active_sketch
    if index < 0 or index >= len(sketches):
        return

    wp = sketches[index].wp
    if not wp:
        return

    global_data.selected.clear()
    global_data.selected.append(wp.slvs_index)

    if context.area:
        context.area.tag_redraw()


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
    auto_create_polylines: BoolProperty(
        name="Auto-Create Polylines",
        description=(
            "Automatically group consecutive lines drawn with the line tool "
            "into a polyline entity when the chain finishes"
        ),
        default=True,
        options={"SKIP_SAVE"},
    )
    selectable_constraints: BoolProperty(
        name="Constraints Selectability",
        default=True,
        options={"SKIP_SAVE"},
        update=update_cb,
    )
    sketch_show_objects: BoolProperty(
        name="Show Blender Objects",
        description="Temporarily show Blender objects for reference while inside a sketch",
        default=False,
        options={"SKIP_SAVE"},
        update=_update_show_objects,
    )
    sketch_show_sketches: BoolProperty(
        name="Show Sketches",
        description="Temporarily show other sketches for reference while inside a sketch",
        default=False,
        options={"SKIP_SAVE"},
        update=_update_show_sketches,
    )
    sketch_show_workplanes: BoolProperty(
        name="Show Workplanes",
        description="Temporarily show workplanes for reference while inside a sketch",
        default=False,
        options={"SKIP_SAVE"},
        update=_update_show_workplanes,
    )

    version: IntVectorProperty(
        name="Extension Version",
        description="CAD Sketcher extension version this scene was saved with",
    )

    # This is needed for the sketches ui list
    ui_active_sketch: IntProperty(update=_update_ui_active_sketch)

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
