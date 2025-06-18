import math

# Mathematical constants
PI = math.pi
HALF_TURN = PI
QUARTER_TURN = PI / 2
FULL_TURN = 2 * PI

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
            except:
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
