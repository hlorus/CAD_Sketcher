import logging
from typing import List

import bpy
import gpu
from mathutils import Vector, Matrix
from bpy.types import PropertyGroup
from gpu_extras.batch import batch_for_shader
from bpy.utils import register_classes_factory

from ..declarations import Operators
from .. import global_data
from ..utilities.draw import draw_rect_2d
from ..utilities.gpu_manager import ShaderManager
from ..shaders import Shaders
from ..utilities import preferences
from ..solver import Solver
from .base_entity import SlvsGenericEntity
from .utilities import slvs_entity_pointer


logger = logging.getLogger(__name__)


class SlvsWorkplane(SlvsGenericEntity, PropertyGroup):
    """Representation of a plane which is defined by an origin point
    and a normal. Workplanes are used to define the position of 2D entities
    which only store the coordinates on the plane.

    Arguments:
        p1 (SlvsPoint3D): Origin Point of the Plane
        nm (SlvsNormal3D): Normal which defines the orientation
    """

    size = 0.4

    def dependencies(self) -> List[SlvsGenericEntity]:
        return [self.p1, self.nm]

    @property
    def size(self):
        return preferences.get_prefs().workplane_size

    def update(self):
        if bpy.app.background:
            return

        p1, nm = self.p1, self.nm

        coords = draw_rect_2d(0, 0, self.size, self.size)
        coords = [(Vector(co))[:] for co in coords]

        indices = ((0, 1), (1, 2), (2, 3), (3, 0))
        self._batch = batch_for_shader(
            self._shader, "LINES", {"pos": coords}, indices=indices
        )
        self.is_dirty = False

    # NOTE: probably better to avoid overwriting draw func..
    def draw(self, context):
        if not self.is_visible(context):
            return

        with gpu.matrix.push_pop():
            scale = context.region_data.view_distance
            gpu.matrix.multiply_matrix(self.matrix_basis)
            gpu.matrix.scale(Vector((scale, scale, scale)))

            col = self.color(context)
            # Let parent draw outline
            super().draw(context)

            # Additionally draw a face
            col_surface = col[:-1] + (0.2,)

            shader = ShaderManager.get_uniform_color_shader()
            shader.bind()
            gpu.state.blend_set("ALPHA")

            shader.uniform_float("color", col_surface)

            coords = draw_rect_2d(0, 0, self.size, self.size)
            coords = [Vector(co)[:] for co in coords]
            indices = ((0, 1, 2), (0, 2, 3))
            batch = batch_for_shader(shader, "TRIS", {"pos": coords}, indices=indices)
            batch.draw(shader)

        self.restore_opengl_defaults()

    def draw_id(self, context):
        with gpu.matrix.push_pop():
            scale = context.region_data.view_distance
            gpu.matrix.multiply_matrix(self.matrix_basis)
            gpu.matrix.scale(Vector((scale, scale, scale)))

            # Draw both the outline (lines) and the surface (triangles) for selection
            # This makes the entire plane selectable, not just the edges
            super().draw_id(context)

            # Draw workplane surface both behind and slightly in front of outline
            # This creates maximum selectability while preserving outline visibility
            shader = self._id_shader
            shader.bind()

            from ..utilities.index import index_to_rgb
            shader.uniform_float("color", (*index_to_rgb(self.slvs_index), 1.0))

            coords = draw_rect_2d(0, 0, self.size, self.size)

            # Draw surface behind outline (for areas not covered by outline)
            coords_behind = [(co[0], co[1], co[2] - 0.0001) for co in coords]
            indices = ((0, 1, 2), (0, 2, 3))
            batch_behind = batch_for_shader(shader, "TRIS", {"pos": coords_behind}, indices=indices)
            batch_behind.draw(shader)

            # Draw surface slightly in front of outline (for better selection area)
            coords_front = [(co[0], co[1], co[2] + 0.0001) for co in coords]
            batch_front = batch_for_shader(shader, "TRIS", {"pos": coords_front}, indices=indices)
            batch_front.draw(shader)

            gpu.shader.unbind()
            self.restore_opengl_defaults()

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        handle = solvesys.add_workplane(group, self.p1.py_data, self.nm.py_data)
        self.py_data = handle

    @property
    def matrix_basis(self):
        mat_rot = self.nm.orientation.to_matrix().to_4x4()
        return Matrix.Translation(self.p1.location) @ mat_rot

    @property
    def normal(self):
        v = global_data.Z_AXIS.copy()
        quat = self.nm.orientation
        v.rotate(quat)
        return v

    def draw_props(self, layout):
        # Display the normals props as they're not drawn in the viewport
        sub = self.nm.draw_props(layout)
        sub.operator(Operators.AlignWorkplaneCursor).index = self.slvs_index
        return sub


slvs_entity_pointer(SlvsWorkplane, "p1")
slvs_entity_pointer(SlvsWorkplane, "nm")

register, unregister = register_classes_factory((SlvsWorkplane,))
