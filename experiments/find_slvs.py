"""Find where 'import slvs' resolves to."""
import slvs
print(f"slvs type: {type(slvs)}")
print(f"slvs file: {slvs.__file__}")
print(f"has clear_sketch: {hasattr(slvs, 'clear_sketch')}")
print(f"has add_point_2d: {hasattr(slvs, 'add_point_2d')}")
print(f"has solve_sketch: {hasattr(slvs, 'solve_sketch')}")
public = [x for x in dir(slvs) if not x.startswith('_')]
print(f"Public: {public}")
