import sys
from enum import Enum

from mathutils import Vector

registered = False

PYPATH = sys.executable

entities = {}
batches = {}

offscreen = None
redraw_selection_buffer = False

hover = ""
# Typed hover element under the cursor for object/mesh-picking tools, published
# by the hover gizmo and rendered by the draw handler. One of:
#   ("OBJECT", name, None) | ("VERTEX"|"EDGE"|"FACE", name, index) | None
hover_element = None
# Accepted pick types of the current stateful-operator state (or None), so the
# hover gizmo detects/highlights what this state will actually pick.
hover_types = None
ignore_list = []
selected = []
pick_map = {}  # {pick_index: curve_id} rebuilt each frame by ID buffer draw

# Allows to highlight a constraint gizmo,
# Value gets unset in the preselection gizmo
highlight_constraint = None

highlight_entities = []

needs_solve = False
needs_redraw = False
needs_curve_update = False
stateful_op_running = False

# Guards re-entry while the depsgraph handler writes face-anchored workplane
# matrices (setting matrix_world itself triggers depsgraph_update_post).
updating_face_wp = False

Z_AXIS = Vector((0, 0, 1))

draw_handle = None
hover_draw_handle = None

COPY_BUFFER = {}


class WpReq(Enum):
    """Workplane requirement options"""

    OPTIONAL, FREE, NOT_FREE = range(3)


solver_state_items = [
    (
        "OKAY",
        "Okay",
        "Successfully solved sketch.",
        "CHECKMARK",
        0,  # SLVS_RESULT_OKAY
    ),
    (
        "INCONSISTENT",
        "Inconsistent",
        (
            f"Cannot solve sketch because of inconsistent constraints, check through the failed constraints "
            f"and remove the ones that contradict each other."
        ),
        "ERROR",
        1,  # SLVS_RESULT_INCONSISTENT
    ),
    (
        "DIDNT_CONVERGE",
        "Didnt Converge",
        "Cannot solve sketch, system didn't converge.",
        "ERROR",
        2,  # SLVS_RESULT_DIDNT_CONVERGE
    ),
    (
        "TOO_MANY_UNKNOWNS",
        "Too Many Unknowns",
        "Cannot solve sketch because of too many unknowns.",
        "ERROR",
        3,  # SLVS_RESULT_TOO_MANY_UNKNOWNS
    ),
    (
        "REDUNDANT_OK",
        "Redundant Constraints",
        (
            f"Some constraints seem to be redundant, this might cause an error once the constraints are no longer consistent. "
            f"Check through the marked constraints and only keep what's necessary."
        ),
        "INFO",
        4,  # SLVS_RESULT_REDUNDANT_OK
    ),
    (
        "UNKNOWN_FAILURE",
        "Unknown Failure",
        "Cannot solve sketch because of unknown failure.",
        "ERROR",
        5,
    ),
]

# Name of the asset library used for CAD Sketcher assets
LIB_NAME = "CAD Sketcher Assets"
