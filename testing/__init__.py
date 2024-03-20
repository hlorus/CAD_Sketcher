import sys
import unittest
from unittest import TestCase
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Add parent directory to sys.path to allow importing from testing
module_path = Path(__file__).parent.parent.as_posix()
if module_path not in sys.path:
    sys.path.append(module_path)



def run(interactive, log_level=None):
    from CAD_Sketcher.testing import test_solver
    from CAD_Sketcher.testing.utils import BgsTestCase

    BgsTestCase.interactive = True
    if log_level:
        BgsTestCase.log_level = log_level

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
    kwargs = {}
    argv = sys.argv

    interactive = False
    log_level = None
    if "--" in argv:
        for arg in argv[argv.index("--") + 1 :]:
            if "=" not in arg:
                args.append(arg)
                continue
            key, value = arg.split("=")
            kwargs[key] = value

        if "-i" in args or "--interactive" in args:
            interactive = True

        if "--log_level" in kwargs.keys():
            log_level = kwargs["--log_level"]

    print("args: {}\nkwargs: {}".format(args, kwargs))
    run(interactive, log_level)
