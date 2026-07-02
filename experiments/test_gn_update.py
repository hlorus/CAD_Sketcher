"""Test different methods to trigger GN modifier re-evaluation.

Run interactively in Blender (not headless) to observe visual results.
Paste into Blender text editor and run.
"""
import bpy
import numpy as np
from mathutils import Vector

# Create a test setup
curve_data = bpy.data.hair_curves.new("UpdateTest")
obj = bpy.data.objects.new("UpdateTestObj", curve_data)
bpy.context.scene.collection.objects.link(obj)

# Add a line
curve_data.add_curves([2])
curve_data.set_types(type="BEZIER")
curve_data.points[0].position = (0.0, 0.0, 0.0)
curve_data.points[1].position = (1.0, 0.0, 0.0)

# Add GN modifier
mod = obj.modifiers.new("Test", "NODES")
# Use a simple built-in node group if available, or skip

print("Setup done. Now testing update methods...")

# Move point
curve_data.points[1].position = (2.0, 0.0, 0.0)

# Method 1: update_tag on data
print("Method 1: curve_data.update_tag()")
curve_data.update_tag()

# Method 2: update_tag on object
print("Method 2: obj.update_tag()")
obj.update_tag()

# Method 3: view_layer update
print("Method 3: bpy.context.view_layer.update()")
try:
    bpy.context.view_layer.update()
except:
    print("  Failed")

# Method 4: depsgraph update
print("Method 4: depsgraph.update()")
try:
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
except:
    print("  Failed")

# Method 5: foreach_set
print("Method 5: foreach_set")
positions = np.array([0, 0, 0, 3, 0, 0], dtype=np.float32)
curve_data.points.foreach_set("position", positions)
curve_data.update_tag()

# Method 6: tag with refresh type
print("Method 6: update_tag with refresh")
try:
    obj.update_tag(refresh={'OBJECT', 'DATA'})
except TypeError:
    print("  refresh kwarg not supported, trying without")
    obj.update_tag()

# Method 7: id_tag_update via msgbus
print("Method 7: bpy.msgbus")
try:
    # This might notify Blender of data changes
    pass
except:
    print("  Failed")

# Method 8: toggle modifier to force recalc
print("Method 8: Toggle modifier show_viewport")
if obj.modifiers:
    mod = obj.modifiers[0]
    mod.show_viewport = False
    mod.show_viewport = True

print("\nCheck viewport - did the curve update?")
print(f"Point positions: {[tuple(p.position) for p in curve_data.points]}")
