import math

from mathutils import Matrix

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


def get_overshoot(scale, dir):
    if dir == 0:
        return 0
    # use factor of 0.005 for one-half arrowhead
    overshoot = scale * 0.005 * get_prefs().arrow_scale
    return -math.copysign(overshoot, dir)


def get_arrow_size(dist, scale):
    size = scale * 0.01 * get_prefs().arrow_scale
    size = min(size, abs(dist * 0.67))
    size = math.copysign(size, dist)
    return size, size / 2
