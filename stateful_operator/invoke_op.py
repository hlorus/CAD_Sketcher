import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Context, Event, Operator

from .constants import Operators
from .utilities import continuation


def _id(value, fallback):
    """Tool and operator ids are str-enum members on this side."""
    value = getattr(value, "value", value)
    return str(value) if value else str(fallback)


class View3D_OT_invoke_tool(Operator):
    bl_idname = Operators.InvokeTool
    bl_label = "Invoke Tool"

    tool_name: StringProperty(name="Tool ID")

    # TODO: get the operator from tool attribute (tool.bl_operator)?
    operator: StringProperty(name="Operator ID")
    group: BoolProperty(
        name="Group Key",
        description=(
            "Start whichever member of the tool's toolbar group is shown, rather "
            "than the tool named here"
        ),
        default=False,
    )
    fallthrough: BoolProperty(
        name="Fall Through",
        description=(
            "Let other shortcuts on the same key run when the tool isn't "
            "available in this context"
        ),
        default=False,
    )

    def invoke(self, context: Context, event: Event):
        from .utilities.switch import tool_available

        if self.fallthrough and not tool_available(context, self.tool_name):
            return {"PASS_THROUGH"}
        return self.execute(context)

    def _group_active(self, context: Context):
        """The tool to start: the one named, or the group's if this is a group key.

        A group key stands for a toolbar button several tools share and starts
        whichever of them the toolbar shows -- the last one used -- just as
        clicking that button would. Every other key names one tool and starts
        exactly that, even when it shares a button with others.
        """
        if not self.group:
            return str(self.tool_name), str(self.operator)

        # Blender's own item_from_id_active_with_group() wrapper mis-unpacks this
        # helper and hands back the index, so call the helper directly.
        try:
            from bl_ui.space_toolsystem_common import ToolSelectPanelHelper

            cls = ToolSelectPanelHelper._tool_class_from_space_type("VIEW_3D")
            item, _index, group = cls._tool_get_by_id_active_with_group(
                context, str(self.tool_name)
            )
        except Exception:
            item, group = None, None

        if getattr(item, "idname", None) is None:
            return str(self.tool_name), str(self.operator)

        tool = _id(item.idname, self.tool_name)
        operator = _id(item.operator, self.operator)
        return self._chain_member(group, tool, operator)

    @staticmethod
    def _chain_member(group, tool: str, operator: str):
        """Swap in a group member that can carry on a chain, if one is needed.

        The member the toolbar shows is the one the key starts -- but while a
        chain is waiting to be carried on, a member that cannot take it would end
        the run instead. The key then starts the member that can, e.g. the
        endpoint arc rather than the center-based one.
        """
        if not continuation.pending() or continuation.accepts(operator):
            return tool, operator
        for member in group or ():
            member_operator = _id(getattr(member, "operator", None), "")
            if member_operator and continuation.accepts(member_operator):
                return _id(getattr(member, "idname", None), tool), member_operator
        return tool, operator

    def execute(self, context: Context):
        tool_name, operator = self._group_active(context)
        bpy.ops.wm.tool_set_by_id(name=tool_name)

        # get the tool operator props
        tool = context.workspace.tools.from_space_view3d_mode(context.mode)
        props = tool.operator_properties(operator)

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

        parts = operator.split(".", 1)
        if len(parts) != 2:
            self.report(
                {"ERROR"},
                f"Invalid operator id '{operator}': expected 'module.name'",
            )
            return {"CANCELLED"}

        module = getattr(bpy.ops, parts[0], None)
        op = getattr(module, parts[1], None) if module is not None else None

        if op is None:
            self.report(
                {"ERROR"},
                f"Operator not found: '{operator}'",
            )
            return {"CANCELLED"}

        if op.poll():
            op("INVOKE_DEFAULT", **options)

        # Whatever the started operator didn't take up is stale: a chain point is
        # offered to the run this keypress starts, not to a later one.
        continuation.clear()
        return {"FINISHED"}
