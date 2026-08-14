import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.sketch_ref import get_active_sketch
from ..utilities.curve_data import refresh_curve_geometry
from ..utilities.projection_anchor import project_mesh_object


class VIEW3D_OT_slvs_project_geometry(Operator):
    """Project a mesh object's edges onto the active sketch"""

    bl_idname = Operators.ProjectGeometry
    bl_label = "Project Geometry"
    bl_description = (
        "Project mesh edges onto the active sketch and keep a live source reference"
    )
    bl_options = {"REGISTER", "UNDO"}

    source: StringProperty(
        name="Source",
        description="Mesh object whose edges are projected onto the active sketch",
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
        meshes = [
            obj
            for obj in context.selected_objects
            if obj is not sketch_ob and obj.type == "MESH"
        ]
        return meshes[0] if len(meshes) == 1 else None

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
        if source is None or source.type != "MESH":
            self.report({"ERROR"}, "Choose a mesh source object")
            return {"CANCELLED"}
        if source == sketch.target_object:
            self.report({"ERROR"}, "The source cannot be the active sketch")
            return {"CANCELLED"}

        _, lines = project_mesh_object(
            sketch,
            source,
            construction=self.construction,
        )
        if not lines:
            self.report({"WARNING"}, "The source mesh has no edges to project")
            return {"CANCELLED"}

        refresh_curve_geometry(sketch)
        from .. import global_data

        global_data.needs_solve = True
        global_data.needs_redraw = True
        self.report(
            {"INFO"},
            f"Projected {len(lines)} edge(s) from {source.name}",
        )
        return {"FINISHED"}


register, unregister = register_classes_factory((VIEW3D_OT_slvs_project_geometry,))
