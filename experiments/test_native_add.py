"""Test that add_* operators now create native curve geometry.

Run with: flatpak run org.blender.Blender --background --python experiments/test_native_add.py
"""
import bpy
import traceback

print("=" * 60)
print("TEST: Native curve creation from add_* methods")
print("=" * 60)

sse = bpy.context.scene.sketcher.entities

# Create workplane infrastructure
print("\n1. Setting up workplane and sketch...")
try:
    origin = sse.add_point_3d((0, 0, 0), fixed=True)
    nm = sse.add_normal_3d((1, 0, 0, 0), fixed=True)  # identity quaternion
    wp = sse.add_workplane(origin, nm, fixed=True)
    sketch = sse.add_sketch(wp)
    print(f"   Sketch: {sketch}, wp: {wp}")
    print(f"   target_object: {sketch.target_object}")
except Exception as e:
    print(f"   FAILED: {e}")
    traceback.print_exc()

# Add a line
print("\n2. Adding a line...")
try:
    p1 = sse.add_point_2d((0.0, 0.0), sketch)
    p2 = sse.add_point_2d((1.0, 0.0), sketch)
    line = sse.add_line_2d(p1, p2, sketch)
    print(f"   Line: {line}, p1={p1}, p2={p2}")
    print(f"   target_object after line: {sketch.target_object}")

    if sketch.target_object:
        cd = sketch.target_object.data
        print(f"   Curves in target: {len(cd.curves)}")
        print(f"   Points in target: {len(cd.points)}")
        for i in range(len(cd.points)):
            print(f"   Point {i}: {tuple(cd.points[i].position)}")

        # Check attributes
        ei = cd.attributes.get("entity_index")
        if ei:
            print(f"   entity_index: {[ei.data[i].value for i in range(len(ei.data))]}")
        sei = cd.attributes.get("segment_entity_index")
        if sei:
            print(f"   segment_entity_index: {[sei.data[i].value for i in range(len(sei.data))]}")
    else:
        print("   NO target_object created!")
except Exception as e:
    print(f"   FAILED: {e}")
    traceback.print_exc()

# Add another line
print("\n3. Adding a second line...")
try:
    p3 = sse.add_point_2d((1.0, 1.0), sketch)
    line2 = sse.add_line_2d(p2, p3, sketch)
    print(f"   Line2: {line2}")

    if sketch.target_object:
        cd = sketch.target_object.data
        print(f"   Curves in target: {len(cd.curves)}")
        print(f"   Points in target: {len(cd.points)}")
        for i in range(len(cd.points)):
            print(f"   Point {i}: {tuple(cd.points[i].position)}")
    else:
        print("   NO target_object!")
except Exception as e:
    print(f"   FAILED: {e}")
    traceback.print_exc()

# Add a circle
print("\n4. Adding a circle...")
try:
    nm2d = sse.add_normal_2d(sketch)
    ct = sse.add_point_2d((2.0, 0.0), sketch)
    circle = sse.add_circle(nm2d, ct, 0.5, sketch)
    print(f"   Circle: {circle}, center={ct}, radius=0.5")

    if sketch.target_object:
        cd = sketch.target_object.data
        print(f"   Curves in target: {len(cd.curves)}")
        print(f"   Points in target: {len(cd.points)}")
        for i, c in enumerate(cd.curves):
            print(f"   Curve {i}: first_point={c.first_point_index}, n_points={c.points_length}")
    else:
        print("   NO target_object!")
except Exception as e:
    print(f"   FAILED: {e}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
