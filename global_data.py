from enum import Enum

from mathutils import Vector

registered = False

entities = {}
batches = {}

# Typed hover element under the cursor for object/mesh-picking tools, published
# by the hover gizmo and rendered by the draw handler. One of:
#   ("OBJECT", name, None) | ("VERTEX"|"EDGE"|"FACE", name, index)
#   | ("CURVE_ELEM", name, element_key) | None
# CURVE_ELEM is a whole curve element (line/arc/circle/point) of a Curves object;
# element_key is its curve_id (sketch) or index tuple (raw), see reference_pick.
hover_element = None
# Accepted pick types of the current stateful-operator state (or None), so the
# hover gizmo detects/highlights what this state will actually pick.
hover_types = None

# NOTE: interactive selection/hover/highlight state lives in
# ``drawing.selection`` (transient, never persisted to the datablock).

needs_solve = False
needs_redraw = False
needs_curve_update = False
stateful_op_running = False
# True while Shift is held during a draw modal -> bypass geometry snapping live.
snap_bypass = False

# Guards re-entry while the depsgraph handler writes face-anchored workplane
# matrices (setting matrix_world itself triggers depsgraph_update_post).
updating_face_wp = False

Z_AXIS = Vector((0, 0, 1))

draw_handle = None
hover_draw_handle = None
icon_draw_handle = None
origin_label_draw_handle = None

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
            "Cannot solve sketch because of inconsistent constraints, check through the failed constraints "
            "and remove the ones that contradict each other."
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
            "Some constraints seem to be redundant, this might cause an error once the constraints are no longer consistent. "
            "Check through the marked constraints and only keep what's necessary."
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
