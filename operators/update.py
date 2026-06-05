import bpy
from bpy.types import Operator
from bpy.utils import register_classes_factory

from ..solver import Solver
from ..converters import update_convertor_geometry
from ..handlers import update_linked_sketches
from ..utilities.reference_geometry import refresh_reference_geometry


class VIEW3D_OT_update(Operator):
    bl_idname = "view3d.slvs_update"
    bl_label = "Update"

    @staticmethod
    def _refresh_all_reference_geometry(context, scene) -> bool:
        refs_changed = False
        for sketch in scene.sketcher.entities.sketches:
            refs_changed = (
                refresh_reference_geometry(context, sketch=sketch) or refs_changed
            )
        return refs_changed

    def execute(self, context):
        scene = context.scene

        # First pass: solve all sketches so source-sketch entities get correct
        # world positions (e.g. after the user moved a source line point).
        solver = Solver(context, None, all=True)
        solver.solve()

        # Propagate source-line changes into dependent linked sketch
        # workplanes and linked-geometry endpoints.
        linked_changed = update_linked_sketches(scene)

        # Refresh TAG-driven reference geometry before the second solve.
        refs_changed = self._refresh_all_reference_geometry(context, scene)

        # Second pass: re-solve all sketches so dependent sketches can
        # recompute their constraints against the now-updated linked geometry.
        solver2 = Solver(context, None, all=True)
        solver2.solve()

        # Final pass: source geometry may still move in the second solve.
        # Refresh references again and solve once more when needed.
        refs_changed_final = self._refresh_all_reference_geometry(context, scene)
        if refs_changed_final:
            solver3 = Solver(context, None, all=True)
            solver3.solve()

        if refs_changed or refs_changed_final or linked_changed:
            print("[CAD_Sketcher] slvs_update: linked/reference geometry refreshed")

        update_convertor_geometry(scene)
        return {"FINISHED"}


register, unregister = register_classes_factory((VIEW3D_OT_update,))
