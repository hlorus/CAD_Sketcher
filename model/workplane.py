import logging
from typing import List

import bpy
import gpu
from mathutils import Vector, Matrix
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..declarations import Operators
from .. import global_data
from ..utilities.draw import draw_rect_2d, safe_batch_for_shader
from ..shaders import Shaders
from ..utilities import preferences
from ..solver import Solver
from ..utilities.index import index_to_rgb
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

        coords_2d = draw_rect_2d(0, 0, self.size, self.size)
        # Convert 2D coords to 3D Vectors (assuming Z=0 in local space)
        coords_3d = [Vector((co[0], co[1], 0.0)) for co in coords_2d]

        indices = ((0, 1), (1, 2), (2, 3), (3, 0))

        # Use safe_batch_for_shader instead
        self._batch = safe_batch_for_shader(
            self._shader, "LINES", {"pos": coords_3d}, indices=indices
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

            shader = Shaders.uniform_color_3d()
            shader.bind()
            gpu.state.blend_set("ALPHA")

            shader.uniform_float("color", col_surface)

            coords_2d = draw_rect_2d(0, 0, self.size, self.size)
            coords_3d = [Vector((co[0], co[1], 0.0)) for co in coords_2d]
            indices = ((0, 1, 2), (0, 2, 3))

            # Use safe_batch_for_shader instead
            batch = safe_batch_for_shader(shader, "TRIS", {"pos": coords_3d}, indices=indices)
            batch.draw(shader)

        self.restore_opengl_defaults()

    def draw_id_face(self, context):
        """Draw only the face of the workplane to the selection buffer"""
        if not self.is_selectable(context):
            return

        shader = self._id_shader
        shader.bind()
        shader.uniform_float("color", (*index_to_rgb(self.slvs_index), 1.0))
        shader.uniform_bool("dashed", (False,))

        with gpu.matrix.push_pop():
            scale = context.region_data.view_distance
            gpu.matrix.multiply_matrix(self.matrix_basis)
            gpu.matrix.scale(Vector((scale, scale, scale)))
            
            # Draw the workplane face with depth testing
            coords_2d = draw_rect_2d(0, 0, self.size, self.size)
            coords_3d = [Vector((co[0], co[1], 0.0)) for co in coords_2d]
            indices = ((0, 1, 2), (0, 2, 3))
            face_batch = safe_batch_for_shader(shader, "TRIS", {"pos": coords_3d}, indices=indices)
            face_batch.draw(shader)
        
        gpu.shader.unbind()

    def draw_id_edges(self, context):
        """Draw only the edges of the workplane to the selection buffer"""
        if not self.is_selectable(context):
            return

        shader = self._id_shader
        shader.bind()
        shader.uniform_float("color", (*index_to_rgb(self.slvs_index), 1.0))
        shader.uniform_bool("dashed", (False,))
        
        # Use thicker lines for better edge selection - increased significantly
        gpu.state.line_width_set(2.0)
        
        # Disable depth testing completely to ensure edges are always drawn
        # regardless of what's in front of them
        gpu.state.depth_test_set('ALWAYS')
        
        with gpu.matrix.push_pop():
            # Apply workplane's transformation
            gpu.matrix.multiply_matrix(self.matrix_basis)
            
            # Apply scale to make it visually the same size
            scale = context.region_data.view_distance
            gpu.matrix.scale(Vector((scale, scale, scale)))
            
            # Create the square edges with precise line geometry
            coords_2d = draw_rect_2d(0, 0, self.size, self.size)
            coords_3d = [Vector((co[0], co[1], 0.0)) for co in coords_2d]
            
            # Draw each edge separately as a thick line
            indices = ((0, 1), (1, 2), (2, 3), (3, 0))
            edge_batch = safe_batch_for_shader(shader, "LINES", {"pos": coords_3d}, indices=indices)
            edge_batch.draw(shader)
        
        # Restore OpenGL state
        gpu.state.line_width_set(1.0)
        gpu.state.depth_test_set('NONE')
        gpu.shader.unbind()

    def draw_id(self, context):
        """Legacy compatibility method - now we use separate face and edge drawing"""
        # Draw both face and edges with the default approach
        self.draw_id_face(context)
        self.draw_id_edges(context)

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        handle = solvesys.addWorkplane(self.p1.py_data, self.nm.py_data, group=group)
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
