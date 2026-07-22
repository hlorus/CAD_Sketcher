"""CAD Sketcher MCP command handlers.

Pure functions taking Blender context + params and returning JSON-serializable
result dicts. Prefer scene.sketcher PropertyGroup APIs over modal operators.
"""

from __future__ import annotations

import io
import logging
import traceback
from contextlib import redirect_stdout
from typing import Any, Dict, List, Optional

import bpy

logger = logging.getLogger(__name__)


class HandlerError(Exception):
    """Raised for invalid MCP requests (bad args, missing entities, etc.)."""


def _sketcher(context=None):
    context = context or bpy.context
    sk = getattr(context.scene, "sketcher", None)
    if sk is None:
        raise HandlerError("CAD Sketcher is not available on this scene")
    return sk


def _entity(entities, index: int, label: str = "entity"):
    if index is None:
        raise HandlerError(f"Missing {label} index")
    ent = entities.get(int(index))
    if ent is None:
        raise HandlerError(f"{label} not found: {index}")
    return ent


def _sketch(entities, sketch_i: Optional[int] = None, required: bool = True):
    if sketch_i is None or sketch_i == -1:
        sk_props = entities.id_data.sketcher
        sketch = sk_props.active_sketch
        if sketch is None and required:
            raise HandlerError("No sketch_i given and no active sketch")
        return sketch
    return _entity(entities, sketch_i, "sketch")


def _entity_summary(entity) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "index": entity.slvs_index,
        "type": getattr(entity, "type", type(entity).__name__),
        "name": str(entity.name) if getattr(entity, "name", None) else str(entity),
        "fixed": bool(getattr(entity, "fixed", False)),
        "construction": bool(getattr(entity, "construction", False)),
        "origin": bool(getattr(entity, "origin", False)),
        "visible": bool(getattr(entity, "visible", True)),
    }
    if hasattr(entity, "sketch_i"):
        data["sketch_i"] = entity.sketch_i
    if hasattr(entity, "co"):
        data["co"] = [float(entity.co[0]), float(entity.co[1])]
    if hasattr(entity, "location"):
        loc = entity.location
        data["location"] = [float(loc[0]), float(loc[1]), float(loc[2])]
    if hasattr(entity, "p1_i"):
        data["p1_i"] = entity.p1_i
    if hasattr(entity, "p2_i"):
        data["p2_i"] = entity.p2_i
    if hasattr(entity, "ct_i"):
        data["ct_i"] = entity.ct_i
    if hasattr(entity, "nm_i"):
        data["nm_i"] = entity.nm_i
    if hasattr(entity, "radius"):
        data["radius"] = float(entity.radius)
    if hasattr(entity, "wp_i"):
        data["wp_i"] = entity.wp_i
    if hasattr(entity, "solver_state"):
        data["solver_state"] = entity.solver_state
    if hasattr(entity, "dof"):
        data["dof"] = int(entity.dof)
    return data


def _constraint_summary(constr) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "uid": getattr(constr, "constraint_uid", ""),
        "type": getattr(constr, "type", type(constr).__name__),
        "name": str(constr),
        "failed": bool(getattr(constr, "failed", False)),
        "visible": bool(getattr(constr, "visible", True)),
    }
    if hasattr(constr, "sketch_i"):
        data["sketch_i"] = constr.sketch_i
    entities = []
    for i in range(1, 5):
        attr = f"entity{i}_i"
        if hasattr(constr, attr):
            val = getattr(constr, attr)
            if val is not None and val != -1:
                entities.append(val)
                data[attr] = val
    data["entities"] = entities
    if hasattr(constr, "value"):
        try:
            data["value"] = float(constr.value)
        except Exception:
            pass
    return data


def get_sketcher_status(context=None, **_params) -> Dict[str, Any]:
    from .. import global_data
    from ..utilities.install import check_module

    context = context or bpy.context
    sk = _sketcher(context)
    active = sk.active_sketch
    module = check_module("slvs", raise_exception=False)
    return {
        "addon_registered": bool(global_data.registered),
        "slvs_available": module is not None,
        "active_sketch_i": sk.active_sketch_i,
        "active_sketch_name": str(active.name) if active else None,
        "sketch_count": len(list(sk.entities.sketches)),
        "entity_count": sum(1 for _ in sk.entities.all),
        "constraint_count": sum(1 for _ in sk.constraints.all),
    }


def ensure_origin(context=None, **_params) -> Dict[str, Any]:
    context = context or bpy.context
    entities = _sketcher(context).entities
    entities.ensure_origin_elements(context)
    return {
        "origin_plane_XY": entities.origin_plane_XY.slvs_index,
        "ok": True,
    }


def list_sketches(context=None, **_params) -> Dict[str, Any]:
    sk = _sketcher(context)
    sketches = [_entity_summary(s) for s in sk.entities.sketches]
    return {"sketches": sketches, "active_sketch_i": sk.active_sketch_i}


def get_sketch(context=None, sketch_i: Optional[int] = None, **_params) -> Dict[str, Any]:
    sk = _sketcher(context)
    sketch = _sketch(sk.entities, sketch_i, required=True)
    summary = _entity_summary(sketch)
    ents = [
        e
        for e in sk.entities.all
        if getattr(e, "sketch_i", None) == sketch.slvs_index
        or e.slvs_index == sketch.slvs_index
    ]
    cons = [
        c
        for c in sk.constraints.all
        if getattr(c, "sketch_i", -1) == sketch.slvs_index
    ]
    summary["entity_count"] = len(ents)
    summary["constraint_count"] = len(cons)
    return summary


def list_entities(
    context=None, sketch_i: Optional[int] = None, include_origin: bool = False, **_params
) -> Dict[str, Any]:
    sk = _sketcher(context)
    filter_i = int(sketch_i) if sketch_i is not None and int(sketch_i) != -1 else None
    items: List[Dict[str, Any]] = []
    for e in sk.entities.all:
        if e.origin and not include_origin:
            continue
        if filter_i is not None:
            belongs = getattr(e, "sketch_i", -1) == filter_i
            is_self = e.slvs_index == filter_i
            if not (belongs or is_self):
                continue
        items.append(_entity_summary(e))
    return {"entities": items}


def list_constraints(
    context=None, sketch_i: Optional[int] = None, **_params
) -> Dict[str, Any]:
    sk = _sketcher(context)
    items = []
    for c in sk.constraints.all:
        if sketch_i is not None and sketch_i != -1:
            if getattr(c, "sketch_i", -1) != int(sketch_i):
                continue
        items.append(_constraint_summary(c))
    return {"constraints": items}


def add_sketch(
    context=None,
    activate: bool = True,
    name: Optional[str] = None,
    workplane_i: Optional[int] = None,
    **_params,
) -> Dict[str, Any]:
    context = context or bpy.context
    sk = _sketcher(context)
    entities = sk.entities
    entities.ensure_origin_elements(context)
    if workplane_i is not None:
        wp = _entity(entities, workplane_i, "workplane")
    else:
        wp = entities.origin_plane_XY
    sketch = entities.add_sketch(wp, index_reference=False)
    # Fixed sketch-space origin (matches interactive add_sketch convention)
    entities.add_point_2d((0.0, 0.0), sketch, fixed=True, index_reference=True)
    if name:
        sketch.name = name
    if activate:
        sk.active_sketch = sketch
    return _entity_summary(sketch)


def set_active_sketch(
    context=None, sketch_i: Optional[int] = None, **_params
) -> Dict[str, Any]:
    sk = _sketcher(context)
    if sketch_i is None or int(sketch_i) == -1:
        sk.active_sketch = None
        return {"active_sketch_i": -1}
    sketch = _entity(sk.entities, sketch_i, "sketch")
    sk.active_sketch = sketch
    return {"active_sketch_i": sketch.slvs_index, "name": str(sketch.name)}


def add_point_2d(
    context=None,
    co=None,
    sketch_i: Optional[int] = None,
    fixed: bool = False,
    construction: bool = False,
    **_params,
) -> Dict[str, Any]:
    if co is None or len(co) != 2:
        raise HandlerError("co must be [x, y]")
    sk = _sketcher(context)
    sketch = _sketch(sk.entities, sketch_i)
    index = sk.entities.add_point_2d(
        (float(co[0]), float(co[1])),
        sketch,
        fixed=fixed,
        construction=construction,
        index_reference=True,
    )
    return _entity_summary(sk.entities.get(index))


def add_line_2d(
    context=None,
    p1_i: Optional[int] = None,
    p2_i: Optional[int] = None,
    sketch_i: Optional[int] = None,
    construction: bool = False,
    **_params,
) -> Dict[str, Any]:
    sk = _sketcher(context)
    sketch = _sketch(sk.entities, sketch_i)
    p1 = _entity(sk.entities, p1_i, "p1")
    p2 = _entity(sk.entities, p2_i, "p2")
    index = sk.entities.add_line_2d(
        p1, p2, sketch, construction=construction, index_reference=True
    )
    return _entity_summary(sk.entities.get(index))


def add_circle_2d(
    context=None,
    center_i: Optional[int] = None,
    radius: float = 1.0,
    sketch_i: Optional[int] = None,
    construction: bool = False,
    **_params,
) -> Dict[str, Any]:
    sk = _sketcher(context)
    sketch = _sketch(sk.entities, sketch_i)
    ct = _entity(sk.entities, center_i, "center")
    nm = sk.entities.add_normal_2d(sketch, index_reference=True)
    index = sk.entities.add_circle(
        nm,
        ct,
        float(radius),
        sketch,
        construction=construction,
        index_reference=True,
    )
    return _entity_summary(sk.entities.get(index))


def add_arc_2d(
    context=None,
    center_i: Optional[int] = None,
    p1_i: Optional[int] = None,
    p2_i: Optional[int] = None,
    sketch_i: Optional[int] = None,
    construction: bool = False,
    invert: bool = False,
    **_params,
) -> Dict[str, Any]:
    sk = _sketcher(context)
    sketch = _sketch(sk.entities, sketch_i)
    ct = _entity(sk.entities, center_i, "center")
    p1 = _entity(sk.entities, p1_i, "p1")
    p2 = _entity(sk.entities, p2_i, "p2")
    nm = sk.entities.add_normal_2d(sketch, index_reference=True)
    index = sk.entities.add_arc(
        nm,
        ct,
        p1,
        p2,
        sketch,
        invert=invert,
        construction=construction,
        index_reference=True,
    )
    return _entity_summary(sk.entities.get(index))


def _resolve_sketch_arg(sk, sketch_i):
    if sketch_i is None:
        return sk.active_sketch
    if int(sketch_i) == -1:
        return None
    return _entity(sk.entities, sketch_i, "sketch")


def add_distance(
    context=None,
    entity1_i: Optional[int] = None,
    entity2_i: Optional[int] = None,
    value: Optional[float] = None,
    sketch_i: Optional[int] = None,
    **_params,
) -> Dict[str, Any]:
    sk = _sketcher(context)
    e1 = _entity(sk.entities, entity1_i, "entity1")
    e2 = _entity(sk.entities, entity2_i, "entity2") if entity2_i is not None else None
    sketch = _resolve_sketch_arg(sk, sketch_i)
    c = sk.constraints.add_distance(e1, e2, sketch=sketch)
    if value is not None:
        c.value = float(value)
    return _constraint_summary(c)


def add_coincident(
    context=None,
    entity1_i: Optional[int] = None,
    entity2_i: Optional[int] = None,
    sketch_i: Optional[int] = None,
    **_params,
) -> Dict[str, Any]:
    sk = _sketcher(context)
    e1 = _entity(sk.entities, entity1_i, "entity1")
    e2 = _entity(sk.entities, entity2_i, "entity2")
    sketch = _resolve_sketch_arg(sk, sketch_i)
    c = sk.constraints.add_coincident(e1, e2, sketch=sketch)
    return _constraint_summary(c)


def add_horizontal(
    context=None,
    entity1_i: Optional[int] = None,
    entity2_i: Optional[int] = None,
    sketch_i: Optional[int] = None,
    **_params,
) -> Dict[str, Any]:
    sk = _sketcher(context)
    e1 = _entity(sk.entities, entity1_i, "entity1")
    e2 = _entity(sk.entities, entity2_i, "entity2") if entity2_i is not None else None
    sketch = _resolve_sketch_arg(sk, sketch_i)
    c = sk.constraints.add_horizontal(e1, e2, sketch=sketch)
    return _constraint_summary(c)


def add_vertical(
    context=None,
    entity1_i: Optional[int] = None,
    entity2_i: Optional[int] = None,
    sketch_i: Optional[int] = None,
    **_params,
) -> Dict[str, Any]:
    sk = _sketcher(context)
    e1 = _entity(sk.entities, entity1_i, "entity1")
    e2 = _entity(sk.entities, entity2_i, "entity2") if entity2_i is not None else None
    sketch = _resolve_sketch_arg(sk, sketch_i)
    c = sk.constraints.add_vertical(e1, e2, sketch=sketch)
    return _constraint_summary(c)


def add_equal(
    context=None,
    entity1_i: Optional[int] = None,
    entity2_i: Optional[int] = None,
    sketch_i: Optional[int] = None,
    **_params,
) -> Dict[str, Any]:
    sk = _sketcher(context)
    e1 = _entity(sk.entities, entity1_i, "entity1")
    e2 = _entity(sk.entities, entity2_i, "entity2")
    sketch = _resolve_sketch_arg(sk, sketch_i)
    c = sk.constraints.add_equal(e1, e2, sketch=sketch)
    return _constraint_summary(c)


def add_parallel(
    context=None,
    entity1_i: Optional[int] = None,
    entity2_i: Optional[int] = None,
    sketch_i: Optional[int] = None,
    **_params,
) -> Dict[str, Any]:
    sk = _sketcher(context)
    e1 = _entity(sk.entities, entity1_i, "entity1")
    e2 = _entity(sk.entities, entity2_i, "entity2")
    sketch = _resolve_sketch_arg(sk, sketch_i)
    c = sk.constraints.add_parallel(e1, e2, sketch=sketch)
    return _constraint_summary(c)


def add_perpendicular(
    context=None,
    entity1_i: Optional[int] = None,
    entity2_i: Optional[int] = None,
    sketch_i: Optional[int] = None,
    **_params,
) -> Dict[str, Any]:
    sk = _sketcher(context)
    e1 = _entity(sk.entities, entity1_i, "entity1")
    e2 = _entity(sk.entities, entity2_i, "entity2")
    sketch = _resolve_sketch_arg(sk, sketch_i)
    c = sk.constraints.add_perpendicular(e1, e2, sketch=sketch)
    return _constraint_summary(c)


def add_tangent(
    context=None,
    entity1_i: Optional[int] = None,
    entity2_i: Optional[int] = None,
    sketch_i: Optional[int] = None,
    **_params,
) -> Dict[str, Any]:
    sk = _sketcher(context)
    e1 = _entity(sk.entities, entity1_i, "entity1")
    e2 = _entity(sk.entities, entity2_i, "entity2")
    sketch = _resolve_sketch_arg(sk, sketch_i)
    c = sk.constraints.add_tangent(e1, e2, sketch=sketch)
    return _constraint_summary(c)


def delete_entity(context=None, index: Optional[int] = None, **_params) -> Dict[str, Any]:
    sk = _sketcher(context)
    entity = _entity(sk.entities, index, "entity")
    if entity.origin:
        raise HandlerError("Cannot delete origin entities")
    removed = entity.slvs_index
    sk.entities.remove(removed)
    return {"removed_index": removed}


def delete_constraint(
    context=None, uid: Optional[str] = None, **_params
) -> Dict[str, Any]:
    if not uid:
        raise HandlerError("uid is required")
    sk = _sketcher(context)
    constr = sk.constraints.get_by_uid(uid)
    if constr is None:
        raise HandlerError(f"Constraint not found: {uid}")
    sk.constraints.remove(constr)
    return {"removed_uid": uid}


def solve(
    context=None, sketch_i: Optional[int] = None, all_sketches: bool = False, **_params
) -> Dict[str, Any]:
    from ..solver import solve_system

    context = context or bpy.context
    sk = _sketcher(context)
    if all_sketches:
        ok = solve_system(context)
        return {"ok": bool(ok), "mode": "all"}
    sketch = _sketch(sk.entities, sketch_i, required=True)
    ok = sketch.solve(context)
    return {
        "ok": bool(ok),
        "sketch_i": sketch.slvs_index,
        "solver_state": sketch.solver_state,
        "dof": int(sketch.dof),
    }


def execute_sketcher_code(context=None, code: str = "", **_params) -> Dict[str, Any]:
    if not code or not isinstance(code, str):
        raise HandlerError("code must be a non-empty string")
    context = context or bpy.context
    sk = _sketcher(context)
    namespace = {
        "bpy": bpy,
        "context": context,
        "sketcher": sk,
        "entities": sk.entities,
        "constraints": sk.constraints,
    }
    stdout = io.StringIO()
    try:
        with redirect_stdout(stdout):
            exec(code, namespace)  # noqa: S102 — intentional escape hatch
    except Exception as e:
        raise HandlerError(f"{type(e).__name__}: {e}\n{traceback.format_exc()}") from e
    return {"stdout": stdout.getvalue()}


HANDLERS = {
    "get_sketcher_status": get_sketcher_status,
    "ensure_origin": ensure_origin,
    "list_sketches": list_sketches,
    "get_sketch": get_sketch,
    "list_entities": list_entities,
    "list_constraints": list_constraints,
    "add_sketch": add_sketch,
    "set_active_sketch": set_active_sketch,
    "add_point_2d": add_point_2d,
    "add_line_2d": add_line_2d,
    "add_circle_2d": add_circle_2d,
    "add_arc_2d": add_arc_2d,
    "add_distance": add_distance,
    "add_coincident": add_coincident,
    "add_horizontal": add_horizontal,
    "add_vertical": add_vertical,
    "add_equal": add_equal,
    "add_parallel": add_parallel,
    "add_perpendicular": add_perpendicular,
    "add_tangent": add_tangent,
    "delete_entity": delete_entity,
    "delete_constraint": delete_constraint,
    "solve": solve,
    "execute_sketcher_code": execute_sketcher_code,
}


def dispatch(command: Dict[str, Any], context=None) -> Dict[str, Any]:
    """Execute one MCP command dict and return a status envelope."""
    cmd_type = command.get("type")
    params = command.get("params") or {}
    if not cmd_type:
        return {"status": "error", "message": "Missing command type"}
    handler = HANDLERS.get(cmd_type)
    if handler is None:
        return {"status": "error", "message": f"Unknown command type: {cmd_type}"}
    try:
        result = handler(context=context or bpy.context, **params)
        return {"status": "success", "result": result}
    except HandlerError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.exception("MCP handler failed: %s", cmd_type)
        return {
            "status": "error",
            "message": f"{type(e).__name__}: {e}",
        }
