import bpy
from bpy.types import UIList, Context, UILayout, PropertyGroup

from ..declarations import Operators
from ..model.sketch_ref import Sketch, is_sketch_object


class VIEW3D_UL_sketches(UIList):
    """List of sketches in the scene.

    Bound to ``scene.objects`` and filtered down to sketch (Curves) objects via
    ``filter_items`` -- no separate backing collection is required. Each row lets
    you toggle visibility, enter, rename and delete the sketch.
    """

    def draw_item(
        self,
        context: Context,
        layout: UILayout,
        data: PropertyGroup,
        item: PropertyGroup,
        icon: int,
        active_data: PropertyGroup,
        active_propname: str,
        index: int = 0,
    ):
        obj = item  # a Curves object (filtered by filter_items)

        if self.layout_type in {"DEFAULT", "COMPACT"}:
            if not obj:
                layout.label(text="", translate=False, icon="OUTLINER_DATA_GP_LAYER")
                return

            row = layout.row(align=True)

            # Visibility toggle (eye)
            row.operator(
                Operators.SetSketchVisibility,
                text="",
                icon="HIDE_ON" if obj.hide_viewport else "HIDE_OFF",
                emboss=False,
            ).sketch_name = obj.name

            # Editable name -- expands to fill, pushing the icons below to the
            # right edge of the row (standard Blender UIList layout).
            row.prop(obj, "name", text="", emboss=False)

            # Trailing controls: solver-state, enter (edit), delete
            if obj.get("solver_state", "OKAY") != "OKAY":
                state = Sketch(obj).get_solver_state()
                row.label(text="", icon=state.icon)
            row.operator(
                Operators.SetActiveSketch,
                text="",
                icon="OUTLINER_DATA_GP_LAYER",
                emboss=False,
            ).sketch_name = obj.name
            row.operator(
                Operators.DeleteSketch,
                text="",
                icon="X",
                emboss=False,
            ).sketch_name = obj.name

        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text="", icon="OUTLINER_DATA_GP_LAYER")

    def filter_items(self, context: Context, data, propname):
        """Show only sketch objects; still honor the built-in name search box."""
        objects = getattr(data, propname)
        helper = bpy.types.UI_UL_list

        if self.filter_name:
            flags = helper.filter_items_by_name(
                self.filter_name, self.bitflag_filter_item, objects, "name"
            )
        else:
            flags = [self.bitflag_filter_item] * len(objects)

        for i, obj in enumerate(objects):
            if not is_sketch_object(obj):
                flags[i] &= ~self.bitflag_filter_item

        return flags, []
