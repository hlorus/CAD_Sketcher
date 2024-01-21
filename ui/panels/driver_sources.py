import bpy
from bpy.types import Object, Context, UILayout, Operator
from bpy.props import IntProperty, PointerProperty, CollectionProperty

from .. import declarations
from .. import types
from . import VIEW3D_PT_sketcher_base

from ...declarations import Operators


class AddLocalDriverSourceOperator(Operator):
    bl_label = "Add Local Driver Source Operator"
    bl_idname = Operators.AddLocalDriverSource

    def invoke(self, context, event):
        sketch = context.scene.sketcher.active_sketch
        #print("Add local driver")
        #print("Adding source. Current count: " + str(len(sketch.driver_sources)))
        driverGroup = sketch.driver_sources.add()
        return {'FINISHED'}

class DeleteLocalDriverSourceOperator(Operator):
    bl_label = "Delete Local Driver Source Operator"
    bl_idname = Operators.DeleteLocalDriverSource 

    index: IntProperty(default=-1)

    def execute(self, context):
        print("Delete local driver")
        sketch = context.scene.sketcher.active_sketch
        return {'FINISHED'}
    
    def invoke(self, context, event):
        print("Delete local driver")
        sketch = context.scene.sketcher.active_sketch
        sketch.driver_sources.remove(self.index)
        return {'FINISHED'}


def draw_driver_listitem(context: Context, layout: UILayout, source, index):
    """
    Creates a single row inside the ``layout`` describing
    the driver ``source``.
    """
    row = layout.row()
    row.prop(source, "source", text="")

    middle_sub = row.row()

    props = row.operator(
        declarations.Operators.DeleteLocalDriverSource,
        text="",
        icon="X",
        emboss=False,
    )
    props.index = index

class VIEW3D_PT_sketcher_drivers(VIEW3D_PT_sketcher_base):
    """
    Driver Menu: Display list of suitable driver sources for selection
    Interactive
    """

    bl_label = "Driver Menu"
    bl_idname = declarations.Panels.SketcherDrivers
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout
        col = layout.column(align=True)

        sketch = bpy.context.scene.sketcher.active_sketch
        if not sketch is None:
            col.label(text = "Sketch specific driver menu sources")
            col.operator(declarations.Operators.AddLocalDriverSource, text="Add", icon="ADD")
            box = layout.box()
            col = box.column(align=True)

            if hasattr(sketch, "driver_sources"):
                sources = sketch.driver_sources
                if not sources is None:
                    for index, source in enumerate(sources):
                        draw_driver_listitem(context, col, source, index)

