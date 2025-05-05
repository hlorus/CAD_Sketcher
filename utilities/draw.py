from collections import deque
from math import sin, cos
from typing import List, Dict, Any, Optional, Union, Tuple
import logging

from mathutils import Vector, Matrix
import gpu
from gpu.types import GPUVertFormat, GPUVertBuf, GPUBatch, GPUIndexBuf
from gpu_extras.batch import batch_for_shader  # We'll wrap this function

from .constants import FULL_TURN
from ..global_data import Z_AXIS

logger = logging.getLogger(__name__)


def safe_batch_for_shader(shader, type: str, 
                         content: Dict[str, Any], 
                         indices: Optional[Union[List, Tuple]] = None) -> GPUBatch:
    """Safely create a batch for a shader, handling single-element data correctly.
    
    This function avoids using batch_for_shader and creates the GPU batch directly
    to prevent the "object of type 'float' has no len()" error.
    
    Args:
        shader: The shader to use for this batch
        type: The type of primitive ('POINTS', 'LINES', etc.)
        content: Dict mapping attribute names to their data
        indices: Optional index data
        
    Returns:
        A GPUBatch object
    """
    try:
        if not content:
            logger.warning("Empty content provided to safe_batch_for_shader")
            return None
        
        # Define vertex format
        fmt = GPUVertFormat()
        
        # Get the shader attribute info directly from the shader if possible
        attrs_info = []
        if hasattr(shader, "attrs_info_get"):
            try:
                # New Blender API
                attrs_info = shader.attrs_info_get()
            except:
                # Fallback: assume standard attributes expected by most shaders
                attrs_info = [("pos", "VEC3")]
        else:
            # Fallback: assume standard attributes expected by most shaders
            attrs_info = [("pos", "VEC3")]
            
        # Add attributes to format
        attr_ids = {}
        for name, attr_type in attrs_info:
            # Only add attributes that are in our content dictionary
            if name in content:
                # Determine component type and length
                comp_type = 'F32'  # Default to float for most attributes
                attr_len = 3      # Default to vec3 for position
                
                # Override for specific attribute types if needed
                if attr_type == 'VEC2':
                    attr_len = 2
                elif attr_type == 'VEC4':
                    attr_len = 4
                    
                # Add attribute to format
                attr_ids[name] = fmt.attr_add(
                    id=name, 
                    comp_type=comp_type, 
                    len=attr_len, 
                    fetch_mode='FLOAT'
                )
        
        # Ensure all content keys are added to format
        for name in content:
            if name not in attr_ids:
                # Add attribute with default settings
                attr_ids[name] = fmt.attr_add(
                    id=name, 
                    comp_type='F32', 
                    len=3,
                    fetch_mode='FLOAT'
                )
                
        # Find the length of the vertex buffer (number of vertices)
        vbo_len = 0
        for data in content.values():
            # Process the data to determine number of vertices
            if isinstance(data, (list, tuple)):
                if not data:
                    continue
                    
                # Check if data is a list of vectors/points or a single vector/point
                if isinstance(data[0], (list, tuple, Vector)):
                    # Data is a list of vectors/points
                    vbo_len = len(data)
                else:
                    # Data is a single vector, make it a list with one element
                    vbo_len = 1
                    
            if vbo_len > 0:
                break
                
        if vbo_len == 0:
            logger.warning("Could not determine vertex buffer length")
            return None
            
        # Create the vertex buffer
        vbo = GPUVertBuf(fmt, vbo_len)
        
        # Fill the vertex buffer with data
        for name, data in content.items():
            if name not in attr_ids:
                continue
                
            # Process data to ensure it's in the right format
            processed_data = data
                
            # If this is a list with a single element that's a float/int,
            # it's likely a position vector and needs to be in a list
            if (isinstance(data, (list, tuple)) and len(data) > 0 and 
                isinstance(data[0], (float, int))):
                # It's a single vector, wrap it in a list
                processed_data = [data]
            
            # Detect the actual dimension of the data (2D vs 3D)
            # and adapt it based on the attribute name
            data_len = None
            attr_len = 3  # Default to 3D for position attributes
            
            # Use attribute naming convention to determine expected dimensions
            if name == "texCoord":
                attr_len = 2  # Texture coordinates are typically 2D
            
            # For "pos" attribute in screen space operations, also check the primitive type
            if name == "pos" and type in ("LINE_STRIP_ADJACENCY", "LINE_STRIP", "LINES", "POINTS") and len(processed_data) > 0:
                # Check first element to determine dimensionality
                sample = processed_data[0]
                if isinstance(sample, (list, tuple, Vector)):
                    data_len = len(sample)
                    
                    # Adapt the data if dimensions don't match
                    if data_len != attr_len:
                        # 2D data for a 3D attribute: add Z=0
                        if data_len == 2 and attr_len == 3:
                            processed_data = [(*item, 0.0) for item in processed_data]
                        # 3D data for a 2D attribute: truncate Z
                        elif data_len == 3 and attr_len == 2:
                            processed_data = [item[:2] for item in processed_data]

            # Fill the attribute with processed data    
            vbo.attr_fill(id=name, data=processed_data)
            
        # Create the batch
        if indices is not None:
            ibo = GPUIndexBuf(type=type, seq=indices)
            return GPUBatch(type=type, buf=vbo, elem=ibo)
        else:
            return GPUBatch(type=type, buf=vbo)
            
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
    mat_rot = Z_AXIS.rotation_difference(orientation).to_matrix()
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
