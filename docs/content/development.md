# Development

## Running the tests

The test suite lives in `testing/` and runs **inside Blender** (it needs `bpy`
and the solver). Tests are plain `unittest` modules named `test_*.py`.

### Full suite (as CI runs it)

CI builds the extension, installs it, and runs every `testing/test_*.py` against
the installed copy:

```bash
blender --background --command extension build --output-filepath ./CAD_Sketcher.zip
blender --background --command extension install-file --repo user_default --enable ./CAD_Sketcher.zip
blender --background --python ./scripts/ci_run_tests.py
```

`scripts/ci_run_tests.py` finds the installed extension, copies `testing/` in
(the release build strips it), discovers every `test_*.py`, and exits non-zero on
any failure. Set `CAD_SKETCHER_SRC` to the source checkout if it isn't the
current directory.

### A single module from a source checkout

For a fast local loop against the addon enabled from source:

```bash
blender --background --addons CAD_Sketcher --python-expr '
import unittest
from bl_ext.<namespace>.CAD_Sketcher.testing import test_operators
suite = unittest.TestLoader().loadTestsFromModule(test_operators)
unittest.TextTestRunner(verbosity=2).run(suite)
'
```

`<namespace>` depends on how the addon is installed (`user_default` for a normal
install; it differs for a dev/linked checkout). Because of this, **never
hardcode the `bl_ext.<namespace>.CAD_Sketcher` path in addon code — always use
relative imports.** `test_prefill.py` has a guard test that fails on any
hardcoded absolute import, since such a path resolves only in the namespace it
was written for and raises `ModuleNotFoundError` everywhere else.

## Test base classes

`testing/utils.py` provides the fixtures:

- **`BgsTestCase`** — creates a fresh scene, exposes `context`, `entities`,
  `constraints`, and a `solve()` helper.
- **`Sketch2dTestCase`** — additionally creates and activates a 2D sketch in
  `setUp`, with geometry helpers `add_point`, `add_line`, `add_arc`,
  `add_circle` (each returns a `CurveRef`).

```python
class TestMyThing(Sketch2dTestCase):
    def test_line(self):
        p1 = self.add_point((0, 0))
        p2 = self.add_point((1, 0))
        line = self.add_line(p1, p2)
        self.assertTrue(line.valid)
```

## Testing stateful operators

The interactive tools ([stateful operators](interaction_system.md)) cannot be
instantiated directly: a `bpy.types.Operator`'s metaclass blocks construction
outside a modal invoke, and their behavior depends on a modal event loop.

`testing/utils.py` solves this with **`OpHarness`**, which drives an operator the
way a user does — without a viewport. It builds a non-bpy *twin* of the operator
class (`make_operator_double`): the real class body (`states`, `main`, `init`,
overrides) is reused verbatim, only `bpy.types.Operator` is dropped from the
bases so the twin is a plain, instantiable object. No operator logic is
duplicated.

The harness mirrors the real lifecycle:

| Method | Mirrors |
|--------|---------|
| `prefill()` | invoke-time selection prefill (Select → Invoke) |
| `pick(ref)` | clicking an existing entity for the current state |
| `place_point(co)` | clicking empty space to place a new point |
| `set_value(v)` | entering a property value (e.g. a circle's radius) |
| `finish()` | committing: `redo_states` + `main` + `fini` |

```python
from .utils import Sketch2dTestCase, OpHarness

class TestAddLine(Sketch2dTestCase):
    def test_two_clicks(self):
        from ..operators.add_line_2d import View3D_OT_slvs_add_line2d
        h = OpHarness(View3D_OT_slvs_add_line2d, self.sketch, self.context)
        h.place_point((0, 0)).place_point((3, 0))
        line = h.finish()          # real main() runs, auto-constraints applied
        self.assertEqual(h.op.target.p1.co.x, 0)
```

Selection-driven paths populate `global_data.selected` (a list of `curve_id` hex
strings) before calling `prefill()`:

```python
from .. import global_data
global_data.selected.clear()
global_data.selected.append(pt.curve_id)
h.prefill()   # pt becomes the first pointer state
```

See `test_operators.py`, `test_prefill.py`, and `test_constraint_ops.py` for
worked examples covering creation tools, the three selection paradigms, and
constraint operators.

### Caveats of the twin

`make_operator_double` reflects the real class, so two Blender-registration
details don't survive and are handled by the harness:

1. **bpy property annotations are inert** on the twin (e.g. `continuous_draw:
   BoolProperty(...)`). Set a plain attribute where a value is needed; `OpHarness`
   already sets the common ones.
2. **Zero-arg `super()`** in a copied method keeps a hidden `__class__` cell
   pointing at the original class. `make_operator_double` rebinds that cell to
   the twin (on a copy of the function, leaving the registered operator
   untouched) so calls like a constraint's `super().main()` resolve correctly.
