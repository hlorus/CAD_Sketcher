import math
from enum import Enum, auto

from mathutils import Matrix

from ..model.types import GenericConstraint
from ..utilities.constants import QUARTER_TURN
from ..utilities.preferences import get_prefs


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


def context_mode_check(context, widget_group):
    tools = context.workspace.tools
    mode = context.mode
    for tool in tools:
        if (tool.widget == widget_group) and (tool.mode == mode):
            break
    else:
        context.window_manager.gizmo_group_type_unlink_delayed(widget_group)
        return False
    return True
