import logging

from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    StringProperty,
)
from bpy.types import Context, Event, Operator
from mathutils import Vector
from mathutils.geometry import intersect_line_plane

from ..curve_solver import solve_system
from ..declarations import Operators
from ..drawing import selection
from ..model.angle import SlvsAngle
from ..model.arc import SlvsArc
from ..model.circle import SlvsCircle
from ..model.curve_ref import ArcRef, CircleRef, LineRef, PointRef, curve_ref
from ..model.distance import align_items
from ..model.line_2d import SlvsLine2D
from ..model.point_2d import SlvsPoint2D
from ..model.sketch_ref import get_active_constraints
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.description import state_desc, stateful_op_desc
from ..stateful_operator.utilities.keymap import (
    get_key_map_desc,
    is_numeric_input,
    is_unit_input,
)
from ..stateful_operator.utilities.numeric import NumericInput, parse_numeric
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.curve_data import refresh_curve_geometry
from ..utilities.view import get_picking_origin_end, refresh
from .base_constraint import GenericConstraintOp

logger = logging.getLogger(__name__)

_PLACEMENT_STATE = "Placement"

# What the tool dimensions. AUTO infers it from the picks; the others restrict the
# picks to that kind, as the separate Distance/Angle/Diameter tools did.
KINDS = (
    ("AUTO", "Auto", "Infer the dimension from the picked geometry"),
    ("DISTANCE", "Distance", "Add a distance constraint"),
    ("ANGLE", "Angle", "Add an angle constraint"),
    ("DIAMETER", "Diameter", "Add a diameter or radius constraint"),
)
_KIND_DESCRIPTIONS = {k: desc for k, _name, desc in KINDS}

_POINT_LINE = (SlvsPoint2D, SlvsLine2D)
_CURVES = (SlvsCircle, SlvsArc)
_ANY = (*_POINT_LINE, *_CURVES)

# Presets a keymap item or button can start the tool with, and their defaults.
_FLAG_DEFAULTS = {
    "kind": "AUTO",
    "align": "NONE",
    "radius": False,
    "supplementary": False,
}


def _same_flags(kmi, properties) -> bool:
    """Whether a keymap item starts the tool with the presets of ``properties``."""
    for name, default in _FLAG_DEFAULTS.items():
        want = getattr(properties, name, default) if properties else default
        if getattr(kmi.properties, name, default) != want:
            return False
    return True


# Label placement attributes kept for a redo, per constraint type.
_LABEL_ATTRS = ("draw_offset", "draw_outset", "leader_angle")


class VIEW3D_OT_slvs_add_dimension(Operator, GenericConstraintOp):
    """Add a dimension, inferring the constraint type from the geometry.

    The user does not choose between distance, angle and diameter up front:

    - a line              -> distance (its length); click a second entity while
                             placing to switch: a line -> angle (or the
                             perpendicular distance if the two are parallel), a
                             point -> point-to-line distance, a circle/arc ->
                             edge-to-line distance
    - a circle or arc     -> diameter; click a point or line while placing to
                             switch to an edge-to-point / edge-to-line distance
    - two points          -> distance
    - point + line        -> point-to-line distance
    - point/line + circle/arc -> edge distance (measured from the curve's edge)
    - circle/arc + circle/arc -> edge-to-edge distance (along the line of centres)

    A line/circle/arc drops straight into an interactive placement state after
    the first pick, where the label is dragged into place (display only, no
    re-solve) and confirmed with a click. A point needs a partner, so it takes a
    required second pick before placement.

    ``kind`` restricts the tool to one dimension type (distance, angle or
    diameter), and ``align``/``radius``/``supplementary`` preset how it measures,
    so every former dimension tool is this operator with flags.
    """

    bl_idname = Operators.AddDimension
    bl_label = "Dimension"
    bl_options = {"UNDO", "REGISTER"}

    # GenericConstraintOp keys off a single constraint ``type``; this operator
    # spans several, so it drives ``states``/creation itself and never resolves a
    # type from the base machinery.
    type = None
    property_keys = ()
    has_value_state = False
    # A re-pick can change which kind of dimension this is; not supported yet.
    editable = False

    # Live label offset. Filled by the placement state's ``state_func`` as a
    # display-only side effect; the property itself is only a confirm carrier.
    placement: FloatProperty(options={"SKIP_SAVE", "HIDDEN"})

    kind: EnumProperty(name="Type", items=KINDS, options={"SKIP_SAVE"})
    align: EnumProperty(name="Alignment", items=align_items, options={"SKIP_SAVE"})
    flip: BoolProperty(name="Flip", options={"SKIP_SAVE"})
    radius: BoolProperty(name="Use Radius", options={"SKIP_SAVE"})
    supplementary: BoolProperty(
        name="Measure Supplementary Angle", options={"SKIP_SAVE"}
    )
    # The value, in the unit of the dimension type (shown in the redo panel).
    length: FloatProperty(
        name="Distance",
        subtype="DISTANCE",
        unit="LENGTH",
        precision=5,
        options={"SKIP_SAVE"},
    )
    angle: FloatProperty(
        name="Angle",
        subtype="ANGLE",
        unit="ROTATION",
        precision=5,
        options={"SKIP_SAVE"},
    )

    # Redo state: what the interactive run made, so a redo rebuilds it exactly.
    partner: StringProperty(options={"SKIP_SAVE", "HIDDEN"})
    result: StringProperty(options={"SKIP_SAVE", "HIDDEN"})
    can_align: BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    can_flip: BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    # Settings the stored value was measured with, to convert it when they change.
    last_align: EnumProperty(items=align_items, options={"SKIP_SAVE", "HIDDEN"})
    last_radius: BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    last_supplementary: BoolProperty(options={"SKIP_SAVE", "HIDDEN"})
    label: FloatVectorProperty(size=3, options={"SKIP_SAVE", "HIDDEN"})
    has_label: BoolProperty(options={"SKIP_SAVE", "HIDDEN"})

    _redoing = False
    _preset_value = None

    @classmethod
    def description(cls, context, properties):
        kind = getattr(properties, "kind", "AUTO") if properties else "AUTO"
        descs = []
        hint = get_key_map_desc(
            context, cls.bl_idname, filter_func=lambda kmi: _same_flags(kmi, properties)
        )
        if hint:
            descs.append(hint)
        if kind == "AUTO":
            descs.append(cls.__doc__.split("\n")[0])
        else:
            descs.append(_KIND_DESCRIPTIONS[kind])
        states = [
            state_desc(s.name, s.description, s.types)
            for s in cls.get_states_definition()
        ]
        return stateful_op_desc(" ".join(descs), *states)

    def is_same_invocation(self, kmi) -> bool:
        # Alt+H while dimensioning with other presets switches to that dimension.
        return _same_flags(kmi, self)

    def _prop(self, name: str, default):
        """An operator property, or ``default`` where it isn't registered (the
        test double runs this code without bpy properties)."""
        return getattr(self, name, default)

    def _kind(self) -> str:
        """The dimension type to make; the presets imply one when ``kind`` is AUTO."""
        kind = self._prop("kind", "AUTO")
        if kind != "AUTO":
            return kind
        if self._prop("align", "NONE") != "NONE":
            return "DISTANCE"
        if self._prop("radius", False):
            return "DIAMETER"
        return "AUTO"

    def _is_3d(self) -> bool:
        sketch = getattr(self, "sketch", None)
        return bool(sketch and getattr(sketch, "is_3d", False))

    @classmethod
    def states(cls, operator=None):
        """Pick the first entity (+ a required partner where the kind needs one),
        then a terminal interactive placement state."""
        kind = operator._kind() if operator else "AUTO"
        first_types = {
            "ANGLE": (SlvsLine2D,),
            "DIAMETER": _CURVES,
        }.get(kind, _ANY)
        if (
            kind == "DISTANCE"
            and operator
            and operator._prop("align", "NONE") != "NONE"
        ):
            # An aligned distance measures between two points (or a line's ends).
            first_types = _POINT_LINE

        states = [
            state_from_args(
                "Entity 1",
                description="Pick geometry to dimension.",
                pointer="entity1",
                types=first_types,
                use_create=False,
            )
        ]

        # Add a partner-pick state when the first entity needs one or when it
        # isn't known yet -- the latter lets a pre-selected pair (e.g. two points)
        # prefill a second entity. Otherwise a known entity goes straight to
        # placement; a line gains its optional partner by a click there instead.
        e1 = getattr(operator, "entity1", None) if operator else None
        partner = cls._partner_state(kind, e1)
        if partner is not None:
            states.append(partner)

        # Placement: no property/pointer, so it neither re-solves nor snapshots
        # per move -- its ``state_func`` just drags the label offset, and a click
        # confirms via the optional-state skip in the state machine.
        states.append(
            state_from_args(
                _PLACEMENT_STATE,
                description="Move to place the dimension label, click to confirm.",
                property=None,
                state_func="_place_dimension",
                interactive=True,
                optional=True,
                allow_prefill=False,
            )
        )
        return states

    @staticmethod
    def _partner_state(kind, e1):
        """The second pick state for ``kind`` after ``e1``, or None."""
        if kind == "DIAMETER":
            return None
        if kind == "ANGLE":
            types, optional = (SlvsLine2D,), False
        elif e1 is None:
            types, optional = _ANY, True
        elif isinstance(e1, PointRef):
            types, optional = _ANY, False
        elif kind == "DISTANCE" and isinstance(e1, (CircleRef, ArcRef)):
            # A lone curve is a diameter, so a distance needs something to measure to.
            types, optional = _ANY, False
        else:
            return None
        return state_from_args(
            "Entity 2",
            description="Pick the entity to measure to.",
            pointer="entity2",
            types=types,
            use_create=False,
            optional=optional,
        )

    def init(self, context: Context, event: Event):
        if not super().init(context, event):
            return False
        # Snapshot the pre-selection: a first-pick type that goes straight to
        # placement (line/circle/arc) has no E2 slot, so a pre-selected partner
        # is adopted from here in _create_constraint rather than via a state.
        self._prefill_selection = list(selection.selected)
        # A value passed in (e.g. by a script) is used instead of the measured one.
        for name in ("length", "angle"):
            if self.properties.is_property_set(name):
                self._preset_value = getattr(self, name)
        return True

    def _second_entity(self):
        """The partner entity, from the state machine (point flow) or from a
        click made during placement (line flow)."""
        return getattr(self, "entity2", None) or getattr(self, "_second_ref", None)

    def _prefill_second(self):
        """Adopt a pre-selected partner for a line/circle/arc first pick.

        Prefill fills only ``entity1`` for these types (their dynamic states drop
        the E2 slot once the type is known), so a pre-selected pair would only
        dimension the first entity. Pull a compatible second from the snapshot.
        """
        if self._second_entity() is not None or self._redoing:
            return
        e1 = getattr(self, "entity1", None)
        if not isinstance(e1, (LineRef, CircleRef, ArcRef)):
            return

        excluded = {e1.curve_id}
        if isinstance(e1, LineRef):
            for p in (e1.p1, e1.p2):
                if p:
                    excluded.add(p.curve_id)
        else:
            ct = getattr(e1, "ct", None)
            if ct is not None:
                excluded.add(ct.curve_id)

        # Prefer the init snapshot; fall back to the live selection (the test
        # harness drives the op without invoke/init). _create_constraint runs
        # before the deselect in super().main(), so the selection is still intact.
        candidates = getattr(self, "_prefill_selection", None)
        if candidates is None:
            candidates = list(selection.selected)

        for cid in candidates:
            if cid in excluded:
                continue
            ref = curve_ref(self.sketch, cid)
            if self._accepts_partner(ref):
                self._set_partner(ref)
                return

    def _available_entities(self):
        return [getattr(self, "entity1", None), self._second_entity()]

    def _is_placement_state(self) -> bool:
        return self.state.name == _PLACEMENT_STATE

    def _apply_undo(self, context: Context):
        """Keep label placement out of the state machine's per-move undo cycle.

        Once the geometry is picked the constraint is stable and only its display
        offset changes. The framework otherwise restores its snapshot on every
        move here -- which deletes the constraint (main() is guarded, so nothing
        recreates it) and resets the offset, leaving the gizmo nothing to track.
        Suppressing it makes placement behave like the standalone tweak modal: a
        single live constraint whose gizmo follows the cursor. Outside placement
        the normal undo/redo still runs so each pick can re-infer the type.
        """
        if self._is_placement_state():
            self._undo = False
            return
        super()._apply_undo(context)

    @staticmethod
    def _lines_parallel(l1: LineRef, l2: LineRef, tol_deg: float = 0.5) -> bool:
        """True if two lines are (anti-)parallel, i.e. their angle is ~0/180."""
        angle = SlvsAngle._get_angle(l1.direction_vec(), l2.direction_vec())
        return angle < tol_deg or angle > 180.0 - tol_deg

    @staticmethod
    def _distance_pair(e1, e2):
        """Order two entities as the native distance solver needs, or return None
        if the pair isn't a supported distance.

        The solver measures a curve (circle/arc) from its edge and requires it as
        entity1; a point/line pair measures point-to-line, so the point goes
        first. Two curves are measured edge-to-edge along the line of centres.
        """
        c1 = isinstance(e1, (CircleRef, ArcRef))
        c2 = isinstance(e2, (CircleRef, ArcRef))
        if c1 and c2:
            return e1, e2
        if c2:
            return e2, e1
        if c1:
            return e1, e2
        if isinstance(e1, LineRef) and isinstance(e2, PointRef):
            return e2, e1
        return e1, e2

    def _is_duplicate(self, context: Context, target) -> bool:
        """True if another constraint already matches ``target``'s type + curve ids.

        Checked at commit rather than while creating, because the inferred type
        can still change during placement (e.g. picking an already-length-
        constrained line, then a second line, to add an *angle*): a premature
        check would block the tentative length and its preview. Counting > 1
        means one besides ``target`` itself exists.
        """
        want = set(target.curve_id_placements())
        align = getattr(target, "align", None)
        count = 0
        for c in get_active_constraints(context).all:
            if type(c) is not type(target):
                continue
            # A horizontal and a vertical distance between the same points differ.
            if (
                set(c.curve_id_placements()) == want
                and getattr(c, "align", None) == align
            ):
                count += 1
                if count > 1:
                    return True
        return False

    def _clear_target(self, context: Context):
        """Drop a previously created constraint before re-inferring the type.

        Adopting a second entity turns a tentative length into an angle/distance;
        the placement path suppresses the snapshot, so remove the stale one
        explicitly rather than relying on an undo to do it.
        """
        target = getattr(self, "target", None)
        if target is None:
            return
        try:
            self.sketch.constraints.remove(target)
        except (ValueError, RuntimeError):
            pass
        self.target = None

    def _create_constraint(self, context: Context):
        """Infer and create the dimensional constraint from the current picks."""
        self._prefill_second()
        e1 = self.entity1
        e2 = self._second_entity()
        kind = self._kind()
        constraints = self.sketch.constraints

        # No dedup here -- see _is_duplicate (checked at fini). The tentative
        # constraint is always created so it previews and can still change type.
        if e2 is None:
            if isinstance(e1, (CircleRef, ArcRef)):
                if kind == "DISTANCE":
                    return
                self.target = self._add(
                    constraints.add_diameter, "DIAMETER", curve_id_1=e1.curve_id
                )
                logger.debug("Dimension -> diameter on %s", e1.curve_id)
            elif isinstance(e1, LineRef):
                if kind == "ANGLE":
                    return
                # The native solver needs two point ids, so measure the line as
                # the distance between its own endpoints.
                p1, p2 = e1.p1, e1.p2
                if p1 and p2:
                    self.target = self._add(
                        constraints.add_distance,
                        "DISTANCE",
                        curve_id_1=p1.curve_id,
                        curve_id_2=p2.curve_id,
                    )
                    logger.debug("Dimension -> line length on %s", e1.curve_id)
            else:
                logger.debug("Dimension: point %s needs a second entity", e1.curve_id)
                return
        elif isinstance(e1, LineRef) and isinstance(e2, LineRef):
            if kind != "ANGLE" and self._lines_parallel(e1, e2):
                # Parallel lines have no angle vertex (their intersection is at
                # infinity), so measure the perpendicular gap instead: a
                # point-to-line distance from one line's endpoint to the other.
                p = e1.p1
                if p:
                    self.target = self._add(
                        constraints.add_distance,
                        "DISTANCE",
                        curve_id_1=p.curve_id,
                        curve_id_2=e2.curve_id,
                    )
                    logger.debug(
                        "Dimension -> distance (parallel lines) %s -> %s",
                        p.curve_id,
                        e2.curve_id,
                    )
            else:
                self.target = self._add(
                    constraints.add_angle,
                    "ANGLE",
                    curve_id_1=e1.curve_id,
                    curve_id_2=e2.curve_id,
                )
                logger.debug(
                    "Dimension -> angle between %s and %s", e1.curve_id, e2.curve_id
                )
        else:
            # A mixed pair -> a distance. Order it as the solver needs (curve or
            # point first); an unsupported pair (curve-to-curve) makes nothing.
            pair = self._distance_pair(e1, e2)
            if pair is None:
                logger.debug(
                    "Dimension: unsupported pair %s + %s", e1.curve_id, e2.curve_id
                )
                return
            a, b = pair
            self.target = self._add(
                constraints.add_distance,
                "DISTANCE",
                curve_id_1=a.curve_id,
                curve_id_2=b.curve_id,
            )
            logger.debug("Dimension -> distance %s -> %s", a.curve_id, b.curve_id)

        # Give the freshly created label a sensible default offset so it is
        # visible before the first placement move (overwritten while dragging).
        target = getattr(self, "target", None)
        if target is None:
            return
        if self._redoing and self._prop("has_label", False):
            for name, value in zip(_LABEL_ATTRS, self.label):
                if hasattr(target, name):
                    setattr(target, name, value)
        elif context.region_data:
            target.draw_offset = 0.05 * context.region_data.view_distance

    def _add(self, add, type_name: str, **ids):
        """Create a dimension of ``type_name`` with the operator's settings.

        The interactive run measures the geometry; a redo re-applies the values
        from the redo panel. Settings that convert the value (alignment, radius,
        supplementary angle) are applied in the order that keeps it meaningful.
        """
        if not self._redoing:
            settings = {}
            if type_name == "DISTANCE" and self._prop("align", "NONE") != "NONE":
                settings["align"] = self.align
            elif type_name == "DIAMETER" and self._prop("radius", False):
                settings["setting"] = True
            target = add(init=True, **ids, **settings)
            # The angle measures as is; the setting only changes what is shown.
            if type_name == "ANGLE" and self._prop("supplementary", False):
                target.setting = True
            if self._preset_value is not None:
                target.value = self._preset_value
            return target

        target = add(init=False, **ids)
        if type_name == "DISTANCE":
            # Changing the alignment re-measures, like on the constraint itself.
            target.align = self.align
            if self.align == self.last_align:
                target.value = self.length
            target.flip = self.flip
        elif type_name == "DIAMETER":
            # The value was measured with the previous setting; toggling converts it.
            target.setting = self.last_radius
            target.value = self.length
            target.setting = self.radius
        elif type_name == "ANGLE":
            target.setting = self.last_supplementary
            target.value = self.angle
            target.setting = self.supplementary
        return target

    def _sync_settings(self):
        """Mirror the created dimension into the operator, for the redo panel."""
        target = getattr(self, "target", None)
        if target is None or not hasattr(self, "result"):
            return
        self.result = target.type
        second = getattr(self, "_second_ref", None)
        self.partner = second.curve_id if second else ""
        if target.type == "DISTANCE":
            self.length = target.value
            self.align = target.align
            self.last_align = target.align
            self.flip = target.flip
            self.can_align = target.use_align()
            self.can_flip = target.use_flipping()
        elif target.type == "DIAMETER":
            self.length = target.value
            self.radius = self.last_radius = target.setting
        elif target.type == "ANGLE":
            self.angle = target.value
            self.supplementary = self.last_supplementary = target.setting
        self.label = [getattr(target, name, 0.0) for name in _LABEL_ATTRS]
        self.has_label = True

    def execute(self, context: Context):
        # A redo runs on the state restored from the properties. The constraint
        # the previous run made was undone, so never touch that reference.
        self._redoing = True
        self.target = None
        self._active_sketch = None
        partner = self._prop("partner", "")
        self._second_ref = None
        if partner:
            ref = curve_ref(self.sketch, partner)
            self._second_ref = ref if ref.valid else None
        return super().execute(context)

    def draw(self, context: Context):
        layout = self.layout
        layout.use_property_split = True
        result = self.result
        if result == "DISTANCE":
            layout.prop(self, "length")
            row = layout.row()
            row.enabled = self.can_align
            row.prop(self, "align")
            if self.can_flip:
                layout.prop(self, "flip")
        elif result == "DIAMETER":
            layout.prop(self, "length", text="Radius" if self.radius else "Diameter")
            layout.prop(self, "radius")
        elif result == "ANGLE":
            layout.prop(self, "angle")
            layout.prop(self, "supplementary")

    def _place_dimension(self, context: Context, coords):
        """Drag the dimension label onto the cursor, display only.

        Projects the cursor onto the constraint's draw plane and offsets the
        label there. Returns ``None`` so the placement state stores no value and
        never triggers a re-solve; confirmation happens via the state click.
        """
        target = getattr(self, "target", None)
        if not target or not hasattr(target, "update_draw_offset"):
            return None

        origin, end_point = get_picking_origin_end(context, coords)
        pos = intersect_line_plane(origin, end_point, *target.draw_plane())
        if pos is not None:
            pos = target.matrix_basis().inverted() @ pos
            target.update_draw_offset(pos, context.preferences.system.ui_scale)
            # Full refresh (show_gizmo + redraw) so the gizmo re-reads the offset.
            refresh(context)
        return None

    def _pick_second(self, context: Context, event: Event):
        """A compatible entity under the cursor to dimension the first pick against.

        Meaningful for a line, circle or arc first pick. A line can pair with a
        line (angle / perpendicular distance), a point or a curve (distance). A
        circle/arc can pair with a point or a line (edge distance) -- not another
        curve. The first entity's own sub-parts and the adopted partner are
        excluded.
        """
        e1 = self.entity1
        if not isinstance(e1, (LineRef, CircleRef, ArcRef)):
            return None

        from ..drawing import picking

        coords = Vector((event.mouse_region_x, event.mouse_region_y))
        cid = picking.update_hover(context, coords)
        if not cid:
            return None

        excluded = {e1.curve_id}
        if isinstance(e1, LineRef):
            for p in (e1.p1, e1.p2):
                if p:
                    excluded.add(p.curve_id)
        else:  # circle/arc -- don't dimension it against its own center
            ct = getattr(e1, "ct", None)
            if ct is not None:
                excluded.add(ct.curve_id)
        current = getattr(self, "_second_ref", None)
        if current is not None:
            excluded.add(current.curve_id)
        if cid in excluded:
            return None

        ref = curve_ref(self.sketch, cid)
        return ref if self._accepts_partner(ref) else None

    def _accepts_partner(self, ref) -> bool:
        """Whether ``ref`` may be adopted as the partner of a line/circle/arc.

        A line pairs with a line (angle/parallel) or anything for a distance; a
        curve pairs with a point/line (edge distance) or another curve (center to
        center). The kind and presets narrow that down.
        """
        if not isinstance(ref, (LineRef, PointRef, CircleRef, ArcRef)):
            return False
        kind = self._kind()
        # These kinds pick their partner in a state, or never take one; an aligned
        # distance only exists between two points (a line's own ends).
        if kind in ("ANGLE", "DIAMETER") or self._prop("align", "NONE") != "NONE":
            return False
        if isinstance(ref, LineRef) and isinstance(self.entity1, LineRef):
            if self._is_3d():
                return False  # no angles in free-3D sketches
            if kind == "DISTANCE":
                return self._lines_parallel(self.entity1, ref)
        return True

    def _set_partner(self, ref):
        self._second_ref = ref
        if hasattr(self, "partner"):
            self.partner = ref.curve_id if ref else ""

    def _switch_second(self, context: Context, ref):
        """Adopt a second entity mid-placement and rebuild as the new type."""
        self._set_partner(ref)
        self._clear_target(context)
        self._create_constraint(context)
        if self.sketch:
            solve_system(context, sketch=self.sketch)
            refresh_curve_geometry(self.sketch)
        refresh(context)
        logger.debug("Dimension: adopted second entity %s", ref.curve_id)

    def _value_input(self) -> NumericInput:
        """Lazily-created numeric buffer for typing the dimension value during
        placement (kept separate from the state machine's own ``_numeric``, which
        stays idle because the placement state has no property)."""
        numeric = getattr(self, "_value_numeric", None)
        if numeric is None:
            numeric = self._value_numeric = NumericInput()
            numeric.is_active = True
        return numeric

    def _apply_value(self, context: Context):
        """Set the dimension value from the typed buffer, then re-solve.

        Routes through the constraint's own ``value`` property so the differing
        subtypes/units (distance, angle, diameter) are parsed correctly -- the
        same reason the standalone tweak modal reads the constraint directly.
        """
        target = getattr(self, "target", None)
        if target is None:
            return
        prop = target.rna_type.properties.get("value")
        if prop is None:
            return
        value = parse_numeric(
            prop, self._value_numeric.current, context.scene.unit_settings.system
        )
        if value is None:
            # Empty or mid-typing/invalid -- keep the current value.
            return
        target.value = value
        if self.sketch and solve_system(context, sketch=self.sketch):
            refresh_curve_geometry(self.sketch)
        refresh(context)
        context.workspace.status_text_set(
            "Value: {}".format(self._value_numeric.current)
        )

    def modal(self, context: Context, event: Event):
        if self._is_placement_state():
            # Numeric value entry: type a number (with units) to set the
            # dimension value, independent of the label drag -- mirrors the tweak
            # modal and the dimensional constraint operators.
            if event.value == "PRESS" and (
                is_numeric_input(event)
                or is_unit_input(event, self._value_input().current)
            ):
                self._value_input().evaluate_event(event)
                self._apply_value(context)
                return {"RUNNING_MODAL"}
            # A click on a second compatible entity switches the inferred
            # dimension (line length -> angle / point-to-line distance) and keeps
            # dragging, instead of confirming.
            if event.type == "LEFTMOUSE" and event.value == "PRESS":
                ref = self._pick_second(context, event)
                if ref is not None:
                    self._switch_second(context, ref)
                    return {"RUNNING_MODAL"}
        return super().modal(context, event)

    def main(self, context: Context):
        e1 = getattr(self, "entity1", None)
        if e1 is None:
            return False

        # While placing the label the geometry is fixed and only ``draw_offset``
        # changes, so skip the recreate/solve and keep the existing constraint.
        if self.initialized and self._is_placement_state() and not self._redoing:
            return bool(getattr(self, "target", None))

        # An entity pick changed the inference -- rebuild the constraint.
        self._clear_target(context)
        self._create_constraint(context)
        return super().main(context)

    def _should_reject(self, context: Context, target):
        """Return ``(report_level, message)`` if the committed dimension must be
        dropped, else ``None``.

        On rejection the target is already removed and the sketch re-solved; on
        keep, the target stays and the sketch is solved. Rejects an exact
        duplicate, and a dimension that leaves the sketch unsolvable -- but the
        latter only when removing it restores solvability, so an inconsistency
        that pre-dates this dimension doesn't discard the user's work.
        """
        if self._is_duplicate(context, target):
            self._clear_target(context)
            if self.sketch and solve_system(context, sketch=self.sketch):
                refresh_curve_geometry(self.sketch)
            return "INFO", "Dimension already exists"

        if self.sketch is None:
            return None

        if solve_system(context, sketch=self.sketch):
            refresh_curve_geometry(self.sketch)
            return None

        # Unsolvable with the new dimension -- reject only if removing it helps.
        self._clear_target(context)
        if solve_system(context, sketch=self.sketch):
            refresh_curve_geometry(self.sketch)
            return "WARNING", "Dimension conflicts with the existing constraints"

        # Pre-existing inconsistency: restore the user's dimension and keep it.
        self._create_constraint(context)
        if solve_system(context, sketch=self.sketch):
            refresh_curve_geometry(self.sketch)
        return None

    def fini(self, context: Context, succeede: bool):
        # Placement happens in this operator's own placement state, so there is no
        # hand-off to the standalone tweak modal (unlike GenericConstraintOp).
        #
        # Both the duplicate and solvability checks happen here, at commit: the
        # tentative constraint may change type and value during placement, so only
        # its final form matters.
        if succeede and getattr(self, "target", None) is not None:
            reason = self._should_reject(context, self.target)
            if reason is not None:
                logger.debug("Dimension: rejected -- %s", reason[1])
                if hasattr(self, "report"):
                    self.report({reason[0]}, reason[1])

        if succeede:
            self._sync_settings()

        # Make sure gizmos end up visible and the label reflects the final offset.
        refresh(context)
        target = getattr(self, "target", None)
        if target is not None:
            logger.debug("Dimension committed: %s (succeeded=%s)", target, succeede)


class DimensionAlias:
    """Base of the former Distance/Angle/Diameter tools, kept under their names
    for keymaps and scripts: they run the Dimension tool with matching flags."""

    bl_options = set()

    wait_for_input: BoolProperty(options={"HIDDEN", "SKIP_SAVE"}, default=True)

    def dimension_flags(self) -> dict:
        """Dimension tool properties this tool stands for."""
        raise NotImplementedError

    def _run(self, mode: str) -> set:
        import bpy

        flags = self.dimension_flags()
        result = bpy.ops.view3d.slvs_add_dimension(
            mode, wait_for_input=self.wait_for_input, **flags
        )
        # The Dimension tool keeps running on its own and makes the undo step.
        if "RUNNING_MODAL" in result:
            return {"FINISHED"}
        return result

    def invoke(self, context: Context, event: Event):
        return self._run("INVOKE_DEFAULT")

    def execute(self, context: Context):
        return self._run("EXEC_DEFAULT")


register, unregister = register_stateops_factory((VIEW3D_OT_slvs_add_dimension,))
