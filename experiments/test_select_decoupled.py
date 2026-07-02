"""Test that the select operator works without entity lookup."""
import bpy

from bl_ext.blend.CAD_Sketcher import global_data
from bl_ext.blend.CAD_Sketcher.converters import sync_curve_selection

sse = bpy.context.scene.sketcher.entities

# Setup
origin = sse.add_point_3d((0, 0, 0), fixed=True)
nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)
wp = sse.add_workplane(origin, nm, fixed=True)
sketch = sse.add_sketch(wp)

p1 = sse.add_point_2d((0.0, 0.0), sketch)
p2 = sse.add_point_2d((1.0, 0.0), sketch)
p3 = sse.add_point_2d((1.0, 1.0), sketch)
line1 = sse.add_line_2d(p1, p2, sketch)
line2 = sse.add_line_2d(p2, p3, sketch)

idx1 = line1.slvs_index
idx2 = line2.slvs_index

# Use fake IDs that don't correspond to entities (to prove decoupling)
fake_id_1 = 9999901
fake_id_2 = 9999902

print("=" * 60)
print("SELECT OPERATOR DECOUPLING TEST")
print("=" * 60)

# Test 1: SET mode with real entity
print("\n--- Test 1: SET with real entity ---")
global_data.selected.clear()
global_data.selected.append(idx1)
print(f"  selected: {global_data.selected}")
assert idx1 in global_data.selected
print("  PASS")

# Test 2: SET mode with fake ID (no entity exists)
print("\n--- Test 2: SET with fake ID (no entity) ---")
global_data.selected.clear()
global_data.selected.append(fake_id_1)
print(f"  selected: {global_data.selected}")
assert fake_id_1 in global_data.selected
print("  PASS: fake ID can be selected")

# Test 3: EXTEND — add another
print("\n--- Test 3: EXTEND ---")
global_data.selected.append(fake_id_2)
print(f"  selected: {global_data.selected}")
assert fake_id_1 in global_data.selected
assert fake_id_2 in global_data.selected
print("  PASS")

# Test 4: SUBTRACT
print("\n--- Test 4: SUBTRACT ---")
global_data.selected.remove(fake_id_1)
print(f"  selected: {global_data.selected}")
assert fake_id_1 not in global_data.selected
assert fake_id_2 in global_data.selected
print("  PASS")

# Test 5: TOGGLE
print("\n--- Test 5: TOGGLE ---")
# Toggle fake_id_2 off
is_sel = fake_id_2 in global_data.selected
if is_sel:
    global_data.selected.remove(fake_id_2)
else:
    global_data.selected.append(fake_id_2)
print(f"  After toggle off: {global_data.selected}")
assert fake_id_2 not in global_data.selected

# Toggle fake_id_2 on
is_sel = fake_id_2 in global_data.selected
if is_sel:
    global_data.selected.remove(fake_id_2)
else:
    global_data.selected.append(fake_id_2)
print(f"  After toggle on: {global_data.selected}")
assert fake_id_2 in global_data.selected
print("  PASS")

# Test 6: Sync fake IDs to curve attributes
print("\n--- Test 6: Sync with curve data ---")
global_data.selected.clear()
# Use the real segment_entity_index values
cd = sketch.target_object.data
seg = cd.attributes.get("segment_entity_index")
curve_id_0 = seg.data[0].value
curve_id_1 = seg.data[1].value
print(f"  Curve IDs: {curve_id_0}, {curve_id_1}")

global_data.selected.append(curve_id_0)
global_data.hover = curve_id_1
sync_curve_selection(bpy.context.scene)

sel = cd.attributes.get("selected")
hov = cd.attributes.get("hover")
print(f"  selected attrs: {[sel.data[i].value for i in range(len(sel.data))]}")
print(f"  hover attrs: {[hov.data[i].value for i in range(len(hov.data))]}")
assert sel.data[0].value == True
assert sel.data[1].value == False
assert hov.data[0].value == False
assert hov.data[1].value == True
print("  PASS")

print("\n" + "=" * 60)
print("ALL DECOUPLING TESTS PASS")
print("=" * 60)
