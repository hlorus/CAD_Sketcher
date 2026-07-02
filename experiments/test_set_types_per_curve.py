"""Test if we can set curve type per-curve instead of set_types on all."""
import bpy

cd = bpy.data.hair_curves.new("PerCurveType")

# Add a point (1-point, should NOT be BEZIER)
cd.add_curves([1])
cd.points[0].position = (0, 0, 0)

# Add a line (2-point, should be BEZIER)
cd.add_curves([2])

# Check: can we set curve_type per-curve via attribute?
ct = cd.attributes.get("curve_type")
print(f"curve_type attribute exists: {ct is not None}")
if ct:
    print(f"  Values before: {[ct.data[i].value for i in range(len(ct.data))]}")

# Try setting only the second curve to BEZIER (type 2)
# Without calling set_types at all
if ct:
    ct.data[1].value = 2  # BEZIER = 2 in Blender's CurveType enum
    print(f"  Values after setting [1]=2: {[ct.data[i].value for i in range(len(ct.data))]}")

# Also try: what values does set_types produce?
cd2 = bpy.data.hair_curves.new("SetTypesTest")
cd2.add_curves([1, 2])
cd2.set_types(type="BEZIER")
ct2 = cd2.attributes.get("curve_type")
if ct2:
    print(f"\nset_types result: {[ct2.data[i].value for i in range(len(ct2.data))]}")

# Check what BEZIER type value is
print(f"\nBEZIER type constants check:")
print(f"  CATMULL_ROM=0, POLY=1, BEZIER=2, NURBS=3 (typical Blender)")

bpy.data.hair_curves.remove(cd)
bpy.data.hair_curves.remove(cd2)
print("\nDONE")
