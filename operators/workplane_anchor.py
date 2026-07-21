"""Recovery operators for detached face-anchored workplanes."""

import logging

import bpy
from bpy.props import StringProperty
from bpy.types import Context, Event, Operator
from bpy.utils import register_classes_factory
from mathutils import Vector

from ..declarations import Operators
from ..stateful_operator.utilities.geometry import get_mesh_element

logger = logging.getLogger(__name__)


class View3D_OT_slvs_make_workplane_free(Operator):
    """Detach this workplane from its mesh face and keep it where it is"""

    bl_idname = Operators.MakeWorkplaneFree
    bl_label = "Make Workplane Free"
    bl_options = {"UNDO"}

    empty_name: StringProperty()

    def execute(self, context: Context):
        from ..utilities.face_anchor import clear_anchor

        empty = bpy.data.objects.get(self.empty_name)
        if empty is None:
            self.report({"WARNING"}, "Workplane not found")
            return {"CANCELLED"}
        clear_anchor(empty)
        self.report({"INFO"}, "Workplane is now free")
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class View3D_OT_slvs_reattach_workplane(Operator):
    """Click a mesh face to re-anchor this workplane to it"""

    bl_idname = Operators.ReattachWorkplane
    bl_label = "Re-attach Workplane to Face"
    bl_options = {"UNDO"}

    empty_name: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def invoke(self, context: Context, event: Event):
        self._empty = bpy.data.objects.get(self.empty_name)
        if self._empty is None:
            self.report({"WARNING"}, "Workplane not found")
            return {"CANCELLED"}
        context.window.cursor_modal_set("EYEDROPPER")
        context.workspace.status_text_set(
            "Click a mesh face to re-anchor the workplane   |   Esc/RMB: cancel"
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _end(self, context: Context):
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)

    def modal(self, context: Context, event: Event):
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            self._end(context)
            return {"CANCELLED"}

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            from ..utilities.geometry import face_workplane_matrix
            from ..utilities.face_anchor import stamp_face_anchor

            coords = Vector((event.mouse_region_x, event.mouse_region_y))
            ob, elem_type, index = get_mesh_element(context, coords, face=True)
            if ob and elem_type == "FACE":
                self._empty.matrix_world = face_workplane_matrix(context, ob, index)
                stamp_face_anchor(self._empty, ob, index)
                self._end(context)
                self.report({"INFO"}, "Workplane re-attached")
                if context.area:
                    context.area.tag_redraw()
                return {"FINISHED"}
            # Missed a face — keep waiting.
            return {"RUNNING_MODAL"}

        return {"PASS_THROUGH"}


register, unregister = register_classes_factory(
    (View3D_OT_slvs_make_workplane_free, View3D_OT_slvs_reattach_workplane)
)
