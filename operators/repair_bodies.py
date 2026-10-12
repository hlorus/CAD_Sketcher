"""Rebuild the Convert setup of bodies whose modifier was removed."""

from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.body import broken_bodies, repair_body


class View3D_OT_slvs_repair_bodies(Operator):
    """Put back the Convert modifier on bodies that are missing it

    A body builds its geometry from its sketch through that modifier. Deleting
    it by hand leaves the sketch intact and the body empty, and nothing restores
    it on its own."""

    bl_idname = Operators.RepairBodies
    bl_label = "Repair Sketch Bodies"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Context):
        return bool(broken_bodies(context.scene))

    def execute(self, context: Context):
        repaired = [
            body.name
            for body in broken_bodies(context.scene)
            if repair_body(context, body)
        ]
        if not repaired:
            self.report({"WARNING"}, "Could not repair any body")
            return {"CANCELLED"}
        context.view_layer.update()
        self.report({"INFO"}, f"Repaired {len(repaired)} body/bodies")
        return {"FINISHED"}


register, unregister = register_classes_factory((View3D_OT_slvs_repair_bodies,))
