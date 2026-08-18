from bpy.types import WorkSpaceTool

from ..declarations import GizmoGroups, Operators, WorkSpaceTools
from ..keymaps import tool_node
from ..stateful_operator.tool import GenericStateTool
from ..stateful_operator.utilities.keymap import operator_access


class VIEW3D_T_slvs_add_sketch(GenericStateTool, WorkSpaceTool):
    bl_space_type = "VIEW_3D"
    bl_context_mode = "OBJECT"
    bl_idname = WorkSpaceTools.AddSketch
    bl_label = "Add Sketch"
    bl_operator = Operators.AddSketch
    bl_icon = "ops.mesh.primitive_grid_add_gizmo"
    bl_widget = GizmoGroups.Workplane
    bl_keymap = (
        # Direct origin-plane pick by the axis normal to the plane: Z -> XY,
        # Y -> XZ, X -> YZ (tool-scoped, so it only shadows those keys here).
        (
            Operators.AddSketchOnPlane,
            {"type": "Z", "value": "PRESS"},
            {"properties": [("plane", "XY")]},
        ),
        (
            Operators.AddSketchOnPlane,
            {"type": "Y", "value": "PRESS"},
            {"properties": [("plane", "XZ")]},
        ),
        (
            Operators.AddSketchOnPlane,
            {"type": "X", "value": "PRESS"},
            {"properties": [("plane", "YZ")]},
        ),
        *tool_node,
        *operator_access(Operators.AddSketch),
    )

    def draw_settings(context, layout, tool):
        layout.prop(context.scene.sketcher, "show_origin", text="Origin Workplanes")
