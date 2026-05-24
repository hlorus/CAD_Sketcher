CURVE_RESOLUTION = 64
ENTITY_PROP_NAMES = ("entity1", "entity2", "entity3", "entity4")

SKETCH_ROLE_ITEMS = [
    (
        "Plan",
        "Plan",
        "Default plan view — lines become wall axes, closed polylines become slabs",
    ),
    (
        "Elevation",
        "Elevation",
        "Elevation view — IfcWall polylines define wall height profiles",
    ),
]

TAG_ITEMS = [
    ("IfcWall", "IfcWall", "Plan run — each segment becomes a separate IfcWall"),
    ("IfcCurtainWall", "IfcCurtainWall", "Curtain wall element"),
    ("IfcSlab", "IfcSlab", "Slab element"),
    ("IfcRoof", "IfcRoof", "Roof element"),
    ("IfcColumn", "IfcColumn", "Column element"),
    ("IfcBeam", "IfcBeam", "Beam element"),
    ("IfcMember", "IfcMember", "Member element"),
    ("IfcDoor", "IfcDoor", "Door element"),
    ("IfcWindow", "IfcWindow", "Window element"),
    ("IfcOpeningElement", "IfcOpeningElement", "Opening / void element"),
    ("IfcSpace", "IfcSpace", "Space element"),
    ("IfcRailing", "IfcRailing", "Railing element"),
    ("IfcStair", "IfcStair", "Stair element"),
    ("IfcFooting", "IfcFooting", "Footing element"),
    ("IfcPile", "IfcPile", "Pile element"),
    (
        "IfcCovering",
        "IfcCovering",
        "Covering element (e.g. flooring, ceiling, cladding)",
    ),
    ("IfcPlate", "IfcPlate", "Plate element"),
]
