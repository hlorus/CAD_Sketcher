import bpy

from enum import Enum

mesh_element_types = bpy.types.MeshVertex, bpy.types.MeshEdge, bpy.types.MeshPolygon

unit_key_types = (
    "M",
    "K",
    "D",
    "C",
    "U",
    "A",
    "H",
    "I",
    "L",
    "N",
    "F",
    "T",
    "Y",
    "U",
    "R",
    "E",
    "G",
)

numeric_events = (
    "ZERO",
    "ONE",
    "TWO",
    "THREE",
    "FOUR",
    "FIVE",
    "SIX",
    "SEVEN",
    "EIGHT",
    "NINE",
    "PERIOD",
    "NUMPAD_0",
    "NUMPAD_1",
    "NUMPAD_2",
    "NUMPAD_3",
    "NUMPAD_4",
    "NUMPAD_5",
    "NUMPAD_6",
    "NUMPAD_7",
    "NUMPAD_8",
    "NUMPAD_9",
    "NUMPAD_PERIOD",
    "MINUS",
    "NUMPAD_MINUS",
)


class Operators(str, Enum):
    InvokeTool = "view3d.invoke_tool"
    Test = "view3d.stateop_test"
