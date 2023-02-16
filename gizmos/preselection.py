import gpu
from bpy.types import Gizmo, GizmoGroup

from .. import global_data
from ..declarations import Gizmos, GizmoGroups
from ..draw_handler import ensure_selection_texture
from ..utilities.index import rgb_to_index
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
        if global_data.highlight_constraint:
            global_data.highlight_constraint = None
            context.area.tag_redraw()

        if global_data.highlight_entities:
            global_data.highlight_entities.clear()
            context.area.tag_redraw()

        # ensure selection texture is up to date
        # TODO: avoid dependency on operators module?
        ensure_selection_texture(context)

        # sample selection texture and mark hovered entity
        mouse_x, mouse_y = location

        offscreen = global_data.offscreen
        if not offscreen:
            return -1
        with offscreen.bind():
            fb = gpu.state.active_framebuffer_get()
            buffer = fb.read_color(mouse_x, mouse_y, 1, 1, 4, 0, "FLOAT")
        r, g, b, alpha = buffer[0][0]

        if alpha > 0:
            index = rgb_to_index(r, g, b)
            if index != global_data.hover:
                global_data.hover = index
                context.area.tag_redraw()
        elif global_data.hover != -1:
            context.area.tag_redraw()
            global_data.hover = -1
        return -1
