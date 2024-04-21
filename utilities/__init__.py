from bpy.app import version
import pathlib

def get_bl_info():

    from .. import bl_info
    return bl_info


def get_addon_version_tuple() -> tuple:
    """Return addon version as a tuple e.g. (0, 27, 1)"""

    if version < (4, 20):
        return get_bl_info()["version"]

    manifest = pathlib.Path(__file__).parent.parent / "blender_manifest.toml"
    try:
        import toml
        version_tuple = toml.load(manifest)["version"]
        return tuple(map(int, version_tuple.split(".")))
    except Exception:
        return ""
    

def get_addon_version() -> str:
    """Return addon version as string"""

    version = get_addon_version_tuple()
    return ".".join(map(str, version))


def get_min_blender_version() -> str:
    """Returns the minimal required blender version from manifest file"""

    if version < (4, 20):
        return str(get_bl_info()["version"])

    manifest = pathlib.Path(__file__).parent.parent / "blender_manifest.toml"
    try:
        import toml
        return toml.load(manifest)["blender_version_min"]
    except Exception:
        return ""