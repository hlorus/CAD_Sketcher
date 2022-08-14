import importlib
import logging
import os
import site
import subprocess
import sys

from .. import global_data

logger = logging.getLogger(__name__)


def check_module(package):
    refresh_path()
    # This was done in the past to make sure modules in usersite can be found.
    # Since using USERBASE this shouldnt be necessary, but it's left as a fallback.
    p = site.USER_SITE
    if p not in sys.path:
        sys.path.insert(0, p)
    try:
        importlib.import_module(package)

    except ModuleNotFoundError as e:
        raise e


def install_pip() -> int:
    import ensurepip

    # ensurepip.bootstrap just hides the return
    # code which is needed for the currect error messages.
    ret_val = ensurepip._bootstrap()
    # Env var left over from pip installation, needs to be removed
    os.environ.pop("PIP_REQ_TRACKER", None)
    return ret_val


def check_pip_installed() -> bool:
    cmd = [global_data.PYPATH, "-m", "pip", "--version"]
    if subprocess.call(cmd, env=global_data.env_vars) == 0:
        return True
    return False


def ensure_pip() -> bool:
    refresh_path()
    if not check_pip_installed():
        return install_pip() == 0
    return True


def refresh_path():
    """refresh path to packages found after install"""

    # set the user base directory
    os.environ["PYTHONUSERBASE"] = global_data.CUSTOM_USER_BASE
    # Applies the PYTHONUSERBASE env var
    importlib.reload(site)


def install_package(package: str, no_deps: bool = True) -> bool:
    refresh_path()
    _install_package("pip")  # update pip if needed
    return _install_package(package, no_deps)


def _install_package(package: str, no_deps: bool = True) -> bool:
    # --user is needed to ensure install always happens into USERBASE
    cmd = [global_data.PYPATH, "-m", "pip", "install", "--upgrade", "--user"]

    if no_deps:
        cmd += ["--no-deps"]

    cmd = cmd + package.split(" ")

    ret_val = subprocess.call(cmd, env=global_data.env_vars)
    refresh_path()
    return ret_val == 0
