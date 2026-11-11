# Export IFC profiles

In **Edit > Preferences > Add-ons > CAD Sketcher**, enable **Integrations >
IFC Profile Export**. The optional exporter stays hidden until you enable it.
Enter a two-dimensional sketch, solve it, and choose **File > Export > CAD
Sketcher IFC Profiles (.ifc)**. The exporter writes named area profiles in an
IFC4 profile library, including contained holes.

IfcOpenShell must be installed in Blender's Python environment. The add-on
remains usable without it; the export command reports a missing dependency
without changing an existing file.

## Geometry and units

Profiles use the sketch's local XY coordinates. Scene **Unit Scale** converts
coordinates and radii to metres exactly once. The IFC library declares metres.
Workplane translation and rotation are omitted because these are reusable
profile definitions, not placed building elements. A scaled or sheared
workplane is rejected rather than silently changing dimensions.

Connect line and arc endpoints using shared points or explicit point-coincidence
constraints. Construction geometry and standalone points are excluded. Lines
remain straight; circles retain their centers and radii. Circular arcs retain
their native circle and angular span as parameter-trimmed IFC curves. The
exporter never substitutes a polygon approximation for curved geometry.

Separate outer outlines become separate profiles. Directly contained boundaries
become holes in an IfcArbitraryProfileDefWithVoids. A further island inside a
hole becomes a separate profile. Drawing order does not decide which circle is
the outer boundary. Multiple profiles use the sketch name and storage-order
number; a single profile keeps the sketch name.

## Rejected geometry

Open or branched paths, zero-area or self-intersecting boundaries, touching or
overlapping boundaries, unknown curve types, free-3D sketches and unsolved
geometry are rejected. Endpoint connectivity comes from native point identity
and explicit constraints, never a proximity weld. The small numerical difference
between a solved float32 arc endpoint and its analytic circle must fit within
the IFC context precision of 0.00000001 metre. Larger gaps are rejected.

All boundaries and void relationships are validated again after unit conversion.
A failed geometry conversion or write leaves the previous file intact. Correct
the reported geometry and export again.

This is a bounded profile-library export. IFC import, editable round trips, IFC
constraints and Bonsai building-element integration are separate features.
