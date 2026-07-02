"""Explore the slvs API to understand correct usage."""
import traceback
from py_slvs import slvs

print("=" * 60)
print("EXPLORING SLVS API")
print("=" * 60)

# Check System class
print("\nslvs.System methods:")
sys_methods = [m for m in dir(slvs.System) if not m.startswith('_')]
print(f"  {sys_methods}")

# Check module-level functions
print("\nModule-level functions:")
mod_funcs = [m for m in dir(slvs) if not m.startswith('_') and callable(getattr(slvs, m, None))]
print(f"  {mod_funcs}")

# Check if we need a System instance or use module-level API
print("\n--- Testing module-level API ---")
try:
    slvs.clear_sketch()
    print("  clear_sketch() works at module level")
except Exception as e:
    print(f"  clear_sketch() failed: {e}")

try:
    sys = slvs.System()
    print(f"  System() created: {sys}")
    sys_methods = [m for m in dir(sys) if not m.startswith('_')]
    print(f"  Instance methods: {sys_methods}")
except Exception as e:
    print(f"  System() failed: {e}")

# Try the module-level API (what the addon uses)
print("\n--- Testing entity creation ---")
try:
    slvs.clear_sketch()

    # Check makePoint3d signature
    print(f"  makePoint3d doc: {slvs.makePoint3d.__doc__}")
except Exception as e:
    print(f"  Error: {e}")

try:
    slvs.clear_sketch()
    p = slvs.makePoint3d(1, 0.0, 0.0, 0.0)
    print(f"  makePoint3d result: {p}")
    print(f"  Type: {type(p)}")
    if hasattr(p, '__getitem__'):
        print(f"  Keys: {list(p.keys()) if hasattr(p, 'keys') else 'no keys'}")
        print(f"  p['param']: {p['param'] if 'param' in p else 'no param key'}")
except Exception as e:
    print(f"  makePoint3d failed: {e}")
    traceback.print_exc()

print("\n--- Testing workplane creation ---")
try:
    slvs.clear_sketch()
    print(f"  makeQuaternion doc: {slvs.makeQuaternion.__doc__}")
    print(f"  makeNormal3d doc: {slvs.makeNormal3d.__doc__}")
    print(f"  makeWorkplane doc: {slvs.makeWorkplane.__doc__}")
except Exception as e:
    print(f"  Error: {e}")

try:
    slvs.clear_sketch()
    origin = slvs.makePoint3d(1, 0.0, 0.0, 0.0)
    print(f"  origin: {origin}")

    quat = slvs.makeQuaternion(0, 0, 1, 0, 1, 0)
    print(f"  quat: {quat}")

    normal = slvs.makeNormal3d(1, quat)
    print(f"  normal: {normal}")

    wp = slvs.makeWorkplane(1, origin, normal)
    print(f"  wp: {wp}")
except Exception as e:
    print(f"  Workplane creation failed: {e}")
    traceback.print_exc()

print("\n--- Testing 2D point creation ---")
try:
    p2d = slvs.makePoint2d(1, 0.0, 0.0, wp)
    print(f"  makePoint2d result: {p2d}")
    print(f"  Type: {type(p2d)}")
except Exception as e:
    print(f"  makePoint2d failed: {e}")
    traceback.print_exc()

print("\n--- Testing line creation ---")
try:
    print(f"  makeLineSegment doc: {slvs.makeLineSegment.__doc__}")
    p2d_a = slvs.makePoint2d(2, 0.0, 0.0, wp)
    p2d_b = slvs.makePoint2d(2, 1.0, 0.0, wp)
    line = slvs.makeLineSegment(2, wp, p2d_a, p2d_b)
    print(f"  line: {line}")
except Exception as e:
    print(f"  Line creation failed: {e}")
    traceback.print_exc()

print("\n--- Testing constraint creation ---")
try:
    print(f"  makeConstraint doc: {slvs.makeConstraint.__doc__}")
except Exception as e:
    print(f"  Error: {e}")

try:
    slvs.clear_sketch()
    origin = slvs.makePoint3d(1, 0.0, 0.0, 0.0)
    quat = slvs.makeQuaternion(0, 0, 1, 0, 1, 0)
    normal = slvs.makeNormal3d(1, quat)
    wp = slvs.makeWorkplane(1, origin, normal)

    p1 = slvs.makePoint2d(2, 0.0, 0.0, wp)
    p2 = slvs.makePoint2d(2, 1.0, 0.0, wp)
    p3 = slvs.makePoint2d(2, 1.1, 0.0, wp)
    p4 = slvs.makePoint2d(2, 1.1, 1.0, wp)

    line1 = slvs.makeLineSegment(2, wp, p1, p2)
    line2 = slvs.makeLineSegment(2, wp, p3, p4)

    # Fix p1
    c1 = slvs.makeConstraint(1, slvs.SLVS_C_WHERE_DRAGGED, wp, 0.0, p1, slvs.E_FREE_IN_3D, slvs.E_FREE_IN_3D, slvs.E_FREE_IN_3D)
    print(f"  WHERE_DRAGGED constraint: {c1}")

    # Coincident p2==p3
    c2 = slvs.makeConstraint(2, slvs.SLVS_C_POINTS_COINCIDENT, wp, 0.0, p2, p3, slvs.E_FREE_IN_3D, slvs.E_FREE_IN_3D)
    print(f"  COINCIDENT constraint: {c2}")

    # Solve
    print("\n--- Solving ---")
    result = slvs.solve_sketch(2, True)
    print(f"  Result: {result}")

    # Read back
    print("\n--- Reading solved values ---")
    for name, p in [("p1", p1), ("p2", p2), ("p3", p3), ("p4", p4)]:
        x = slvs.get_param_value(p['param'][0])
        y = slvs.get_param_value(p['param'][1])
        print(f"  {name}: ({x:.4f}, {y:.4f})")

except Exception as e:
    print(f"  FAILED: {e}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("DONE")
print("=" * 60)
