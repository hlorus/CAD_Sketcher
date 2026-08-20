"""Project a single picked mesh element into the active sketch.

A minimal single-state stateful operator: the one state picks a mesh vertex,
edge or face (via the framework's native mesh-element picking), and ``main``
projects just that element as live native curves through the shared
``project_mesh_element`` path. Re-run to project more; shared corners are reused.
"""

import bpy
from bpy.props import BoolProperty
from bpy.types import Context, Operator

from ..declarations import Operators
from ..model.sketch_ref import get_active_sketch
from ..stateful_operator.constants import mesh_element_types
from ..stateful_operator.integration import StatefulOperator
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.curve_data import refresh_curve_geometry
from ..utilities.projection_anchor import project_mesh_element
from .base_stateful import GenericEntityOp

_TYPE_TO_ELEMENT = {
    bpy.types.MeshVertex: "VERTEX",
    bpy.types.MeshEdge: "EDGE",
    bpy.types.MeshPolygon: "FACE",
}


class VIEW3D_OT_slvs_project_geometry(Operator, GenericEntityOp):
    """Project a picked mesh vertex, edge or face into the active sketch"""

    bl_idname = Operators.ProjectGeometry
    bl_label = "Project Geometry"
    bl_options = {"REGISTER", "UNDO"}

    construction: BoolProperty(
        name="Construction Geometry",
        description="Create the projected points and lines as construction geometry",
        default=True,
    )

    states = (
        state_from_args(
            "Element",
            description="Pick a mesh vertex, edge or face to project into the sketch",
            pointer="element",
            types=mesh_element_types,
            property=None,
            use_create=False,
        ),
    )

    @classmethod
    def poll(cls, context: Context):
        return get_active_sketch(context) is not None

    def pick_element(self, context: Context, coords):
        # Only the raw mesh-element pick; skip GenericEntityOp's curve/constraint
        # hover handling, which is irrelevant when projecting scene meshes.
        return StatefulOperator.pick_element(self, context, coords)

    def main(self, context: Context):
        sketch = get_active_sketch(context)
        data = self._state_data.get(0, {})
        elem = _TYPE_TO_ELEMENT.get(data.get("type"))
        pointer = self.get_state_pointer(index=0, implicit=True)
        if sketch is None or elem is None or not pointer:
            return False

        obj_name, mesh_index = pointer
        source = bpy.data.objects.get(obj_name)
        if source is None or source.type != "MESH":
            return False

        n_points, n_lines = project_mesh_element(
            sketch, source, elem, mesh_index, construction=self.construction
        )
        if n_points or n_lines:
            refresh_curve_geometry(sketch)
            from .. import global_data

            global_data.needs_solve = True
            global_data.needs_redraw = True

        self.target = sketch
        return True

    def fini(self, context: Context, succeed: bool):
        pass


register, unregister = register_stateops_factory((VIEW3D_OT_slvs_project_geometry,))
