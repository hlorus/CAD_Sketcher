The geometry that is used in the extension isn't native blender geometry, that means
blender doesn't know anything about it and native tools cannot work with it.
So in order to further process drawn shapes they have to be converted to a native type first.

> **INFO:** There are some [limitations](integration.md#limitations) to keep in mind when converting.

## Convert Types
When a sketch is active you can choose the convert type for it in the sidebar. By
default this is set to None which means no native geometry will be created.

> **INFO:** Setting this to something other than None will disable the visibility
of the sketch so that it will only show when it's active

### Bezier Converter
Converts the sketch to a bezier curve.

### Mesh Converter
Converts the sketch to a mesh. This doesn't convert to mesh directly
but rather uses the bezier converter and the native [to_mesh()](https://docs.blender.org/api/current/bpy.types.Object.html#bpy.types.Object.to_mesh) function behind the scene.

## Fill Shape
Some converters support the Fill Shape setting. When this isn't set the resulting geometry
won't have surfaces at all but rather just edges.

> **INFO:** The setting toggles the bezier's fill_mode option between None and Front

## Limitations
### 3D Geometry
Conversion requires a sketch, the extension currently doesn't support creating 3D sketches
and is therefor limited to the conversion of 2D entities.

### Non-Persistent Geometry
The output geometry will be re-generated each time a sketch is deactivated. Converters
don't take any modifications that are done after the conversion into account.

> **INFO:** Indices of created geometry elements aren't persistent. Referencing
such elements isn't currently supported.

In order to further process geometry after the conversion make sure you do this in
a procedural way, otherwise things might break when editing the sketch.

### Path Connections
Converters parse the geometry depending on shared start-/endpoints, connections created
with coincident constraints or overlaps between entities aren't interpreted as a connection.

### Precision
Bezier curves cannot exactly represent a circle. Converted curves are only an approximation to an exact
arc or circle. Converted meshes also suffer from that error since the mesh convert type is currently based on the bezier converter.

## Best Practices
To avoid running into such limitations try to follow these practices:

- Connect entities by sharing a start-/endpoint, avoid using the coincident constraint
to connect entities that are part of a path that you intend to later convert.
- Use the construction option whenever you create geometry that you don't intend to convert.
- If you have alot of construction geometry create a dedicated sketch that is used for
construction only. Then create another sketch on the same workplane and reference
entities from the construction sketch.
- If the Fill Shape option is set make sure the drawn shape is a closed path and
that multiple closed paths don't overlap each other.
