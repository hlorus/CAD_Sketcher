import bpy
from bpy.types import Operator

from .. import global_data
from ..declarations import Operators
from ..utilities.install import check_module
from ..utilities.install import install_package, ensure_pip, show_package_info


class View3D_OT_slvs_install_package(Operator):
    """Install module from local .whl file or from PyPi"""

    bl_idname = Operators.InstallPackage
    bl_label = "Install"

    package: bpy.props.StringProperty(subtype="FILE_PATH")

    @classmethod
    def poll(cls, context):
        return not global_data.registered

    def execute(self, context):
        if not ensure_pip():
            self.report(
                {"WARNING"},
                "PIP is not available and cannot be installed, please install PIP manually",
            )
            return {"CANCELLED"}

        if not self.package:
            self.report({"WARNING"}, "Specify package to be installed")
            return {"CANCELLED"}

        if install_package(self.package):
            try:
                check_module("py_slvs")
                from ..registration import register_full

                register_full()

                self.report({"INFO"}, "Package successfully installed")
            except ModuleNotFoundError:
                msg = """Package should be available but cannot be found, check console for detailed info.
                Try restarting blender, otherwise get in contact."""
                self.report(
                    {"WARNING"},
                    msg,
                )
            show_package_info("py_slvs")
        else:
            self.report({"WARNING"}, "Cannot install package: {}".format(self.package))
            return {"CANCELLED"}
        return {"FINISHED"}


def register():
    bpy.utils.register_class(View3D_OT_slvs_install_package)


def unregister():
    bpy.utils.unregister_class(View3D_OT_slvs_install_package)
