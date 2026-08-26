from os import path

import bpy

from .register import get_path


def _preset_path():
    # register_preset_path looks for presets under "<path>/presets/<subdir>";
    # the bundled presets live in "<addon>/resources/presets/bgs/theme".
    return path.join(get_path(), "resources")


def register_addon_presets():
    bpy.utils.register_preset_path(_preset_path())


def unregister_addon_presets():
    bpy.utils.unregister_preset_path(_preset_path())
