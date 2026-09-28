"""Turn sketches into solids: extrude, revolve, array, boolean, parts.

Each of these drives the add-on's own operator rather than building a modifier
by hand, so an agent's feature is the same thing the interactive tool makes:
same node group, same boolean plumbing, same part membership, and the user can
edit it afterwards in the redo panel like any other.

The one thing deliberately not inherited is the silent auto-boolean. A tool run
by hand can watch what it just absorbed; an agent cannot, and a solid that
quietly merges into its neighbour and is then hidden as a cutter is the most
confusing thing this add-on does. So ``boolean`` is an explicit argument here,
defaulting to leaving the solid alone.
"""

from typing import Any, Dict, List, Optional

import bpy

from ..utilities.body import body_of, is_body, sketch_of
from ..utilities.part import is_part_root, part_root_of

# What `boolean` accepts, mapped to the operator's own enum.
BOOLEAN_OPERATIONS = {
    "none": "None",
    "difference": "Difference",
    "union": "Union",
    "intersect": "Intersect",
}


class FeatureError(Exception):
    """A feature that cannot be built, with a reason the agent should read."""


def solid_objects(context) -> List[bpy.types.Object]:
    """Every mesh body in the scene, which is what features act on."""
    return [obj for obj in context.scene.objects if is_body(obj)]


def find_target(context, name: Optional[str]) -> bpy.types.Object:
    """The object a feature goes on, from a sketch name or a body name.

    A sketch is the natural thing to name, but the feature stack lives on the
    mesh body that realises it, so a sketch resolves to its body.
    """
    if not name:
        raise FeatureError(
            "Name the sketch or body to work on. describe_scene lists them."
        )

    obj = bpy.data.objects.get(name)
    if obj is None:
        known = ", ".join(sorted(o.name for o in context.scene.objects)) or "none"
        raise FeatureError(f"No object named {name!r}. In this scene: {known}.")

    target = body_of(obj) or obj
    if target.type not in {"MESH", "CURVE"}:
        raise FeatureError(
            f"{name!r} is a {target.type.lower()}, which no feature can be built "
            "on. Name a sketch or a body."
        )
    return target


def _operation(value: Optional[str]) -> str:
    """The operator's boolean enum for what the agent asked for."""
    key = (value or "none").lower()
    if key not in BOOLEAN_OPERATIONS:
        raise FeatureError(
            f"boolean must be one of {', '.join(sorted(BOOLEAN_OPERATIONS))}, "
            f"got {value!r}"
        )
    return BOOLEAN_OPERATIONS[key]


def _ensure_node_group(kind: str) -> None:
    """Build the node group a feature needs, as the tool's ``init`` would.

    The interactive tools build theirs when the modal run starts. Driving the
    same operator by name skips ``init``, so the group has to be built here or
    the operator fails with "Unable to load node group".
    """
    if kind == "extrude":
        from ..utilities.extrude_nodes import (
            build_extrude_node_group,
            ensure_extrude_edge_walls,
        )

        build_extrude_node_group()
        ensure_extrude_edge_walls(bpy.data.node_groups.get("CAD Sketcher Extrude"))
    elif kind == "revolve":
        from ..utilities.revolve_nodes import build_revolve_node_group

        build_revolve_node_group()
    elif kind == "boolean":
        from ..utilities.boolean_nodes import build_boolean_node_group

        build_boolean_node_group()
    elif kind == "array_linear":
        from ..utilities.array_nodes import build_array_node_group

        build_array_node_group()
    elif kind == "array_circular":
        from ..utilities.circular_array_nodes import build_circular_array_node_group

        build_circular_array_node_group()


def _run(operator, **props) -> None:
    """Run one of the add-on's operators, turning a refusal into an error."""
    try:
        result = operator(**props)
    except RuntimeError as e:
        raise FeatureError(str(e)) from e
    if "FINISHED" not in result:
        raise FeatureError(
            f"CAD Sketcher declined to build it ({', '.join(result)}). The "
            "profile may be open, empty, or not something a solid can be made "
            "from."
        )


def extrude(context, params: Dict[str, Any]) -> bpy.types.Object:
    """Give a sketch thickness."""
    target = find_target(context, params.get("sketch") or params.get("target"))
    distance = params.get("distance")
    if not isinstance(distance, (int, float)) or isinstance(distance, bool):
        raise FeatureError("distance must be a number, in Blender units")
    if distance == 0:
        raise FeatureError("distance must not be zero")

    props = {
        "target_name": target.name,
        "offset": float(distance),
        "mirror": bool(params.get("mirror", False)),
        "operation": _operation(params.get("boolean")),
        # Say the choice is already made. Left undecided, the tool re-decides
        # from what the solid overlaps whenever the file's Auto Boolean is on,
        # which would silently overrule what was asked for here.
        "boolean_detected": True,
    }
    asymmetry = params.get("asymmetry_distance")
    if asymmetry is not None:
        props["asymmetry"] = True
        props["asymmetry_distance"] = float(asymmetry)

    _ensure_node_group("extrude")
    _run(bpy.ops.view3d.slvs_node_extrude, **props)
    return target


def revolve(context, params: Dict[str, Any]) -> bpy.types.Object:
    """Sweep a sketch around an axis."""
    target = find_target(context, params.get("sketch") or params.get("target"))
    angle = params.get("angle")
    if not isinstance(angle, (int, float)) or isinstance(angle, bool):
        raise FeatureError("angle must be a number, in radians")

    props = {
        "target_name": target.name,
        "angle": float(angle),
        "flip": bool(params.get("flip", False)),
        "operation": _operation(params.get("boolean")),
        # Say the choice is already made. Left undecided, the tool re-decides
        # from what the solid overlaps whenever the file's Auto Boolean is on,
        # which would silently overrule what was asked for here.
        "boolean_detected": True,
    }
    if params.get("axis_origin") is not None:
        props["axis_origin"] = _vector(params["axis_origin"], "axis_origin")
    if params.get("axis_direction") is not None:
        props["axis_direction"] = _vector(params["axis_direction"], "axis_direction")

    _ensure_node_group("revolve")
    _run(bpy.ops.view3d.slvs_node_revolve, **props)
    return target


def array(context, params: Dict[str, Any]) -> bpy.types.Object:
    """Repeat a solid, in a row or around an axis."""
    target = find_target(context, params.get("target") or params.get("sketch"))
    mode = (params.get("mode") or "linear").lower()
    count = params.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 2:
        raise FeatureError("count must be a whole number of 2 or more")

    if mode == "linear":
        offset = params.get("offset")
        if offset is None:
            raise FeatureError("a linear array needs offset, as [x, y, z]")
        _ensure_node_group("array_linear")
        _run(
            bpy.ops.view3d.slvs_node_array_linear,
            target_name=target.name,
            count=count,
            offset=_vector(offset, "offset"),
            use_total_distance=bool(params.get("offset_is_total", False)),
            merge=bool(params.get("merge", False)),
        )
    elif mode == "circular":
        props = {
            "target_name": target.name,
            "count": count,
            "angle": float(params.get("angle", 6.283185307179586)),
            "use_total_angle": bool(params.get("angle_is_total", True)),
            "merge": bool(params.get("merge", False)),
        }
        if params.get("axis_origin") is not None:
            props["axis_origin"] = _vector(params["axis_origin"], "axis_origin")
        if params.get("axis_direction") is not None:
            props["axis_direction"] = _vector(
                params["axis_direction"], "axis_direction"
            )
        _ensure_node_group("array_circular")
        _run(bpy.ops.view3d.slvs_node_array_circular, **props)
    else:
        raise FeatureError(f"mode must be linear or circular, got {mode!r}")

    return target


def boolean(context, params: Dict[str, Any]) -> bpy.types.Object:
    """Cut one solid with another, or merge them."""
    target = find_target(context, params.get("target"))
    cutter = find_target(context, params.get("cutter"))
    if cutter.name == target.name:
        raise FeatureError("a solid cannot be booleaned with itself")

    operation = _operation(params.get("operation") or "difference")
    if operation == "None":
        raise FeatureError(
            "operation must be difference, union or intersect; 'none' would do "
            "nothing here"
        )

    _ensure_node_group("boolean")
    _run(
        bpy.ops.view3d.slvs_node_boolean,
        target_name=target.name,
        cutter_name=cutter.name,
        operation=operation,
        self_intersection=bool(params.get("self_intersection", False)),
        hole_tolerant=bool(params.get("hole_tolerant", False)),
    )
    return target


def make_part(context, params: Dict[str, Any]) -> bpy.types.Object:
    """Promote a body to a part, so it moves and instances as one thing.

    Unlike the feature tools this one reads the selection rather than a name, so
    the selection is set here and put back afterwards: an agent must not leave
    the user's selection somewhere they did not put it.
    """
    root = find_target(context, params.get("target"))
    members = [find_target(context, name) for name in params.get("members") or []]

    view_layer = context.view_layer
    previous = list(context.selected_objects)
    previous_active = view_layer.objects.active
    try:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in (root, *members):
            obj.select_set(True)
        view_layer.objects.active = root
        _run(bpy.ops.view3d.slvs_make_part)
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in previous:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if previous_active is not None and previous_active.name in bpy.data.objects:
            view_layer.objects.active = previous_active
    return root


def _vector(value: Any, what: str) -> List[float]:
    """A 3D vector from an agent's list."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise FeatureError(f"{what} must be [x, y, z], got {value!r}")
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise FeatureError(f"{what} must be three numbers, got {value!r}")
    return [float(c) for c in value]


# -- Reporting ---------------------------------------------------------------


def body_data(obj: bpy.types.Object) -> Dict[str, Any]:
    """One body: what made it, what is stacked on it, and where it belongs."""
    sketch = sketch_of(obj)
    root = part_root_of(obj)
    data: Dict[str, Any] = {
        "name": obj.name,
        "from_sketch": sketch.name if sketch is not None else None,
        "features": [m.name for m in obj.modifiers],
        "visible": not obj.hide_viewport,
    }
    if root is not None:
        data["part"] = root.name
    if is_part_root(obj):
        data["is_part_root"] = True
    if obj.hide_viewport:
        # The one state a user cannot see in the outliner by default, so say it.
        data["hidden_because"] = (
            "it is a cutter feeding another body; its own solid would sit over "
            "the result"
        )
    return data
