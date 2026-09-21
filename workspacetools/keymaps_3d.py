"""Workspace keymaps specific to native free-3D sketches."""

from .. import keymaps

tool_access_3d = keymaps.tool_keys(keymaps.SKETCH_3D_TOOL_KEYS)


tool_generic_3d = (
    *keymaps.tool_base_keymap,
    keymaps.use_construction,
    *keymaps.tool_use_select,
    *tool_access_3d,
)
