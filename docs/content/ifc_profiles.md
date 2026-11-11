# Export straight-line IFC profiles

Enter a two-dimensional sketch, solve it, and choose **File > Export > CAD
Sketcher IFC Profiles (.ifc)**. The exporter writes each separate closed outline
as a named `IfcArbitraryClosedProfileDef` in an IFC4 profile library.

IfcOpenShell must be installed in the Python environment used by Blender. The
add-on remains usable without it; the export command reports a missing
dependency without changing an existing file.

## Geometry and units

Profiles use the sketch's local XY coordinates. Scene **Unit Scale** converts
those coordinates to metres, and the IFC library declares metres explicitly.
The sketch's workplane translation, rotation and object placement are not
included: these are reusable profile definitions, not placed building elements
or exported extrusions.

Connect line endpoints using shared points or explicit point-coincidence
constraints. Construction geometry and standalone points are excluded. Separate,
disjoint outlines become separate profiles; when there is more than one, their
names use the sketch name followed by their storage-order number.

The exporter rejects open or branched paths, zero-area or self-intersecting
boundaries, touching/overlapping outlines, nested outlines (holes), arcs,
circles, free-3D sketches, and unsolved geometry. It does not approximate curves,
close a gap by distance, or silently drop an unsupported outline. Correct the
reported geometry and export again. A failed export leaves the previous file
intact.

This is a bounded profile-library export. IFC import, editable round trips,
curved profiles, voids, IFC constraints and Bonsai building-element integration
are separate features.
