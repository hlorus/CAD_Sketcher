from bpy.types import Operator, Context
from bpy.props import IntProperty, BoolProperty
from bpy.utils import register_classes_factory
import logging

from ..utilities.logging import setup_logger
from .utilities import select_extend, select_invert
from ..utilities.select import select_all, deselect_all
from .. import global_data
from ..declarations import Operators
from ..utilities.highlighting import HighlightElement
from ..utilities.select import mode_property
from ..gizmos.preselection import VIEW3D_GT_slvs_preselection

logger = logging.getLogger(__name__)
setup_logger(logger)


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
    cycle: BoolProperty(name="Cycle through overlapping entities", default=True)

    def invoke(self, context, event):
        # When clicking directly, enable cycling behavior
        self.cycle = True
        return self.execute(context)

    def execute(self, context: Context):
        logger.debug(f"[SELECT] index={self.index}, mode={self.mode}, cycle={self.cycle}, hover={getattr(global_data, 'hover', None)}, hover_stack={getattr(global_data, 'hover_stack', None)}")
        # Handle when directly selecting an entity by index (e.g., from UI)
        if self.properties.is_property_set("index") and self.index != -1:
            entity = context.scene.sketcher.entities.get(self.index)
            logger.debug(f"[SELECT] Direct index selection: {self.index}, entity={getattr(entity, 'name', None)}, selected={getattr(entity, 'selected', None)}")
            if entity:
                if self.mode == "SET":
                    logger.debug("[SELECT] Deselecting all (direct index)")
                    deselect_all(context)
                
                value = True
                if self.mode == "SUBTRACT":
                    value = False
                if self.mode == "TOGGLE":
                    value = not entity.selected
                logger.debug(f"[SELECT] Setting entity.selected = {value}")
                entity.selected = value
                context.area.tag_redraw()
                return {"FINISHED"}
        
        # Handle selection by hover
        index = global_data.hover
        hit = index != -1
        mode = self.mode
        logger.debug(f"[SELECT] Hover selection: index={index}, hit={hit}, mode={mode}, hover_stack={getattr(global_data, 'hover_stack', None)}")

        # ---- CYCLE FIRST -------------------------------------------------
        if hit and self.cycle and len(global_data.hover_stack) > 1:
            entity = context.scene.sketcher.entities.get(index)
            logger.debug(f"[SELECT] Cycle check: entity={getattr(entity, 'name', None)}, selected={getattr(entity, 'selected', None)}, mode={mode}")
            if entity.selected and mode in {"SET", "TOGGLE"}:
                logger.debug("[SELECT] Attempting to cycle hover stack...")
                try:
                    VIEW3D_GT_slvs_preselection.cycle_hover_stack(context)
                except Exception as e:
                    logger.error(f"[SELECT] Error cycling hover stack: {e}")
                index = global_data.hover
                entity = context.scene.sketcher.entities.get(index)
                logger.debug(f"[SELECT] After cycle: index={index}, entity={getattr(entity, 'name', None)}")
                entity.selected = True
                logger.info(f"Cycled to entity: {getattr(entity, 'name', None)}")
                context.area.tag_redraw()
                return {"FINISHED"}

        # ---- NORMAL SELECTION -------------------------------------------
        if mode == "SET" or not hit:
            logger.debug("[SELECT] Deselecting all (normal selection)")
            deselect_all(context)

        if hit:
            entity = context.scene.sketcher.entities.get(index)
            logger.debug(f"[SELECT] Normal selection: entity={getattr(entity, 'name', None)}, selected={getattr(entity, 'selected', None)}")
            value = True
            if mode == "SUBTRACT":
                value = False
            if mode == "TOGGLE":
                value = not entity.selected
            logger.debug(f"[SELECT] Setting entity.selected = {value}")
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


def _find_preselection_gizmo(context):
    """Find the active VIEW3D_GT_slvs_preselection gizmo instance in all VIEW_3D areas."""
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        if hasattr(region, 'gizmo_map'):
                            for gizmo in region.gizmo_map.gizmos:
                                if isinstance(gizmo, VIEW3D_GT_slvs_preselection):
                                    return gizmo
    return None


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_select,
        View3D_OT_slvs_select_all,
        View3D_OT_slvs_select_invert,
        View3D_OT_slvs_select_extend,
        View3D_OT_slvs_select_extend_all,
    )
)
