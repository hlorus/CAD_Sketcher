"""Test incremental curve addition - can we add curves one at a time?"""
import bpy
import numpy as np

print("=" * 60)
print("INCREMENTAL CURVE ADDITION TEST")
print("=" * 60)

curve_data = bpy.data.hair_curves.new("IncrTest")
obj = bpy.data.objects.new("IncrTestObj", curve_data)
bpy.context.scene.collection.objects.link(obj)

# Add first line
print("\n1. Add first line (2 points)")
curve_data.add_curves([2])
curve_data.points[0].position = (0.0, 0.0, 0.0)
curve_data.points[1].position = (1.0, 0.0, 0.0)
print(f"   Curves: {len(curve_data.curves)}, Points: {len(curve_data.points)}")
for i in range(len(curve_data.points)):
    print(f"   Point {i}: {tuple(curve_data.points[i].position)}")

# Add second line incrementally
print("\n2. Add second line (2 more points)")
curve_data.add_curves([2])
print(f"   Curves: {len(curve_data.curves)}, Points: {len(curve_data.points)}")

# Check if first line's points are preserved
print("   First line points preserved?")
for i in range(len(curve_data.points)):
    print(f"   Point {i}: {tuple(curve_data.points[i].position)}")

# Set second line points
curve_data.points[2].position = (1.0, 0.0, 0.0)
curve_data.points[3].position = (1.0, 1.0, 0.0)
print("\n   After setting second line:")
for i in range(len(curve_data.points)):
    print(f"   Point {i}: {tuple(curve_data.points[i].position)}")

# Add attribute and check it survives adding more curves
print("\n3. Add attribute, then add more curves")
attr = curve_data.attributes.new("entity_index", type='INT', domain='POINT')
for i in range(len(curve_data.points)):
    attr.data[i].value = (i + 1) * 100
print(f"   Attributes before: {[attr.data[i].value for i in range(len(attr.data))]}")

# Add third curve
curve_data.add_curves([3])  # 3-point curve (for an arc)
print(f"   Curves: {len(curve_data.curves)}, Points: {len(curve_data.points)}")

# Check if attribute survived and what values new points have
attr = curve_data.attributes.get("entity_index")
if attr:
    vals = [attr.data[i].value for i in range(len(attr.data))]
    print(f"   Attributes after: {vals}")
    print(f"   Old values preserved: {vals[:4] == [100, 200, 300, 400]}")
else:
    print("   ATTRIBUTE LOST!")

# Check if positions survived
print("\n4. Verify all positions after incremental adds:")
for i in range(len(curve_data.points)):
    print(f"   Point {i}: {tuple(curve_data.points[i].position)}")

# Test curve structure
print("\n5. Curve structure:")
for i, c in enumerate(curve_data.curves):
    print(f"   Curve {i}: first_point={c.first_point_index}, n_points={c.points_length}")

# Test: can we set curve type after adding more curves?
print("\n6. Set curve types incrementally")
try:
    # Set all to BEZIER
    curve_data.set_types(type="BEZIER")
    print("   set_types(BEZIER) works after incremental adds")
except Exception as e:
    print(f"   FAILED: {e}")

# Cleanup
bpy.data.objects.remove(obj)
bpy.data.hair_curves.remove(curve_data)

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
