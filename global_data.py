import sys
from enum import Enum
from mathutils import Vector

registered = False

PYPATH = sys.executable


entities = {}
batches = {}

offscreen = None

hover = None
ignore_list = []
selected = []

Z_AXIS = Vector((0, 0, 1))

draw_handle = None

# Workplane requirement options
class WpReq(Enum):
    OPTIONAL, FREE, NOT_FREE = range(3)
