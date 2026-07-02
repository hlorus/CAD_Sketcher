"""Check if we can import the solvespace module."""
import sys
print("Checking slvs import...")

try:
    from py_slvs import slvs
    print(f"OK: slvs imported from py_slvs")
    print(f"  Has SolveSystem: {hasattr(slvs, 'SolveSystem')}")
    print(f"  Has System: {hasattr(slvs, 'System')}")
    # List key functions/classes
    public = [x for x in dir(slvs) if not x.startswith('_')]
    print(f"  Public API: {public}")
except ImportError as e:
    print(f"FAIL direct import: {e}")
    # Try via the addon
    try:
        import bl_ext.blend.CAD_Sketcher
        print("Addon loaded, trying again...")
        from py_slvs import slvs
        print(f"OK after addon load: slvs imported")
    except Exception as e2:
        print(f"FAIL via addon: {e2}")

    # Search for slvs in sys.path
    print("\nRelevant sys.path entries:")
    for p in sys.path:
        print(f"  {p}")
