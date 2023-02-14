import bpy
from bpy.types import Context

from CAD_Sketcher.declarations import Operators
from .panels import VIEW3D_PT_sketcher_base
from .sketches_list import VIEW3D_UL_sketches
from .sketches_menu import VIEW3D_MT_sketches


def draw_object_context_menu(self, context: Context):
    layout = self.layout
    ob = context.active_object
    row = layout.row()

    props = row.operator(Operators.SetActiveSketch, text="Edit Sketch")

    if ob and ob.sketch_index != -1:
        row.enabled = True
        props.index = ob.sketch_index
    else:
        row.enabled = False
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
