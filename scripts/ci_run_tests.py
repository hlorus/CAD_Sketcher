"""Run the full test suite against the installed extension and fail on error.

Meant for CI (``blender --background --python scripts/ci_run_tests.py``). The
released build excludes ``testing/`` (see the manifest ``[build]`` section), so
the installed extension has no tests; this copies them in from the source
checkout, then runs every ``testing/test_*.py`` module and exits non-zero if any
test fails — the piece the old ``slvs_test`` invocation was missing.

Set ``CAD_SKETCHER_SRC`` to the source checkout dir (defaults to the current
working directory).
"""

import glob
import importlib
import os
import shutil
import sys
import unittest

import addon_utils


def _find_extension():
    for mod in addon_utils.modules():
        if mod.__name__.split(".")[-1] == "CAD_Sketcher":
            return mod
    raise SystemExit("CAD_Sketcher extension not found — was it installed/enabled?")


def main():
    mod = _find_extension()
    pkg = mod.__name__                       # e.g. bl_ext.user_default.CAD_Sketcher
    addon_utils.enable(pkg, default_set=True)  # register + activate bundled wheels

    install_dir = os.path.dirname(mod.__file__)
    dst = os.path.join(install_dir, "testing")

    # Tests are stripped from the release build; inject them from the checkout.
    if not os.path.isdir(dst):
        src_root = os.environ.get("CAD_SKETCHER_SRC", os.getcwd())
        src = os.path.join(src_root, "testing")
        if not os.path.isdir(src):
            raise SystemExit(f"testing/ not found in checkout: {src}")
        shutil.copytree(src, dst)
        importlib.invalidate_caches()

    names = [
        f"{pkg}.testing." + os.path.splitext(os.path.basename(f))[0]
        for f in sorted(glob.glob(os.path.join(dst, "test_*.py")))
    ]
    print(f"Running {len(names)} test modules from {pkg}.testing")

    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromNames(names)
    )
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
