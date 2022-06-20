import bpy
from bpy.types import Panel, Menu, UIList, Context, UILayout

from . import functions, class_defines, operators
from .declarations import Menus, Operators, Panels


class VIEW3D_UL_sketches(UIList):
    def draw_item(
        self, context, layout, data, item, icon, active_data, active_propname, index=0
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            if item:
                active = index == getattr(active_data, active_propname)

                row = layout.row(align=True)
                row.alignment = "LEFT"
                row.prop(
                    item,
                    "visible",
                    icon_only=True,
                    icon=("HIDE_OFF" if item.visible else "HIDE_ON"),
                    emboss=False,
                )
                row.prop(item, "name", text="", emboss=False, icon_value=icon)

                row = layout.row()
                row.alignment = "RIGHT"

                if item.solver_state != "OKAY":
                    row.operator(
                        Operators.ShowSolverState,
                        text="",
                        emboss=False,
                        icon_value=layout.enum_item_icon(
                            item, "solver_state", item.solver_state
                        ),
                    ).index = item.slvs_index

                row.operator(
                    Operators.SetActiveSketch,
                    icon="OUTLINER_DATA_GP_LAYER",
                    text="",
                    emboss=False,
                ).index = item.slvs_index

                if active:
                    row.operator(
                        Operators.DeleteEntity, text="", icon="X", emboss=False,
                    ).index = item.slvs_index
                else:
                    row.separator()
                    row.separator()

            else:
                layout.label(text="", translate=False, icon_value=icon)
        elif self.layout_type in {"GRID"}:
            layout.alignment = "CENTER"
            layout.label(text="", icon_value=icon)


class VIEW3D_PT_sketcher_base(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sketcher"


class VIEW3D_PT_sketcher(VIEW3D_PT_sketcher_base):
    bl_label = "Sketcher"
    bl_idname = Panels.Sketcher

    def draw(self, context: Context):
        layout = self.layout

        sketch_selector(context, layout, show_selector=False)
        sketch = context.scene.sketcher.active_sketch
        layout.use_property_split = True
        layout.use_property_decorate = False

        if sketch:
            row = layout.row()
            row.alignment = "CENTER"
            row.scale_y = 1.2

            if sketch.solver_state != "OKAY":
                state = sketch.get_solver_state()
                row.operator(
                    Operators.ShowSolverState,
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

            row = layout.row()
            row.prop(sketch, "name")
            layout.prop(sketch, "convert_type")
            if sketch.convert_type != "NONE":
                layout.prop(sketch, "fill_shape")

            layout.operator(
                Operators.DeleteEntity, text="Delete Sketch", icon="X",
            ).index = sketch.slvs_index

        else:
            layout.template_list(
                "VIEW3D_UL_sketches",
                "",
                context.scene.sketcher.entities,
                "sketches",
                context.scene.sketcher,
                "ui_active_sketch",
            )


class VIEW3D_PT_sketcher_debug(VIEW3D_PT_sketcher_base):
    bl_label = "Debug Settings"
    bl_idname = Panels.SketcherDebugPanel

    def draw(self, context: Context):
        layout = self.layout

        prefs = functions.get_prefs()
        layout.operator(Operators.WriteSelectionTexture)
        layout.operator(Operators.Solve)
        layout.operator(Operators.Solve, text="Solve All").all = True

        layout.operator(Operators.Test)
        layout.prop(context.scene.sketcher, "show_origin")
        layout.prop(prefs, "hide_inactive_constraints")
        layout.prop(prefs, "all_entities_selectable")
        layout.prop(prefs, "force_redraw")

    @classmethod
    def poll(cls, context: Context):
        prefs = functions.get_prefs()
        return prefs.show_debug_settings


class VIEW3D_PT_sketcher_add_constraints(VIEW3D_PT_sketcher_base):
    bl_label = "Add Constraints"
    bl_idname = Panels.SketcherAddContraint
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout
        layout.label(text="Constraints:")
        col = layout.column(align=True)
        for op in operators.constraint_operators:
            col.operator(op.bl_idname)


class VIEW3D_PT_sketcher_entities(VIEW3D_PT_sketcher_base):
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
            if isinstance(e, class_defines.SlvsSketch):
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
                Operators.DeleteEntity, text="", icon="X", emboss=False,
            )
            props.index = e.slvs_index
            props.highlight_hover = True


class VIEW3D_PT_sketcher_constraints(VIEW3D_PT_sketcher_base):
    bl_label = "Constraints"
    bl_idname = Panels.SketcherContraints
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.8

        layout.operator_enum(Operators.SetAllConstraintsVisibility, "visibility")

        sketch = context.scene.sketcher.active_sketch
        for c in context.scene.sketcher.constraints.all:
            if not c.is_active(sketch):
                continue
            row = col.row()

            # Left part
            sub = row.row()
            sub.alignment = "LEFT"

            sub.prop(
                c,
                "visible",
                icon_only=True,
                icon=("HIDE_OFF" if c.visible else "HIDE_ON"),
                emboss=False,
            )

            # Failed hint
            sub.label(
                text="", icon=("ERROR" if c.failed else "CHECKMARK"),
            )

            index = context.scene.sketcher.constraints.get_index(c)

            # Context menu, shows constraint name
            props = sub.operator(Operators.ContextMenu, text=str(c), emboss=False,)
            props.type = c.type
            props.index = index
            props.highlight_hover = True
            props.highlight_active = True

            # Right part
            sub = row.row()
            sub.alignment = "RIGHT"

            # Delete operator
            props = sub.operator(
                Operators.DeleteConstraint, text="", icon="X", emboss=False,
            )
            props.type = c.type
            props.index = index
            props.highlight_hover = True


class VIEW3D_MT_sketches(Menu):
    bl_label = "Sketches"
    bl_idname = Menus.Sketches

    def draw(self, context: Context):
        layout = self.layout
        sse = context.scene.sketcher.entities
        layout.operator(Operators.AddSketch).wait_for_input = True

        if len(sse.sketches):
            layout.separator()

        for i, sk in enumerate(sse.sketches):
            layout.operator(
                Operators.SetActiveSketch, text=sk.name
            ).index = sk.slvs_index


def sketch_selector(
    context: Context,
    layout: UILayout,
    is_header: bool = False,
    show_selector: bool = True,
):
    row = layout.row(align=is_header)
    index = context.scene.sketcher.active_sketch_i
    name = "Sketches"

    scale_y = 1 if is_header else 1.8

    if index != -1:
        sketch = context.scene.sketcher.active_sketch
        name = sketch.name

        row.operator(
            Operators.SetActiveSketch, text="Leave: " + name, icon="BACK", depress=True,
        ).index = -1

        row.active = True
        row.scale_y = scale_y

    else:
        row.scale_y = scale_y
        # TODO: Don't show text when is_header
        row.operator(Operators.AddSketch, icon="ADD").wait_for_input = True

        if not is_header:
            row = layout.row()
        if show_selector:
            row.menu(VIEW3D_MT_sketches.bl_idname, text=name)


def draw_object_context_menu(self, context: Context):
    layout = self.layout
    ob = context.active_object
    row = layout.row()

    props = row.operator(Operators.SetActiveSketch, text="Edit Sketch")

    if ob and ob.sketch_index != -1:
        row.active = True
        props.index = ob.sketch_index
    else:
        row.active = False
    layout.separator()


def draw_add_sketch_in_add_menu(self, context: Context):
    self.layout.separator()
    self.layout.operator_context = "INVOKE_DEFAULT"
    self.layout.operator("view3d.slvs_add_sketch", text="Sketch")


classes = [
    VIEW3D_UL_sketches,
    VIEW3D_MT_sketches,
]

classes.extend(panel for panel in VIEW3D_PT_sketcher_base.__subclasses__())


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.VIEW3D_MT_object_context_menu.prepend(draw_object_context_menu)
    bpy.types.VIEW3D_MT_add.append(draw_add_sketch_in_add_menu)


def unregister():
    bpy.types.VIEW3D_MT_object_context_menu.remove(draw_object_context_menu)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    bpy.types.VIEW3D_MT_object_context_menu.remove(draw_object_context_menu)
    bpy.types.VIEW3D_MT_add.remove(draw_add_sketch_in_add_menu)
