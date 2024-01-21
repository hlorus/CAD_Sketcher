
import bpy
from bpy.types import Operator, Menu
from bpy.props import StringProperty, IntProperty

from ...declarations import Operators, Menus


# Define the operator class
class DriverMenuOperator(Operator):
    bl_label = "Driver Menu Operator"
    bl_idname = Operators.DriverMenu # "object.driver_menu"
    type: StringProperty(name="Type", options={"SKIP_SAVE"})
    index: IntProperty(name="Index", default=-1, options={"SKIP_SAVE"})

    def invoke(self, context, event):
        VIEW3D_MT_driver_menu.index = self.index
        VIEW3D_MT_driver_menu.type = self.type
        bpy.ops.wm.call_menu(name=VIEW3D_MT_driver_menu.bl_idname)
        return {'FINISHED'}

# Define the operator class
class SetDriverOperator(Operator):
    bl_label = "Set Driver Operator"
    bl_idname = Operators.SetDriver # "object.set_driver"

    type: StringProperty(name="Type", options={"SKIP_SAVE"})
    index: IntProperty(name="Index", default=-1, options={"SKIP_SAVE"})
    sourceobject: StringProperty(name="sourceobject", options={"SKIP_SAVE"})
    sourceproperty: StringProperty(name="sourceproperty", options={"SKIP_SAVE"})

   
    # https://blender.stackexchange.com/questions/262012/how-to-set-up-driver-via-python-script-between-custom-properties-of-objects
    @staticmethod
    def add_driver(source, target, prop, dataPath):
        

        # add the new driver
        d = source.driver_add( prop ).driver
        v = d.variables.new()
        v.name                 = prop
        v.targets[0].id        = target
        v.targets[0].data_path = dataPath
        d.expression = v.name


    def execute(self, context):
        constraints = context.scene.sketcher.constraints
        constraint = constraints.get_from_type_index(self.type, self.index)

        # Remove any existing drivers
        # It might be useful to add another button to enable adding multiple drivers to the constraint,
        # which would make it easier to assemble collections of drivers for a complex experssion.
        while constraint.driver_remove("value", 0):
            pass

        if(self.sourceobject == ""):
            return {'FINISHED'}

        src = bpy.data.objects[self.sourceobject]
        print(src)
        self.add_driver(constraint, src, "value", f'["'+self.sourceproperty+'"]')
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return self.execute(context)



# Define the menu class
class VIEW3D_MT_driver_menu(Menu):
    bl_label = "Select Driver"
    bl_idname = Menus.DriverMenu
    
    type = ""
    index = -1

    def draw(self, context):
        layout = self.layout

        props = layout.operator(
            Operators.SetDriver,
            text="None",
            icon="TRASH"
        )
        props.type = self.type
        props.index = self.index
        props.sourceobject = ""
        props.sourceproperty = ""

        r = layout

        sketch = bpy.context.scene.sketcher.active_sketch
        if sketch is None:
            return 
        
        sources = []
        for group in sketch.driver_sources:
            if not group is None:
                source = group.source
                if not source is None:
                    sources.append(source)

        sources.sort(key=lambda s: s.name)

        for source in sources:
            drewSource = False
            for i, k in enumerate(source.keys()):
                v = source[k]
                if isinstance(v, int) or isinstance(v, float): 

                    if not drewSource:
                        drewSource = True
                        r.separator()
                        r.label(text=source.name, icon="OBJECT_DATA")

                    props = r.operator(
                        Operators.SetDriver,
                        text= k + " " + str(v),
                        icon="DRIVER"
                    )
                    props.type = self.type
                    props.index = self.index
                    props.sourceobject = source.name
                    props.sourceproperty = k





