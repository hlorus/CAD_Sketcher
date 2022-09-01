from .point_3d import SlvsPoint3D
from .line_3d import SlvsLine3D
from .normal_3d import SlvsNormal3D
from .point_2d import SlvsPoint2D
from .line_2d import SlvsLine2D
from .arc import SlvsArc
from .circle import SlvsCircle

point_3d = (SlvsPoint3D,)
point_2d = (SlvsPoint2D,)
normal_3d = (SlvsNormal3D,)
point = (*point_3d, *point_2d)
line = (SlvsLine3D, SlvsLine2D)
curve = (SlvsCircle, SlvsArc)
segment = (*line, *curve)
