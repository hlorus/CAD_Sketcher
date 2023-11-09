import bpy
from bpy.utils import register_tool, unregister_tool

from .add_arc2d import VIEW3D_T_slvs_add_arc2d
from .add_circle2d import VIEW3D_T_slvs_add_circle2d
from .add_line2d import VIEW3D_T_slvs_add_line2d
from .add_line3d import VIEW3D_T_slvs_add_line3d
from .add_point2d import VIEW3D_T_slvs_add_point2d
from .add_point3d import VIEW3D_T_slvs_add_point3d
from .add_rectangle import VIEW3D_T_slvs_add_rectangle
from .add_workplane import VIEW3D_T_slvs_add_workplane
from .add_workplane_face import VIEW3D_T_slvs_add_workplane_face
from .bevel import VIEW3D_T_slvs_bevel
from .offset import VIEW3D_T_slvs_offset
from .select import VIEW3D_T_slvs_select
from .trim import VIEW3D_T_slvs_trim


tools = (
    (VIEW3D_T_slvs_select, {"separator": True, "group": False}),
    (VIEW3D_T_slvs_add_point2d, {"separator": True, "group": True}),
    (
        VIEW3D_T_slvs_add_point3d,
        {
            "after": {VIEW3D_T_slvs_add_point2d.bl_idname},
        },
    ),
    (VIEW3D_T_slvs_add_line2d, {"separator": False, "group": True}),
    (
        VIEW3D_T_slvs_add_line3d,
        {
            "after": {VIEW3D_T_slvs_add_line2d.bl_idname},
        },
    ),
    (VIEW3D_T_slvs_add_circle2d, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_add_arc2d, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_add_rectangle, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_trim, {"separator": True, "group": False}),
    (VIEW3D_T_slvs_bevel, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_offset, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_add_workplane_face, {"separator": True, "group": True}),
    (
        VIEW3D_T_slvs_add_workplane,
        {"after": {VIEW3D_T_slvs_add_workplane_face.bl_idname}},
    ),
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
