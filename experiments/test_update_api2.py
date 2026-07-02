"""Test which update methods actually trigger GN re-evaluation."""
import bpy
import numpy as np

# Setup
curve_data = bpy.data.hair_curves.new("GNTest")
obj = bpy.data.objects.new("GNTestObj", curve_data)
bpy.context.scene.collection.objects.link(obj)

curve_data.add_curves([2])
curve_data.set_types(type="BEZIER")
curve_data.points[0].position = (0.0, 0.0, 0.0)
curve_data.points[1].position = (1.0, 0.0, 0.0)

# Initial depsgraph eval
dg = bpy.context.evaluated_depsgraph_get()
dg.update()

def check_eval_position(label):
    """Check if the evaluated object sees the position change."""
    dg = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(dg)
    eval_data = eval_obj.data
    if len(eval_data.points) > 0:
        pos = tuple(eval_data.points[1].position)
        print(f"  {label}: eval pos = {pos}")
    else:
        print(f"  {label}: no eval points")

# Baseline
check_eval_position("baseline")

# Test 1: per-point assignment + update_tag
print("\n--- Test 1: per-point + update_tag ---")
curve_data.points[1].position = (2.0, 0.0, 0.0)
curve_data.update_tag()
check_eval_position("after update_tag on data")

obj.update_tag()
check_eval_position("after update_tag on obj")

dg.update()
check_eval_position("after dg.update()")

# Test 2: foreach_set + update_tag
print("\n--- Test 2: foreach_set + update_tag ---")
pos = np.array([0, 0, 0, 3, 0, 0], dtype=np.float32)
curve_data.points.foreach_set("position", pos)
curve_data.update_tag()
obj.update_tag()
dg = bpy.context.evaluated_depsgraph_get()
dg.update()
check_eval_position("foreach_set + tags + dg.update")

# Test 3: view_layer.update
print("\n--- Test 3: view_layer.update ---")
curve_data.points[1].position = (4.0, 0.0, 0.0)
bpy.context.view_layer.update()
check_eval_position("view_layer.update")

# Test 4: reassign data
print("\n--- Test 4: reassign obj.data ---")
curve_data.points[1].position = (5.0, 0.0, 0.0)
obj.data = curve_data  # force reassignment
dg = bpy.context.evaluated_depsgraph_get()
dg.update()
check_eval_position("reassign obj.data")

# Test 5: modifier toggle
print("\n--- Test 5: check without modifier ---")
print(f"  Modifiers: {[m.name for m in obj.modifiers]}")
# Even without GN modifier, does eval see changes?
check_eval_position("no modifier check")

# Cleanup
bpy.data.objects.remove(obj)
bpy.data.hair_curves.remove(curve_data)
