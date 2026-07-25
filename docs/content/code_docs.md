# Code Documentation

CAD Sketcher stores its data in **two coexisting layers**. Knowing which layer
owns what is the key to reading the codebase.

| Layer | Owns | Identity | Accessors |
|-------|------|----------|-----------|
| **Native curves** | 2D sketch geometry (points, lines, arcs, circles) | `curve_id` (128-bit UUID) | `CurveRef` and subclasses |
| **Entity PropertyGroups** | origin elements, 3D entities, workplanes, sketches, and the type tokens used for state matching | `slvs_index` (int) | `SlvsEntities.get(index)` |

The native-curve layer is the **source of truth for everything drawn inside a
sketch**. The entity layer is the older Solvespace-style data model; it is still
live for the pieces that were not moved onto curves (origins, 3D, workplanes,
sketches) and for the `SlvsPoint2D` / `SlvsLine2D` / `SlvsArc` / `SlvsCircle`
classes, which now serve mainly as **type tokens** (e.g. a state declares
`types=(SlvsPoint2D,)` and a `PointRef` is matched against it).

## Native Curve Model

A sketch is backed by a Blender **Curves** data-block (`bpy.types.Curves`). Each
sketch entity is one curve in that object, and its metadata lives in **curve
attributes** rather than in a PropertyGroup:

- `sketch_type` — what the curve represents (point, line, arc, circle).
- `curve_id` — the entity's stable identity (see below).
- relationship attributes — `start_point_id`, `end_point_id`, `center_point_id`
  link a segment to its defining points (by their `curve_id`).

Because Blender re-indexes curves whenever one is removed, **positional indices
are not stable** — always refer to an entity by its `curve_id`.

### curve_id (UUID identity)

`curve_id` is a 128-bit UUID. On disk it is stored as hidden `INT32_2D`
sub-attributes (`curve_id_lo` / `curve_id_hi`, and likewise for the
`*_point_id` relationship fields) so it survives Blender's native
delete/duplicate. In Python it is handled as a 32-character lowercase hex
string, which is what appears in `global_data.selected`, `global_data.pick_map`,
and the constraint `curve_id_N` properties.

Helpers live in `utilities/curve_data.py`:

- `new_uuid()` — mint a fresh id.
- `get_uuid(cd, field, i)` / `set_uuid(...)` — read/write a single field.
- `read_uuid_list(cd, field)` — **bulk** read via `foreach_get`; use this in
  draw/hot loops, never `get_uuid` per curve.

### CurveRef accessors

Rather than manipulate raw attributes, code works through lightweight accessor
objects in `model/curve_ref.py`:

- `curve_ref(sketch, curve_id)` — factory returning the right typed accessor.
- `PointRef`, `LineRef`, `ArcRef`, `CircleRef` — typed views exposing `.co`,
  `.p1` / `.p2`, `.ct`, `.radius`, etc., and a `.create(...)` classmethod.

An accessor is just `(sketch, curve_id)`; it resolves live data on each access,
so it stays valid across re-indexing as long as the `curve_id` exists.

### Workplanes as empties

A workplane can be any Blender Object: its `matrix_world` is the workplane
transform, and the sketch's Curves object is parented to it. `Entity2D.wp_matrix`
resolves the workplane from the empty / parent / entity.

### Self-healing

Native edit-mode operations (delete/duplicate in the curves object) can leave
geometry in an inconsistent state. `utilities/validate.py`, run from the
depsgraph handler (gated by a signature check, skipped in Edit Mode), mints ids
for empty/duplicate curves, removes degenerate segments, and prunes constraints
that reference no existing curve. Because `curve_id`s survive native operations,
no fingerprint/backup is needed.

## Entity Model (legacy layer)

The root of the entity data lives in `SketcherProps`, registered on the Scene:

```
bpy.context.scene.sketcher
  - entities      (SlvsEntities)
      - points3D, lines3D, workplanes, sketches, ...
  - constraints   (SlvsConstraints)
```

Entities inherit from `SlvsGenericEntity` and are identified by a unique
`entity.slvs_index`, assigned by the `add_*` methods on `SlvsEntities`. Pointers
are stored as an `IntProperty` (via `slvs_entity_pointer`, which adds
getter/setters that resolve `entities.get(index)`).

This layer is still used for:

- **Origin elements** — `ensure_origin_elements` creates the origin point, axes
  and the XY/XZ/YZ origin planes as entities.
- **3D entities** — `SlvsPoint3D`, `SlvsLine3D`, `SlvsNormal3D`.
- **Workplanes and sketches** — created via `add_workplane` / `add_sketch`.
- **Type identity** — the 2D entity classes are matched against state `types`.

## Constraints

Constraints inherit from `GenericConstraint` and, unlike entities, render and
handle selection through Blender's [Gizmo API](https://docs.blender.org/api/current/bpy.types.Gizmo.html)
rather than a custom draw batch.

A sketch's constraints are stored on the Curves data-block
(`sketch_constraints`). Each constraint references its operands by their curve
ids through `curve_id_1` / `curve_id_2` / `curve_id_3` `StringProperty`s — note
that PropertyGroups are **not** affected by the string-attribute drop that
native curve removal causes, so these references are safe.

## Drawing

Geometry is drawn in the viewport with the [GPU Module](https://docs.blender.org/api/current/gpu.html).
The draw handler must be registered on the viewport type; because the context at
registration time is limited, the extension defers this with an
[Application Timer](https://docs.blender.org/api/current/bpy.app.timers.html)
shortly after the addon registers.

> **NOTE:** In-place edits of curve point positions do **not** trigger a Geometry
> Nodes re-evaluation — call `refresh_curve_geometry()` after changing positions
> directly.

## Selection

Selection uses the classic
[offscreen id-buffer](http://www.opengl-tutorial.org/miscellaneous/clicking-on-objects/picking-with-an-opengl-hack/)
technique, but keyed to curves rather than `slvs_index`:

- `_draw_curves_id_buffer` (in `draw_handler.py`) draws every visible curve into
  an offscreen buffer, coloring it by a per-frame **pick index** via
  `index_to_rgb`, and records `global_data.pick_map[pick_index] = curve_id`.
- The `VIEW3D_GT_slvs_preselection` gizmo reads the pixel under the cursor and
  writes the resolved `curve_id` to `global_data.hover`.
- `global_data.selected` holds the list of selected `curve_id` hex strings.

## Solver

The extension uses the [Python binding](https://pypi.org/project/py-slvs/) of
[Solvespace](https://solvespace.com/index.pl). Solver data is not persistent: a
fresh `slvs.System` is built on every solve.

For sketch geometry this is driven by **`CurveSolver`** (`curve_solver.py`),
which reads the curve attributes directly (`sketch_type`, positions, relationship
ids) and adds the corresponding Solvespace entities — see
`create_slvs_data_from_curves` / `solve_sketch_from_curves`. Constraints add
themselves to the system. On success the solved positions are written back to the
curve data. (3D entities still implement their own `create_slvs_data` /
`update_from_slvs`.)

You can explore the solver interactively from Blender's Python console:

```python
import slvs
sys = slvs.System()
```

## Interaction

Most viewport tools are **stateful operators** — a declarative framework for
multi-step tools (pick/place points, enter values). The behavior is documented
in the [interaction chapter](interaction_system.md); the code lives in
`stateful_operator/` with extension-specific types added by `GenericEntityOp`
(`operators/base_stateful.py`) and 2D specifics in `Operator2d`
(`operators/base_2d.py`). See the [development guide](development.md) for how to
drive and test these without a modal region.

## Gotchas

### `remove_curves` drops STRING attributes

Removing curves (including native edit-mode delete) drops **all STRING**
attributes on the Curves data-block, on both domains. `INT` / `BOOL` / `FLOAT`
attributes survive and re-index. This is why identity lives in `INT32_2D`
sub-attributes, not strings, and why the only remaining STRING attribute
(`name`, cosmetic) is snapshotted and restored around removal.

### Stale attribute wrappers

After `remove_curves`, **re-fetch** the attribute wrapper via
`curve_data.attributes.get(...)` — a wrapper obtained before the removal reads
stale data.

### Don't resolve ids in hot loops

`get_uuid` performs two `attributes.get()` calls per invocation. Never call it
per curve inside a draw or id-buffer loop; use `read_uuid_list` for a single bulk
read instead.
