from bpy.types import Panel


class VIEW3D_PT_sketcher_base(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sketcher"


# XXX: Import order matters, use registration.module_register_factory
from . import (  # noqa: F401, E402
    sketch_select,
    add_constraint,
    entities_list,
    constraints_list,
    debug,
)
