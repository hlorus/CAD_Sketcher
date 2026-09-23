import bpy
from bpy.props import StringProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from .utilities import activate_sketch


class View3D_OT_slvs_set_active_sketch(Operator):
    """Set the active sketch"""

    bl_idname = Operators.SetActiveSketch
    bl_label = "Set active Sketch"
    bl_options = {"UNDO"}

    sketch_name: StringProperty(
        name="Sketch Name",
        description="Name of the sketch object to activate (empty to deactivate)",
        default="",
    )

    def execute(self, context: Context):
        if not self.sketch_name:
            from ..model.sketch_ref import get_active_sketch

            if not get_active_sketch(context):
                return {"PASS_THROUGH"}
            return activate_sketch(context, None, self)

        ob = bpy.data.objects.get(self.sketch_name)
        if ob:
            from ..model.sketch_ref import is_sketch_object

            if is_sketch_object(ob):
                return activate_sketch(context, ob, self)

        return {"CANCELLED"}


class View3D_OT_slvs_set_sketch_visibility(Operator):
    """Show or hide a sketch in the viewport

    The curves themselves, not the body they are realised on: the body carries
    the features (extrudes, booleans, whatever the user added) and looks nothing
    like the profile, so showing it is not what "show this sketch" means. A
    sketch is hidden when it is created, so this is how its outline is put back
    on screen over the geometry it made.
    """

    bl_idname = Operators.SetSketchVisibility
    bl_label = "Toggle Sketch Visibility"

    sketch_name: StringProperty(name="Sketch Name", default="")

    @classmethod
    def description(cls, context, properties):
        ob = bpy.data.objects.get(properties.sketch_name)
        if ob and ob.hide_viewport:
            return "Show this sketch's curves in the viewport"
        return "Hide this sketch's curves in the viewport"

    def execute(self, context: Context):
        ob = bpy.data.objects.get(self.sketch_name)
        if not ob:
            return {"CANCELLED"}
        ob.hide_viewport = not ob.hide_viewport
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_set_active_sketch,
        View3D_OT_slvs_set_sketch_visibility,
    )
)
