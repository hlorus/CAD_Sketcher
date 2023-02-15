import pathlib


def get_addon_icon_path(icon_name):
    return str(
        pathlib.Path(__file__).parent.parent
        / "ressources" / "icons" / icon_name
    )
