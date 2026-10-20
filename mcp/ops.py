"""Interpret an agent's edit ops against a sketch.

One call carries a whole list of ops and is all-or-nothing: every op is checked
against the sketch and against each constraint's declared ``signature`` before
anything is written. That check is not politeness. solvespace aborts the process
when a constraint is handed the wrong kind of entity, and an abort takes the
user's unsaved work with it, so a wrong type must never reach the solver.

Ops name geometry, they do not index it: the agent picks the names, and a name
created earlier in the same list can be referenced later in it.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..model.curve_ref import ArcRef, CircleRef, LineRef, PointRef, curve_ref
from ..model.identifiers import kind_labels, matches_types
from ..model.sketch_ref import Sketch
from ..model.types import SlvsConstraints
from ..operators.delete_entity import delete_curve
from ..utilities.curve_data import batch_update, read_curve_id_list

# Constraint type -> the SlvsConstraints method that creates it. Going through the
# public adders keeps uid minting and value initialisation in one place.
ADDERS = {
    "COINCIDENT": "add_coincident",
    "EQUAL": "add_equal",
    "DISTANCE": "add_distance",
    "ANGLE": "add_angle",
    "DIAMETER": "add_diameter",
    "PARALLEL": "add_parallel",
    "HORIZONTAL": "add_horizontal",
    "VERTICAL": "add_vertical",
    "TANGENT": "add_tangent",
    "MIDPOINT": "add_midpoint",
    "PERPENDICULAR": "add_perpendicular",
    "RATIO": "add_ratio",
    "SYMMETRY": "add_symmetry",
}

# Constraints that carry a number. Given no value they measure the geometry, as
# the interactive tools do.
VALUED = ("DISTANCE", "ANGLE", "DIAMETER", "RATIO")

FLAGS = ("construction", "fixed", "visible")


class OpError(Exception):
    """An op that cannot be applied. Raised before anything is written."""


class Resolver:
    """Maps the names in an op list to the curves they refer to.

    Names given by ops in this batch win over the sketch's existing names, so a
    list can shadow an old name with geometry it creates itself.
    """

    def __init__(self, sketch: Sketch):
        self.sketch = sketch
        self.created: Dict[str, str] = {}
        # Points written inline as [x, y] are entities too, and the agent is told
        # how many it made, so they are counted where they are created.
        self.implicit_points = 0
        self._existing = self._read_existing()

    def _read_existing(self) -> Dict[str, str]:
        names: Dict[str, str] = {}
        curve_data = self.sketch.target_object.data
        for curve_id in read_curve_id_list(curve_data):
            if curve_id:
                names[curve_ref(self.sketch, curve_id).name] = curve_id
        return names

    def note(self, name: Optional[str], curve_id: str) -> None:
        """Remember a curve this batch created, under the name the agent gave it."""
        if name:
            self.created[name] = curve_id

    def find_curve_id(self, token: Any) -> Optional[str]:
        """The curve_id a reference token names, or None."""
        if not isinstance(token, str) or not token:
            return None
        if token in self.created:
            return self.created[token]
        if token in self._existing:
            return self._existing[token]
        # An id the agent read out of a previous dump.
        if token in read_curve_id_list(self.sketch.target_object.data):
            return token
        return None

    def curve_id(self, token: Any, what: str = "entity") -> str:
        """The curve_id a reference token names."""
        curve_id = self.find_curve_id(token)
        if curve_id is not None:
            return curve_id
        if not isinstance(token, str) or not token:
            raise OpError(f"{what} must be the name or id of an entity, got {token!r}")
        known = ", ".join(sorted({*self.created, *self._existing})) or "none"
        raise OpError(
            f"No entity named {token!r} in {self.sketch.name}. Known: {known}."
        )

    def ref(self, token: Any, what: str = "entity"):
        """A typed CurveRef for a reference token."""
        return curve_ref(self.sketch, self.curve_id(token, what))

    def point(self, token: Any, what: str) -> PointRef:
        """A point reference, created on the spot when given coordinates."""
        if isinstance(token, (list, tuple)):
            if len(token) != 2:
                raise OpError(f"{what} coordinates must be [x, y], got {token!r}")
            point = PointRef.create(self.sketch, (_num(token[0]), _num(token[1])))
            self.implicit_points += 1
            return point
        ref = self.ref(token, what)
        if not isinstance(ref, PointRef):
            raise OpError(f"{what} must be a point, but {token!r} is a {_kind(ref)}")
        return ref

    def find_constraint(self, token: Any):
        """A constraint by uid or by the name a dump showed, or None."""
        if not isinstance(token, str) or not token:
            return None
        from .describe import constraint_labels

        labels = constraint_labels(self.sketch.constraints)
        for constraint in self.sketch.constraints.all:
            uid = constraint.constraint_uid
            if token in (uid, labels.get(uid), constraint.name):
                return constraint
        return None

    def constraint(self, token: Any):
        """A constraint by uid or by the name a dump showed."""
        constraint = self.find_constraint(token)
        if constraint is not None:
            return constraint
        from .describe import constraint_labels

        labels = constraint_labels(self.sketch.constraints)
        known = ", ".join(labels.values()) or "none"
        raise OpError(f"No constraint {token!r} in {self.sketch.name}. Known: {known}.")


def _num(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpError(f"expected a number, got {value!r}")
    return float(value)


def _kind(ref) -> str:
    for check, label in (
        ("is_point", "point"),
        ("is_line", "line"),
        ("is_circle", "circle"),
        ("is_arc", "arc"),
    ):
        if getattr(ref, check)():
            return label
    return "unknown entity"


def _slot_types(cls, index: int, picked: Sequence):
    """The types a constraint accepts in one slot, given what came before it.

    A slot is not fixed: Horizontal on a line takes nothing further, while on a
    point it needs a second point, and Equal narrows its partner to what the
    first pick can actually be equal to. ``get_types`` returning None means the
    slot does not apply, which is how a constraint says it has all it needs. Same
    call the interactive picker builds its states from.
    """
    if not hasattr(cls, "get_types"):
        return cls.signature[index]
    entities = list(picked) + [None] * (len(cls.signature) - len(picked))
    return cls.get_types(index, entities)


def accepted_kinds(constraint_type: str) -> List[List[str]]:
    """Per argument, the entity kinds a constraint type accepts."""
    cls = SlvsConstraints.cls_from_type(constraint_type)
    if cls is None:
        return []
    return [kind_labels(types) for types in cls.signature]


def _check_refs(constraint_type: str, refs: Sequence) -> None:
    """Reject a constraint the solver would fail on, or abort the process over."""
    cls = SlvsConstraints.cls_from_type(constraint_type)

    for i, ref in enumerate(refs):
        if i >= len(cls.signature):
            raise OpError(
                f"{constraint_type} does not take a {i + 1}th entity, got {len(refs)}"
            )
        types = _slot_types(cls, i, refs[:i])
        if types is None:
            given = ", ".join(r.name for r in refs[i:])
            raise OpError(
                f"{constraint_type} on a {_kind(refs[0])} takes only {i} "
                f"entities; drop {given}"
            )
        if not matches_types(ref, types):
            wants = "/".join(kind_labels(types)) or "entity"
            raise OpError(
                f"{constraint_type} argument {i + 1} must be a {wants}, "
                f"but {ref.name!r} is a {_kind(ref)}"
            )

    # Slots left over that still accept something: the constraint is incomplete.
    if len(refs) < len(cls.signature):
        types = _slot_types(cls, len(refs), refs)
        if types is not None:
            wants = "/".join(kind_labels(types)) or "entity"
            raise OpError(
                f"{constraint_type} still needs a {wants} as argument {len(refs) + 1}"
            )

    # Type-correct pairs the solver still has no form for. Equal knows its own.
    compatible = getattr(cls, "_compatible", None)
    if compatible is not None and len(refs) == 2 and not compatible(*refs):
        raise OpError(
            f"{constraint_type} cannot relate a {_kind(refs[0])} to a {_kind(refs[1])}"
        )


def apply_ops(sketch: Sketch, ops: Sequence[Dict[str, Any]]) -> Tuple[int, int]:
    """Apply an op list to ``sketch``, returning (entities added, constraints added).

    Writes are batched so segments rebuild once at the end instead of per op.
    Raises :class:`OpError` for anything invalid, leaving the ops before it
    applied.
    """
    if not isinstance(ops, (list, tuple)) or not ops:
        raise OpError("ops must be a non-empty list of edit operations")

    resolver = Resolver(sketch)
    entities = 0
    constraints = 0

    # One rebuild at the end instead of one per op; the full rebuild also
    # refreshes the weld ids that a scoped one leaves alone.
    with batch_update(sketch):
        for i, op in enumerate(ops):
            if not isinstance(op, dict):
                raise OpError(f"op {i} must be an object, got {op!r}")
            kind = op.get("op")
            handler = _HANDLERS.get(kind)
            if handler is None:
                known = ", ".join(sorted(_HANDLERS))
                raise OpError(f"op {i}: unknown op {kind!r}. Available: {known}.")
            try:
                added_entity, added_constraint = handler(sketch, resolver, op)
            except OpError as e:
                raise OpError(f"op {i} ({kind}): {e}") from e
            entities += added_entity
            constraints += added_constraint

    return entities + resolver.implicit_points, constraints


# -- Op handlers -------------------------------------------------------------
# Each returns (entities added, constraints added).


def _op_point(sketch, resolver, op):
    co = op.get("co")
    if not isinstance(co, (list, tuple)) or len(co) != 2:
        raise OpError("needs co as [x, y]")
    point = PointRef.create(
        sketch,
        (_num(co[0]), _num(co[1])),
        construction=bool(op.get("construction", False)),
        fixed=bool(op.get("fixed", False)),
        name=op.get("name"),
    )
    resolver.note(op.get("name"), point.curve_id)
    return 1, 0


def _op_line(sketch, resolver, op):
    p1 = resolver.point(op.get("p1"), "p1")
    p2 = resolver.point(op.get("p2"), "p2")
    line = LineRef.create(
        sketch,
        p1,
        p2,
        construction=bool(op.get("construction", False)),
        name=op.get("name"),
    )
    resolver.note(op.get("name"), line.curve_id)
    return 1, 0


def _op_circle(sketch, resolver, op):
    center = resolver.point(op.get("center"), "center")
    radius = _num(op.get("radius"))
    if radius <= 0:
        raise OpError(f"radius must be positive, got {radius}")
    circle = CircleRef.create(
        sketch,
        center,
        radius,
        construction=bool(op.get("construction", False)),
        name=op.get("name"),
    )
    resolver.note(op.get("name"), circle.curve_id)
    return 1, 0


def _op_arc(sketch, resolver, op):
    center = resolver.point(op.get("center"), "center")
    start = resolver.point(op.get("start"), "start")
    end = resolver.point(op.get("end"), "end")
    arc = ArcRef.create(
        sketch,
        center,
        start,
        end,
        construction=bool(op.get("construction", False)),
        name=op.get("name"),
    )
    resolver.note(op.get("name"), arc.curve_id)
    return 1, 0


def _op_constrain(sketch, resolver, op):
    raw_type = op.get("type")
    if not isinstance(raw_type, str):
        raise OpError(f"needs type, one of {', '.join(sorted(ADDERS))}")
    constraint_type = raw_type.upper()
    adder = ADDERS.get(constraint_type)
    if adder is None:
        raise OpError(
            f"unknown constraint type {raw_type!r}. "
            f"Available: {', '.join(sorted(ADDERS))}."
        )

    raw_refs = op.get("refs")
    if not isinstance(raw_refs, (list, tuple)) or not raw_refs:
        raise OpError("needs refs, the entities to constrain")
    refs = [resolver.ref(token, f"refs[{i}]") for i, token in enumerate(raw_refs)]
    _check_refs(constraint_type, refs)

    ids = {f"curve_id_{i + 1}": ref.curve_id for i, ref in enumerate(refs)}
    value = op.get("value")

    if constraint_type in VALUED:
        # Always measure first, then override the number. A distance to a line
        # is signed, and the side is only worked out while measuring: given a
        # value up front the constraint keeps the default side instead, and the
        # solver mirrors the point through the line. The interactive tools never
        # meet this because picking measures before anything is typed.
        constraint = getattr(sketch.constraints, adder)(init=True, **ids)
        if value is not None:
            constraint.assign_settings(value=_num(value))
    else:
        if value is not None:
            raise OpError(f"{constraint_type} takes no value")
        constraint = getattr(sketch.constraints, adder)(**ids)

    if op.get("measure_only"):
        constraint.is_reference = True
    resolver.note(op.get("name"), constraint.constraint_uid)
    return 0, 1


def _op_delete(sketch, resolver, op):
    target = op.get("target")
    if not isinstance(target, str) or not target:
        raise OpError("needs target, the name of an entity or constraint")

    curve_id = resolver.find_curve_id(target)
    if curve_id is not None:
        ref = curve_ref(sketch, curve_id)
        if ref.is_origin:
            raise OpError("the sketch origin cannot be deleted")
        # Whatever was built on it goes too, along with the constraints that
        # referenced any of it.
        delete_curve(sketch, curve_id)
        return 0, 0

    constraint = resolver.find_constraint(target)
    if constraint is not None:
        sketch.constraints.remove(constraint)
        return 0, 0

    raise OpError(f"nothing named {target!r} in {sketch.name}")


def _op_set_value(sketch, resolver, op):
    constraint = resolver.constraint(op.get("target"))
    if "value" not in getattr(constraint, "props", ()):
        raise OpError(f"{constraint.type} has no value to set")
    constraint.assign_settings(value=_num(op.get("value")))
    return 0, 0


def _op_rename(sketch, resolver, op):
    name = op.get("name")
    if not isinstance(name, str) or not name:
        raise OpError("needs name")
    ref = resolver.ref(op.get("target"), "target")
    ref.name = name
    resolver.note(name, ref.curve_id)
    return 0, 0


def _op_set_flag(sketch, resolver, op):
    flag = op.get("flag")
    if flag not in FLAGS:
        raise OpError(f"flag must be one of {', '.join(FLAGS)}")
    ref = resolver.ref(op.get("target"), "target")
    setattr(ref, flag, bool(op.get("value", True)))
    return 0, 0


_HANDLERS = {
    "point": _op_point,
    "line": _op_line,
    "circle": _op_circle,
    "arc": _op_arc,
    "constrain": _op_constrain,
    "delete": _op_delete,
    "set_value": _op_set_value,
    "rename": _op_rename,
    "set_flag": _op_set_flag,
}
