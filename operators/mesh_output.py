"""Operator: create a live mesh mirror of the active sketch.

The sketch object is Curves-typed, so its filled/wire output is not usable as a
real mesh (export, mesh tools). This spawns a companion mesh object carrying the
``CAD Sketcher To Mesh`` group, which reads the sketch's evaluated geometry, so
the mesh follows the sketch live and can be exported or applied to bake it.
"""

import bpy
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..model.sketch_ref import get_active_sketch
from ..utilities.mesh_output_nodes import (
    build_mesh_output_node_group,
    mesh_output_input_ids,
)
from .modifiers import set_modifier_input


class View3D_OT_slvs_create_mesh_output(Operator):
    """Create a mesh object that mirrors the active sketch's output, live"""

    bl_idname = Operators.CreateMeshOutput
    bl_label = "Create Mesh Output"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Context) -> bool:
        sketch = get_active_sketch(context)
        return sketch is not None and sketch.target_object is not None

    def execute(self, context: Context):
        sketch = get_active_sketch(context)
        source = sketch.target_object

        name = f"{sketch.name} Mesh"
        mesh = bpy.data.meshes.new(name)
        ob = bpy.data.objects.new(name, mesh)
        # Match the sketch's transform: Object Info RELATIVE then yields geometry
        # planar in this object's local space (pleasant to edit) but world-correct.
        ob.matrix_world = source.matrix_world.copy()

        for collection in source.users_collection or (context.scene.collection,):
            collection.objects.link(ob)

        group = build_mesh_output_node_group()
        modifier = ob.modifiers.new("CAD Sketcher Mesh", "NODES")
        modifier.node_group = group
        set_modifier_input(modifier, mesh_output_input_ids(group)["Sketch"], source)

        for selected in context.selected_objects:
            selected.select_set(False)
        ob.select_set(True)
        context.view_layer.objects.active = ob

        self.report({"INFO"}, f"Created mesh output '{name}'")
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_create_mesh_output,))
