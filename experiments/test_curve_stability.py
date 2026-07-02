"""Test if Blender re-indexes curves after removal, and check for stable IDs."""
import bpy

curve_data = bpy.data.hair_curves.new("StabilityTest")
obj = bpy.data.objects.new("StabilityTestObj", curve_data)
bpy.context.scene.collection.objects.link(obj)

# Add 4 curves
curve_data.add_curves([2, 2, 2, 2])

# Set positions to identify each curve
for i in range(4):
    c = curve_data.curves[i]
    curve_data.points[c.points[0].index].position = (float(i), 0, 0)
    curve_data.points[c.points[1].index].position = (float(i), 1, 0)

# Check what's on a curve object
print("=== Curve object properties ===")
c = curve_data.curves[0]
print(f"Type: {type(c)}")
for attr in dir(c):
    if not attr.startswith('_') and not callable(getattr(c, attr, None)):
        try:
            val = getattr(c, attr)
            print(f"  {attr}: {val}")
        except:
            pass

print(f"\n=== CurvePoint properties ===")
p = curve_data.points[0]
print(f"Type: {type(p)}")
for attr in dir(p):
    if not attr.startswith('_') and not callable(getattr(p, attr, None)):
        try:
            val = getattr(p, attr)
            print(f"  {attr}: {val}")
        except:
            pass

# Check curve indices before removal
print(f"\n=== Before removal ===")
for i in range(len(curve_data.curves)):
    c = curve_data.curves[i]
    p0 = curve_data.points[c.points[0].index].position
    print(f"  Curve {i}: first_point={c.first_point_index} pos=({p0.x:.0f},{p0.y:.0f})")

# Remove curve 1 (the one starting at x=1)
print(f"\n=== Removing curve at index 1 ===")
curve_data.remove_curves(indices=[1])

print(f"\n=== After removal ===")
for i in range(len(curve_data.curves)):
    c = curve_data.curves[i]
    p0 = curve_data.points[c.points[0].index].position
    print(f"  Curve {i}: first_point={c.first_point_index} pos=({p0.x:.0f},{p0.y:.0f})")

# Check if there's a stable ID
print(f"\n=== Check for stable ID attributes ===")
print(f"Built-in attributes: {[a.name for a in curve_data.attributes]}")

# Check if there's an .id property on curves
print(f"\n=== Curve slice methods ===")
c = curve_data.curves[0]
methods = [m for m in dir(c) if not m.startswith('_')]
print(f"  {methods}")

# Check if PointerProperty can point to curve geometry
print(f"\n=== bpy.types with 'Curve' in name ===")
for name in dir(bpy.types):
    if 'Curve' in name and not name.startswith('_'):
        print(f"  {name}")

bpy.data.objects.remove(obj)
bpy.data.hair_curves.remove(curve_data)
