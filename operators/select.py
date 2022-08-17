from bpy.types import Operator, Context
from bpy.props import IntProperty, BoolProperty
from bpy.utils import register_classes_factory

from .utilities import select_all, deselect_all, select_extend, select_invert
from .. import global_data
from ..declarations import Operators
from ..utilities.highlighting import HighlightElement

class View3D_OT_slvs_select(Operator, HighlightElement):
    """
    TODO: Add selection modes

    Select an entity

    Either the entity specified by the index property or the hovered index
    if the index property is not set

    """

    bl_idname = Operators.Select
    bl_label = "Select Solvespace Entities"

    index: IntProperty(name="Index", default=-1)

    def execute(self, context: Context):
        index = (
            self.index
            if self.properties.is_property_set("index")
            else global_data.hover
        )
        if index != -1:
            entity = context.scene.sketcher.entities.get(index)
            entity.selected = not entity.selected
        else:
            deselect_all(context)
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


register, unregister = register_classes_factory((
    View3D_OT_slvs_select,
    View3D_OT_slvs_select_all,
    View3D_OT_slvs_select_invert,
    View3D_OT_slvs_select_extend,
    View3D_OT_slvs_select_extend_all))
