"""Workspace keymaps specific to native free-3D sketches."""

from .. import keymaps
from ..declarations import Operators, WorkSpaceTools
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
    *keymaps.tool_base_keymap,
    keymaps.use_construction,
    *keymaps.tool_use_select,
    *tool_access_3d,
)
