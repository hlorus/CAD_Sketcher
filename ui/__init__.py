import bpy
from bpy.types import Context

from .. import declarations
from .. import icon_manager
from ..model import types
from ..stateful_operator import constants
from ..utilities import preferences
from .panels.tools import VIEW3D_PT_sketcher_tools
from .panels.constraints_list import VIEW3D_PT_sketcher_constraints
from .panels.debug import VIEW3D_PT_sketcher_debug
from .panels.entities_list import VIEW3D_PT_sketcher_entities
from .panels.sketch_select import VIEW3D_PT_sketcher
from .sketches_list import VIEW3D_UL_sketches
from .selected_menu import VIEW3D_MT_selected_menu


def draw_object_context_menu(self, context: Context):
    layout = self.layout
    ob = context.active_object
    row = layout.row()

    props = row.operator(declarations.Operators.SetActiveSketch, text="Edit Sketch")

    from ..model.sketch_ref import is_sketch_object
    if ob and is_sketch_object(ob):
        row.enabled = True
        props.sketch_name = ob.name
    else:
        row.enabled = False
    layout.separator()


def draw_add_sketch_in_add_menu(self, context: Context):
    from ..declarations import Operators, WorkSpaceTools
    from ..stateful_operator.constants import Operators as StatefulOps

    self.layout.separator()
    self.layout.operator_context = "INVOKE_DEFAULT"
    # Switch to the Add Sketch tool (workplane gizmo), then invoke the operator.
    props = self.layout.operator(StatefulOps.InvokeTool.value, text="Sketch")
    props.tool_name = WorkSpaceTools.AddSketch.value
    props.operator = Operators.AddSketch.value


def draw_sketch_header(self, context: Context):
    from ..model.sketch_ref import get_active_sketch
    sketch = get_active_sketch(context)
    if not sketch:
        return
    layout = self.layout
    row = layout.row(align=True)
    row.separator()
    row.label(text=sketch.target_object.name)
    row.operator(declarations.Operators.SetActiveSketch, text="Leave Sketch", icon='BACK').sketch_name = ""


classes = [
    VIEW3D_UL_sketches,
    VIEW3D_PT_sketcher,
    VIEW3D_PT_sketcher_tools,
    VIEW3D_PT_sketcher_entities,
    VIEW3D_PT_sketcher_constraints,
    VIEW3D_PT_sketcher_debug,
    VIEW3D_MT_selected_menu,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.VIEW3D_MT_object_context_menu.prepend(draw_object_context_menu)
    bpy.types.VIEW3D_MT_add.append(draw_add_sketch_in_add_menu)
    bpy.types.VIEW3D_HT_header.append(draw_sketch_header)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    bpy.types.VIEW3D_HT_header.remove(draw_sketch_header)
    bpy.types.VIEW3D_MT_object_context_menu.remove(draw_object_context_menu)
    bpy.types.VIEW3D_MT_add.remove(draw_add_sketch_in_add_menu)
