"""Write complete, metre-based IFC4 sketch-profile libraries atomically."""

import math
import os
import stat
import tempfile
from collections.abc import Sequence
from numbers import Real
from pathlib import Path

from . import ifc_export
from .ifc_profile import (
    IFC_PRECISION,
    Boundary,
    Profile,
    add_profile,
    arrange_boundaries,
    boundary_precision,
    scale_boundary,
)

SketchBoundaries = tuple[str, Sequence[Boundary]]


def _new_document(ifc, filename: str, precision: float):
    document = ifc.file(schema="IFC4")
    metre = document.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    radian = document.create_entity(
        "IfcSIUnit", UnitType="PLANEANGLEUNIT", Name="RADIAN"
    )
    units = document.create_entity("IfcUnitAssignment", Units=[metre, radian])
    origin = document.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    placement = document.create_entity("IfcAxis2Placement2D", Location=origin)
    context = document.create_entity(
        "IfcGeometricRepresentationContext",
        ContextIdentifier="Sketch",
        ContextType="Plan",
        CoordinateSpaceDimension=2,
        Precision=precision,
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
        Description="Analytic profiles and voids in their local sketch coordinates.",
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
    sketches: Sequence[SketchBoundaries],
    *,
    unit_scale: float = 1.0,
) -> str:
    """Write named sketch boundaries as IFC profiles and return the output path.

    ``unit_scale`` is Blender's metres per scene unit. Every coordinate is
    multiplied by it exactly once; the IFC project's length unit is METRE.
    Each item contains a sketch name and its topologically connected boundaries.
    Validate their geometry and classify direct holes after unit conversion;
    original names, boundary order and local sketch origins are retained.

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
    precision = IFC_PRECISION
    for name, boundaries in sketches:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("each profile needs a nonempty name")
        scaled = [scale_boundary(boundary, scale) for boundary in boundaries]
        if not scaled:
            raise ValueError("at least one closed sketch profile is required")
        tolerance = boundary_precision(scaled)
        groups = arrange_boundaries(scaled)
        scaled_profiles.extend(
            Profile(
                name if len(groups) == 1 else f"{name} {i + 1}",
                scaled[outer],
                tuple(scaled[hole] for hole in holes),
            )
            for i, (outer, holes) in enumerate(groups)
        )
        # Joins use their own arc's roundoff bound; the declared context
        # precision covers the largest coordinate magnitude in the library.
        precision = max(precision, tolerance)
    if not scaled_profiles:
        raise ValueError("at least one closed sketch profile is required")
    destination = Path(path).expanduser().absolute()
    ifc = ifc_export.require_ifcopenshell()
    document = _new_document(ifc, destination.name, precision)
    for profile in scaled_profiles:
        add_profile(document, profile)

    # A private directory hides the incomplete file while ordinary creation
    # applies the process umask. mkstemp would impose owner-only permissions.
    with tempfile.TemporaryDirectory(
        prefix=f".{destination.name}.", dir=destination.parent
    ) as staging:
        # Even an owner-restricting umask must leave private staging usable.
        os.chmod(staging, 0o700)
        temporary = Path(staging) / destination.name
        with temporary.open("x"):
            pass
        mode = stat.S_IMODE(temporary.stat().st_mode)
        os.chmod(temporary, 0o600)
        try:
            mode = stat.S_IMODE(destination.stat().st_mode)
        except FileNotFoundError:
            pass
        document.write(str(temporary))
        os.chmod(temporary, 0o600)
        with temporary.open("rb") as written:
            # Some IFC writers replace the staged inode themselves. Apply the
            # intended mode after serialization, including on existing exports.
            os.chmod(temporary, mode)
            os.fsync(written.fileno())
        # Staging beside the selected file keeps this replacement on one
        # filesystem, including when the destination already exists.
        os.replace(temporary, destination)
    return str(destination)
