import pathlib, toml

def get_addon_version():
    """Return addon version from manifest file"""

    manifest = pathlib.Path(__file__).parent.parent / "blender_manifest.toml"
    try:
        return toml.load(manifest)["version"]
    except Exception:
        return ""
    
def get_min_blender_version():
    """Returns the minimal required blender version from manifest file"""

    manifest = pathlib.Path(__file__).parent.parent / "blender_manifest.toml"
    try:
        return toml.load(manifest)["blender_version_min"]
    except Exception:
        return ""