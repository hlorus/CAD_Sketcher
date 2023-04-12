from bpy.types import Context

from .. import declarations
from . import VIEW3D_PT_sketcher_base


class VIEW3D_PT_sketcher_entities(VIEW3D_PT_sketcher_base):
    """
    Entities Menu: List of entities in the sketch.
    Interactive
    """

    bl_label = "Entities"
    bl_idname = declarations.Panels.SketcherEntities
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.8

        sketch = context.scene.sketcher.active_sketch
        for e in context.scene.sketcher.entities.all:
            if not e.is_active(sketch):
                continue
            if e.is_sketch():
                continue

            row = col.row()
            row.alert = e.selected

            # Select operator
            props = row.operator(
                declarations.Operators.Select,
                text="",
                emboss=False,
                icon=("RADIOBUT_ON" if e.selected else "RADIOBUT_OFF"),
            )
            props.mode = "TOGGLE"
            props.index = e.slvs_index
            props.highlight_hover = True

            # Visibility toggle
            row.prop(
                e,
                "visible",
                icon_only=True,
                icon=("HIDE_OFF" if e.visible else "HIDE_ON"),
                emboss=False,
            )

            row.prop(e, "name", text="")

            # Context menu
            props = row.operator(
                declarations.Operators.ContextMenu,
                text="",
                icon="OUTLINER_DATA_GP_LAYER",
                emboss=False,
            )
            props.highlight_hover = True
            props.highlight_active = True
            props.index = e.slvs_index

            # Delete operator
            props = row.operator(
                declarations.Operators.DeleteEntity,
                text="",
                icon="X",
                emboss=False,
            )
            props.index = e.slvs_index
            props.highlight_hover = True

            # Props
            if e.props:
                row_props = col.row()
                row_props.alignment = "RIGHT"
                for entity_prop in e.props:
                    row_props.prop(e, entity_prop, text="")
                col.separator()
