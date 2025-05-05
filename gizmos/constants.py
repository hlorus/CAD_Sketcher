"""
Constants used by the gizmos module.
"""

# The distance tolerance in pixels for workplane edge detection.
# Higher values make it easier to select workplane edges.
WORKPLANE_EDGE_SELECT_TOLERANCE = 15  # Increased from 5 to 15 for better edge selection

# When to consider mouse movement significant enough to reset hover state
SIGNIFICANT_MOUSE_MOVEMENT = 5