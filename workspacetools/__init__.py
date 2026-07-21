import bpy
from bpy.utils import register_tool, unregister_tool

from .add_arc2d import VIEW3D_T_slvs_add_arc2d
from .add_circle2d import VIEW3D_T_slvs_add_circle2d
from .add_line2d import VIEW3D_T_slvs_add_line2d
from .add_point2d import VIEW3D_T_slvs_add_point2d
from .add_rectangle import VIEW3D_T_slvs_add_rectangle
from .bevel import VIEW3D_T_slvs_bevel
from .offset import VIEW3D_T_slvs_offset
from .select import VIEW3D_T_slvs_select
from .trim import VIEW3D_T_slvs_trim


tools = (
    (VIEW3D_T_slvs_select, {"separator": True, "group": False}),
    (VIEW3D_T_slvs_add_point2d, {"separator": True, "group": False}),
    (VIEW3D_T_slvs_add_line2d, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_add_circle2d, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_add_arc2d, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_add_rectangle, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_trim, {"separator": True, "group": False}),
    (VIEW3D_T_slvs_bevel, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_offset, {"separator": False, "group": False}),
)


def register():
    if bpy.app.background:
        return

    for tool in tools:
        register_tool(tool[0], **tool[1])


def unregister():
    if bpy.app.background:
        return

    for tool in reversed(tools):
        unregister_tool(tool[0])
