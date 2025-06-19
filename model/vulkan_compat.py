"""
Geometry-based rendering utilities for CAD Sketcher entities.

This module provides common functionality for geometry-based rendering
to ensure consistent visual appearance across all GPU backends.
"""

import logging
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from ..utilities.constants import RenderingConstants
from ..utilities.draw import draw_billboard_quad_3d

logger = logging.getLogger(__name__)


class GeometryRenderer:
    """Mixin class providing geometry-based rendering methods for entities."""

    def create_batch(self, coords, batch_type="LINES", indices=None):
        """Create a GPU batch with appropriate parameters."""
        kwargs = {"pos": coords}
        if indices is not None:
            return batch_for_shader(self._shader, batch_type, kwargs, indices=indices)
        return batch_for_shader(self._shader, batch_type, kwargs)

    def setup_line_rendering(self, coords, is_dashed=False):
        """Setup line rendering with proper batch type."""
        if is_dashed:
            # Dashed lines use LINES (individual segments)
            return self.create_batch(coords, "LINES")
        else:
            # Solid lines can use LINE_STRIP for efficiency
            return self.create_batch(coords, "LINE_STRIP")

    def setup_point_rendering(self, coords, indices):
        """Setup point rendering using triangle geometry."""
        # Points as triangles for all backends
        return self.create_batch(coords, "TRIS", indices)


class BillboardPointRenderer:
    """Mixin class providing billboard point rendering for camera-facing squares."""

    def get_screen_consistent_size(self, context, base_size):
        """Calculate screen-consistent size based on view distance."""
        if hasattr(context, 'region_data') and context.region_data:
            view_distance = context.region_data.view_distance
            # Scale the point size inversely with view distance
            return base_size * view_distance * 0.1
        else:
            # Fallback if no context available
            return base_size

    def get_point_location_3d(self):
        """Get the 3D location for billboard rendering. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_point_location_3d()")

    def get_point_base_size(self):
        """Get the base size for this point type. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_point_base_size()")

    def update_billboard_point(self):
        """Update method for billboard points - creates initial geometry."""
        if bpy.app.background:
            return

        # Get location and size
        location_3d = self.get_point_location_3d()
        base_size = self.get_point_base_size()

        # Calculate screen-consistent size
        context = bpy.context
        screen_consistent_size = self.get_screen_consistent_size(context, base_size)

        # Create billboard geometry
        coords, indices = draw_billboard_quad_3d(*location_3d, screen_consistent_size)
        self._batch = batch_for_shader(
            self._shader, "TRIS", {"pos": coords}, indices=indices
        )
        self.is_dirty = False

    def draw_billboard_point(self, context):
        """Draw method for billboard points - regenerates geometry each frame."""
        if not self.is_visible(context):
            return

        # Get location and size
        location_3d = self.get_point_location_3d()
        base_size = self.get_point_base_size()

        # Calculate screen-consistent size
        screen_consistent_size = self.get_screen_consistent_size(context, base_size)

        # Generate fresh billboard geometry that faces the camera
        coords, indices = draw_billboard_quad_3d(*location_3d, screen_consistent_size)
        batch = batch_for_shader(self._shader, "TRIS", {"pos": coords}, indices=indices)

        # Render the batch
        shader = self._shader
        shader.bind()
        gpu.state.blend_set("ALPHA")

        col = self.color(context)
        shader.uniform_float("color", col)

        batch.draw(shader)
        gpu.shader.unbind()
        self.restore_opengl_defaults()


class DashedLineRenderer:
    """Utility class for creating dashed line geometry."""

    @staticmethod
    def create_dashed_coords(start_point, end_point):
        """Create dashed line coordinates between two points."""
        line_vec = end_point - start_point
        line_length = line_vec.length

        if line_length == 0:
            return [start_point, end_point]

        # Use centralized constants
        dash_length = RenderingConstants.DASH_LENGTH
        pattern_length = RenderingConstants.dash_pattern_length()

        coords = []
        direction = line_vec.normalized()

        current_pos = 0.0
        while current_pos < line_length:
            # Start of dash
            dash_start = start_point + direction * current_pos
            dash_end_pos = min(current_pos + dash_length, line_length)
            dash_end = start_point + direction * dash_end_pos

            # Add dash segment
            coords.extend([dash_start, dash_end])

            # Move to next dash (skip gap)
            current_pos += pattern_length

        return coords

    @staticmethod
    def create_dashed_arc_coords(center, radius, total_angle, start_offset, segments_per_dash):
        """Create dashed arc coordinates."""
        from ..utilities.draw import coords_arc_2d
        import math

        if radius <= 0 or total_angle <= 0:
            return []

        # Convert world units to angular measurements
        dash_length_world = RenderingConstants.DASH_LENGTH
        gap_length_world = RenderingConstants.GAP_LENGTH

        dash_angle = dash_length_world / radius
        gap_angle = gap_length_world / radius
        pattern_angle = dash_angle + gap_angle

        # Calculate number of complete patterns that fit in the arc
        num_patterns = int(total_angle / pattern_angle)

        coords = []
        current_angle = 0.0

        for i in range(num_patterns):
            # Create dash segment within the arc
            dash_start = current_angle
            dash_end = min(current_angle + dash_angle, total_angle)

            if dash_end > dash_start:
                # Generate points for this dash
                dash_coords = coords_arc_2d(0, 0, radius, segments_per_dash,
                                          angle=(dash_end - dash_start),
                                          offset=(start_offset + dash_start))

                # Convert to line segments (pairs of points)
                for j in range(len(dash_coords) - 1):
                    coords.extend([dash_coords[j], dash_coords[j + 1]])

            # Move to next dash (skip gap)
            current_angle += pattern_angle

            # Stop if we've covered the entire arc
            if current_angle >= total_angle:
                break

        # Add final partial dash if there's remaining arc length
        if current_angle < total_angle:
            dash_start = current_angle
            dash_end = total_angle

            if dash_end > dash_start:
                dash_coords = coords_arc_2d(0, 0, radius, segments_per_dash,
                                          angle=(dash_end - dash_start),
                                          offset=(start_offset + dash_start))

                for j in range(len(dash_coords) - 1):
                    coords.extend([dash_coords[j], dash_coords[j + 1]])

        return coords