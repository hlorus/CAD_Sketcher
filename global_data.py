import sys
from enum import Enum
from mathutils import Vector

registered = False

PYPATH = sys.executable

entities = {}
batches = {}

offscreen = None
redraw_selection_buffer = False

hover = -1
ignore_list = []
selected = []

# Allows to highlight a constraint gizmo,
# Value gets unset in the preselection gizmo
highlight_constraint = None

highlight_entities = []

Z_AXIS = Vector((0, 0, 1))

draw_handle = None

# Workplane requirement options
class WpReq(Enum):
    OPTIONAL, FREE, NOT_FREE = range(3)


solver_state_items = [
    ("OKAY", "Okay", "Successfully solved sketch", "CHECKMARK", 0),
    (
        "INCONSISTENT",
        "Inconsistent",
        "Cannot solve sketch because of inconsistent constraints",
        "ERROR",
        1,
    ),
    (
        "DIDNT_CONVERGE",
        "Didnt Converge",
        "Cannot solve sketch, system didn't converge",
        "ERROR",
        2,
    ),
    (
        "TOO_MANY_UNKNOWNS",
        "Too Many Unknowns",
        "Cannot solve sketch because of too many unknowns",
        "ERROR",
        3,
    ),
    (
        "UNKNOWN_FAILURE",
        "Unknown Failure",
        "Cannot solve sketch because of unknown failure",
        "ERROR",
        4,
    ),
]
