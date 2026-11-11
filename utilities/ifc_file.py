"""Write complete, metre-based IFC4 sketch-profile libraries atomically."""

import math
import os
import tempfile
from collections.abc import Sequence
from numbers import Real
from pathlib import Path

from . import ifc_export

Point2D = tuple[float, float]
SketchProfiles = Sequence[tuple[str, Sequence[Point2D]]]


def _new_document(ifc, filename: str):
    document = ifc.file(schema="IFC4")
    metre = document.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    units = document.create_entity("IfcUnitAssignment", Units=[metre])
    origin = document.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    placement = document.create_entity("IfcAxis2Placement2D", Location=origin)
    context = document.create_entity(
        "IfcGeometricRepresentationContext",
        ContextIdentifier="Sketch",
        ContextType="Plan",
        CoordinateSpaceDimension=2,
        Precision=1e-8,
        WorldCoordinateSystem=placement,
    )
    project = document.create_entity(
        "IfcProject",
        GlobalId=ifc.guid.new(),
        Name="CAD Sketcher profiles",
        RepresentationContexts=[context],
        UnitsInContext=units,
    )
    library = document.create_entity(
        "IfcProjectLibrary",
        GlobalId=ifc.guid.new(),
        Name="CAD Sketcher profile library",
        Description="Closed straight-line profiles in their local sketch coordinates.",
        RepresentationContexts=[context],
        UnitsInContext=units,
    )
    document.create_entity(
        "IfcRelDeclares",
        GlobalId=ifc.guid.new(),
        RelatingContext=project,
        RelatedDefinitions=[library],
    )
    # Profiles are geometric definitions, not IfcDefinitionSelect members. Do
    # not manufacture product types or invalid declarations to attach them.
    document.header.file_description.description = (
        "CAD Sketcher closed 2D profile definitions",
    )
    document.header.file_name.name = filename
    document.header.file_name.originating_system = "CAD Sketcher"
    return document


def write_sketch_profiles(
    path: str | os.PathLike[str],
    profiles: SketchProfiles,
    *,
    unit_scale: float = 1.0,
) -> str:
    """Write named local-plane profiles in metres and return the output path.

    ``unit_scale`` is Blender's metres per scene unit. Every coordinate is
    multiplied by it exactly once; the IFC project's length unit is METRE.
    Original names, profile order and local sketch origins are retained.

    All geometry is validated and serialized before replacing the destination.
    A failed conversion or write leaves an existing destination untouched.
    IfcOpenShell remains optional until this function is called.
    """
    if (
        isinstance(unit_scale, bool)
        or not isinstance(unit_scale, Real)
        or not math.isfinite(unit_scale)
        or unit_scale <= 0
    ):
        raise ValueError("scene unit scale must be a finite positive number")
    scale = float(unit_scale)
    scaled_profiles = []
    for name, points in profiles:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("each profile needs a nonempty name")
        # Validate after conversion as very small or large scaling can collapse
        # distinct points or produce non-finite coordinates.
        scaled = [(float(x) * scale, float(y) * scale) for x, y in points]
        scaled_profiles.append((name, ifc_export.closed_loop_points(scaled)))
    if not scaled_profiles:
        raise ValueError("at least one closed sketch profile is required")

    destination = Path(path).expanduser().absolute()
    ifc = ifc_export._ifcopenshell()
    document = _new_document(ifc, destination.name)
    for name, points in scaled_profiles:
        ifc_export.add_arbitrary_profile(document, name, points)

    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".ifc", dir=destination.parent
    )
    os.close(descriptor)
    try:
        document.write(temporary)
        with open(temporary, "rb") as written:
            os.fsync(written.fileno())
        # Staging beside the selected file keeps this replacement on one
        # filesystem, including when the destination already exists.
        os.replace(temporary, destination)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return str(destination)
