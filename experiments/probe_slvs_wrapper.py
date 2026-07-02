"""Probe the slvs wrapper API step by step."""
import slvs
import traceback

print("=" * 60)

# Step by step with error catching
print("1. clear_sketch")
try:
    slvs.clear_sketch()
    print("   OK")
except Exception as e:
    print(f"   FAIL: {e}")

print("2. add_point_3d")
try:
    origin = slvs.add_point_3d(1, 0, 0, 0)
    print(f"   OK: {origin}")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("3. make_quaternion")
try:
    quat = slvs.make_quaternion(0, 0, 1, 0, 1, 0)
    print(f"   OK: {quat}")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("4. add_normal_3d")
try:
    normal = slvs.add_normal_3d(1, quat)
    print(f"   OK: {normal}")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("5. add_workplane")
try:
    wp = slvs.add_workplane(1, origin, normal)
    print(f"   OK: {wp}")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("6. add_point_2d (group=1)")
try:
    p0 = slvs.add_point_2d(1, 0.0, 0.0, wp)
    print(f"   OK: {p0}")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("7. add_point_2d (group=2)")
try:
    p1 = slvs.add_point_2d(2, 1.0, 0.0, wp)
    print(f"   OK: {p1}")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("8. add_line_2d")
try:
    line = slvs.add_line_2d(2, p0, p1, wp)
    print(f"   OK: {line}")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("9. dragged")
try:
    c = slvs.dragged(1, p0, wp)
    print(f"   OK: {c}")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("10. add_point_2d more points")
try:
    p2 = slvs.add_point_2d(2, 1.1, 0.0, wp)
    p3 = slvs.add_point_2d(2, 1.1, 1.0, wp)
    line2 = slvs.add_line_2d(2, p2, p3, wp)
    print(f"   OK: p2={p2}, p3={p3}, line2={line2}")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("11. coincident")
try:
    c2 = slvs.coincident(2, p1, p2, wp)
    print(f"   OK: {c2}")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("12. solve_sketch")
try:
    result = slvs.solve_sketch(2, True)
    print(f"   OK: {result}")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("13. get_param_value")
try:
    x = slvs.get_param_value(p1['param'][0])
    y = slvs.get_param_value(p1['param'][1])
    print(f"   OK: p1 solved to ({x}, {y})")
except Exception as e:
    print(f"   FAIL: {e}")
    traceback.print_exc()

print("\nDONE")
