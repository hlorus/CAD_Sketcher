import site
import sys
import importlib


def check_module(package):
    """
    Note: Blender might be installed in a directory that needs admin rights
    and thus defaulting to a user installation. That path however might not
    be in sys.path
    """

    p = site.USER_SITE
    if p not in sys.path:
        sys.path.append(p)
    try:
        importlib.import_module(package)

    except ModuleNotFoundError as e:
        raise e
