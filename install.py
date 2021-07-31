import bpy
from . import (
    functions,
    global_data,
    class_defines,
    operators,
    gizmos,
    workspacetools,
    ui,
)
from bpy.types import Operator

modules = (
    class_defines,
    operators,
    gizmos,
    workspacetools,
    ui,
)


def startup_cb(*args):
    bpy.ops.view3d.slvs_register_draw_cb()
    return None


def register_full():
    for m in modules:
        m.register()

    # Register drawcallback
    bpy.app.timers.register(startup_cb, first_interval=1, persistent=True)


def unregister_full():
    bpy.types.SpaceView3D.draw_handler_remove(global_data.draw_handle, "WINDOW")

    for m in reversed(modules):
        m.unregister()


def check_module():
    # Note: Blender might be installed in a directory that needs admin rights and thus defaulting to a user installation.
    # That path however might not be in sys.path....
    import sys, site

    p = site.USER_BASE + "/lib/python{}.{}/site-packages".format(
        sys.version_info.major, sys.version_info.minor
    )
    if p not in sys.path:
        sys.path.append(p)
    try:
        import python_solvespace

        global_data.registered = True
        register_full()
    except ModuleNotFoundError as e:
        global_data.registered = False
        raise e


class View3D_OT_slvs_install_package(Operator):
    """Install module from local .whl file"""

    bl_idname = "view3d.slvs_install_package"
    bl_label = "Install"

    package: bpy.props.StringProperty(subtype="FILE_PATH")

    @classmethod
    def poll(cls, context):
        return not global_data.registered

    def execute(self, context):

        # blender 2.8 and above should come with pip installed...
        # TODO: Check if pip is available
        # functions.install_pip()
        # functions.update_pip()

        if not self.package:
            self.report({"WARNING"}, "Specify package to be installed")
            return {"CANCELLED"}

        if functions.install_package(self.package):
            self.report({"INFO"}, "Package successfully installed")
        else:
            self.report({"WARNING"}, "Cannot install package: {}".format(self.package))
            return {"CANCELLED"}
        return {"FINISHED"}


def register():
    bpy.utils.register_class(View3D_OT_slvs_install_package)


def unregister():
    bpy.utils.unregister_class(View3D_OT_slvs_install_package)
