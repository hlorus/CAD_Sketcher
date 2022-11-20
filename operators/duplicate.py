from bpy.types import Macro
from bpy.utils import register_class, unregister_class

from ..declarations import Macros


class View3D_OT_slvs_duplicate_move(Macro):
    """Duplicate selected entities"""

    bl_idname = Macros.DuplicateMove
    bl_label = "Duplicate"
    bl_options = {"UNDO"}


def register():
    register_class(View3D_OT_slvs_duplicate_move)
    View3D_OT_slvs_duplicate_move.define("VIEW3D_OT_slvs_copy")
    View3D_OT_slvs_duplicate_move.define("VIEW3D_OT_slvs_paste")


def unregister():
    unregister_class(View3D_OT_slvs_duplicate_move)
