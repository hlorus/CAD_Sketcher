"""Export the active sketch as a reusable IFC4 profile library."""

from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory
from bpy_extras.io_utils import ExportHelper

from ..declarations import Operators
from ..model.sketch_ref import Sketch, get_active_sketch, is_sketch_object
from ..utilities.ifc_export import IfcOpenShellMissing
from ..utilities.ifc_file import write_sketch_profiles
from ..utilities.ifc_sketch import sketch_profiles
from ..utilities.preferences import get_prefs


class ExportCADSketcherIFC(Operator, ExportHelper):
    """Export analytic closed profiles and holes from the active 2D sketch"""

    bl_idname = Operators.ExportIFC
    bl_label = "Export IFC Profiles"
    filename_ext = ".ifc"

    filter_glob: StringProperty(default="*.ifc", options={"HIDDEN"})
    sketch_name: StringProperty(options={"HIDDEN"})

    @classmethod
    def poll(cls, context: Context) -> bool:
        """Offer export only when enabled and a native 2D sketch is active."""
        if not get_prefs().enable_ifc_profile_export:
            cls.poll_message_set(
                "Enable IFC Profile Export in CAD Sketcher preferences"
            )
            return False
        sketch = get_active_sketch(context)
        if sketch is None or sketch.is_3d:
            cls.poll_message_set("Enter a two-dimensional sketch before exporting")
            return False
        return True

    def invoke(self, context: Context, event: bpy.types.Event) -> set[str]:
        """Capture the active sketch before opening Blender's file browser."""
        sketch = get_active_sketch(context)
        self.sketch_name = sketch.name
        if not self.filepath:
            self.filepath = bpy.path.clean_name(sketch.name) + self.filename_ext
        return ExportHelper.invoke(self, context, event)

    def draw(self, context: Context) -> None:
        """Describe the exported geometry and coordinate frame in the browser."""
        self.layout.label(text="Lines, circular arcs, circles and contained holes")
        self.layout.label(text="Construction geometry is excluded")
        self.layout.label(text="Coordinates use the sketch's local frame")

    def execute(self, context: Context) -> set[str]:
        """Convert the selected native sketch and atomically publish its IFC file."""
        if self.sketch_name:
            obj = context.scene.objects.get(self.sketch_name)
            if not is_sketch_object(obj):
                self.report({"ERROR"}, "The selected sketch is no longer available")
                return {"CANCELLED"}
            sketch = Sketch(obj)
        else:
            sketch = get_active_sketch(context)
        if sketch is None:
            self.report({"ERROR"}, "Enter a two-dimensional sketch before exporting")
            return {"CANCELLED"}
        try:
            profiles = sketch_profiles(
                sketch, unit_scale=context.scene.unit_settings.scale_length
            )
            write_sketch_profiles(
                self.filepath,
                profiles,
                unit_scale=context.scene.unit_settings.scale_length,
            )
        except IfcOpenShellMissing:
            self.report(
                {"ERROR"},
                "Install IfcOpenShell in this Blender Python environment to export IFC profiles",
            )
            return {"CANCELLED"}
        except (ValueError, OSError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Exported {len(profiles)} profile(s) to {Path(self.filepath).name}",
        )
        return {"FINISHED"}


def _export_menu(self: bpy.types.Menu, context: Context) -> None:
    if get_prefs().enable_ifc_profile_export:
        self.layout.operator(
            Operators.ExportIFC, text="CAD Sketcher IFC Profiles (.ifc)"
        )


_register, _unregister = register_classes_factory((ExportCADSketcherIFC,))


def register() -> None:
    """Register the exporter and its standard File > Export entry."""
    _register()
    bpy.types.TOPBAR_MT_file_export.append(_export_menu)


def unregister() -> None:
    """Remove the export menu before unregistering its operator."""
    bpy.types.TOPBAR_MT_file_export.remove(_export_menu)
    _unregister()
