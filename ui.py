import bpy
from bpy.types import Panel, Menu
from . import operators, functions


class VIEW3D_PT_sketcher(Panel):
    bl_label = "Sketcher"
    bl_idname = "VIEW3D_PT_sketcher"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = __package__.capitalize()

    def draw(self, context):
        layout = self.layout

        sketch_selector(context, layout)
        sketch = context.scene.sketcher.active_sketch
        if sketch:
            layout.use_property_split = True
            layout.use_property_decorate = False
            layout.prop(sketch, "name")
            layout.prop(sketch, "convert_type")

        layout.separator()

        layout.label(text="Add:")
        layout.operator(operators.View3D_OT_slvs_add_workplane.bl_idname)
        layout.separator()

        layout.label(text="Constraints:")
        layout.operator_enum(operators.VIEW3D_OT_slvs_add_constraint.bl_idname, "type")
        layout.separator()
        layout.operator_context = "EXEC_DEFAULT"

        if functions.get_prefs().show_debug_settings:
            layout.label(text="Debug:")
            layout.operator(operators.VIEW3D_OT_slvs_write_selection_texture.bl_idname)
            layout.operator(operators.View3D_OT_slvs_solve.bl_idname)
            layout.prop(context.scene.sketcher, "show_origin")


from . import global_data


class VIEW3D_MT_context_menu(Menu):
    bl_label = "Context Menu"
    bl_idname = "VIEW3D_MT_context_menu"

    def draw(self, context):
        layout = self.layout

        index = global_data.hover
        if index != None:
            entity = context.scene.sketcher.entities.get(index)
            layout.label(text="Type: " + type(entity).__name__)

            if functions.get_prefs().show_debug_settings:
                layout.label(text="Index: " + str(entity.slvs_index))
            layout.label(text="Is Origin: " + str(entity.origin))
            layout.separator()

            layout.prop(entity, "visible")
            layout.prop(entity, "fixed")
            layout.prop(entity, "construction")
            layout.separator()

            if hasattr(entity, "draw_props"):
                entity.draw_props(layout)
                layout.separator()

            layout.operator(
                operators.View3D_OT_slvs_delete_entity.bl_idname
            ).index = index
        else:
            layout.label(text="No entity hovered")


class VIEW3D_MT_sketches(Menu):
    bl_label = "Sketches"
    bl_idname = "VIEW3D_MT_sketches"

    def draw(self, context):
        layout = self.layout
        sse = context.scene.sketcher.entities
        layout.operator(operators.View3D_OT_slvs_add_sketch.bl_idname)

        if len(sse.sketches):
            layout.separator()

        for i, sk in enumerate(sse.sketches):
            layout.operator(
                operators.View3D_OT_slvs_set_active_sketch.bl_idname, text=sk.name
            ).index = sk.slvs_index


def sketch_selector(context, layout, is_header=False):
    row = layout.row(align=is_header)
    index = context.scene.sketcher.active_sketch_i
    name = "Sketches"

    scale_y = 1 if is_header else 1.8

    if index != -1:
        sketch = context.scene.sketcher.active_sketch
        name = sketch.name

        row.operator(
            operators.View3D_OT_slvs_set_active_sketch.bl_idname,
            text="Leave: " + name,
            icon="BACK",
            depress=True,
        ).index = -1

        row.active = True
        row.scale_y = scale_y

    else:
        row.scale_y = scale_y
        # TODO: Don't show text when is_header
        row.operator(operators.View3D_OT_slvs_add_sketch.bl_idname, icon="ADD")

        if not is_header:
            row = layout.row()
        row.menu(VIEW3D_MT_sketches.bl_idname, text=name)


def draw_item(self, context):
    layout = self.layout
    layout.separator()

    sketch_selector(context, layout, is_header=True)


classes = (
    VIEW3D_PT_sketcher,
    VIEW3D_MT_context_menu,
    VIEW3D_MT_sketches,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.VIEW3D_HT_header.append(draw_item)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

        bpy.types.VIEW3D_HT_header.remove(draw_item)
