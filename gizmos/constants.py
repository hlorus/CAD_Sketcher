"""
Constants used by the gizmos module.
"""

# The distance tolerance in pixels for workplane edge detection.
# Higher values make it easier to select workplane edges.
WORKPLANE_EDGE_SELECT_TOLERANCE = 5

# Line width for workplane edges in the selection buffer.
# Thicker lines make edge selection easier.
WORKPLANE_EDGE_LINE_WIDTH = 6.0

# When to consider mouse movement significant enough to reset hover state
SIGNIFICANT_MOUSE_MOVEMENT = 5