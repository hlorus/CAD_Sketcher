import bpy
from bpy.props import StringProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from .utilities import activate_sketch


class View3D_OT_slvs_set_active_sketch(Operator):
    """Set the active sketch"""

    bl_idname = Operators.SetActiveSketch
    bl_label = "Set Active Sketch"
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


class View3D_OT_slvs_set_cutter_visibility(Operator):
    """Show or hide the solid of a cutter that is currently cutting

    A cutter is hidden while it cuts, since its own solid would sit over the
    result. That is the right default and the wrong answer when you are looking
    for the body you just made, so this overrides it. The choice is stored on the
    cutter: the display rules run again whenever part membership changes, and a
    bare unhide would be undone by the next pass.
    """

    bl_idname = Operators.SetCutterVisibility
    bl_label = "Toggle Cutter Visibility"
    bl_options = {"REGISTER", "UNDO"}

    body_name: StringProperty(name="Body Name", default="")

    @classmethod
    def description(cls, context, properties):
        ob = bpy.data.objects.get(properties.body_name)
        if ob and ob.hide_viewport:
            return "Show this cutter's solid, as a wireframe"
        return "Hide this cutter's solid again while it cuts"

    def execute(self, context: Context):
        from ..utilities.part import SHOW_CUTTER_KEY, refresh_cutter

        ob = bpy.data.objects.get(self.body_name)
        if not ob:
            return {"CANCELLED"}

        if ob.get(SHOW_CUTTER_KEY, False):
            del ob[SHOW_CUTTER_KEY]
        else:
            ob[SHOW_CUTTER_KEY] = True
        refresh_cutter(context.scene, ob)

        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_set_active_sketch,
        View3D_OT_slvs_set_cutter_visibility,
        View3D_OT_slvs_set_sketch_visibility,
    )
)
