# API Reference

CAD Sketcher stores data in two layers (see the [code documentation](code_docs.md)).
The **curve model** is the source of truth for 2D sketch geometry; the **entity
model** is the legacy layer, still live for origins, 3D entities, workplanes,
sketches and type identity.

## Curve model

The active accessors for sketch geometry. A reference is a lightweight
`(sketch, curve_id)` view that resolves live curve attributes on each access.

::: CAD_Sketcher.model.sketch_ref.Sketch

::: CAD_Sketcher.model.curve_ref.curve_ref

::: CAD_Sketcher.model.curve_ref.CurveRef

::: CAD_Sketcher.model.curve_ref.PointRef

::: CAD_Sketcher.model.curve_ref.LineRef

::: CAD_Sketcher.model.curve_ref.ArcRef

::: CAD_Sketcher.model.curve_ref.CircleRef

## Entity model (legacy layer)

::: CAD_Sketcher.model.types.SketcherProps

::: CAD_Sketcher.model.types.SlvsEntities

::: CAD_Sketcher.model.types.SlvsConstraints
