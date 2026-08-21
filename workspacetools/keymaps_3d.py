"""Workspace keymaps specific to native free-3D sketches."""

# Ruff 0.16.4 disagrees with the repository's established relative-import order
# for this isolated helper module. Keep the imports explicit and scope the
# exception to import sorting only; F/E9 checks remain active.
# ruff: noqa: I001
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
