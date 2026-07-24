import bpy
import gpu
from bpy import app
from bpy.types import Gizmo, GizmoGroup
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .. import global_data
from ..declarations import GizmoGroups, Gizmos
from ..shaders import Shaders
from ..utilities import preferences
from ..utilities.geometry import face_bounds_in_plane, face_workplane_matrix
from ..utilities.preferences import get_prefs
from ..utilities.workplane import (
    WP_ID_XY,
    WP_ID_XZ,
    WP_ID_YZ,
    iter_wp_empties,
    resolve_sketch_base,
    wp_plane_bounds,
)
from .utilities import context_mode_check


# Blender-style axis colors used to tint the origin planes by their normal
# (XY -> Z/blue, XZ -> Y/green, YZ -> X/red).
_AXIS_X = (0.80, 0.24, 0.24)
_AXIS_Y = (0.34, 0.67, 0.20)
_AXIS_Z = (0.22, 0.40, 0.80)
_ORIGIN_AXIS_COLOR = {
    WP_ID_XY: _AXIS_Z,
    WP_ID_XZ: _AXIS_Y,
    WP_ID_YZ: _AXIS_X,
}


class VIEW3D_GGT_slvs_workplane(GizmoGroup):
    """Draws and hover-picks workplane empties while the owning tool is active.

    Bound to a tool via ``bl_widget``; visible whenever that tool is selected so
    the user sees the available sketch bases without invoking an operator.
    """

    bl_idname = GizmoGroups.Workplane
    bl_label = "Workplane Gizmo Group"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D"}

    @classmethod
    def poll(cls, context):
        return context_mode_check(context, cls.bl_idname)

    def setup(self, context):
        self.gizmo = self.gizmos.new(VIEW3D_GT_slvs_workplane.bl_idname)


class VIEW3D_GT_slvs_workplane(Gizmo):
    """Single gizmo that renders all workplane rectangles and tracks hover.

    ``test_select`` never claims the click (returns -1) — like the preselection
    gizmo it only publishes the hovered empty via ``global_data.hover`` so the
    Add Sketch operator's ``pick_element`` can resolve it. This keeps the
    operator's state machine and its mesh-face fallback intact.

    When the cursor is over a mesh face (which would create a new face-aligned
    workplane), that plane is previewed via ``mesh_preview`` = (object_name,
    face_index).
    """

    bl_idname = Gizmos.Workplane

    # Margin added around a hovered face's bounding box, as a fraction of its
    # larger side, when previewing the workplane it would create.
    FACE_PREVIEW_MARGIN = 0.15

    __slots__ = ("mesh_preview",)

    def _plane_color(self, pick_id, is_hovered, ts):
        """Fill/outline color for a workplane rectangle.

        Origin planes are tinted by their normal axis; other planes keep the
        themed default/highlight look.
        """
        axis = _ORIGIN_AXIS_COLOR.get(pick_id)
        if axis is None:
            return tuple(ts.highlight) if is_hovered else (*ts.default[:3], 0.3)
        if is_hovered:
            # Brighten the axis tint toward white and raise opacity.
            return tuple(c + (1.0 - c) * 0.4 for c in axis) + (0.6,)
        return (*axis, 0.3)

    def _draw_rect(self, context, mat, bounds, scale, col, is_hovered):
        """Draw a workplane rectangle (outline + translucent fill).

        ``bounds`` is (min_x, min_y, max_x, max_y) in the plane's local frame.
        """
        min_x, min_y, max_x, max_y = bounds
        corners = [
            mat @ Vector((min_x, min_y, 0)),
            mat @ Vector((max_x, min_y, 0)),
            mat @ Vector((max_x, max_y, 0)),
            mat @ Vector((min_x, max_y, 0)),
        ]

        line_shader = Shaders.polyline_color_3d()
        fill_shader = Shaders.uniform_color_3d()

        # Outline
        lines = []
        for i in range(4):
            lines.append(corners[i][:])
            lines.append(corners[(i + 1) % 4][:])

        line_shader.bind()
        gpu.state.blend_set("ALPHA")
        line_width = (3 if is_hovered else 1.5) * scale
        gpu.state.line_width_set(line_width)
        line_shader.uniform_float("color", col)
        if app.version >= (4, 5):
            line_shader.uniform_float("lineWidth", line_width)
            line_shader.uniform_float(
                "viewportSize", (context.region.width, context.region.height)
            )
        batch = batch_for_shader(line_shader, "LINES", {"pos": lines})
        batch.draw(line_shader)
        gpu.shader.unbind()
        gpu.state.line_width_set(1)

        # Filled face
        col_surface = col[:3] + (0.2,)
        fill_shader.bind()
        fill_shader.uniform_float("color", col_surface)
        verts = [c[:] for c in corners]
        batch = batch_for_shader(
            fill_shader, "TRIS", {"pos": verts}, indices=((0, 1, 2), (0, 2, 3))
        )
        batch.draw(fill_shader)
        gpu.shader.unbind()

        gpu.state.blend_set("NONE")

    def draw(self, context):
        scale = preferences.get_scale()
        ts = get_prefs().theme_settings.entity

        for wp_obj, pick_id in iter_wp_empties(context):
            is_hovered = global_data.hover == pick_id
            col = self._plane_color(pick_id, is_hovered, ts)
            bounds = wp_plane_bounds(context, pick_id)
            self._draw_rect(context, wp_obj.matrix_world, bounds, scale, col, is_hovered)

        # Preview the workplane a hovered mesh face would create, sized to the
        # face's bounding box plus a margin.
        preview = getattr(self, "mesh_preview", None)
        if preview:
            ob = bpy.data.objects.get(preview[0])
            if ob is not None:
                try:
                    mat = face_workplane_matrix(context, ob, preview[1])
                    bounds = face_bounds_in_plane(context, ob, preview[1], mat)
                except (IndexError, AttributeError):
                    bounds = None
                if bounds is not None:
                    min_x, min_y, max_x, max_y = bounds
                    margin = max(max_x - min_x, max_y - min_y) * self.FACE_PREVIEW_MARGIN
                    bounds = (min_x - margin, min_y - margin,
                              max_x + margin, max_y + margin)
                    self._draw_rect(context, mat, bounds, scale, ts.highlight, True)

    def test_select(self, context, location):
        # Mirror the operator's pick priority (border > mesh > interior) so the
        # feedback always matches what a click would create.
        kind, a, b = resolve_sketch_base(context, Vector(location))
        if kind in ("border", "interior"):
            new_hover, preview = a, None  # a = workplane pick id
        elif kind == "mesh":
            new_hover, preview = "", (a.name, b)  # a = object, b = face index
        else:
            new_hover, preview = "", None

        changed = False
        if new_hover != global_data.hover:
            global_data.hover = new_hover
            changed = True
        if preview != getattr(self, "mesh_preview", None):
            self.mesh_preview = preview
            changed = True
        if changed:
            context.area.tag_redraw()

        # Never claim the click: fall through to the tool keymap / operator.
        return -1
