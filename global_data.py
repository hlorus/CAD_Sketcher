from enum import Enum

from mathutils import Vector

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

# The value(s) the running stateful operator is resolving, to show by the
# geometry they belong to:
#   (boxes, region pointer) | None,  boxes = ((text, start, end, focus), ...)
# ``start`` and ``end`` are the ends of the stretch the value measures, already
# in region pixels, so the draw handler can dimension it. ``focus`` is one of
# the BOX_ constants below.
# One box while the value is only being dragged, one per component once it is
# being typed into. The region pointer pins them to the view the mouse is in, so
# they aren't drawn at the same spot in every other 3D view of the screen.
state_value = None

# How a value box is drawn: a plain number, the one a typed digit would land in
# (outlined, so the box itself says a value can be entered), or the one being
# typed into (filled).
BOX_PLAIN = 0
BOX_ACTIVE = 1
BOX_EDITING = 2

# NOTE: interactive selection/hover/highlight state lives in
# ``drawing.selection`` (transient, never persisted to the datablock).

needs_solve = False
needs_redraw = False
needs_curve_update = False
stateful_op_running = False
# True while Shift is held during a draw modal -> bypass geometry snapping live.
snap_bypass = False

# True while a state is picking a revolve axis: the base planes' own directions
# are drawn as lines to aim at, and the one under the cursor is published here.
axis_picker = False
hover_axis = None

# True while an older file is being converted: the names are being handed over
# in steps there, and a pass that re-derived them mid-way would take the name
# the body is about to be given.
migrating_bodies = False

# Guards re-entry while the depsgraph handler writes face-anchored workplane
# matrices (setting matrix_world itself triggers depsgraph_update_post).
updating_face_wp = False

Z_AXIS = Vector((0, 0, 1))

draw_handle = None
hover_draw_handle = None
icon_draw_handle = None
origin_label_draw_handle = None
axis_draw_handle = None
state_value_draw_handle = None

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
