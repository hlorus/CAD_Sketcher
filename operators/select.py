from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..drawing import selection
from ..utilities.highlighting import HighlightElement
from ..utilities.select import deselect_all, mode_property, select_all
from .utilities import select_extend, select_invert


class View3D_OT_slvs_select(Operator, HighlightElement):
    """
    Select an entity

    Either the entity specified by the index property or the hovered index
    if the index property is not set

    """

    bl_idname = Operators.Select
    bl_label = "Select Sketch Entities"

    # Selection keys are curve ids (see selection.selected); when unset the
    # currently hovered curve id is used.
    index: StringProperty(name="Curve ID", default="")
    mode: mode_property
    # Alt+click: step to the next entity in the overlapping stack under the cursor
    # before selecting, so repeated Alt+clicks reach occluded geometry (issue #50).
    cycle: BoolProperty(name="Cycle Overlapping", default=False, options={"SKIP_SAVE"})

    def execute(self, context: Context):
        if self.cycle:
            selection.cycle_hover(1)
        index = (
            self.index if self.properties.is_property_set("index") else selection.hover
        )
        hit = bool(index)
        mode = self.mode

        if mode == "SET" or not hit:
            deselect_all(context)

        if hit:
            # Work directly with selection.selected — no entity lookup needed
            is_selected = index in selection.selected

            if mode == "SUBTRACT":
                if is_selected:
                    selection.selected.remove(index)
            elif mode == "TOGGLE":
                if is_selected:
                    selection.selected.remove(index)
                else:
                    selection.selected.append(index)
            else:  # SET or EXTEND
                if not is_selected:
                    selection.selected.append(index)

        if context.area:
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


class View3D_OT_slvs_hover_cycle(Operator):
    """Cycle the hovered element through entities overlapping under the cursor"""

    bl_idname = Operators.HoverCycle
    bl_label = "Cycle Hovered Element"
    bl_options = {"INTERNAL"}

    direction: IntProperty(default=1)

    def execute(self, context: Context):
        if not selection.cycle_hover(self.direction):
            return {"CANCELLED"}
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_select,
        View3D_OT_slvs_select_all,
        View3D_OT_slvs_select_invert,
        View3D_OT_slvs_select_extend,
        View3D_OT_slvs_select_extend_all,
        View3D_OT_slvs_hover_cycle,
    )
)
