A sketch is a Curves object holding the geometry you draw, and nothing else. What
you see as a solid is its **body**: a mesh object whose modifier stack reads the
sketch, converts it to mesh, and then extrudes, revolves and booleans it.

That makes the result ordinary Blender geometry. You can apply the stack, export
it, convert it, or feed it to any mesh tool, and it keeps following the sketch
until you do.

## The body's stack

Select a body and its modifiers are in the Properties editor as usual:

- **CAD Sketcher Convert** &mdash; reads the sketch and meshes it.
    - **Sketch** &mdash; the Curves object it is built from.
    - **Fill** &mdash; surface closed shapes, rather than leaving just edges.
    - **Angular Resolution** &mdash; the largest angle per edge when arcs and
      circles are meshed. The default comes from the add-on preferences.
- **Extrude**, **Revolve**, **Boolean**, **Array** &mdash; added by the tools, in
  the order you applied them, and reorderable like any modifier.

Construction geometry and degenerate segments are dropped during the conversion,
so they never reach the mesh.

## Limitations

### Precision

Arcs and circles are tessellated, so a meshed circle is a polygon: the edge count
follows Angular Resolution. Lower it where a curve needs to be smoother.

### Element indices

Vertex and face indices of the generated mesh are not stable across edits, so
anything referencing them by index can break when the sketch changes. Work
procedurally on top of the body instead.

### Paths

The conversion joins geometry by shared start/end points. Entities merely held
together by a coincident constraint, or overlapping, are not read as one path.

## Best practices

- Connect entities by sharing a start/end point rather than coinciding two
  separate points, for anything you intend to fill or extrude.
- Mark geometry you do not want in the result as construction.
- If you have a lot of construction geometry, put it in its own sketch and
  reference it from a second sketch on the same workplane.
- With Fill on, draw closed paths and avoid overlapping them.
