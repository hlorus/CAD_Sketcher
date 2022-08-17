import bpy
from bpy.types import Operator, Context
from bpy.props import StringProperty

from .constants import Operators

class View3D_OT_invoke_tool(Operator):
    bl_idname = Operators.InvokeTool
    bl_label = "Invoke Tool"

    tool_name: StringProperty(name="Tool ID")

    # TODO: get the operator from tool attribute (tool.bl_operator)?
    operator: StringProperty(name="Operator ID")

    def execute(self, context: Context):
        bpy.ops.wm.tool_set_by_id(name=self.tool_name)

        # get the tool operator props
        tool = context.workspace.tools.from_space_view3d_mode(context.mode)
        props = tool.operator_properties(self.operator)

        options = {}
        for p in props.rna_type.properties.keys():
            if p in ("bl_rna", "rna_type", "state_index"):
                continue
            if p.startswith("_"):
                continue

            default = props.rna_type.properties[p].default
            value = getattr(props, p)

            # NOTE: Setting all values might mess around with operators that check
            # if properties are set. Checking is_property_set here doesn't seem to work.
            # manually check if value is the same as the default however that also
            # seems to fail for vectorproperties and maybe others but prevents
            # the problems from caused by pointer set-state checking...
            if value != default:
                options[p] = value

        options["wait_for_input"] = True

        op_name = self.operator.split(".", 1)
        op = getattr(getattr(bpy.ops, op_name[0]), op_name[1])
        if op.poll():
            op("INVOKE_DEFAULT", **options)
        return {"FINISHED"}
