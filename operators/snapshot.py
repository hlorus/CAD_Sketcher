import bpy
from bpy.types import Operator, Context
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..serialize import scene_to_dict, scene_from_dict

# Buffer to store snapshot data
_snapshot_buffer = None


class View3D_OT_slvs_snapshot(Operator):
    """Take a snapshot of the current CAD Sketcher data"""

    bl_idname = Operators.Snapshot
    bl_label = "Snapshot"
    bl_options = {"UNDO"}

    def execute(self, context: Context):
        global _snapshot_buffer
        _snapshot_buffer = scene_to_dict(context.scene)
        self.report({"INFO"}, "Snapshot taken")
        return {"FINISHED"}


class View3D_OT_slvs_restore(Operator):
    """Restore CAD Sketcher data from snapshot"""

    bl_idname = Operators.Restore
    bl_label = "Restore"
    bl_options = {"UNDO"}

    def execute(self, context: Context):
        global _snapshot_buffer
        if _snapshot_buffer is None:
            self.report({"WARNING"}, "No snapshot available")
            return {"CANCELLED"}

        scene_from_dict(context.scene, _snapshot_buffer)
        context.area.tag_redraw()
        self.report({"INFO"}, "Snapshot restored")
        return {"FINISHED"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_snapshot, View3D_OT_slvs_restore)
)
