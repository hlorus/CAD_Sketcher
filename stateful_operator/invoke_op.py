import bpy
from bpy.props import StringProperty
from bpy.types import Context, Operator

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
        prop_names = props.rna_type.properties.keys()

        for p in prop_names:
            if p in ("bl_rna", "rna_type", "state_index"):
                continue
            if p.startswith("_"):
                continue

            prop = props.rna_type.properties[p]

            # Collection/pointer properties have no default and cannot be
            # forwarded as invoke options.
            if not hasattr(prop, "default"):
                continue

            default = prop.default
            value = getattr(props, p)

            # Only forward values that differ from their defaults.
            if value != default:
                options[p] = value

        # Stateful drawing operators expose wait_for_input, but simple
        # operators such as Add 3D Sketch do not.
        if "wait_for_input" in prop_names:
            options["wait_for_input"] = True

        parts = self.operator.split(".", 1)
        if len(parts) != 2:
            self.report(
                {"ERROR"},
                f"Invalid operator id '{self.operator}': expected 'module.name'",
            )
            return {"CANCELLED"}

        module = getattr(bpy.ops, parts[0], None)
        op = getattr(module, parts[1], None) if module is not None else None

        if op is None:
            self.report(
                {"ERROR"},
                f"Operator not found: '{self.operator}'",
            )
            return {"CANCELLED"}

        if op.poll():
            op("INVOKE_DEFAULT", **options)

        return {"FINISHED"}