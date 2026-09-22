"""Operators to move a sketch to another workplane and manage face anchors."""

import logging

import bpy
from bpy.props import StringProperty
from bpy.types import Context, Event, Operator, SpaceView3D
from bpy.utils import register_classes_factory
from mathutils import Vector

from ..declarations import Operators
from ..stateful_operator.utilities.geometry import get_mesh_element

logger = logging.getLogger(__name__)


class View3D_OT_slvs_make_workplane_free(Operator):
    """Stop the workplane following its mesh face and keep it where it is. Other sketches on the same workplane stay anchored"""

    bl_idname = Operators.MakeWorkplaneFree
    bl_label = "Make Workplane Free"
    bl_options = {"UNDO"}

    empty_name: StringProperty()
    sketch_name: StringProperty(
        description="Free the workplane for this sketch only (takes precedence)"
    )

    def execute(self, context: Context):
        from ..utilities.face_anchor import clear_anchor
        from .add_sketch import free_sketch_workplane

        sketch_obj = (
            bpy.data.objects.get(self.sketch_name) if self.sketch_name else None
        )
        from .add_sketch import _sketch_workplane

        if sketch_obj is not None and _sketch_workplane(sketch_obj) is not None:
            free_sketch_workplane(context, sketch_obj)
        else:
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
    """Click a mesh face to anchor this workplane to it, replacing any current anchor. Moves every sketch on the workplane"""

    bl_idname = Operators.ReattachWorkplane
    bl_label = "Anchor Workplane to Face"
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
        from ..utilities.face_anchor import is_origin_workplane

        # The origin planes are shared by every scene-level sketch and forced
        # back to their fixed transform, so they can never follow a face.
        if is_origin_workplane(context.scene, self._empty):
            self.report({"WARNING"}, "Origin workplanes can't be anchored")
            return {"CANCELLED"}
        context.window.cursor_modal_set("EYEDROPPER")
        context.workspace.status_text_set(
            "Click a mesh face to anchor the workplane   |   Esc/RMB: cancel"
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
            from ..stateful_operator.utilities.geometry import get_evaluated_obj
            from ..utilities.face_anchor import (
                can_anchor_face,
                clear_anchor,
                stamp_face_anchor,
            )
            from ..utilities.geometry import face_workplane_matrix

            coords = Vector((event.mouse_region_x, event.mouse_region_y))
            ob, elem_type, index = get_mesh_element(context, coords, face=True)
            if ob and elem_type == "FACE":
                if not can_anchor_face(ob, get_evaluated_obj(context, ob)):
                    self.report(
                        {"WARNING"},
                        "Can't anchor to a mesh whose modifiers change its faces",
                    )
                    return {"RUNNING_MODAL"}
                # Drop the previous anchor first so its face id doesn't linger on
                # the old mesh.
                clear_anchor(self._empty)
                self._empty.matrix_world = face_workplane_matrix(context, ob, index)
                stamp_face_anchor(self._empty, ob, index)
                self._end(context)
                self.report({"INFO"}, "Workplane anchored to " + ob.name)
                if context.area:
                    context.area.tag_redraw()
                return {"FINISHED"}
            # Missed a face — keep waiting.
            return {"RUNNING_MODAL"}

        return {"PASS_THROUGH"}


# Key -> origin plane, by the axis normal to it (same as the Add Sketch tool).
_ORIGIN_PLANE_KEYS = {"Z": "wp_xy", "Y": "wp_xz", "X": "wp_yz"}


class View3D_OT_slvs_change_sketch_workplane(Operator):
    """Pick a workplane or mesh face to move the active sketch onto. The sketch keeps its geometry and constraints"""

    bl_idname = Operators.ChangeSketchWorkplane
    bl_label = "Change Sketch Workplane"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        from ..model.sketch_ref import get_active_sketch

        if context.area is None or context.area.type != "VIEW_3D":
            return False
        sketch = get_active_sketch(context)
        return sketch is not None and not sketch.is_3d

    def invoke(self, context: Context, event: Event):
        from ..utilities.workplane import ensure_origin_workplane_empties

        ensure_origin_workplane_empties(context)
        self._hover, self._preview = "", None
        # The Add Sketch gizmo only exists while its tool is active, which isn't
        # available in sketch mode, so draw the same picker from here.
        self._draw_handle = SpaceView3D.draw_handler_add(
            self._draw, (), "WINDOW", "POST_VIEW"
        )
        context.window.cursor_modal_set("EYEDROPPER")
        context.workspace.status_text_set(
            "Pick a workplane or mesh face   |   X/Y/Z: origin plane   |   "
            "Esc/RMB: cancel"
        )
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _draw(self):
        from ..gizmos.workplane import draw_workplane_picker

        draw_workplane_picker(bpy.context, self._hover, self._preview)

    def _end(self, context: Context):
        SpaceView3D.draw_handler_remove(self._draw_handle, "WINDOW")
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        context.area.tag_redraw()

    def _pick(self, context: Context, event: Event):
        """Move the sketch to what a click resolves to; None if it hit nothing."""
        from ..model.sketch_ref import get_active_sketch
        from ..utilities.workplane import resolve_sketch_base
        from .add_sketch import move_sketch_to_face, set_sketch_workplane

        coords = Vector((event.mouse_region_x, event.mouse_region_y))
        kind, a, b = resolve_sketch_base(context, coords)
        sketch_obj = get_active_sketch(context).target_object
        if kind in ("border", "interior"):
            return self._finish(context, set_sketch_workplane(context, sketch_obj, b))
        if kind == "mesh":
            move_sketch_to_face(context, sketch_obj, a, b)
            return self._finish(context, True)
        return None

    def _finish(self, context: Context, moved: bool):
        from ..utilities.preferences import get_prefs

        self._end(context)
        if not moved:
            self.report({"INFO"}, "Sketch is already on this workplane")
            return {"CANCELLED"}
        if get_prefs().use_align_view:
            bpy.ops.view3d.slvs_align_view(use_active=True)
        return {"FINISHED"}

    def modal(self, context: Context, event: Event):
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            self._end(context)
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE":
            from ..gizmos.workplane import resolve_picker_hover

            state = resolve_picker_hover(
                context, (event.mouse_region_x, event.mouse_region_y)
            )
            if state != (self._hover, self._preview):
                self._hover, self._preview = state
                context.area.tag_redraw()
            return {"PASS_THROUGH"}

        if event.value == "PRESS" and event.type in _ORIGIN_PLANE_KEYS:
            from ..model.sketch_ref import get_active_sketch
            from .add_sketch import set_sketch_workplane

            empty = getattr(context.scene.sketcher, _ORIGIN_PLANE_KEYS[event.type])
            if empty is None:
                return {"RUNNING_MODAL"}
            sketch_obj = get_active_sketch(context).target_object
            return self._finish(
                context, set_sketch_workplane(context, sketch_obj, empty)
            )

        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            result = self._pick(context, event)
            # None: the click hit nothing, keep waiting.
            return {"RUNNING_MODAL"} if result is None else result

        return {"PASS_THROUGH"}


register, unregister = register_classes_factory(
    (
        View3D_OT_slvs_make_workplane_free,
        View3D_OT_slvs_reattach_workplane,
        View3D_OT_slvs_change_sketch_workplane,
    )
)
