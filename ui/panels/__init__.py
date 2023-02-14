from bpy.types import Panel


class VIEW3D_PT_sketcher_base(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sketcher"


from . import (  # noqa: F401, E402
    add_constraint,
    constraints_list,
    debug,
    entities_list,
    sketch_select,
)
