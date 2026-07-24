CURVE_RESOLUTION = 64
ENTITY_PROP_NAMES = ("entity1", "entity2", "entity3", "entity4")


class SketchCurveType:
    """Type identifier stored as 'sketch_type' attribute on each curve."""
    POINT = 0
    LINE = 1
    ARC = 2
    CIRCLE = 3


class BezierHandleType:
    AUTO = 0
    FREE = 1
    ALIGN = 3
