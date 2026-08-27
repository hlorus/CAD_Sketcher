from bpy.types import Context

from ...model.sketch_ref import get_active_sketch
from ...utilities.custom_attributes import definitions
from . import VIEW3D_PT_sketcher_base


class VIEW3D_PT_sketcher_custom_attributes(VIEW3D_PT_sketcher_base):
    """User-defined values that are authored on native sketch geometry."""

    bl_label = "Attributes"
    bl_idname = "VIEW3D_PT_sketcher_custom_attributes"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return get_active_sketch(context) is not None

    def draw(self, context: Context):
        layout = self.layout
        sketch = get_active_sketch(context)
        defs = definitions(sketch)

        if not defs:
            layout.label(text="No custom attributes")

        for entry in defs:
            row = layout.row(align=True)
            row.label(text=entry["name"])
            row.label(text=entry["domain"].title())
            set_op = row.operator(
                "view3d.slvs_set_custom_attribute", text="Set", icon="GREASEPENCIL"
            )
            set_op.name = entry["name"]
            remove_op = row.operator(
                "view3d.slvs_remove_custom_attribute", text="", icon="X"
            )
            remove_op.name = entry["name"]

        layout.operator(
            "view3d.slvs_add_custom_attribute", text="Add Attribute", icon="ADD"
        )
