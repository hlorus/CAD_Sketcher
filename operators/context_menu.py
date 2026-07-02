import bpy
from ..model.sketch_ref import get_active_constraints
from bpy.utils import register_classes_factory
from bpy.props import StringProperty, BoolProperty, IntProperty
from bpy.types import Operator, Context, Event, PropertyGroup

from .. import global_data
from ..utilities.highlighting import HighlightElement
from ..declarations import Operators


class View3D_OT_slvs_context_menu(Operator, HighlightElement):
    """Show element's settings"""

    bl_idname = Operators.ContextMenu
    bl_label = "Solvespace Context Menu"

    type: StringProperty(name="Type", options={"SKIP_SAVE"})
    index: IntProperty(name="Index", default=-1, options={"SKIP_SAVE"})
    delayed: BoolProperty(default=False)

    @classmethod
    def description(cls, context: Context, properties: PropertyGroup):
        cls.handle_highlight_hover(context, properties)
        if properties.type:
            return properties.type.capitalize()
        return cls.__doc__

    def invoke(self, context: Context, event: Event):
        if not self.delayed:
            return self.execute(context)

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: Context, event: Event):
        if event.value == "RELEASE":
            return self.execute(context)
        return {"RUNNING_MODAL"}

    def execute(self, context: Context):
        is_entity = True
        entity_index = None
        constraint_index = None
        element = None

        # Constraints
        if self.properties.is_property_set("type"):
            constraint_index = self.index
            constraints = get_active_constraints(context)
            element = constraints.get_from_type_index(self.type, self.index)
            is_entity = False
        else:
            # Entities
            hover = (
                self.index
                if self.properties.is_property_set("index")
                else global_data.hover
            )

            if hover and hover > 0:
                # Try as curve_id — show CurveRef info
                from ..model.sketch_ref import get_active_sketch
                sketch = get_active_sketch(context)
                if sketch:
                    from ..model.curve_ref import curve_ref
                    ref = curve_ref(sketch, hover)
                    if ref.valid:
                        element = ref

        def draw_context_menu(self, context: Context):
            col = self.layout.column()
            element.draw_props(col)

        if not element:
            bpy.ops.wm.call_menu(name="VIEW3D_MT_selected_menu")
            return {"FINISHED"}

        context.window_manager.popup_menu(draw_context_menu)
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_context_menu,))
