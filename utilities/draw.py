from collections import deque
from math import sin, cos
from typing import List

import bpy
from mathutils import Vector, Matrix

from .. import global_data
from .constants import FULL_TURN


# def draw_circle_2d(cx: float, cy: float, r: float, num_segments: int):
#     """NOTE: Not used?"""
#     # circle outline
#     # NOTE: also see gpu_extras.presets.draw_circle_2d
#     theta = FULL_TURN / num_segments

#     # precalculate the sine and cosine
#     c = math.cos(theta)
#     s = math.sin(theta)

#     # start at angle = 0
#     x = r
#     y = 0
#     coords = []
#     for _ in range(num_segments):
#         coords.append((x + cx, y + cy))
#         # apply the rotation matrix
#         t = x
#         x = c * x - s * y
#         y = s * t + c * y
#     coords.append(coords[0])
#     return coords


def draw_rect_2d(cx: float, cy: float, width: float, height: float):
    # NOTE: this currently returns xyz coordinates, might make sense to return 2d coords
    ox = cx - (width / 2)
    oy = cy - (height / 2)
    cz = 0
    return (
        (ox, oy, cz),
        (ox + width, oy, cz),
        (ox + width, oy + height, cz),
        (ox, oy + height, cz),
    )


def draw_rect_3d(origin: Vector, orientation: Vector, width: float) -> List[Vector]:
    mat_rot = global_data.Z_AXIS.rotation_difference(orientation).to_matrix()
    mat = Matrix.Translation(origin) @ mat_rot.to_4x4()
    coords = draw_rect_2d(0, 0, width, width)
    coords = [(mat @ Vector(co))[:] for co in coords]
    return coords


def draw_quad_3d(cx: float, cy: float, cz: float, width: float):
    half_width = width / 2
    coords = (
        (cx - half_width, cy - half_width, cz),
        (cx + half_width, cy - half_width, cz),
        (cx + half_width, cy + half_width, cz),
        (cx - half_width, cy + half_width, cz),
    )
    indices = ((0, 1, 2), (2, 3, 0))
    return coords, indices


def draw_billboard_quad_3d(cx: float, cy: float, cz: float, width: float):
    """Create a screen-facing quad that always appears as a square regardless of view angle."""
    half_width = width / 2
    center = Vector((cx, cy, cz))

    # Get current view matrix to determine camera orientation
    context = bpy.context
    if hasattr(context, 'region_data') and context.region_data:
        # Get the view matrix to determine camera orientation
        view_matrix = context.region_data.view_matrix

        # Extract camera right and up vectors from the view matrix
        # The view matrix transforms from world to view space
        # So we need the inverse to get world space vectors
        view_matrix_inv = view_matrix.inverted()

        # Camera right vector (X axis in view space)
        right = Vector((view_matrix_inv[0][0], view_matrix_inv[1][0], view_matrix_inv[2][0])).normalized()
        # Camera up vector (Y axis in view space)
        up = Vector((view_matrix_inv[0][1], view_matrix_inv[1][1], view_matrix_inv[2][1])).normalized()
    else:
        # Fallback to XY plane if no context
        right = Vector((1, 0, 0))
        up = Vector((0, 1, 0))

    # Create quad vertices using camera-relative vectors
    coords = (
        center - right * half_width - up * half_width,  # Bottom-left
        center + right * half_width - up * half_width,  # Bottom-right
        center + right * half_width + up * half_width,  # Top-right
        center - right * half_width + up * half_width,  # Top-left
    )

    # Convert to tuples for GPU batch
    coords = [co[:] for co in coords]
    indices = ((0, 1, 2), (2, 3, 0))

    return coords, indices


def tris_from_quad_ids(id0: int, id1: int, id2: int, id3: int):
    return (id0, id1, id2), (id1, id2, id3)


def draw_cube_3d(cx: float, cy: float, cz: float, width: float):
    half_width = width / 2
    coords = []
    for x in (cx - half_width, cx + half_width):
        for y in (cy - half_width, cy + half_width):
            for z in (cz - half_width, cz + half_width):
                coords.append((x, y, z))
    # order: ((-x, -y, -z), (-x, -y, +z), (-x, +y, -z), ...)
    indices = (
        *tris_from_quad_ids(0, 1, 2, 3),
        *tris_from_quad_ids(0, 1, 4, 5),
        *tris_from_quad_ids(1, 3, 5, 7),
        *tris_from_quad_ids(2, 3, 6, 7),
        *tris_from_quad_ids(0, 2, 4, 6),
        *tris_from_quad_ids(4, 5, 6, 7),
    )

    return coords, indices


def coords_circle_2d(x: float, y: float, radius: float, segments: int):
    coords = []
    m = (1.0 / (segments - 1)) * FULL_TURN

    for p in range(segments):
        p1 = x + cos(m * p) * radius
        p2 = y + sin(m * p) * radius
        coords.append((p1, p2))
    return coords


def coords_arc_2d(
    x: float,
    y: float,
    radius: float,
    segments: int,
    angle=FULL_TURN,
    offset: float = 0.0,
    type="LINE_STRIP",
):
    coords = deque()
    segments = max(segments, 1)

    m = (1.0 / segments) * angle

    prev_point = None
    for p in range(segments + 1):
        co_x = x + cos(m * p + offset) * radius
        co_y = y + sin(m * p + offset) * radius
        if type == "LINES":
            if prev_point:
                coords.append(prev_point)
                coords.append((co_x, co_y))
            prev_point = co_x, co_y
        else:
            coords.append((co_x, co_y))
    return coords
