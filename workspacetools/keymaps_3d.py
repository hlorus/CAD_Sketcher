"""Workspace keymaps specific to native free-3D sketches."""

from ..declarations import Operators, WorkSpaceTools
from ..keymaps import tool_base_keymap, tool_use_select, use_construction
from ..stateful_operator.utilities.keymap import tool_invoke_kmi


tool_access_3d = (
    tool_invoke_kmi(
        "P",
        WorkSpaceTools.AddPoint3D,
        Operators.AddPoint3D,
    ),
    tool_invoke_kmi(
        "L",
        WorkSpaceTools.AddLine3D,
        Operators.AddLine3D,
    ),
)


tool_generic_3d = (
    *tool_base_keymap,
    use_construction,
    *tool_use_select,
    *tool_access_3d,
)
