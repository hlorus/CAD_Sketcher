# pyright: reportInvalidTypeForm=false
import logging
import gpu
from typing import List
from math import cos, sin, pi

import bpy
from bpy.types import PropertyGroup, Context
from bpy.props import FloatVectorProperty
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from bpy.utils import register_classes_factory

from ..utilities.draw import draw_rect_2d
from ..declarations import WorkSpaceTools
from ..solver import Solver
from .base_entity import SlvsGenericEntity, Entity2D, _entity_dirty_update
from .utilities import slvs_entity_pointer, make_coincident
from .line_2d import SlvsLine2D
from ..utilities.constants import HALF_TURN
from ..utilities.preferences import get_prefs
from ..utilities import preferences
from ..shaders import Shaders

logger = logging.getLogger(__name__)


class Point2D(Entity2D):
    @classmethod
    def is_point(cls):
        return True

    def _is_selected_line_origin(self, context: Context) -> bool:
        """True when this point is p1 of a selected line in select tool mode."""
        workspace = getattr(context, "workspace", None)
        if workspace is None:
            return False

        tool = workspace.tools.from_space_view3d_mode(context.mode)
        if tool is None or tool.idname != WorkSpaceTools.Select:
            return False

        sketch = context.scene.sketcher.active_sketch
        if sketch is None:
            return False

        sse = context.scene.sketcher.entities
        for entity in sse.selected_active:
            if not isinstance(entity, SlvsLine2D):
                continue
            if entity.sketch != sketch:
                continue
            if entity.p1.slvs_index == self.slvs_index:
                return True
        return False

    def _linked_line_origin_state(self, context: Context):
        """Return linked-Y inversion state when this point is origin of a linking line.

        Returns:
            `True` when Y is inverted,
            `False` when Y is normal,
            `None` when this point is not a linking-line origin.
        """
        sketch = context.scene.sketcher.active_sketch
        if sketch is None:
            return None

        sse = context.scene.sketcher.entities
        for line in sse.lines2D:
            if line.sketch != sketch:
                continue
            if line.p1.slvs_index != self.slvs_index:
                continue

            for linked_sketch in sse.sketches:
                if getattr(linked_sketch, "source_line_i", -1) == line.slvs_index:
                    return bool(getattr(linked_sketch, "linked_y_inverted", False))
        return None

    def _draw_linked_origin_marker(self, context: Context, inverted: bool):
        col = get_prefs().theme_settings.linked_geometry.linking
        center = self.location

        wp_mat = self.wp.matrix_basis
        x_axis = wp_mat.col[0].to_3d().normalized()
        y_axis = wp_mat.col[1].to_3d().normalized()

        radius = 0.06 * preferences.get_scale()
        if radius <= 0.0:
            radius = 0.06

        circle_steps = 24
        circle_coords = []
        for i in range(circle_steps + 1):
            a = (2.0 * pi * i) / circle_steps
            p = center + (cos(a) * radius) * x_axis + (sin(a) * radius) * y_axis
            circle_coords.append(p[:])

        shader_line = Shaders.polyline_color_3d()
        shader_line.bind()
        shader_line.uniform_float("color", col)
        if bpy.app.version >= (4, 5):
            shader_line.uniform_float("lineWidth", self.line_width)
            shader_line.uniform_float(
                "viewportSize", (context.region.width, context.region.height)
            )
        gpu.state.blend_set("ALPHA")
        gpu.state.line_width_set(self.line_width)

        circle_batch = batch_for_shader(
            shader_line,
            "LINE_STRIP",
            {"pos": circle_coords},
        )
        circle_batch.draw(shader_line)

        if inverted:
            d = radius * 0.6
            x_coords = (
                (center + (x_axis + y_axis) * d)[:],
                (center - (x_axis + y_axis) * d)[:],
                (center + (x_axis - y_axis) * d)[:],
                (center - (x_axis - y_axis) * d)[:],
            )
            x_batch = batch_for_shader(
                shader_line,
                "LINES",
                {"pos": x_coords},
            )
            x_batch.draw(shader_line)
        else:
            shader_point = Shaders.point_color_3d()
            shader_point.bind()
            shader_point.uniform_float("color", col)
            gpu.state.point_size_set(max(1.0, self.point_size * 0.55))
            dot_batch = batch_for_shader(
                shader_point,
                "POINTS",
                {"pos": (center[:],)},
            )
            dot_batch.draw(shader_point)

        gpu.shader.unbind()
        self.restore_opengl_defaults()

    def update(self):
        if bpy.app.background:
            return

        u, v = self.co
        mat_local = Matrix.Translation(Vector((u, v, 0)))

        mat = self.wp.matrix_basis @ mat_local
        size = 0.1
        coords = draw_rect_2d(0, 0, size, size)
        coords = [(mat @ Vector(co))[:] for co in coords]
        indices = ((0, 1, 2), (0, 2, 3))
        pos = self.location
        self._batch = batch_for_shader(self._shader, "POINTS", {"pos": (pos[:],)})
        self.is_dirty = False

    @property
    def location(self):
        u, v = self.co
        mat_local = Matrix.Translation(Vector((u, v, 0)))
        mat = self.wp.matrix_basis @ mat_local
        return mat @ Vector((0, 0, 0))

    def placement(self):
        return self.location

    def create_slvs_data(self, solvesys, coords=None, group=Solver.group_fixed):
        if not coords:
            coords = self.co

        handle = solvesys.add_point_2d(group, *coords, self.wp.py_data)
        self.py_data = handle

    def update_from_slvs(self, solvesys):
        coords = [solvesys.get_param_value(self.py_data["param"][i]) for i in range(2)]
        self.co = coords

    def closest_picking_point(self, origin, view_vector):
        """Returns the point on this entity which is closest to the picking ray"""
        return self.location

    @property
    def point_size(self):
        state = self._linked_line_origin_state(bpy.context)
        if state is not None:
            return 1.2 * super().point_size
        if self._is_selected_line_origin(bpy.context):
            return 1.1 * super().point_size
        return super().point_size

    def color(self, context: Context):
        state = self._linked_line_origin_state(context)
        if state is not None:
            return get_prefs().theme_settings.linked_geometry.linking
        if self._is_selected_line_origin(context):
            return get_prefs().theme_settings.entity.line_origin
        return super().color(context)

    def draw(self, context):
        state = self._linked_line_origin_state(context)
        if state is not None:
            if not self.is_visible(context):
                return
            self._draw_linked_origin_marker(context, state)
            return
        super().draw(context)


class SlvsPoint2D(Point2D, PropertyGroup):
    """Representation of a point in 2D space.

    Arguments:
        co (FloatVectorProperty): The coordinates of the point on the worpkplane in the form (U, V)
        sketch (SlvsSketch): The sketch this entity belongs to
    """

    co: FloatVectorProperty(
        name="Coordinates",
        description="The coordinates of the point on its sketch",
        subtype="XYZ",
        size=2,
        unit="LENGTH",
        update=_entity_dirty_update,
    )
    props = ("co",)

    def dependencies(self) -> List[SlvsGenericEntity]:
        return [
            self.sketch,
        ]

    def draw_props(self, layout):
        sub = super().draw_props(layout)
        sub.prop(self, "co")
        return sub


slvs_entity_pointer(Point2D, "sketch")

register, unregister = register_classes_factory((SlvsPoint2D,))
