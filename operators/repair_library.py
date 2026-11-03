"""Make this file safe to link from: flag its bodies so overrides keep their links."""

from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators
from ..utilities.library_refs import (
    cached_state,
    repair_blocker,
    repair_bodies,
)


def repaired_message(count: int) -> str:
    noun = "link" if count == 1 else "links"
    return f"Repaired {count} {noun}. Save this file now."


def failed_message(remaining: int) -> str:
    noun = "object" if remaining == 1 else "objects"
    return f"{remaining} {noun} could not be repaired."


class View3D_OT_slvs_repair_library(Operator):
    """Mark this file's bodies so overrides of them keep their sketch links

    Run it in the library file itself, then save that file and reload the files
    that link it. It changes only this file's own bodies, in memory, and does
    not save."""

    bl_idname = Operators.RepairLibrary
    bl_label = "Repair Library File"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: Context):
        return bool(cached_state().repairable)

    def execute(self, context: Context):
        blocker = repair_blocker()
        if blocker:
            self.report({"WARNING"}, blocker)
            return {"CANCELLED"}
        count = repair_bodies()
        remaining = cached_state().repairable
        if not count:
            self.report({"WARNING"}, failed_message(remaining))
        elif remaining:
            self.report(
                {"WARNING"}, f"{repaired_message(count)} {failed_message(remaining)}"
            )
        else:
            self.report({"INFO"}, repaired_message(count))
        return {"FINISHED"} if count else {"CANCELLED"}


register, unregister = register_classes_factory((View3D_OT_slvs_repair_library,))
