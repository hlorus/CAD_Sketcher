import math
import logging

logger = logging.getLogger(__name__)

# Mathematical constants
PI = math.pi
HALF_TURN = PI
QUARTER_TURN = PI / 2
FULL_TURN = 2 * PI

# Rendering constants for Vulkan compatibility
class RenderingConstants:
    """Centralized rendering constants for consistent visual appearance."""

    # Point sizes for Vulkan geometry-based rendering
    VULKAN_POINT_2D_SIZE = 0.06  # Size of 2D point rectangles
    VULKAN_POINT_3D_SIZE = 0.03  # Size of 3D point cubes

    # Line widths
    LINE_WIDTH_REGULAR = 2.0     # Regular line thickness
    LINE_WIDTH_CONSTRUCTION = 1.5 # Construction line thickness

    # Construction line dash patterns
    DASH_LENGTH = 0.1            # Length of each dash segment
    GAP_LENGTH = 0.05            # Length of each gap between dashes

    @classmethod
    def dash_pattern_length(cls):
        """Total length of one dash pattern (dash + gap)."""
        return cls.DASH_LENGTH + cls.GAP_LENGTH

# GPU Backend detection cache
class BackendCache:
    """Cache GPU backend detection to avoid repeated expensive queries."""
    _backend_type = None
    _is_vulkan = None

    @classmethod
    def get_backend_type(cls):
        """Get the current GPU backend type, cached after first call."""
        if cls._backend_type is None:
            try:
                import gpu
                cls._backend_type = gpu.platform.backend_type_get()
                logger.debug(f"Detected GPU backend: {cls._backend_type}")
            except (ImportError, AttributeError) as e:
                logger.warning(f"Failed to detect GPU backend, using OpenGL fallback: {e}")
                cls._backend_type = 'OPENGL'  # Safe fallback
        return cls._backend_type

    @classmethod
    def is_vulkan(cls):
        """Check if current backend is Vulkan, cached after first call."""
        if cls._is_vulkan is None:
            cls._is_vulkan = cls.get_backend_type() == 'VULKAN'
        return cls._is_vulkan

    @classmethod
    def reset_cache(cls):
        """Reset cache - useful for testing or backend changes."""
        cls._backend_type = None
        cls._is_vulkan = None
