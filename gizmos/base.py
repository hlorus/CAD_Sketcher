import math
from enum import Enum, auto

from mathutils import Matrix

from .. import global_data
from ..declarations import Operators
from ..model.types import GenericConstraint
from ..utilities.constants import QUARTER_TURN
from ..utilities.preferences import get_prefs


def draw_arrow_shape(target, shoulder, width, is_3d=False):
    v = shoulder - target
    mat = Matrix.Rotation(QUARTER_TURN, (3 if is_3d else 2), "Z")
    v.rotate(mat)
    v.length = abs(width / 2)

    return (
        ((shoulder + v)),
        target,
        target,
        ((shoulder - v)),
        ((shoulder - v)),
        ((shoulder + v)),
    )


def get_arrow_size(dist, scale):
    size = scale * 0.01 * get_prefs().arrow_scale
    size = min(size, abs(dist * 0.67))
    size = math.copysign(size, dist)
    return size, size / 2


def get_overshoot(scale, dir):
    if dir == 0:
        return 0
    # use factor of 0.005 for one-half arrowhead
    overshoot = scale * 0.005 * get_prefs().arrow_scale
    return -math.copysign(overshoot, dir)


class Color(Enum):
    Default = auto()
    Failed = auto()
    Reference = auto()
    Text = auto()


def get_constraint_color_type(constraint: GenericConstraint):
    if constraint.failed:
        return Color.Failed
    if constraint.is_reference:
        return Color.Reference
    return Color.Default


def get_color(color_type: Color, highlit: bool):
    c_theme = get_prefs().theme_settings.constraint
    theme_match = {
        # (type, highlit): color
        (Color.Default, False): c_theme.default,
        (Color.Default, True): c_theme.highlight,
        (Color.Failed, False): c_theme.failed,
        (Color.Failed, True): c_theme.failed_highlight,
        (Color.Reference, False): c_theme.reference,
        (Color.Reference, True): c_theme.reference_highlight,
        (Color.Text, False): c_theme.text,
        (Color.Text, True): c_theme.text_highlight,
    }
    return theme_match[(color_type, highlit)]


def set_gizmo_colors(gz, constraint):
    color_type = get_constraint_color_type(constraint)
    color = get_color(color_type, highlit=False)
    color_highlight = get_color(color_type, highlit=True)

    gz.color = color[0:-1]
    gz.alpha = color[-1]
    gz.color_highlight = color_highlight[0:-1]
    gz.alpha_highlight = color_highlight[-1]


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
