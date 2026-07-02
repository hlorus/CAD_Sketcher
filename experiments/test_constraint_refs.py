"""Test that constraints use CurveRef for placements, init_props, matrix_basis."""
import bpy
from mathutils import Matrix

scene = bpy.context.scene
sse = scene.sketcher.entities
ssc = scene.sketcher.constraints

sse.ensure_origin_elements(bpy.context)
wp = sse.origin_plane_XY
sketch = sse.add_sketch(wp)
scene.sketcher.active_sketch_i = sketch.slvs_index

# Create geometry
p0 = sse.add_point_2d((0, 0), sketch, fixed=True)
p1 = sse.add_point_2d((3, 0), sketch)
p2 = sse.add_point_2d((0, 4), sketch)
line1 = sse.add_line_2d(p0, p1, sketch)
line2 = sse.add_line_2d(p0, p2, sketch)

# Build native curves
from bl_ext.blend.CAD_Sketcher.converters import (
    DirectConverter, get_curve_id_for_entity, ensure_sketch_curve_object,
)
curve_data = ensure_sketch_curve_object(sketch)
conv = DirectConverter(scene, sketch)
conv.to_bezier(curve_data)

# Map entity → curve_id
cid_p0 = get_curve_id_for_entity(sketch, p0.slvs_index)
cid_p1 = get_curve_id_for_entity(sketch, p1.slvs_index)
cid_p2 = get_curve_id_for_entity(sketch, p2.slvs_index)
cid_l1 = get_curve_id_for_entity(sketch, line1.slvs_index)
cid_l2 = get_curve_id_for_entity(sketch, line2.slvs_index)

print(f"curve_ids: p0={cid_p0}, p1={cid_p1}, p2={cid_p2}, l1={cid_l1}, l2={cid_l2}")

# --- Test distance constraint ---
print("\n=== Distance ===")
c_dist = ssc.add_distance(p0, p1, sketch=sketch, init=False)
c_dist.curve_id_1 = cid_p0
c_dist.curve_id_2 = cid_p1
c_dist.assign_init_props()

r1 = c_dist.ref(1)
r2 = c_dist.ref(2)
print(f"ref(1)={r1}, ref(2)={r2}")
assert r1 is not None and r1.valid
assert r2 is not None and r2.valid

from bl_ext.blend.CAD_Sketcher.model.curve_ref import PointRef
assert isinstance(r1, PointRef), f"Expected PointRef, got {type(r1)}"

mb = c_dist.matrix_basis()
print(f"matrix_basis: {mb}")
assert mb != Matrix(), "matrix_basis should not be identity"

print(f"value={c_dist.value:.4f}")
assert abs(c_dist.value - 3.0) < 0.01, f"Expected ~3.0, got {c_dist.value}"

# --- Test angle constraint ---
print("\n=== Angle ===")
c_angle = ssc.add_angle(line1, line2, sketch=sketch, init=False)
c_angle.curve_id_1 = cid_l1
c_angle.curve_id_2 = cid_l2
c_angle.assign_init_props()

r1 = c_angle.ref(1)
r2 = c_angle.ref(2)
print(f"ref(1)={r1}, ref(2)={r2}")
assert r1 is not None and r1.valid

from bl_ext.blend.CAD_Sketcher.model.curve_ref import LineRef
assert isinstance(r1, LineRef), f"Expected LineRef, got {type(r1)}"

mb = c_angle.matrix_basis()
print(f"matrix_basis: {mb}")
assert mb != Matrix(), "matrix_basis should not be identity"

import math
print(f"value={math.degrees(c_angle.value):.1f} deg")
assert abs(math.degrees(c_angle.value) - 90.0) < 1.0

# --- Test horizontal constraint placements ---
print("\n=== Horizontal ===")
c_horiz = ssc.add_horizontal(line1, sketch=sketch)
c_horiz.curve_id_1 = cid_l1

pl = c_horiz.placements()
print(f"placements={pl}")
assert len(pl) == 1
from bl_ext.blend.CAD_Sketcher.model.curve_ref import CurveRef
assert isinstance(pl[0], CurveRef), f"Expected CurveRef, got {type(pl[0])}"

# --- Test parallel constraint placements ---
print("\n=== Parallel ===")
c_par = ssc.add_parallel(line1, line2, sketch=sketch)
c_par.curve_id_1 = cid_l1
c_par.curve_id_2 = cid_l2

pl = c_par.placements()
print(f"placements={pl}")
assert len(pl) == 2
assert all(isinstance(p, CurveRef) for p in pl)

# --- Test line distance (line length) ---
print("\n=== Line Length ===")
c_len = ssc.add_distance(line1, None, sketch=sketch, init=False)
c_len.curve_id_1 = cid_l1
# Re-init now that curve_id is set
c_len.assign_init_props()

r1 = c_len.ref(1)
print(f"ref(1)={r1}")
assert isinstance(r1, LineRef)

mb = c_len.matrix_basis()
print(f"matrix_basis: {mb}")
print(f"value={c_len.value:.4f}")
assert abs(c_len.value - 3.0) < 0.01

print("\nAll tests PASSED")
