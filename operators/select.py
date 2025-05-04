from bpy.types import Operator, Context
from bpy.props import IntProperty, BoolProperty
from bpy.utils import register_classes_factory
import logging

from .utilities import select_extend, select_invert
from ..utilities.select import select_all, deselect_all
from .. import global_data
from ..declarations import Operators
from ..utilities.highlighting import HighlightElement
from ..utilities.select import mode_property
from ..gizmos.preselection import VIEW3D_GT_slvs_preselection

logger = logging.getLogger(__name__)


class View3D_OT_slvs_select(Operator, HighlightElement):
    """
    Select an entity

    Either the entity specified by the index property or the hovered index
    if the index property is not set. 
    
    When clicking on the same spot with overlapping entities, cycles through them.
    """

    bl_idname = Operators.Select
    bl_label = "Select Sketch Entities"

    index: IntProperty(name="Index", default=-1)
    mode: mode_property
    cycle: BoolProperty(name="Cycle through overlapping entities", default=False)

    def invoke(self, context, event):
        # When clicking directly, enable cycling behavior
        self.cycle = True
        return self.execute(context)

    def execute(self, context: Context):
        # Handle when directly selecting an entity by index (e.g., from UI)
        if self.properties.is_property_set("index") and self.index != -1:
            entity = context.scene.sketcher.entities.get(self.index)
            if entity:
                if self.mode == "SET":
                    deselect_all(context)
                
                value = True
                if self.mode == "SUBTRACT":
                    value = False
                if self.mode == "TOGGLE":
                    value = not entity.selected
                
                entity.selected = value
                context.area.tag_redraw()
                return {"FINISHED"}
        
        # Handle selection by hover
        index = global_data.hover
        hit = index != -1
        mode = self.mode

        # If we're in "SET" mode or nothing is hit, deselect all
        if mode == "SET" or not hit:
            deselect_all(context)

        if hit:
            # Check if we're trying to cycle through stacked entities
            if self.cycle and len(global_data.hover_stack) > 1:
                # Check if this is a click on already selected entity - if so, cycle
                entity = context.scene.sketcher.entities.get(index)
                if entity.selected and mode in ("SET", "TOGGLE"):
                    # Get all gizmo groups
                    for gizmogroup in context.window_manager.gizmo_group_properties:
                        # Find our preselection gizmo group
                        if gizmogroup.name == "preselection ggt":
                            # Find the gizmo instance
                            for space in context.workspace.screens[0].areas:
                                if space.type == 'VIEW_3D':
                                    for region in space.regions:
                                        if region.type == 'WINDOW':
                                            gizmo_instances = [g for g in region.gizmos if isinstance(g, VIEW3D_GT_slvs_preselection)]
                                            if gizmo_instances:
                                                # Cycle to the next entity
                                                gizmo_instances[0].cycle_hover_stack(context)
                                                # Now the hover has been updated, select the new entity
                                                index = global_data.hover
                                                entity = context.scene.sketcher.entities.get(index)
                                                entity.selected = True
                                                logger.info(f"Cycled to entity: {entity.name}")
                                                context.area.tag_redraw()
                                                return {"FINISHED"}
            
            # Normal selection behavior
            entity = context.scene.sketcher.entities.get(index)
            
            # Add null check to prevent NoneType error
            if entity is None:
                self.report({"WARNING"}, "No entity found at index {}".format(index))
                return {"CANCELLED"}

            value = True
            if mode == "SUBTRACT":
                value = False
            if mode == "TOGGLE":
                value = not entity.selected

            entity.selected = value

        context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_select_all(Operator):
    """Select / Deselect all entities"""

    bl_idname = Operators.SelectAll
    bl_label = "Select / Deselect Entities"

    deselect: BoolProperty(name="Deselect")

    def execute(self, context: Context):
        if self.deselect:
            deselect_all(context)
        else:
            select_all(context)
        context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_select_invert(Operator):
    """Invert entities selection"""

    bl_idname = Operators.SelectInvert
    bl_label = "Invert entities selection"

    def execute(self, context: Context):
        select_invert(context)
        context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_select_extend(Operator):
    """Select neighbour entities"""

    bl_idname = Operators.SelectExtend
    bl_label = "Select neighbour entities"

    def execute(self, context: Context):
        select_extend(context)
        context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_select_extend_all(Operator):
    """Select neighbour entities"""

    bl_idname = Operators.SelectExtendAll
    bl_label = "Select neighbour entities"

    def execute(self, context: Context):
        while select_extend(context):
            pass
        context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_select,
        View3D_OT_slvs_select_all,
        View3D_OT_slvs_select_invert,
        View3D_OT_slvs_select_extend,
        View3D_OT_slvs_select_extend_all,
    )
)
