import bpy

from .declarations import Operators, WorkSpaceTools
from .stateful_operator.utilities.keymap import tool_invoke_kmi

constraint_access = (
    (
        Operators.AddCoincident,
        {"type": "C", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddVertical,
        {"type": "V", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddHorizontal,
        {"type": "H", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddEqual,
        {"type": "E", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddParallel,
        {"type": "A", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddPerpendicular,
        {"type": "P", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddTangent,
        {"type": "T", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddMidPoint,
        {"type": "M", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddRatio,
        {"type": "R", "value": "PRESS", "shift": True},
        {"properties": [("wait_for_input", True), ]}
    ),

    # Dimensional Constraints
    (
        Operators.AddDistance,
        {"type": "D", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddDistance,
        {"type": "V", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ("align", "VERTICAL")]}
    ),
    (
        Operators.AddDistance,
        {"type": "H", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ("align", "HORIZONTAL")]}
    ),
    (
        Operators.AddAngle,
        {"type": "A", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddDiameter,
        {"type": "O", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ]}
    ),
    (
        Operators.AddDiameter,
        {"type": "R", "value": "PRESS", "alt": True},
        {"properties": [("wait_for_input", True), ("setting", True)]}
    ),
)

tool_access = (
    tool_invoke_kmi(
        "P",
        WorkSpaceTools.AddPoint2D,
        Operators.AddPoint2D,
    ),
    tool_invoke_kmi(
        "L",
        WorkSpaceTools.AddLine2D,
        Operators.AddLine2D,
    ),
    tool_invoke_kmi(
        "C",
        WorkSpaceTools.AddCircle2D,
        Operators.AddCircle2D,
    ),
    tool_invoke_kmi(
        "A",
        WorkSpaceTools.AddArc2D,
        Operators.AddArc2D,
    ),
    tool_invoke_kmi(
        "R",
        WorkSpaceTools.AddRectangle,
        Operators.AddRectangle,
    ),
    tool_invoke_kmi(
        "Y",
        WorkSpaceTools.Trim,
        Operators.Trim,
    ),
        tool_invoke_kmi(
        "S",
        WorkSpaceTools.Split,
        Operators.Split,
    ),
    (
        Operators.AddSketch,
        {"type": "S", "value": "PRESS"},
        {"properties": [("wait_for_input", True), ]}
    ),
    *constraint_access,
)

addon_keymaps = []


def register():
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon:
        km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')

        # Select
        kmi = km.keymap_items.new('wm.tool_set_by_id', 'ESC', 'PRESS', shift=True)
        kmi.properties.name = WorkSpaceTools.Select
        addon_keymaps.append((km, kmi))

        # Add Sketch
        kmi = km.keymap_items.new(Operators.AddSketch, 'A', 'PRESS', ctrl=True, shift=True)
        kmi.properties.wait_for_input = True
        addon_keymaps.append((km, kmi))

def unregister():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
            addon_keymaps.clear()
