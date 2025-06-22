import math
import logging

logger = logging.getLogger(__name__)

# Mathematical constants
PI = math.pi
HALF_TURN = PI
QUARTER_TURN = PI / 2
FULL_TURN = 2 * PI

# Rendering constants for geometry-based rendering
class RenderingConstants:
    """
    Centralized rendering constants for consistent visual appearance across all GPU backends.

    These constants ensure consistent rendering using geometry-based approaches:
    - Point sizes are used for triangle geometry (rectangles/cubes)
    - Line widths apply to POLYLINE_UNIFORM_COLOR shader uniforms
    - Dash patterns create actual geometry gaps rather than shader effects
    """

    # Point size for screen-space billboard rendering
    POINT_SIZE = 0.06  # Base size for screen-space point billboards

    # Line widths (in pixels for POLYLINE_UNIFORM_COLOR shader)
    LINE_WIDTH_REGULAR = 2.0      # Regular line thickness
    LINE_WIDTH_CONSTRUCTION = 1.5 # Construction line thickness

    # Construction line dash patterns
    DASH_LENGTH = 0.1            # Length of each dash segment
    GAP_LENGTH = 0.05            # Length of each gap between dashes

    # Selection and depth sorting constants
    WORKPLANE_SELECTION_PRIORITY = 0.1  # Multiplier to give workplanes selection priority
    VIEW_CHANGE_THRESHOLD = 0.001       # Minimum view distance change to trigger geometry update

    # Performance constants
    CLEANUP_FRAME_INTERVAL = 1000       # Frames between GPU batch cleanup cycles
    CLEANUP_INTERVAL_SECONDS = 10.0     # Seconds between time-based cleanup cycles

    # UI interaction constants
    UI_BORDER_MARGIN = 5                # Pixel margin to avoid UI boundary issues

    @classmethod
    def dash_pattern_length(cls):
        """
        Calculate total length of one complete dash pattern.

        Returns:
            float: Combined length of dash + gap for pattern calculations
        """
        return cls.DASH_LENGTH + cls.GAP_LENGTH
