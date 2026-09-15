import blf
from bpy.types import Gizmo, GizmoGroup
from mathutils import Matrix, Vector

from .. import global_data, units
from ..declarations import GizmoGroups, Gizmos, Operators
from ..drawing import constraint_icons, frame_cache
from .base import ConstraintGizmo, forget_gizmos
from .utilities import Color

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
        forget_gizmos()
        if not active_sketch:
            return
        mapping, signature = self._layout(context, active_sketch)
        self._create_gizmos(context, active_sketch, mapping)
        _layout_signatures[self.as_pointer()] = signature

    def _layout(self, context, active_sketch):
        """The dimensional constraints to give value gizmos, and a signature.

        Geometric constraints share one icon gizmo (VIEW3D_GT_slvs_constraint)
        that picks from the icons as drawn, so only dimensions shape the group.
        """
        from ..model.base_constraint import DimensionalConstraint

        dimensional = []
        for coll in active_sketch.constraints.get_lists():
            for index, c in enumerate(coll):
                if isinstance(c, DimensionalConstraint):
                    dimensional.append((c.type, index))
        signature = (active_sketch.target_object.as_pointer(), tuple(dimensional))
        return dimensional, signature

    def _create_gizmos(self, context, active_sketch, dimensional):
        gz = self.gizmos.new(VIEW3D_GT_slvs_constraint.bl_idname)
        gz.use_draw_modal = True

        # Add value gizmos for dimensional constraints
        for constraint_type, index in dimensional:
            gz = self.gizmos.new(VIEW3D_GT_slvs_constraint_value.bl_idname)
            gz.type = constraint_type
            gz.index = index

            props = gz.target_set_operator(Operators.TweakConstraintValuePos)
            props.type = constraint_type
            props.index = index

    def refresh(self, context):
        """Rebuild the gizmos only when their layout changed.

        Blender refreshes the group on nearly every update, including each mouse
        move of a drawing operator. Recreating every gizmo (and its operator
        binding) each time made drawing slower with every constraint in the
        sketch.
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
                return

        self.gizmos.clear()
        _layout_signatures.pop(self.as_pointer(), None)
        forget_gizmos()
        if active_sketch is None:
            return
        self._create_gizmos(context, active_sketch, mapping)
        _layout_signatures[self.as_pointer()] = signature


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


class VIEW3D_GT_slvs_constraint(Gizmo):
    """Picks geometric constraints by their icons, one gizmo for all of them.

    A gizmo per constraint cost a Python call per constraint on every redraw and
    mouse move, and recreating hundreds of them on changes. This one answers hit
    tests from the icons as drawn (drawing.constraint_icons) and has a part per
    icon, each bound to that constraint's context menu, so hover highlighting and
    clicking behave as they did per constraint.
    """

    bl_idname = Gizmos.Constraint

    __slots__ = ("_bound",)

    def _bind(self):
        """Bind each icon's part to its constraint when the icons changed."""
        targets = constraint_icons.targets()
        if getattr(self, "_bound", None) == targets:
            return
        # Highest part first: the part array grows to fit, so this allocates once.
        for part in reversed(range(len(targets))):
            constraint_type, index = targets[part]
            props = self.target_set_operator(Operators.ContextMenu, index=part)
            props.type = constraint_type
            props.index = index
            # Defer opening the menu until the mouse is released, otherwise the
            # click's RELEASE falls through and triggers the entry under the
            # cursor (often "Delete"). Matches the right-click keymap.
            props.delayed = True
            props.highlight_hover = True
            props.highlight_members = True
        self._bound = targets

    def test_select(self, context, location):
        # Don't intercept hover/picking while a stateful operator is running.
        if global_data.stateful_op_running:
            return -1
        part = constraint_icons.hit_test(location)
        if part is None or getattr(self, "_bound", None) != constraint_icons.targets():
            return -1
        return part

    def draw(self, context):
        # The icons are drawn for all constraints at once; keep the parts bound
        # to the constraints they were laid out for.
        if not global_data.stateful_op_running:
            self._bind()

    def setup(self):
        self._bound = None


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
