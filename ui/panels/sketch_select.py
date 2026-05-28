from bpy.types import Context, UILayout, UIList

from .. import declarations
from . import VIEW3D_PT_sketcher_base


class VIEW3D_UL_sketch_tags(UIList):
    """UIList of role tags on the active sketch."""

    bl_idname = "VIEW3D_UL_sketch_tags"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index=0,
        flt_flag=0,
    ):
        tag = item
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.prop(
                tag,
                "enabled",
                text="",
                emboss=False,
                icon="HIDE_OFF" if tag.enabled else "HIDE_ON",
            )
            row.prop(tag, "value", text="", emboss=True)
            edit_op = row.operator(
                declarations.Operators.EditTagParameters,
                text="",
                emboss=False,
                icon="PREFERENCES",
            )
            edit_op.owner_kind = "SKETCH"
            edit_op.sketch_index = context.scene.sketcher.active_sketch.slvs_index
            edit_op.tag_index = index
            props = row.operator(
                declarations.Operators.ContextMenuSketch,
                text="",
                emboss=False,
                icon="OUTLINER_DATA_GP_LAYER",
            )
            props.sketch_index = context.scene.sketcher.active_sketch.slvs_index
            props.tag_index = index
            props.index = index
            op = row.operator(
                "view3d.slvs_sketch_role_from_preset",
                text="",
                icon="VIEWZOOM",
            )
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=tag.value or "\u2014")


def sketch_selector(
    context: Context,
    layout: UILayout,
):
    row = layout.row(align=True)
    row.scale_y = 1.8
    active_sketch = context.scene.sketcher.active_sketch

    if not active_sketch:
        row.operator(declarations.Operators.AddSketch, icon="ADD").wait_for_input = True

    else:
        row.operator(
            declarations.Operators.SetActiveSketch,
            text="Leave: " + active_sketch.name,
            icon="BACK",
            depress=True,
        ).index = -1
        row.active = True

    row.alert = bool(active_sketch and not active_sketch.geometry_solved)
    row.operator(declarations.Operators.Update, icon="FILE_REFRESH", text="")


class VIEW3D_PT_sketcher(VIEW3D_PT_sketcher_base):
    """Menu for selecting the sketch you want to enter into"""

    bl_label = "Sketcher"
    bl_idname = declarations.Panels.Sketcher

    def draw(self, context: Context):
        layout = self.layout

        sketch_selector(context, layout)
        sketch = context.scene.sketcher.active_sketch
        layout.use_property_split = True
        layout.use_property_decorate = False

        if sketch:
            # Sketch is selected, show info about the sketch itself
            row = layout.row()
            row.alignment = "CENTER"
            row.scale_y = 1.2

            if sketch.solver_state != "OKAY":
                state = sketch.get_solver_state()
                row.operator(
                    declarations.Operators.ShowSolverState,
                    text=state.name,
                    icon=state.icon,
                    emboss=False,
                ).index = sketch.slvs_index
            else:
                dof = sketch.dof
                dof_ok = dof <= 0
                dof_msg = (
                    "Fully defined sketch"
                    if dof_ok
                    else "Degrees of freedom: " + str(dof)
                )
                dof_icon = "CHECKMARK" if dof_ok else "ERROR"
                row.label(text=dof_msg, icon=dof_icon)

            layout.separator()

            col = layout.column()
            col.use_property_split = False
            row = col.row()
            row.prop(context.scene.sketcher, "sketch_show_objects", toggle=False)
            row.prop(context.scene.sketcher, "sketch_show_sketches", toggle=False)
            row.prop(context.scene.sketcher, "sketch_show_workplanes", toggle=False)
            row.prop(
                context.scene.sketcher, "sketch_show_reference_geometry", toggle=False
            )

            row = layout.row()
            row.prop(sketch, "name")
            layout.prop(sketch, "convert_type")

            if sketch.convert_type == "MESH":
                layout.prop(sketch, "curve_resolution")
            if sketch.convert_type != "NONE":
                layout.prop(sketch, "fill_shape")

            # Sketch tags UIList
            layout.label(text=f'Tags for "{sketch.name}":', icon="BOOKMARKS")
            row_tags = layout.row()
            col_tags = row_tags.column()
            col_tags.template_list(
                "VIEW3D_UL_sketch_tags",
                "",
                sketch,
                "tags",
                sketch,
                "active_tag_index",
                rows=2,
            )
            col_tag_ops = row_tags.column(align=True)
            col_tag_ops.operator("view3d.slvs_add_sketch_tag", text="", icon="ADD")
            col_tag_ops.operator(
                "view3d.slvs_remove_sketch_tag", text="", icon="REMOVE"
            )

            layout.operator(
                declarations.Operators.DeleteEntity,
                text="Delete Sketch",
                icon="X",
            ).index = sketch.slvs_index

        else:
            # No active Sketch , show list of available sketches
            layout.template_list(
                "VIEW3D_UL_sketches",
                "",
                context.scene.sketcher.entities,
                "sketches",
                context.scene.sketcher,
                "ui_active_sketch",
                item_dyntip_propname="name",
            )
