# MCP sketch authoring — agent instructions

## Role & objective

You are driving CAD Sketcher through MCP in a live Blender session. Produce
**fully constrained** sketches (`solver_state == "OKAY"`, preferably DOF 0) that
match design intent and convert cleanly later.

## Core parametric philosophy

Prefer geometric constraints (Horizontal, Vertical, Equal, Perpendicular,
Tangent, Midpoint used **correctly**) over stacking many hard dimensions.

But: **a solved `OKAY` sketch beats an elegant `INCONSISTENT` one.** If a
clever constraint pattern fails validation, fall back to a proven pattern (below)
and verify with coordinates + screenshot.

- **No duplicated dimensions:** same-size holes → one `Diameter` + `Equal`, not
  four diameters.
- **Design intent:** measure what a machinist would measure (centered pattern,
  edge clearance). Prefer centering via axes/origin over arbitrary corner
  stacks — *when the solver accepts it*.
- **Path connections:** closed profiles must **share endpoints** between segments.
  Do not join separate points with Coincident and expect mesh fill to work.
- **Construction geometry:** layout-only lines/points → `construction=True`.
- **Sketch separation:** heavy layout vs final profile can be split across sketches
  on the same workplane when needed.

## Standard operating procedure

1. **Anchoring** — fix a datum (corner or origin point), `ensure_origin_elements`.
2. **Rough topology** — shared endpoints, approximate placement (`index_reference=True`).
3. **Geometric constraints** — H/V, Equal, etc.
4. **Dimensional constraints** — overall size, then feature sizes.
5. **`solve` + validate** — must be `OKAY`. Print coords. Screenshot.
6. **Interior features** (holes, etc.) — second phase after the outer profile is
   healthy (see two-phase rule).

---

## Technical rules (MCP / Solvespace)

### Setup

1. Blender GUI (not `-b`); CAD Sketcher + `slvs` loaded.
2. Sketcher → **MCP** → Start Server (**9877**).
3. Cursor `cad-sketcher` MCP connected (`blender` MCP on 9876 for screenshots).

### Units

- Check `scene.unit_settings` (default metric **meters**).
- 10 cm → `0.10`; 1 cm inset → `0.01`; Ø8 mm → radius `0.004`,
  **diameter constraint value `0.008`** (the UI label is diameter, not radius).

### API

Prefer PropertyGroup APIs over modal `bpy.ops.view3d.slvs_*`.
`execute_sketcher_code` injects `bpy`, `context`, `sketcher`, `entities`,
`constraints`.

```python
entities.ensure_origin_elements(context)
sketch = entities.add_sketch(entities.origin_plane_XY)
sketcher.active_sketch = sketch
```

### Stale RNA pointers

Always prefer `index_reference=True` and keep **integer indices**. Resolve with
`entities.get(i)` when needed. Or `context.view_layer.update()` between phases.

Failure signatures:

- `'NoneType' ... 'py_data'` / `'is_line'`
- `Cannot create constraint between one entity itself`

**If a session has already returned `INCONSISTENT` / partial wipes:** create a
**new Scene** and rebuild. Do not keep patching a polluted sketcher collection.

### Signed vs unsigned distances (critical)

Point–to–line `add_distance(point, line)` is **side-ambiguous**. The solver may
place the point inside or outside at the same distance.

**Symptom:** hole seeded at `±0.04` ends at `±0.06` (outside a `±0.05` plate).

Do **not** trust seeds alone. Prefer two-phase construction (below) or
side-unambiguous point–point construction with a post-solve coord check.
Guessing `flip` without verifying is how holes end up outside.

### Midpoint footgun (critical)

`constraints.add_midpoint(point, line)` means: **`point` is the midpoint of
`line`**.

**Wrong (does not center a square about the origin):**

```python
# Makes `center` the midpoint of `bottom` → bottom edge passes THROUGH the origin
constraints.add_midpoint(center, bottom, sketch)
```

**Correct intuition for a plate centered on the origin:** the midpoint of the
*bottom* edge should lie on the **vertical centerline** (x=0), at y = −half —
it is **not** the plate’s geometric center. Don’t use Midpoint(center, outer_edge)
to “center the plate.”

### Patterns that look right but stay INCONSISTENT

These failed in practice (coords ok, `solver_state == "INCONSISTENT"`):

- Pinning every corner/hole from a fixed center with many point–point H/V +
  distance helpers, *plus* H/V on outer lines (easy to overconstrain).
- Rebuilding on a scene after multiple failed wipe/retry cycles.

**Rule:** `INCONSISTENT` with pretty coordinates is still a **failed** sketch.
Simplify until `OKAY`.

### Two-phase construction (reliable for inset holes)

1. Build outer profile only → `solve` → must print `True OKAY`.
2. Add hole centers at **known interior** coordinates with `fixed=True`.
3. Circles: one `add_normal_2d`, circles on those centers, `Equal` + one
   `Diameter` → `solve` again → `OKAY`.

Proven outer profile for an axis-aligned square:

```python
# shared endpoints; SW fixed as datum
sw = entities.add_point_2d((-half, -half), sketch, fixed=True, index_reference=True)
se = entities.add_point_2d(( half, -half), sketch, index_reference=True)
ne = entities.add_point_2d(( half,  half), sketch, index_reference=True)
nw = entities.add_point_2d((-half,  half), sketch, index_reference=True)
bottom = entities.add_line_2d(sw, se, sketch, index_reference=True)
right  = entities.add_line_2d(se, ne, sketch, index_reference=True)
top    = entities.add_line_2d(ne, nw, sketch, index_reference=True)
left   = entities.add_line_2d(nw, sw, sketch, index_reference=True)
constraints.add_horizontal(bottom, sketch=sketch)
constraints.add_horizontal(top, sketch=sketch)
constraints.add_vertical(right, sketch=sketch)
constraints.add_vertical(left, sketch=sketch)
constraints.add_equal(bottom, right, sketch)
constraints.add_distance(sw, se, sketch).value = side  # e.g. 0.10
assert sketch.solve(context) and sketch.solver_state == "OKAY"
```

Then holes (10 cm plate, 1 cm edge clearance → centers at `±0.04`):

```python
inset = half - margin  # 0.05 - 0.01
cts = [
    entities.add_point_2d((-inset, -inset), sketch, fixed=True, index_reference=True),
    entities.add_point_2d(( inset, -inset), sketch, fixed=True, index_reference=True),
    entities.add_point_2d(( inset,  inset), sketch, fixed=True, index_reference=True),
    entities.add_point_2d((-inset,  inset), sketch, fixed=True, index_reference=True),
]
nm = entities.add_normal_2d(sketch, index_reference=True)
c0 = entities.add_circle(nm, cts[0], radius, sketch, index_reference=True)
# ... c1,c2,c3 ...
constraints.add_equal(c0, c1, sketch)  # etc.
constraints.add_diameter(c0, sketch).value = 2 * radius  # Ø, not radius
assert sketch.solve(context) and sketch.solver_state == "OKAY"
```

### Circles

- One `add_normal_2d(sketch)` then `add_circle(nm, center_index, radius, ...)`.
- Diameter constraint `.value` is the **diameter**.
- Prefer `Equal` across holes + a single diameter.

### Validation checklist (mandatory)

After each phase:

```python
ok = sketch.solve(context)
print(ok, sketch.solver_state, sketch.dof)
for e in entities.all:
    if getattr(e, "sketch_i", -1) != sketch.slvs_index:
        continue
    if e.type == "SlvsPoint2D" and not e.construction:
        print(e.slvs_index, float(e.co.x), float(e.co.y), e.fixed)
```

Then screenshot. For an inset pattern:

- `|hole_x| < |corner_x|` and `|hole_y| < |corner_y|` (holes **inside**).
- Edge clearance ≈ margin; diameter label ≈ specified Ø.

### Cleanup

Wipe sketch fully (constraints → entities → sketch) **or** start a new Scene.
Never layer retries on a failing sketch.

### Tooling map

| Goal | Use |
|------|-----|
| Sketch / constraints / solve | `cad-sketcher` MCP (9877) |
| Screenshot / scene | `blender` MCP (9876) |
| Multi-step builds | `execute_sketcher_code` |

## Worked example: 10×10 cm plate, Ø8 mm holes, 1 cm from edges

| | Good | Bad |
|--|------|-----|
| Corners | `(±0.05, ±0.05)` | — |
| Hole centers | `(±0.04, ±0.04)` inside | `(±0.06, ±0.06)` outside |
| Hole size | diameter value `0.008` | treating `0.008` as radius |
| Solve | `OKAY`, DOF 0 | `INCONSISTENT` even if coords look fine |

**Bad patterns already observed:** point–line inset without verifying side;
`Midpoint(center, outer_edge)` to “center” a plate; axis-helper overconstraint
from a fixed center; rebuilding on a polluted scene after failed attempts.
