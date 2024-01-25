import bpy
from bpy.types import Object, Context, UILayout, Operator
from bpy.props import IntProperty, PointerProperty, CollectionProperty

from .. import declarations
from .. import types
from . import VIEW3D_PT_sketcher_base

from ...declarations import Operators

class AddDriverSourceOperator(Operator):
    bl_label = "Add Driver Source Operator"
    bl_idname = Operators.AddDriverSource

    def execute(self, context):
        sketch = context.scene.sketcher.driver_sources.add()
        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)


class DeleteDriverSourceOperator(Operator):
    bl_label = "Delete Local Driver Source Operator"
    bl_idname = Operators.DeleteDriverSource 

    index: IntProperty(default=-1)

    def execute(self, context):
        context.scene.sketcher.driver_sources.remove(self.index)
        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)


class AddLocalDriverSourceOperator(Operator):
    bl_label = "Add Local Driver Source Operator"
    bl_idname = Operators.AddLocalDriverSource

    def execute(self, context):
        driverGroup = context.scene.sketcher.active_sketch.driver_sources.add()
        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)


class DeleteLocalDriverSourceOperator(Operator):
    bl_label = "Delete Local Driver Source Operator"
    bl_idname = Operators.DeleteLocalDriverSource 

    index: IntProperty(default=-1)

    def execute(self, context):
        context.scene.sketcher.active_sketch.driver_sources.remove(self.index)
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return self.execute(context)


def draw_driver_listitem(context: Context, layout: UILayout, source, index, op):
    """
    Creates a single row inside the ``layout`` describing
    the driver ``source``.
    """
    row = layout.row()
    row.prop(source, "source", text="")

    middle_sub = row.row()

    props = row.operator(
        op, 
        text="",
        icon="X",
        emboss=False,
    )
    props.index = index

def draw_drivers(context: Context, layout, driver_sources, op_add, op_delete):
    col = layout.column(align=True)
    col.operator(op_add, text="Add", icon="ADD")
    box = layout.box()
    col = box.column(align=True)
    if not driver_sources is None:
        for index, source in enumerate(driver_sources):
            draw_driver_listitem(context, col, source, index, op_delete)

class VIEW3D_PT_sketcher_drivers(VIEW3D_PT_sketcher_base):
    """
    Driver Menu: Display list of suitable driver sources for selection
    Interactive
    """

    bl_label = "Global Drivers"
    bl_idname = declarations.Panels.SketcherDrivers
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout

        draw_drivers(context, layout, bpy.context.scene.sketcher.driver_sources, declarations.Operators.AddDriverSource, declarations.Operators.DeleteDriverSource)


class VIEW3D_PT_sketcher_local_drivers(VIEW3D_PT_sketcher_base):
    """
    Driver Menu: Display list of suitable driver sources for selection
    Interactive
    """

    bl_label = "Local Drivers"
    bl_idname = declarations.Panels.SketcherLocalDrivers
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout

        sketch = bpy.context.scene.sketcher.active_sketch
        if not sketch is None:
            draw_drivers(context, layout, sketch.driver_sources, declarations.Operators.AddLocalDriverSource, declarations.Operators.DeleteLocalDriverSource)

