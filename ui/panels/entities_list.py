from bpy.types import Context

from CAD_Sketcher.declarations import Operators, Panels
from . import VIEW3D_PT_sketcher_base


class VIEW3D_PT_sketcher_entities(VIEW3D_PT_sketcher_base):
    """
    Entities Menu: List of entities in the sketch.
    Interactive
    """

    bl_label = "Entities"
    bl_idname = Panels.SketcherEntities
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

            # Left part
            sub = row.row(align=True)
            sub.alignment = "LEFT"

            # Select operator
            props = sub.operator(
                Operators.Select,
                text="",
                emboss=False,
                icon=("RADIOBUT_ON" if e.selected else "RADIOBUT_OFF"),
            )
            props.mode = "TOGGLE"
            props.index = e.slvs_index
            props.highlight_hover = True

            # Visibility toggle
            sub.prop(
                e,
                "visible",
                icon_only=True,
                icon=("HIDE_OFF" if e.visible else "HIDE_ON"),
                emboss=False,
            )

            # Middle Part
            sub = row.row()
            sub.alignment = "LEFT"
            sub.prop(e, "name", text="")

            # Right part
            sub = row.row()
            sub.alignment = "RIGHT"

            # Context menu
            props = sub.operator(
                Operators.ContextMenu,
                text="",
                icon="OUTLINER_DATA_GP_LAYER",
                emboss=False,
            )
            props.highlight_hover = True
            props.highlight_active = True
            props.index = e.slvs_index

            # Delete operator
            props = sub.operator(
                Operators.DeleteEntity,
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
