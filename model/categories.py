from .point_3d import SlvsPoint3D
from .line_3d import SlvsLine3D
from .normal_3d import SlvsNormal3D
from .point_2d import SlvsPoint2D
from .line_2d import SlvsLine2D
from .arc import SlvsArc
from .circle import SlvsCircle
from .normal_2d import SlvsNormal2D

POINT3D = (SlvsPoint3D,)
POINT2D = (SlvsPoint2D,)
NORMAL3D = (SlvsNormal3D,)
POINT = (*POINT3D, *POINT2D)
LINE = (SlvsLine3D, SlvsLine2D)
CURVE = (SlvsCircle, SlvsArc)
SEGMENT = (*LINE, *CURVE)

ELEMENT_2D = (*POINT2D, SlvsLine2D, SlvsNormal2D, SlvsArc, SlvsCircle)
