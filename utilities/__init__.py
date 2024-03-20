import pathlib, toml

def get_addon_version():
    """Return addon version from manifest file"""

    manifest = pathlib.Path(__file__).parent / "blender_manifest.toml"
    try:
        return toml.load(manifest)["version"]
    except Exception:
        return ""