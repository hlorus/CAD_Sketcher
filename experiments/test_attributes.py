"""Test attribute access on Curves in Blender 5.0"""
import bpy

curve_data = bpy.data.hair_curves.new("AttrTest")
curve_data.add_curves([2, 2])

# Find the right attribute API
print("Available attributes on Curves data:")
for attr in dir(curve_data):
    if "attr" in attr.lower():
        print(f"  {attr}: {type(getattr(curve_data, attr, None))}")

print("\nTrying curve_data.attributes:")
try:
    attrs = curve_data.attributes
    print(f"  Type: {type(attrs)}")
    print(f"  Existing: {[a.name for a in attrs]}")

    # Try creating point-domain attribute
    a = attrs.new("entity_index", type='INT', domain='POINT')
    print(f"  Created: {a.name}, type={a.data_type}, domain={a.domain}")
    for i in range(len(curve_data.points)):
        a.data[i].value = i * 10
    vals = [a.data[i].value for i in range(len(curve_data.points))]
    print(f"  Point values: {vals}")

    # Curve-domain attribute
    b = attrs.new("sketch_id", type='INT', domain='CURVE')
    print(f"  Created: {b.name}, type={b.data_type}, domain={b.domain}")
    for i in range(len(curve_data.curves)):
        b.data[i].value = 42 + i
    vals2 = [b.data[i].value for i in range(len(curve_data.curves))]
    print(f"  Curve values: {vals2}")

    # Float vector attribute
    c = attrs.new("test_vec", type='FLOAT_VECTOR', domain='POINT')
    print(f"  Created: {c.name}, type={c.data_type}, domain={c.domain}")
    c.data[0].vector = (1.0, 2.0, 3.0)
    print(f"  Vector value: {tuple(c.data[0].vector)}")

    # Boolean attribute
    d = attrs.new("is_fixed", type='BOOLEAN', domain='POINT')
    d.data[0].value = True
    d.data[1].value = False
    print(f"  Bool values: {[d.data[i].value for i in range(len(curve_data.points))]}")

    # Foreach on attributes
    import numpy as np
    idx_vals = np.zeros(len(curve_data.points), dtype=np.int32)
    a.data.foreach_get("value", idx_vals)
    print(f"  foreach_get entity_index: {idx_vals}")

    print("\nOK: All attribute tests passed")
except Exception as e:
    print(f"  FAILED: {e}")
    import traceback
    traceback.print_exc()

bpy.data.hair_curves.remove(curve_data)
