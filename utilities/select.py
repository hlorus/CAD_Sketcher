from bpy.props import EnumProperty


mode_property = EnumProperty(
    name="Mode",
    items=[
        ("SET", "Set", "Set new selection", "SELECT_SET", 1),
        ("EXTEND", "Extend", "Add to existing selection", "SELECT_EXTEND", 2),
        (
            "SUBTRACT",
            "Subtract",
            "Subtract from existing selection",
            "SELECT_SUBTRACT",
            3,
        ),
        ("TOGGLE", "Toggle", "Toggle selection", "RADIOBUT_OFF", 4),
    ],
)
