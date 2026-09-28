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

BY_NAME = {tool["name"]: tool for tool in TOOLS}


def listing() -> List[Dict[str, Any]]:
    """The tools as ``tools/list`` reports them, without the local handlers."""
    return [{k: v for k, v in tool.items() if k != "handler"} for tool in TOOLS]
