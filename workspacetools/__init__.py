from .manager import ToolGroup, add
from . import manager

from .add_sketch import VIEW3D_T_slvs_add_sketch
from .add_arc2d import VIEW3D_T_slvs_add_arc2d
from .add_circle2d import VIEW3D_T_slvs_add_circle2d
from .add_line2d import VIEW3D_T_slvs_add_line2d
from .add_point2d import VIEW3D_T_slvs_add_point2d
from .add_rectangle import VIEW3D_T_slvs_add_rectangle
from .array_linear import VIEW3D_T_slvs_node_array_linear
from .bevel import VIEW3D_T_slvs_bevel
from .extrude import VIEW3D_T_slvs_node_extrude
from .offset import VIEW3D_T_slvs_offset
from .select import VIEW3D_T_slvs_select
from .trim import VIEW3D_T_slvs_trim

# Always visible
add(VIEW3D_T_slvs_select, visibility=ToolGroup.SKETCH, separator=True, group=False)

# Sketch-only tools (visible when a sketch is active)
add(VIEW3D_T_slvs_add_point2d, visibility=ToolGroup.SKETCH, separator=True, group=False)
add(VIEW3D_T_slvs_add_line2d, visibility=ToolGroup.SKETCH, separator=False, group=False)
add(VIEW3D_T_slvs_add_circle2d, visibility=ToolGroup.SKETCH, separator=False, group=False)
add(VIEW3D_T_slvs_add_arc2d, visibility=ToolGroup.SKETCH, separator=False, group=False)
add(VIEW3D_T_slvs_add_rectangle, visibility=ToolGroup.SKETCH, separator=False, group=False)
add(VIEW3D_T_slvs_trim, visibility=ToolGroup.SKETCH, separator=True, group=False)
add(VIEW3D_T_slvs_bevel, visibility=ToolGroup.SKETCH, separator=False, group=False)
add(VIEW3D_T_slvs_offset, visibility=ToolGroup.SKETCH, separator=False, group=False)

# Non-sketch tools (visible when no sketch is active)
add(VIEW3D_T_slvs_add_sketch, visibility=ToolGroup.NON_SKETCH, separator=True, group=False)
add(VIEW3D_T_slvs_node_extrude, visibility=ToolGroup.NON_SKETCH, separator=True, group=False)
add(VIEW3D_T_slvs_node_array_linear, visibility=ToolGroup.NON_SKETCH, separator=False, group=False)


def register():
    manager.register()


def unregister():
    manager.unregister()
