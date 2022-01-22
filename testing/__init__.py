import unittest
from unittest import TestCase
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def run(interactive):
    from geometry_sketcher.testing import test_solver
    from geometry_sketcher.testing.utils import BgsTestCase
    BgsTestCase.interactive = True

    loader = unittest.TestLoader()
    path = Path(__file__) / ".."
    suite = loader.discover(path.absolute().as_posix())
    runner = unittest.TextTestRunner()
    runner.run(suite)

    if not interactive:
        import bpy
        bpy.ops.wm.quit_blender()


if __name__ == "__main__":
    import sys
    args = []
    argv = sys.argv
    if "--" in argv:
        args = argv[argv.index("--") + 1:]

    interactive = False
    if "-i" in argv or "--interactive" in argv:
        interactive = True

    run(interactive)
