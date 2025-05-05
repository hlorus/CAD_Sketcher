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
from ..utilities.index import index_to_rgb
from .base_entity import SlvsGenericEntity
from .utilities import slvs_entity_pointer
from ..base.constants import DEFAULT_WORKPLANE_SIZE, SOLVER_GROUP_FIXED
from .constants import WORKPLANE_EDGE_LINE_WIDTH
from ..global_data import Z_AXIS

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
        prefs = preferences.get_prefs()
        # Return the default size if preferences are not available yet
        return prefs.workplane_size if prefs else DEFAULT_WORKPLANE_SIZE

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

    def draw_id_face(self, context, shader):
        """Draw only the face of the workplane to the selection buffer"""
        # Selectability check removed, handled by caller (draw_selection_buffer)
        # if not self.is_selectable(context):
        #     return

        batch = self._batch # Assuming face uses the same batch for ID
        if not batch:
            logger.debug(f"draw_id_face({self.slvs_index}): No batch found.")
            return

        logger.debug(f"draw_id_face({self.slvs_index}): Drawing with shader {shader.name}")
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
            # Recreate batch specifically for face geometry if needed
            face_batch = safe_batch_for_shader(shader, "TRIS", {"pos": coords_3d}, indices=indices)
            if face_batch:
                face_batch.draw(shader)
                logger.debug(f"draw_id_face({self.slvs_index}): Face batch drawn.")
            else:
                logger.debug(f"draw_id_face({self.slvs_index}): Failed to create face batch.")

    def draw_id_edges(self, context, shader):
        """Draw only the edges of the workplane to the selection buffer"""
        # Selectability check removed, handled by caller (draw_selection_buffer)
        # if not self.is_selectable(context):
        #     return

        batch = self._batch
        if not batch:
             logger.debug(f"draw_id_edges({self.slvs_index}): No batch found.")
             return
             
        logger.debug(f"draw_id_edges({self.slvs_index}): Drawing with shader {shader.name}")
        shader.uniform_float("color", (*index_to_rgb(self.slvs_index), 1.0))
        shader.uniform_bool("dashed", (False,))
        
        # Use thick lines for selection
        gpu.state.line_width_set(self.line_width_select)
        
        with gpu.matrix.push_pop():
            # Apply workplane's transformation
            gpu.matrix.multiply_matrix(self.matrix_basis)
            
            # Apply scale to make it visually the same size
            scale = context.region_data.view_distance
            gpu.matrix.scale(Vector((scale, scale, scale)))
            
            # Create the square edges
            coords_2d = draw_rect_2d(0, 0, self.size, self.size)
            coords_3d = [Vector((co[0], co[1], 0.0)) for co in coords_2d]
            indices = ((0, 1), (1, 2), (2, 3), (3, 0))
            
            # Use the main batch for edges
            edge_batch = safe_batch_for_shader(shader, "LINES", {"pos": coords_3d}, indices=indices)
            if edge_batch:
                edge_batch.draw(shader)
                logger.debug(f"draw_id_edges({self.slvs_index}): Edge batch drawn.")
            else:
                 logger.debug(f"draw_id_edges({self.slvs_index}): Failed to create edge batch.")
        
        # Restore line width
        gpu.state.line_width_set(1.0)

    def draw_id(self, context, shader):
        """Draw only the edges for selection buffer identification."""
        # Selectability check removed, handled by caller (draw_selection_buffer)
        # if not self.is_selectable(context):
        #     return
        # Call draw_id_edges with the provided shader
        self.draw_id_edges(context, shader)

    def create_slvs_data(self, solvesys, group=SOLVER_GROUP_FIXED):
        handle = solvesys.addWorkplane(self.p1.py_data, self.nm.py_data, group=group)
        self.py_data = handle

    @property
    def matrix_basis(self):
        mat_rot = self.nm.orientation.to_matrix().to_4x4()
        return Matrix.Translation(self.p1.location) @ mat_rot

    @property
    def normal(self):
        v = Z_AXIS.copy()
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
