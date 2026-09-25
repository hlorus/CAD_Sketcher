from .. import global_data
from ..declarations import Operators
from ..drawing import frame_cache, selection
from ..model.types import GenericConstraint
from .utilities import get_constraint_color_type, set_gizmo_colors


def use_plain_attributes(cls) -> None:
    """Skip ``Gizmo``'s per-attribute property lookup on a gizmo class.

    ``bpy.types.Gizmo`` routes every attribute access through a lookup of the
    gizmo type's registered properties first, costing a path resolve per access.
    Constraint gizmos register no such properties but read a dozen attributes
    for each of hundreds of gizmos every redraw, so they use plain access.
    """
    import bpy

    cls.__getattribute__ = bpy.types.bpy_struct.__getattribute__
    cls.__setattr__ = bpy.types.bpy_struct.__setattr__


# gizmo pointer -> the color it was last given, so it is only set when it changes.
_gizmo_colors = {}


class ConstraintGizmo:
    def _get_constraint(self, context):
        sketch = frame_cache.active_sketch(context)
        if not sketch:
            return None
        return frame_cache.constraint_at(sketch, self.type, self.index)

    def get_constraint_color(self, constraint: GenericConstraint):
        is_highlight = constraint == selection.highlight_constraint or self.is_highlight
        col = get_constraint_color_type(constraint)
        return frame_cache.constraint_color(col, is_highlight)

    def _set_colors(self, context, constraint: GenericConstraint):
        """Overwrite default color when gizmo is highlighted"""

        color_setting = self.get_constraint_color(constraint)
        color = tuple(color_setting[:3])
        pointer = self.as_pointer()
        if _gizmo_colors.get(pointer) != color:
            self.color = color
            _gizmo_colors[pointer] = color
        return color_setting


# gizmo pointer -> the matrix_basis it was last given.
_gizmo_bases = {}


def forget_gizmos() -> None:
    """Drop what was remembered per gizmo, before a group recreates its gizmos.

    A new gizmo can reuse a freed one's pointer and must not inherit its state.
    """
    _gizmo_colors.clear()
    _gizmo_bases.clear()


class ConstraintGizmoGeneric(ConstraintGizmo):
    def _update_matrix_basis(self, constr, basis=None):
        if basis is None:
            basis = constr.matrix_basis()
        pointer = self.as_pointer()
        if _gizmo_bases.get(pointer) is not basis:
            self.matrix_basis = basis
            _gizmo_bases[pointer] = basis

    def setup(self):
        pass

    def _shape_signature(self, context, constr, basis):
        """Everything the drawn shape depends on. The shape (arrows/helplines) is
        rebuilt only when this changes, so a static viewport -- including every
        redraw during a modal drag -- doesn't re-upload a GPU batch per gizmo."""
        return (
            round(getattr(constr, "value", 0.0), 7),
            round(getattr(constr, "radius", 0.0), 7),
            round(getattr(constr, "draw_offset", 0.0), 7),
            round(getattr(constr, "draw_outset", 0.0), 7),
            round(getattr(constr, "leader_angle", 0.0), 7),
            tuple(v for row in basis for v in row),
            # Helplines follow the referenced geometry, not just the placement.
            frame_cache.dimension_geometry_key(
                frame_cache.active_sketch(context), constr
            ),
            frame_cache.view_scale_key(context),
            frame_cache.arrow_scale(),
            frame_cache.ui_scale(context),
        )

    def draw(self, context):
        constr = self._get_constraint(context)
        if not constr or not constr.visible:
            return
        self._set_colors(context, constr)
        basis = frame_cache.dimension_basis(frame_cache.active_sketch(context), constr)
        self._update_matrix_basis(constr, basis)

        # Rebuild the geometry batch only when its inputs change (dimension value,
        # placement, or view), not on every redraw -- the per-frame GPU churn that
        # made constraint-heavy sketches laggy.
        sig = self._shape_signature(context, constr, basis)
        if (
            getattr(self, "_shape_sig", None) != sig
            or getattr(self, "custom_shape", None) is None
        ):
            self._create_shape(context, constr)
            self._shape_sig = sig
        self.draw_custom_shape(self.custom_shape)

    def draw_select(self, context, select_id):
        # While a stateful operator runs, stay out of the gizmo select buffer so
        # the dimension label (which follows the cursor) neither highlights nor
        # swallows a click meant for the geometry underneath -- gating the select
        # pass directly avoids the one-frame lag/flicker of toggling hide_select.
        if global_data.stateful_op_running:
            return
        constr = self._get_constraint(context)
        if not constr or not constr.visible:
            return
        # The select shape (no helplines) overwrites custom_shape, so invalidate
        # the display cache to force draw() to rebuild the real shape next time.
        self._create_shape(context, constr, select=True)
        self._shape_sig = None
        self.draw_custom_shape(self.custom_shape, select_id=select_id)


# gizmo group pointer -> signature of the constraints its gizmos were made for.
_group_signatures = {}


class ConstraintGenericGGT:
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE", "3D", "SHOW_MODAL_ALL"}

    def setup(self, context):
        from ..model.sketch_ref import get_active_sketch

        forget_gizmos()
        _group_signatures[self.as_pointer()] = self._signature(context)
        active_sketch = get_active_sketch(context)
        if not active_sketch:
            return
        for index, c in enumerate(active_sketch.constraints.get_list(self.type)):
            gz = self.gizmos.new(self.gizmo_type)
            gz.index = index

            set_gizmo_colors(gz, c)

            gz.use_draw_modal = True
            gz.target_set_prop("offset", c, "draw_offset")

            props = gz.target_set_operator(Operators.TweakConstraintValuePos)
            props.type = self.type
            props.index = gz.index

    def refresh(self, context):
        """Recreate the gizmos only when this type's constraints changed.

        Blender refreshes groups on nearly every update. Each gizmo binds its
        offset to its constraint, so the gizmos are recreated whenever a
        constraint was added, removed or moved in memory (adding one can move the
        others), and otherwise kept.
        """
        if _group_signatures.get(self.as_pointer()) == self._signature(context):
            return
        self.gizmos.clear()
        self.setup(context)

    def _signature(self, context):
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return None
        return (
            sketch.target_object.as_pointer(),
            tuple(c.as_pointer() for c in sketch.constraints.get_list(self.type)),
        )

    @classmethod
    def poll(cls, context):
        # TODO: Allow to hide
        return True
