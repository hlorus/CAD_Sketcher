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
    from .utils import BgsTestCase

    BgsTestCase.interactive = interactive
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
    import os

    args = []
    kwargs = {}
    argv = sys.argv

    # Check environment variable first (most reliable)
    interactive = os.environ.get("RUN_TESTS_INTERACTIVE", "").lower() in ("true", "1", "yes")

    # Then check command line args
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

    # Set environment variable for child processes
    os.environ["RUN_TESTS_INTERACTIVE"] = "1" if interactive else "0"

    print("args: {}\nkwargs: {}".format(args, kwargs))
    print(f"Interactive mode: {interactive}")
    run(interactive, log_level)
