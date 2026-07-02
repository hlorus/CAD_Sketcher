"""Test if set_types crashes when applied to 1-point curves."""
import bpy

cd = bpy.data.hair_curves.new("CrashTest")

# Add a 1-point curve (point)
cd.add_curves([1])
cd.points[0].position = (0, 0, 0)
print(f"After adding 1-point curve: {len(cd.curves)} curves")

# Add a 2-point curve (line) and set types to BEZIER
cd.add_curves([2])
print(f"After adding 2-point curve: {len(cd.curves)} curves")

# This sets ALL curves to BEZIER, including the 1-point one
print("Calling set_types(type='BEZIER')...")
try:
    cd.set_types(type="BEZIER")
    print("OK - no crash")
except Exception as e:
    print(f"Error: {e}")

print(f"Points: {len(cd.points)}")
for i in range(len(cd.curves)):
    c = cd.curves[i]
    print(f"  Curve {i}: {c.points_length} points")

bpy.data.hair_curves.remove(cd)
print("PASS")
