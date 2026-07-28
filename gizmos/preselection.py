from bpy.types import Gizmo, GizmoGroup

from ..drawing import selection
from ..declarations import Gizmos, GizmoGroups
from ..drawing import picking
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

    __slots__ = ()

    def draw(self, context):
        pass

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
        return -1