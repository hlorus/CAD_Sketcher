"""Test setting curve_type per-curve without set_types."""
import bpy

cd = bpy.data.hair_curves.new("Test")

# Add point + line
cd.add_curves([1, 2])
cd.points[0].position = (0, 0, 0)
cd.points[1].position = (1, 0, 0)
cd.points[2].position = (2, 0, 0)

# Create curve_type attribute manually and set only line to BEZIER
ct = cd.attributes.new("curve_type", type="INT8", domain="CURVE")
ct.data[0].value = 0  # CATMULL_ROM (point stays non-bezier)
ct.data[1].value = 2  # BEZIER (line)

print(f"curve_type: {[ct.data[i].value for i in range(len(ct.data))]}")
print(f"Curves: {len(cd.curves)}")

# Check if handles exist (BEZIER needs handles)
hl = cd.attributes.get("handle_left")
hr = cd.attributes.get("handle_right")
print(f"handle_left exists: {hl is not None}")
print(f"handle_right exists: {hr is not None}")

# Try adding handles manually
if not hl:
    hl = cd.attributes.new("handle_left", type="FLOAT_VECTOR", domain="POINT")
    hr = cd.attributes.new("handle_right", type="FLOAT_VECTOR", domain="POINT")
    print("Created handle attributes manually")

# Now test: add another curve, only set IT to bezier
cd.add_curves([2])
ct = cd.attributes.get("curve_type")
print(f"\nAfter add_curves: curve_type = {[ct.data[i].value for i in range(len(ct.data))]}")
# New curve should have default (0)
ct.data[2].value = 2  # Set only the new curve to BEZIER
print(f"After per-curve set: curve_type = {[ct.data[i].value for i in range(len(ct.data))]}")

bpy.data.hair_curves.remove(cd)
print("\nDONE")
