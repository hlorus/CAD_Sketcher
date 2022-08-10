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
    (
        "OKAY",
        "Okay",
        "Successfully solved sketch",
        "CHECKMARK",
        0,  # SLVS_RESULT_OKAY
    ),
    (
        "INCONSISTENT",
        "Inconsistent",
        "Cannot solve sketch because of inconsistent constraints",
        "ERROR",
        1,  # SLVS_RESULT_INCONSISTENT
    ),
    (
        "DIDNT_CONVERGE",
        "Didnt Converge",
        "Cannot solve sketch, system didn't converge",
        "ERROR",
        2,  # SLVS_RESULT_DIDNT_CONVERGE
    ),
    (
        "TOO_MANY_UNKNOWNS",
        "Too Many Unknowns",
        "Cannot solve sketch because of too many unknowns",
        "ERROR",
        3,  # SLVS_RESULT_TOO_MANY_UNKNOWNS
    ),
    (
        "INIT_ERROR",
        "Initialize Error",
        "Initializing solver failed",
        "ERROR",
        4,  # SLVS_RESULT_INIT_ERROR
    ),
    (
        "REDUNDANT_OK",
        "Redundant Ok",
        "Constraints seem redundand",
        "CHECKMARK",
        5,  # SLVS_RESULT_REDUNDANT_OK
    ),
    (
        "UNKNOWN_FAILURE",
        "Unknown Failure",
        "Cannot solve sketch because of unknown failure",
        "ERROR",
        6,
    ),
]
