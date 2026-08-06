from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector

from ..declarations import GizmoGroups, Gizmos
from ..drawing import picking, selection
from ..drawing.snap import draw_snap_marker
from ..utilities.view import get_blender_snap_info
from .utilities import context_mode_check


class VIEW3D_GGT_slvs_preselection(GizmoGroup):
    bl_idname = GizmoGroups.Preselection
    bl_label = "preselection ggt"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    # NOTE: it would be great to expose the hovered entity as a gizmogroup prop
    # rather than using global variables...

    @classmethod
    def poll(cls, context):
        return context_mode_check(context, cls.bl_idname)

    def setup(self, context):
        self.gizmo = self.gizmos.new(VIEW3D_GT_slvs_preselection.bl_idname)


# NOTE: idealy gizmo would expose active element as a property and
# operators would access hovered element from there
class VIEW3D_GT_slvs_preselection(Gizmo):
    bl_idname = Gizmos.Preselection

    # ``_snap``: current geometry snap target (dict or None); ``_snap_key``: a
    # cheap comparison key so we only redraw when the snap actually changes.
    __slots__ = ("_snap", "_snap_key")

    def draw(self, context):
        # Same marker the draw operator uses; shown while the tool is idle.
        draw_snap_marker(self, context)

    def test_select(self, context, location):
        # reset gizmo highlight
        if selection.highlight_constraint:
            selection.highlight_constraint = None
            context.area.tag_redraw()

        if selection.highlight_entities:
            selection.highlight_entities.clear()
            context.area.tag_redraw()

        if selection.highlight_curve_ids:
            selection.highlight_curve_ids = []
            context.area.tag_redraw()

        # CPU screen-space pick of the active sketch's geometry under the cursor.
        cid = picking.pick(context, location)
        if cid != selection.hover:
            selection.hover = cid
            context.area.tag_redraw()

        # Snap to external geometry, mirroring the operator's live snapping, and
        # redraw only when the snapped point/type changes.
        snap = get_blender_snap_info(context, Vector(location))
        key = (snap.get("type"), tuple(snap["world_point"])) if snap else None
        if key != getattr(self, "_snap_key", None):
            self._snap = snap
            self._snap_key = key
            context.area.tag_redraw()
        return -1