"""
GPU Resource Management for CAD Sketcher

This module provides centralized management of GPU resources including
shader caching, batch management, and memory cleanup to improve performance
and prevent resource leaks.
"""

import logging
import time
import gpu
from typing import Dict, Optional

from .constants import RenderingConstants

logger = logging.getLogger(__name__)


class ShaderManager:
    """Centralized shader management with caching and lifecycle control."""

    _cached_shaders: Dict[str, gpu.types.GPUShader] = {}
    _last_cleanup_time: float = 0.0

    @classmethod
    def get_uniform_color_shader(cls) -> gpu.types.GPUShader:
        """Get cached uniform color shader for points and solid rendering."""
        shader_key = 'uniform_color'
        if shader_key not in cls._cached_shaders:
            try:
                cls._cached_shaders[shader_key] = gpu.shader.from_builtin("UNIFORM_COLOR")
                logger.debug(f"Created shader: {shader_key}")
            except Exception as e:
                logger.error(f"Failed to create uniform color shader: {e}")
                # Return a fallback or re-raise depending on criticality
                raise
        return cls._cached_shaders[shader_key]

    @classmethod
    def get_polyline_shader(cls) -> gpu.types.GPUShader:
        """Get cached polyline shader for thick lines."""
        shader_key = 'polyline_uniform_color'
        if shader_key not in cls._cached_shaders:
            try:
                cls._cached_shaders[shader_key] = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
                logger.debug(f"Created shader: {shader_key}")
            except Exception as e:
                logger.error(f"Failed to create polyline shader: {e}")
                raise
        return cls._cached_shaders[shader_key]

    @classmethod
    def get_id_shader(cls, is_point: bool = False) -> gpu.types.GPUShader:
        """Get cached ID shader for selection rendering."""
        from ..shaders import Shaders

        shader_key = 'id_point' if is_point else 'id_line'
        if shader_key not in cls._cached_shaders:
            try:
                if is_point:
                    cls._cached_shaders[shader_key] = Shaders.id_shader_3d()
                else:
                    cls._cached_shaders[shader_key] = Shaders.id_line_3d()
                logger.debug(f"Created shader: {shader_key}")
            except Exception as e:
                logger.error(f"Failed to create ID shader ({shader_key}): {e}")
                raise
        return cls._cached_shaders[shader_key]

    @classmethod
    def cleanup_unused_shaders(cls, force: bool = False) -> int:
        """
        Clean up shader cache periodically or on demand.

        Args:
            force: If True, clear all cached shaders immediately

        Returns:
            Number of shaders cleaned up
        """
        current_time = time.time()
        cleanup_interval = RenderingConstants.CLEANUP_INTERVAL_SECONDS

        if not force and (current_time - cls._last_cleanup_time) < cleanup_interval:
            return 0

        if force:
            # Force cleanup - clear all cached shaders
            count = len(cls._cached_shaders)
            cls._cached_shaders.clear()
            cls._last_cleanup_time = current_time
            logger.debug(f"Force cleaned up {count} cached shaders")
            return count
        else:
            # Periodic cleanup - shaders are lightweight, just update timestamp
            cls._last_cleanup_time = current_time
            return 0

    @classmethod
    def get_cache_stats(cls) -> Dict[str, int]:
        """Get statistics about cached shaders for debugging."""
        return {
            'cached_shaders': len(cls._cached_shaders),
            'shader_types': list(cls._cached_shaders.keys())
        }


class GPUResourceManager:
    """Manages GPU resources beyond shaders - batches, textures, etc."""

    _last_memory_check: float = 0.0
    _memory_check_interval: float = 30.0  # Check every 30 seconds

    @classmethod
    def periodic_cleanup(cls, context) -> Dict[str, int]:
        """
        Perform periodic cleanup of GPU resources.

        Returns:
            Dictionary with cleanup statistics
        """
        current_time = time.time()

        if (current_time - cls._last_memory_check) < cls._memory_check_interval:
            return {'cleaned_shaders': 0, 'cleaned_batches': 0}

        cls._last_memory_check = current_time

        stats = {
            'cleaned_shaders': ShaderManager.cleanup_unused_shaders(),
            'cleaned_batches': 0
        }

        # Clean up unused batches
        try:
            from .. import global_data
            if hasattr(global_data, 'cleanup_unused_batches'):
                global_data.cleanup_unused_batches(context)
                # We don't get a count back, but we attempted cleanup
                stats['cleaned_batches'] = -1  # Indicate cleanup was attempted
        except Exception as e:
            logger.debug(f"Batch cleanup failed: {e}")

        if any(stats.values()):
            logger.debug(f"GPU cleanup stats: {stats}")

        return stats

    @classmethod
    def force_cleanup_all(cls, context) -> Dict[str, int]:
        """Force cleanup of all GPU resources."""
        stats = {
            'cleaned_shaders': ShaderManager.cleanup_unused_shaders(force=True),
            'cleaned_batches': 0
        }

        try:
            from .. import global_data
            if hasattr(global_data, 'cleanup_unused_batches'):
                global_data.cleanup_unused_batches(context)
                stats['cleaned_batches'] = -1
        except Exception as e:
            logger.debug(f"Force batch cleanup failed: {e}")

        logger.info(f"Force GPU cleanup completed: {stats}")
        return stats


# Convenience functions for backward compatibility
def get_uniform_color_shader() -> gpu.types.GPUShader:
    """Convenience function to get uniform color shader."""
    return ShaderManager.get_uniform_color_shader()


def get_polyline_shader() -> gpu.types.GPUShader:
    """Convenience function to get polyline shader."""
    return ShaderManager.get_polyline_shader()


def get_id_shader(is_point: bool = False) -> gpu.types.GPUShader:
    """Convenience function to get ID shader."""
    return ShaderManager.get_id_shader(is_point)