from collections import deque
from math import sin, cos
from typing import List, Dict, Any, Optional, Union, Tuple
import logging

from mathutils import Vector, Matrix
import gpu
from gpu.types import GPUVertFormat, GPUVertBuf, GPUBatch
from gpu_extras.batch import batch_for_shader  # We'll wrap this function

from .. import global_data
from .constants import FULL_TURN

logger = logging.getLogger(__name__)


def safe_batch_for_shader(shader, type: str, 
                         content: Dict[str, Any], 
                         indices: Optional[Union[List, Tuple]] = None) -> GPUBatch:
    """Safely create a batch for a shader, handling single-element data correctly.
    
    This function wraps batch_for_shader and ensures that coordinate data is 
    properly formatted to avoid the "object of type 'float' has no len()" error.
    
    Args:
        shader: The shader to use for this batch
        type: The type of primitive ('POINTS', 'LINES', etc.)
        content: Dict mapping attribute names to their data
        indices: Optional index data
        
    Returns:
        A GPUBatch object
    """
    try:
        # For safety, ensure all data is properly formatted as lists
        safe_content = {}
        for key, data in content.items():
            if not data:
                # Handle empty data
                logger.warning(f"Empty data for attribute {key}, using empty list")
                safe_content[key] = []
                continue
                
            # Ensure data is a list of vectors/lists rather than a single vector or tuple
            if isinstance(data, (list, tuple)):
                if len(data) == 0:
                    safe_content[key] = []
                elif isinstance(data[0], (float, int)):
                    # Single vector/point case (e.g., [x, y, z])
                    safe_content[key] = [data]
                else:
                    # Already a list of points
                    safe_content[key] = data
            else:
                # Unexpected data type
                logger.warning(f"Unexpected data type for attribute {key}: {type(data)}")
                safe_content[key] = [data]
                
        # Now use the standard batch_for_shader with our safe data
        return batch_for_shader(shader, type, safe_content, indices=indices)
    except Exception as e:
        logger.error(f"Error creating batch: {e}")
        # Create an empty batch in case of failure
        fmt = GPUVertFormat()
        for key in content.keys():
            fmt.attr_add(id=key, comp_type='F32', len=3, fetch_mode='FLOAT')
        vbo = GPUVertBuf(fmt, 0)  # Zero-length buffer
        batch = GPUBatch(type=type, buf=vbo)
        return batch


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
