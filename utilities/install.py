import importlib
import logging
import site
import sys
from types import ModuleType

logger = logging.getLogger(__name__)


def check_module(package: str, raise_exception: bool = False) -> ModuleType:
    """
    Note: Blender might be installed in a directory that needs admin rights
    and thus defaulting to a user installation. That path however might not
    be in sys.path
    """

    p = site.USER_SITE
    if p not in sys.path:
        sys.path.append(p)
    try:
        module = importlib.import_module(package)

        # Print information about the loaded module
        logger.info(f"Module loaded: {package}")
        logger.info(f"Module path: {getattr(module, '__file__', 'Unknown')}")
        logger.info(f"Module version: {getattr(module, '__version__', 'Unknown')}")

        return module

    except ModuleNotFoundError as e:
        if raise_exception:
            raise e
        else:
            logger.debug(f"Module not found: {package}. \n{e}")
            return None
