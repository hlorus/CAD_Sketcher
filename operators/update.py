import bpy
from bpy.types import Operator
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..converters import update_convertor_geometry
from ..handlers import update_linked_sketches


class VIEW3D_OT_update(Operator):
    bl_idname = "view3d.slvs_update"
    bl_label = "Update"

    def execute(self, context):
        scene = context.scene

        # First pass: solve all sketches so source-sketch entities get correct
        # world positions (e.g. after the user moved a source line point).
        solver = Solver(context, None, all=True)
        solver.solve()

        # Propagate source-line changes into dependent linked sketch
        # workplanes and linked-geometry endpoints.
        update_linked_sketches(scene)

        # Second pass: re-solve all sketches so dependent sketches can
        # recompute their constraints against the now-updated linked geometry.
        solver2 = Solver(context, None, all=True)
        solver2.solve()

        update_convertor_geometry(scene)
        return {"FINISHED"}


register, unregister = register_classes_factory((VIEW3D_OT_update,))
