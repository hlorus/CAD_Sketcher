"""The tools this server offers, and their JSON schemas.

Deliberately few. An agent is poor at interactive one-pick-at-a-time work and
good at emitting a whole parametric sketch in one go, so the write path is a
single transactional tool that takes a list of edits, solves once, and answers
with the resulting sketch.

Each constraint's accepted entity kinds are read from its ``signature``, so the
schema an agent reads and the check that guards the solver cannot drift apart.
"""

from typing import Any, Dict, List

from . import handlers
from .ops import ADDERS, VALUED, accepted_kinds

SERVER_NAME = "cad-sketcher"

# Handed to the model on discovery. Parametric CAD has conventions an agent will
# not guess (constrain rather than place, metres rather than millimetres, one
# call rather than twenty), and a wrong guess makes a sketch that looks right and
# falls apart the moment a dimension changes.
INSTRUCTIONS = """\
These tools drive CAD Sketcher, a parametric constraint-based sketcher, inside a
Blender session the user is watching. Work the way a CAD user does:

1. Call describe_scene first. It says which sketches exist, which is active, and
   what a length means in this file.
2. Lengths are Blender units, where 1.0 is one metre by default. A 50 mm hole is
   0.05, not 50. Angles are radians.
3. Build a shape in one edit_sketch call, not one call per line. The ops run in
   order, a name given to one op can be used by later ops in the same list, and
   a point can be written inline as [x, y] wherever a point is expected.
4. Place geometry roughly, then constrain it. Coordinates are a starting guess
   the solver moves; constraints are what holds the shape. A sketch is finished
   when describe_sketch reports dof 0, which means nothing is left floating.
   Aim for that, and say so when a sketch is still under-defined.
5. Fix or otherwise tie down one point, or the whole sketch can slide.
6. Look at your work. render_sketch shows one sketch square-on; render_part
   shows the solids from any side, which is the only way to check depth.
   Coordinates and dof rarely reveal that a shape came out inside out or
   mirrored, and a picture does.
7. If the solver reports failed constraints, two of them contradict. Remove or
   change one rather than piling more on.
8. A drawing becomes a part through extrude or revolve, then boolean and array.
   Those act on a sketch or on the body a sketch made; describe_scene lists
   both. Build the profile fully defined first, because the solid follows it.
9. A solid stands on its own unless you pass a boolean. Passing one consumes it
   into the body it touches and hides it, which looks like the solid vanished,
   so use it deliberately and say what you did.
10. Sketch work should end in the sketch, part work should not. Drawing one
   enters it, and building a solid from the sketch the user is in takes them
   back out; working on any other sketch leaves them alone. Pass
   activate: false, or call set_active_sketch, when you want it otherwise.
11. The user is in Blender with you. Every edit is one step in their undo
   history, and destructive tools are worth asking about before you use them.\
"""


def _constraint_help() -> str:
    """One line per constraint type, saying what it takes."""
    lines = []
    for constraint_type in sorted(ADDERS):
        kinds = accepted_kinds(constraint_type)
        args = ", ".join("/".join(k) or "entity" for k in kinds)
        note = (
            " (value optional, measured when omitted)"
            if constraint_type in VALUED
            else ""
        )
        lines.append(f"{constraint_type}: {args}{note}")
    return "; ".join(lines)


_REFERENCE = (
    "The name of an entity: one given by an earlier op in this same list, or one "
    "from describe_sketch. An entity id also works."
)

_EDIT_OPS_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "description": (
        "Edits applied in order, as one transaction. If any op is invalid nothing "
        "is applied. Points may be written inline as [x, y] wherever a point is "
        "expected, which saves declaring them separately."
    ),
    "items": {
        "type": "object",
        "required": ["op"],
        "properties": {
            "op": {
                "type": "string",
                "enum": [
                    "point",
                    "line",
                    "circle",
                    "arc",
                    "constrain",
                    "delete",
                    "set_value",
                    "rename",
                    "set_flag",
                ],
            },
            "name": {
                "type": "string",
                "description": (
                    "Name for what this op creates, so later ops and you can refer "
                    "to it. Also the new name for a rename op."
                ),
            },
            "co": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
                "description": "point: sketch-local [x, y] in Blender units.",
            },
            "p1": {"description": f"line: start point. {_REFERENCE}"},
            "p2": {"description": f"line: end point. {_REFERENCE}"},
            "center": {"description": f"circle/arc: centre point. {_REFERENCE}"},
            "start": {"description": f"arc: start point. {_REFERENCE}"},
            "end": {"description": f"arc: end point. {_REFERENCE}"},
            "radius": {"type": "number", "description": "circle: radius."},
            "type": {
                "type": "string",
                "enum": sorted(ADDERS),
                "description": f"constrain: which constraint. {_constraint_help()}",
            },
            "refs": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "constrain: the entities to constrain, in the order the type "
                    "expects. Passing the wrong kind is rejected."
                ),
            },
            "value": {
                "type": "number",
                "description": (
                    "constrain/set_value: the dimension. Lengths in Blender units, "
                    "angles in radians. Omit on a new dimension to measure the "
                    "geometry as it stands."
                ),
            },
            "measure_only": {
                "type": "boolean",
                "description": (
                    "constrain: report the measurement without driving the "
                    "geometry with it."
                ),
            },
            "target": {
                "type": "string",
                "description": (
                    "delete/set_value/rename/set_flag: the entity or constraint to "
                    "act on, by name or id."
                ),
            },
            "flag": {
                "type": "string",
                "enum": ["construction", "fixed", "visible"],
                "description": "set_flag: which flag to change.",
            },
            "construction": {
                "type": "boolean",
                "description": (
                    "Create as construction geometry: it constrains other "
                    "geometry but is not built."
                ),
            },
            "fixed": {"type": "boolean", "description": "point: pin it in place."},
        },
    },
}

_TARGET = {
    "type": "string",
    "description": (
        "The sketch or body to act on, by name. Naming a sketch acts on the "
        "body that realises it. describe_scene lists both."
    ),
}

_BOOLEAN = {
    "type": "string",
    "enum": ["none", "difference", "union", "intersect"],
    "description": (
        "What the new solid does to the bodies it touches. Default none: it "
        "stands on its own. Anything else consumes it into those bodies and "
        "hides it, so say what you did when you use one."
    ),
}

FEATURE_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "extrude",
        "title": "Extrude a sketch",
        "description": (
            "Give a sketch thickness, making a solid. The profile has to be "
            "closed. This is what turns a drawing into a part."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["sketch", "distance"],
            "properties": {
                "sketch": _TARGET,
                "distance": {
                    "type": "number",
                    "description": "How far to extrude, in Blender units.",
                },
                "mirror": {
                    "type": "boolean",
                    "description": (
                        "Grow both ways from the sketch plane, so the solid is "
                        "centred on it, rather than only one way."
                    ),
                },
                "asymmetry_distance": {
                    "type": "number",
                    "description": "Extrude this far the other way as well.",
                },
                "boolean": _BOOLEAN,
            },
        },
        "handler": handlers.extrude,
    },
    {
        "name": "revolve",
        "title": "Revolve a sketch",
        "description": "Sweep a sketch around an axis to make a solid of revolution.",
        "inputSchema": {
            "type": "object",
            "required": ["sketch", "angle"],
            "properties": {
                "sketch": _TARGET,
                "angle": {
                    "type": "number",
                    "description": "How far to sweep, in radians. A full turn is 2*pi.",
                },
                "flip": {"type": "boolean", "description": "Sweep the other way."},
                "axis_origin": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "A point on the axis, in world space.",
                },
                "axis_direction": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "Which way the axis runs, in world space.",
                },
                "boolean": _BOOLEAN,
            },
        },
        "handler": handlers.revolve,
    },
    {
        "name": "array",
        "title": "Repeat a solid",
        "description": "Repeat a solid in a row, or around an axis.",
        "inputSchema": {
            "type": "object",
            "required": ["target", "count"],
            "properties": {
                "target": _TARGET,
                "mode": {
                    "type": "string",
                    "enum": ["linear", "circular"],
                    "description": "A row, or around an axis. Default linear.",
                },
                "count": {
                    "type": "integer",
                    "minimum": 2,
                    "description": "How many copies in total, the original included.",
                },
                "offset": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "linear: the step between copies, as [x, y, z].",
                },
                "offset_is_total": {
                    "type": "boolean",
                    "description": (
                        "linear: read offset as the distance across the whole "
                        "array rather than between neighbours."
                    ),
                },
                "angle": {
                    "type": "number",
                    "description": "circular: how far round, in radians. Default a full turn.",
                },
                "angle_is_total": {
                    "type": "boolean",
                    "description": (
                        "circular: read angle as the whole sweep rather than "
                        "the step. Default true."
                    ),
                },
                "axis_origin": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "circular: a point on the axis.",
                },
                "axis_direction": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                    "description": "circular: which way the axis runs.",
                },
                "merge": {
                    "type": "boolean",
                    "description": "Weld the copies where they touch.",
                },
            },
        },
        "handler": handlers.array,
    },
    {
        "name": "boolean",
        "title": "Boolean two solids",
        "description": (
            "Cut one solid with another, merge them, or keep the overlap. The "
            "cutter is consumed into the target and hidden."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["target", "cutter"],
            "properties": {
                "target": {**_TARGET, "description": "The body that is changed."},
                "cutter": {**_TARGET, "description": "The body doing the cutting."},
                "operation": {
                    "type": "string",
                    "enum": ["difference", "union", "intersect"],
                    "description": "Default difference.",
                },
                "self_intersection": {
                    "type": "boolean",
                    "description": "Handle geometry that crosses itself. Slower.",
                },
                "hole_tolerant": {
                    "type": "boolean",
                    "description": "Cope with a profile that is not watertight.",
                },
            },
        },
        "handler": handlers.boolean,
    },
    {
        "name": "render_part",
        "title": "Look at the solids",
        "description": (
            "A PNG of the solids from a named direction. render_sketch only "
            "shows one sketch square-on to its own plane, which says nothing "
            "about how tall a part is, so use this to check a shape that has "
            "any depth to it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "part": {
                    "type": "string",
                    "description": (
                        "Show only this part or body, and what belongs to it. "
                        "Omit to show everything solid in the scene."
                    ),
                },
                "view": {
                    "type": "string",
                    "enum": [
                        "iso",
                        "front",
                        "back",
                        "left",
                        "right",
                        "top",
                        "bottom",
                    ],
                    "description": (
                        "Where to look from. Default iso, which shows depth; "
                        "the straight-on views are for checking one dimension."
                    ),
                },
                "size": {
                    "type": "integer",
                    "minimum": 256,
                    "maximum": 2048,
                    "description": "Image size in pixels, square. Default 800.",
                },
            },
        },
        "annotations": {"readOnlyHint": True},
        "handler": handlers.render_part,
    },
    {
        "name": "make_part",
        "title": "Make a part",
        "description": (
            "Make a body, and anything named with it, into one part: it then "
            "moves, instances and is placed in an assembly as a single thing."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["target"],
            "properties": {
                "target": {**_TARGET, "description": "The body the part is rooted in."},
                "members": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Other bodies to join into the part.",
                },
            },
        },
        "handler": handlers.make_part,
    },
]

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "describe_scene",
        "title": "List sketches",
        "description": (
            "The CAD Sketcher sketches in the open Blender scene, which one is "
            "active, and the unit settings. Start here."
        ),
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
        "handler": handlers.describe_scene,
    },
    {
        "name": "describe_sketch",
        "title": "Read a sketch",
        "description": (
            "Everything in one sketch: its entities with their geometry, its "
            "constraints, its degrees of freedom and its solver state. A sketch "
            "with dof 0 and solver state OKAY is fully defined."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sketch": {
                    "type": "string",
                    "description": "Sketch name. Defaults to the active sketch.",
                }
            },
        },
        "annotations": {"readOnlyHint": True},
        "handler": handlers.describe_sketch,
    },
    {
        "name": "render_sketch",
        "title": "Look at a sketch",
        "description": (
            "A PNG of a sketch seen square-on to its plane, framed on its "
            "geometry. Use it to check your work: the numbers rarely reveal that a "
            "shape came out wrong, and the picture does."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sketch": {
                    "type": "string",
                    "description": "Sketch name. Defaults to the active sketch.",
                },
                "size": {
                    "type": "integer",
                    "minimum": 256,
                    "maximum": 2048,
                    "description": "Image size in pixels, square. Default 800.",
                },
            },
        },
        "annotations": {"readOnlyHint": True},
        "handler": handlers.render_sketch,
    },
    {
        "name": "edit_sketch",
        "title": "Edit a sketch",
        "description": (
            "Apply a list of edits to a sketch as one transaction, then solve and "
            "return the sketch as it now stands. Nothing is applied unless every "
            "op is valid, and the whole call is one undo step for the user. Build "
            "a shape in one call rather than one call per element."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["ops"],
            "properties": {
                "sketch": {
                    "type": "string",
                    "description": "Sketch name. Defaults to the active sketch.",
                },
                "ops": _EDIT_OPS_SCHEMA,
            },
        },
        "handler": handlers.edit_sketch,
    },
    {
        "name": "create_sketch",
        "title": "Create a sketch",
        "description": (
            "Start a new sketch on one of the scene's base planes and make it active."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name for the new sketch."},
                "activate": {
                    "type": "boolean",
                    "description": (
                        "Enter the new sketch, which is what a person "
                        "drawing one would see. Default true. Pass false "
                        "when the sketch is a step towards a solid rather "
                        "than the thing the user asked for."
                    ),
                },
                "plane": {
                    "type": "string",
                    "enum": ["XY", "XZ", "YZ"],
                    "description": "Which base plane to sketch on. Default XY.",
                },
            },
        },
        "handler": handlers.create_sketch,
    },
    {
        "name": "set_active_sketch",
        "title": "Enter or leave a sketch",
        "description": (
            "Enter a sketch, or leave sketch mode when no name is given. The "
            "other tools all take a name, so this is only about what the user "
            "is looking at: sketch mode switches their tools and fades "
            "everything else. Leave it when you are done."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sketch": {
                    "type": "string",
                    "description": "Sketch to enter. Omit to leave sketch mode.",
                }
            },
        },
        "handler": handlers.set_active_sketch,
    },
    {
        "name": "delete_sketch",
        "title": "Delete a sketch",
        "description": (
            "Delete a sketch and the geometry built from it. This cannot be "
            "undone through this server; ask before using it."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["sketch"],
            "properties": {
                "sketch": {"type": "string", "description": "Sketch name."},
            },
        },
        "annotations": {"destructiveHint": True},
        "handler": handlers.delete_sketch,
    },
    {
        "name": "solve_sketch",
        "title": "Solve a sketch",
        "description": (
            "Re-run the constraint solver on a sketch and report its state. "
            "edit_sketch already solves, so this is for checking a sketch you "
            "have not just edited."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sketch": {
                    "type": "string",
                    "description": "Sketch name. Defaults to the active sketch.",
                }
            },
        },
        "handler": handlers.solve_sketch,
    },
]

TOOLS += FEATURE_TOOLS

BY_NAME = {tool["name"]: tool for tool in TOOLS}


def listing() -> List[Dict[str, Any]]:
    """The tools as ``tools/list`` reports them, without the local handlers."""
    return [{k: v for k, v in tool.items() if k != "handler"} for tool in TOOLS]
