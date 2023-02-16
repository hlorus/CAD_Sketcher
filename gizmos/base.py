from .. import global_data
from ..declarations import Operators
from ..model.types import GenericConstraint
from .utilities import get_color, get_constraint_color_type, set_gizmo_colors


class ConstraintGizmo:
    def _get_constraint(self, context):
        return context.scene.sketcher.constraints.get_from_type_index(
            self.type, self.index
        )

    def get_constraint_color(self, constraint: GenericConstraint):
        is_highlight = (
            constraint == global_data.highlight_constraint or self.is_highlight
        )
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

    def draw(self, context):
        constr = self._get_constraint(context)
        if not constr.visible:
            return
        self._set_colors(context, constr)
        self._update_matrix_basis(constr)

        self._create_shape(context, constr)
        self.draw_custom_shape(self.custom_shape)

    # NOTE: Idealy the geometry batch wouldn't be recreated every redraw,
    # however the geom changes with the distance value, maybe at least
    # track changes for that value
    # if not hasattr(self, "custom_shape"):
    def draw_select(self, context, select_id):
        if not context.scene.sketcher.selectable_constraints:
            return

        constr = self._get_constraint(context)
        if not constr.visible:
            return
        self._create_shape(context, constr, select=True)
        self.draw_custom_shape(self.custom_shape, select_id=select_id)


class ConstraintGenericGGT:
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT", "SCALE", "3D"}

    def _list_from_type(self, context):
        return context.scene.sketcher.constraints.get_list(self.type)

    def setup(self, context):
        for c in self._list_from_type(context):
            if not c.is_active(context.scene.sketcher.active_sketch):
                continue
            gz = self.gizmos.new(self.gizmo_type)
            gz.index = context.scene.sketcher.constraints.get_index(c)

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
