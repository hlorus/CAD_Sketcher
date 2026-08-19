import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.sketch_ref import get_active_sketch
from ..utilities.curve_data import refresh_curve_geometry
from ..utilities.projection_anchor import project_curves_object, project_mesh_object

# Object types this tool can project onto the active sketch.
_MESH_SOURCE = {"MESH"}
_CURVE_SOURCE = {"CURVES", "CURVE"}


class VIEW3D_OT_slvs_project_geometry(Operator):
    """Project a mesh object's edges or a sketch's lines onto the active sketch"""

    bl_idname = Operators.ProjectGeometry
    bl_label = "Project Geometry"
    bl_description = (
        "Project a mesh's edges or another sketch's lines onto the active sketch "
        "and keep a live source reference"
    )
    bl_options = {"REGISTER", "UNDO"}

    source: StringProperty(
        name="Source",
        description=(
            "Mesh or sketch object whose geometry is projected onto the active sketch"
        ),
        default="",
    )
    construction: BoolProperty(
        name="Construction Geometry",
        description="Create the projected points and lines as construction geometry",
        default=True,
    )

    @classmethod
    def poll(cls, context: Context):
        return get_active_sketch(context) is not None

    def _selected_source(self, context):
        sketch = get_active_sketch(context)
        sketch_ob = sketch.target_object if sketch else None
        candidates = [
            obj
            for obj in context.selected_objects
            if obj is not sketch_ob and obj.type in (_MESH_SOURCE | _CURVE_SOURCE)
        ]
        return candidates[0] if len(candidates) == 1 else None

    def invoke(self, context: Context, event):
        if not self.source:
            selected = self._selected_source(context)
            if selected is not None:
                self.source = selected.name
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context):
        layout = self.layout
        layout.prop_search(self, "source", bpy.data, "objects", text="Source")
        layout.prop(self, "construction")

    def execute(self, context: Context):
        sketch = get_active_sketch(context)
        if sketch is None:
            self.report({"ERROR"}, "Enter a sketch before projecting geometry")
            return {"CANCELLED"}

        source = bpy.data.objects.get(self.source)
        if source is None or source.type not in (_MESH_SOURCE | _CURVE_SOURCE):
            self.report({"ERROR"}, "Choose a mesh or sketch source object")
            return {"CANCELLED"}
        if source == sketch.target_object:
            self.report({"ERROR"}, "The source cannot be the active sketch")
            return {"CANCELLED"}

        skipped = 0
        if source.type in _MESH_SOURCE:
            points, lines = project_mesh_object(
                sketch, source, construction=self.construction
            )
            summary = f"{len(lines)} edge(s)"
            empty_msg = "The source mesh has no edges to project"
        else:
            points, lines, skipped = project_curves_object(
                sketch, source, construction=self.construction
            )
            summary = f"{len(lines)} line(s), {len(points)} point(s)"
            empty_msg = "The source sketch has no lines or points to project"
        if not points and not lines:
            self.report({"WARNING"}, empty_msg)
            return {"CANCELLED"}

        refresh_curve_geometry(sketch)
        from .. import global_data

        global_data.needs_solve = True
        global_data.needs_redraw = True
        message = f"Projected {summary} from {source.name}"
        if skipped:
            # Arcs/circles project to an ellipse on a non-parallel plane, which
            # has no native representation, so they are left out (see #626).
            message += f" (skipped {skipped} arc(s)/circle(s), not supported)"
        self.report({"INFO"}, message)
        return {"FINISHED"}


register, unregister = register_classes_factory((VIEW3D_OT_slvs_project_geometry,))
