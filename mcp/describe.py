"""Read a sketch into plain JSON-safe data for an agent.

Every write tool answers with the sketch this produces, so the agent always sees
the result of what it just did (dof, solver state, which constraints failed)
without asking a second time.
"""

from typing import Any, Dict, List, Optional

import bpy

from ..model.curve_ref import curve_ref
from ..model.sketch_ref import Sketch, get_active_sketch, get_sketches
from ..utilities.curve_data import read_curve_id_list


def _round(value: float, digits: int = 6) -> float:
    """Trim solver float noise, so identical geometry reads identically."""
    return round(float(value), digits)


def _co(vec) -> List[float]:
    return [_round(vec[0]), _round(vec[1])]


def entity_data(ref) -> Dict[str, Any]:
    """One entity as name, kind, geometry and flags."""
    data: Dict[str, Any] = {
        "name": ref.name,
        "id": ref.curve_id,
        "kind": _kind(ref),
    }

    if ref.is_point():
        data["co"] = _co(ref.co)
    elif ref.is_line():
        p1, p2 = ref.p1, ref.p2
        data["p1"] = p1.name if p1 else None
        data["p2"] = p2.name if p2 else None
        data["length"] = _round(ref.length)
    elif ref.is_circle():
        ct = ref.ct
        data["center"] = ct.name if ct else None
        data["radius"] = _round(ref.radius)
    elif ref.is_arc():
        ct, start, end = ref.ct, ref.start, ref.end
        data["center"] = ct.name if ct else None
        data["start"] = start.name if start else None
        data["end"] = end.name if end else None
        data["radius"] = _round(ref.radius)

    if ref.construction:
        data["construction"] = True
    if ref.fixed:
        data["fixed"] = True
    if ref.is_origin:
        data["origin"] = True
    return data


def _kind(ref) -> str:
    if ref.is_point():
        return "point"
    if ref.is_line():
        return "line"
    if ref.is_circle():
        return "circle"
    if ref.is_arc():
        return "arc"
    return "unknown"


def constraint_data(constraint, names: Dict[str, str], label: str) -> Dict[str, Any]:
    """One constraint as type, the entity names it holds, and its value."""
    refs = [
        names.get(cid, cid)
        for cid in (getattr(constraint, f"curve_id_{n}", "") for n in (1, 2, 3))
        if cid
    ]
    data: Dict[str, Any] = {
        "name": label,
        "uid": constraint.constraint_uid,
        "type": constraint.type,
        "refs": refs,
    }
    if "value" in getattr(constraint, "props", ()):
        data["value"] = _round(constraint.value)
    if constraint.failed:
        data["failed"] = True
    if getattr(constraint, "is_reference", False):
        data["measure_only"] = True
    return data


def constraint_labels(constraints) -> Dict[str, str]:
    """A distinct name per constraint, keyed by uid.

    A constraint's own ``name`` defaults to its type, so a sketch usually holds
    several called "Distance". An agent needs to tell them apart, so an ordinal
    is appended wherever a name is shared.
    """
    counts: Dict[str, int] = {}
    labels: Dict[str, str] = {}
    all_names = [c.name for c in constraints.all]
    for constraint in constraints.all:
        name = constraint.name
        if all_names.count(name) == 1:
            labels[constraint.constraint_uid] = name
            continue
        counts[name] = counts.get(name, 0) + 1
        labels[constraint.constraint_uid] = f"{name} {counts[name]}"
    return labels


def sketch_data(sketch: Sketch) -> Dict[str, Any]:
    """A whole sketch: entities, constraints, degrees of freedom, solver state."""
    entities = []
    names = {}
    curve_data = sketch.target_object.data
    for curve_id in read_curve_id_list(curve_data):
        if not curve_id:
            continue
        ref = curve_ref(sketch, curve_id)
        entities.append(entity_data(ref))
        names[curve_id] = ref.name

    labels = constraint_labels(sketch.constraints)
    constraints = [
        constraint_data(c, names, labels[c.constraint_uid])
        for c in sketch.constraints.all
    ]

    return {
        "sketch": sketch.name,
        "is_3d": sketch.is_3d,
        "dof": sketch.dof,
        "solver_state": sketch.solver_state,
        "fully_defined": sketch.dof == 0 and sketch.solver_state == "OKAY",
        "entities": entities,
        "constraints": constraints,
    }


def scene_data(context) -> Dict[str, Any]:
    """The sketches in the scene, the active one, and how to read lengths."""
    units = context.scene.unit_settings
    active = get_active_sketch(context)

    sketches = []
    for sketch in get_sketches(context):
        sketches.append(
            {
                "name": sketch.name,
                "is_3d": sketch.is_3d,
                "dof": sketch.dof,
                "solver_state": sketch.solver_state,
                "entity_count": len(sketch.target_object.data.curves),
                "constraint_count": sum(1 for _ in sketch.constraints.all),
            }
        )

    return {
        "sketches": sketches,
        "active_sketch": active.name if active else None,
        "units": {
            "system": units.system,
            "length_unit": units.length_unit,
            "scale_length": _round(units.scale_length),
            "note": (
                "Coordinates and distances in these tools are Blender units "
                "(1.0 = 1 m at the default scale), not the display unit."
            ),
        },
        "blender_version": ".".join(str(v) for v in bpy.app.version),
    }


def find_sketch(context, name: Optional[str]) -> Sketch:
    """The named sketch, or the active one when no name is given."""
    if not name:
        sketch = get_active_sketch(context)
        if sketch is None:
            raise LookupError(
                "No sketch name given and no sketch is active. "
                "Call describe_scene to list the sketches."
            )
        return sketch

    for sketch in get_sketches(context):
        if sketch.name == name:
            return sketch

    known = ", ".join(s.name for s in get_sketches(context)) or "none"
    raise LookupError(f"No sketch named {name!r}. Sketches in the scene: {known}.")
