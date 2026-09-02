from .. import global_data
from ..declarations import Operators
from ..drawing import selection
from ..model.types import GenericConstraint
from .utilities import get_color, get_constraint_color_type, set_gizmo_colors


class ConstraintGizmo:
    def _get_constraint(self, context):
        from ..model.sketch_ref import get_active_sketch

        sketch = get_active_sketch(context)
        if not sketch:
            return None
        return sketch.constraints.get_from_type_index(self.type, self.index)

    def get_constraint_color(self, constraint: GenericConstraint):
        is_highlight = constraint == selection.highlight_constraint or self.is_highlight
        col = get_constraint_color_type(constraint)
        return get_color(col, is_highlight)

    def _set_colors(self, context, constraint: GenericConstraint):
        """Overwrite default color when gizmo is highlighted"""

        color_setting = self.get_constraint_color(constraint)
        self.color = color_setting[:3]
        return color_setting


class ConstraintGizmoGeneric(ConstraintGizmo):
    def _update_matrix_basis(self, constr):
        self.matrix_basis = constr.matrix_basis()

    def setup(self):
        pass

    def _shape_signature(self, context, constr):
        """Everything the drawn shape depends on. The shape (arrows/helplines) is
        rebuilt only when this changes, so a static viewport -- including every
        redraw during a modal drag -- doesn't re-upload a GPU batch per gizmo."""
        rv3d = context.region_data
        persp = (
            tuple(rv3d.perspective_matrix[i][j] for i in range(4) for j in range(4))
            if rv3d
            else None
        )
        mw = self.matrix_world
        try:
            offset = float(self.target_get_value("offset"))
        except (TypeError, ValueError):
            offset = None
        return (
            round(getattr(constr, "value", 0.0), 7),
            round(getattr(constr, "radius", 0.0), 7),
            round(getattr(constr, "draw_offset", 0.0), 7),
            round(getattr(constr, "draw_outset", 0.0), 7),
            round(getattr(constr, "leader_angle", 0.0), 7),
            offset,
            tuple(mw[i][j] for i in range(4) for j in range(4)),
            persp,
            context.preferences.system.ui_scale,
        )

    def draw(self, context):
        constr = self._get_constraint(context)
        if not constr or not constr.visible:
            return
        self._set_colors(context, constr)
        self._update_matrix_basis(constr)

        # Rebuild the geometry batch only when its inputs change (dimension value,
        # placement, or view), not on every redraw -- the per-frame GPU churn that
        # made constraint-heavy sketches laggy.
        sig = self._shape_signature(context, constr)
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


class ConstraintGenericGGT:
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE", "3D"}

    def setup(self, context):
        from ..model.sketch_ref import get_active_sketch

        active_sketch = get_active_sketch(context)
        if not active_sketch:
            return
        for c in active_sketch.constraints.get_list(self.type):
            gz = self.gizmos.new(self.gizmo_type)
            gz.index = active_sketch.constraints.get_index(c)

            set_gizmo_colors(gz, c)

            gz.use_draw_modal = True
            gz.target_set_prop("offset", c, "draw_offset")

            props = gz.target_set_operator(Operators.TweakConstraintValuePos)
            props.type = self.type
            props.index = gz.index

    def refresh(self, context):
        # recreate gizmos here!
        self.gizmos.clear()
        self.setup(context)

    @classmethod
    def poll(cls, context):
        # TODO: Allow to hide
        return True
