import math

import blf
from bpy.types import Gizmo, GizmoGroup
from mathutils import Matrix, Vector

from .. import global_data, units
from ..declarations import GizmoGroups, Gizmos, Operators
from ..drawing import frame_cache
from ..utilities.preferences import get_prefs
from ..utilities.view import get_2d_coords, get_scale_from_pos
from .base import ConstraintGizmo, forget_gizmos
from .utilities import (
    Color,
    get_constraint_color_type,
    set_gizmo_colors,
)

GIZMO_OFFSET = Vector((1.0, 1.0))
FONT_ID = 0


# constraint type -> unit of its value property (fixed per type).
_value_units = {}


def _get_formatted_value(context, constr):
    unit = _value_units.get(constr.type)
    if unit is None:
        unit = _value_units[constr.type] = constr.rna_type.properties["value"].unit
    value = constr.value

    if unit == "LENGTH":
        if constr.type == "DIAMETER" and constr.setting:
            s = "R" + units.format_distance(value)
        else:
            s = units.format_distance(value)
        return s
    elif unit == "ROTATION":
        return units.format_angle(value)
    return ""


class VIEW3D_GGT_slvs_constraint(GizmoGroup):
    bl_idname = GizmoGroups.Constraint
    bl_label = "Constraint Gizmo Group"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE"}

    @classmethod
    def poll(cls, context):
        # TODO: Allow to hide
        return True

    def setup(self, context):
        from ..model.sketch_ref import get_active_sketch

        active_sketch = get_active_sketch(context)
        _layout_signatures.pop(self.as_pointer(), None)
        _gizmo_color_keys.clear()
        forget_gizmos()
        if not active_sketch:
            return
        mapping, signature = self._layout(context, active_sketch)
        self._create_gizmos(context, active_sketch, mapping)
        _layout_signatures[self.as_pointer()] = signature

    def _layout(self, context, active_sketch):
        """Placement mapping for the gizmos, plus a signature of their layout.

        The signature covers everything ``_create_gizmos`` bakes into a gizmo that
        is not refreshed while drawing: which constraints exist and where each
        marker is anchored, the stacking order, and the scale preferences.
        """
        from ..model.base_constraint import DimensionalConstraint

        # Build mapping: placement_key -> [constraints]
        # Uses curve_ids when available, falls back to entity objects
        mapping = {}
        dimensional = []
        # Indices come from enumerating each collection: looking each one up
        # with get_index scans its collection, which made this quadratic in the
        # number of constraints on every refresh.
        index_of = {}
        for coll in active_sketch.constraints.get_lists():
            for index, c in enumerate(coll):
                index_of[c.as_pointer()] = index
                if isinstance(c, DimensionalConstraint):
                    dimensional.append((c.type, index))
                    continue

                # Try curve_id placements first
                cid_placements = c.curve_id_placements()
                if cid_placements:
                    for cid in cid_placements:
                        key = ("curve_id", cid)
                        mapping.setdefault(key, []).append(c)
                elif hasattr(c, "placements"):
                    # Fallback to entity placements
                    for e in c.placements():
                        if e and hasattr(e, "placement") and e.is_visible(context):
                            key = ("entity", e.slvs_index)
                            mapping.setdefault(key, []).append(c)

        signature = (
            active_sketch.target_object.as_pointer(),
            context.preferences.system.ui_scale,
            get_prefs().gizmo_scale,
            tuple(
                (key, tuple((c.type, index_of[c.as_pointer()]) for c in constrs))
                for key, constrs in mapping.items()
            ),
            tuple(dimensional),
        )
        return mapping, signature

    def _create_gizmos(self, context, active_sketch, mapping):
        for key, constrs in mapping.items():
            kind, ident = key

            for i, c in enumerate(constrs):
                gz = self.gizmos.new(VIEW3D_GT_slvs_constraint.bl_idname)
                gz.type = c.type
                gz.index = active_sketch.constraints.get_index(c)

                if kind == "curve_id":
                    gz.entity_index = -1
                    gz.curve_id = ident
                else:
                    gz.entity_index = ident
                    gz.curve_id = getattr(c, "curve_id_1", "")

                gz.placement_pos = _marker_position(c, active_sketch)

                ui_scale = context.preferences.system.ui_scale
                scale = get_prefs().gizmo_scale * ui_scale
                offset_base = Vector((scale * 1.0, 0.0))
                offset = offset_base * i * ui_scale

                gz.offset = offset
                gz.scale_basis = scale

                set_gizmo_colors(gz, c)

                gz.use_draw_modal = True

                op = Operators.ContextMenu
                props = gz.target_set_operator(op)
                props.type = c.type
                props.index = gz.index
                # Defer opening the menu until the mouse is released, otherwise
                # the click's RELEASE falls through and triggers the entry under
                # the cursor (often "Delete"). Matches the right-click keymap.
                props.delayed = True

                props.highlight_hover = True
                props.highlight_members = True

        # Add value gizmos for dimensional constraints
        for c in active_sketch.constraints.dimensional:
            gz = self.gizmos.new(VIEW3D_GT_slvs_constraint_value.bl_idname)
            index = active_sketch.constraints.get_index(c)
            gz.type = c.type
            gz.index = index

            props = gz.target_set_operator(Operators.TweakConstraintValuePos)
            props.type = c.type
            props.index = index

    def refresh(self, context):
        """Rebuild the gizmos only when their layout changed.

        Blender refreshes the group on nearly every update, including each mouse
        move of a drawing operator. Recreating every gizmo (and its operator
        binding) each time made drawing slower with every constraint in the
        sketch. When the layout is unchanged, only the state that can change
        without it (colors, computed marker positions) is updated in place.
        """
        from ..model.sketch_ref import get_active_sketch

        active_sketch = get_active_sketch(context)
        if active_sketch is not None and global_data.stateful_op_running:
            # A drawing operator refreshes the group on every mouse move, and its
            # preview never changes which constraints exist without changing how
            # many there are. Only a changed count needs the full layout check;
            # the refresh after the operator ends does it regardless.
            counts = _constraint_counts(active_sketch)
            if _layout_counts.get(self.as_pointer()) == counts:
                return
        if active_sketch is not None:
            mapping, signature = self._layout(context, active_sketch)
            _layout_counts[self.as_pointer()] = _constraint_counts(active_sketch)
            if _layout_signatures.get(self.as_pointer()) == signature:
                # Colors and marker positions only feed the gizmo's hit-test,
                # which is off while a stateful operator runs (see test_select). The
                # operator's _end forces a refresh, so they're brought current as
                # soon as it finishes. The layout check above still runs, so a
                # gizmo added mid-operator (e.g. a dimension's value) appears.
                if not global_data.stateful_op_running:
                    self._update_in_place(active_sketch)
                return

        self.gizmos.clear()
        _layout_signatures.pop(self.as_pointer(), None)
        # Freed gizmo pointers can be reused by new gizmos; drop their color keys
        # so a new gizmo never inherits a stale "colors already set" entry.
        _gizmo_color_keys.clear()
        forget_gizmos()
        if active_sketch is None:
            return
        self._create_gizmos(context, active_sketch, mapping)
        _layout_signatures[self.as_pointer()] = signature

    def _update_in_place(self, active_sketch):
        constraints = active_sketch.constraints
        theme = _theme_signature()
        for gz in self.gizmos:
            if gz.bl_idname != VIEW3D_GT_slvs_constraint.bl_idname:
                continue
            c = constraints.get_from_type_index(gz.type, gz.index)
            if c is None:
                continue
            # Resolving theme colors is the expensive part of a refresh, and they
            # only change with the constraint's color type (failed, reference) or
            # the theme, so reapply them only then.
            key = (get_constraint_color_type(c), theme)
            if _gizmo_color_keys.get(gz.as_pointer()) != key:
                set_gizmo_colors(gz, c)
                _gizmo_color_keys[gz.as_pointer()] = key
            gz.placement_pos = _marker_position(c, active_sketch)


# gizmo group pointer -> layout signature of the gizmos it currently holds. Keyed
# by pointer because Blender may hand refresh() a fresh Python wrapper.
_layout_signatures = {}

# gizmo group pointer -> constraint counts its layout was last checked for.
_layout_counts = {}


def _constraint_counts(sketch):
    """How many constraints of each type the sketch has."""
    return (
        sketch.target_object.as_pointer(),
        tuple(len(coll) for coll in sketch.constraints.get_lists()),
    )


# gizmo pointer -> (color type, theme) its colors were last set for.
_gizmo_color_keys = {}


def _theme_signature():
    """The constraint theme colors, as a hashable value."""
    c_theme = get_prefs().theme_settings.constraint
    return tuple(
        tuple(getattr(c_theme, name))
        for name in (
            "default",
            "highlight",
            "failed",
            "failed_highlight",
            "reference",
            "reference_highlight",
        )
    )


def _marker_position(constraint, sketch):
    """A constraint's computed marker position (e.g. a tangent point), or None."""
    if not hasattr(constraint, "marker_position"):
        return None
    try:
        return constraint.marker_position(sketch)
    except Exception:
        return None


class VIEW3D_GT_slvs_constraint(ConstraintGizmo, Gizmo):
    bl_idname = Gizmos.Constraint

    __slots__ = (
        "custom_shape",
        "type",
        "index",
        "entity_index",
        "offset",
        "placement_pos",
        "_placed_frame",
    )

    def _update_matrix_basis(self, context, constr):
        pos = None

        # A constraint may supply a computed world position (e.g. a tangent
        # point); otherwise fall back to the referenced curve's placement.
        world_pos = getattr(self, "placement_pos", None)
        if world_pos is None and hasattr(self, "curve_id") and self.curve_id:
            sketch = frame_cache.active_sketch(context)
            if sketch:
                # Shared with the icon pass and every other marker on this curve.
                world_pos = frame_cache.curve_placement(sketch, self.curve_id)
            else:
                return

        if world_pos is not None:
            pos = get_2d_coords(context, world_pos)
            if not pos:
                return

            scale_3d = max(1, get_scale_from_pos(pos, context.region_data) / 500)
            pos += GIZMO_OFFSET * self.scale_basis / scale_3d + self.offset

        if pos:
            mat = Matrix.Translation(Vector((pos[0], pos[1], 0.0)))
            self.matrix_basis = mat

    def test_select(self, context, location):
        # Don't intercept hover/picking while a stateful operator is running.
        if global_data.stateful_op_running:
            return -1
        # Place the hit area under the icon, at most once per redraw and only while
        # the mouse moves, instead of for every constraint on every redraw.
        if getattr(self, "_placed_frame", None) != frame_cache.frame_id():
            self._placed_frame = frame_cache.frame_id()
            constraint = self._get_constraint(context)
            if constraint is None or not constraint.visible:
                return -1
            self._update_matrix_basis(context, constraint)
        location = Vector(location).to_3d()
        location -= self.matrix_basis.translation
        location *= 1.0 / self.scale_basis

        if math.pow(location.length, 2) < 1.0:
            return 0
        return -1

    def draw(self, context):
        # Blender requires a draw callback, but the icon is drawn for all
        # constraints at once by drawing.constraint_icons and the hit area is
        # placed on demand by test_select.
        pass

    def setup(self):
        pass


class VIEW3D_GT_slvs_constraint_value(ConstraintGizmo, Gizmo):
    """Display the value of a dimensional constraint"""

    bl_idname = Gizmos.ConstraintValue

    __slots__ = ("type", "index", "width", "height")

    def test_select(self, context, location):
        # Don't intercept hover/picking while a stateful operator is running.
        if global_data.stateful_op_running:
            return -1
        coords = Vector(location) - self.matrix_basis.translation.to_2d()

        width, height = self.width, self.height
        if -width / 2 < coords.x < width / 2 and -height / 2 < coords.y < height / 2:
            return 0
        return -1

    def draw(self, context):
        constr = self._get_constraint(context)

        # constr is None when its constraint was just deleted but the gizmo group
        # hasn't refreshed yet (e.g. clearing failed constraints on an
        # over-constrained sketch) -- skip drawing rather than dereference None.
        if not constr or not constr.visible or not hasattr(constr, "value_placement"):
            return

        color = frame_cache.constraint_color(Color.Text, self.is_highlight)
        text = _get_formatted_value(context, constr)
        text_size = frame_cache.text_size()

        blf.color(FONT_ID, *color)
        blf.size(FONT_ID, text_size)
        self.width, self.height = blf.dimensions(FONT_ID, text)

        margin = text_size / 4

        sketch = frame_cache.active_sketch(context)
        basis = frame_cache.dimension_basis(sketch, constr) if sketch else None
        pos = constr.value_placement(context, basis)
        if not pos:
            return
        # Update Matrix for selection
        if tuple(self.matrix_basis.translation.to_2d()) != tuple(pos):
            self.matrix_basis = Matrix.Translation(pos.to_3d())

        blf.position(FONT_ID, pos[0] - self.width / 2, pos[1] + margin, 0)
        blf.draw(FONT_ID, text)

    def setup(self):
        self.width = 0
        self.height = 0
