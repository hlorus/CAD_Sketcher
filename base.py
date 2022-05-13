# Expose API to check and manipulate addon state from other addons


def _get_name():
    # get the name of the root folder
    import os
    p = os.path.dirname(os.path.realpath(__file__))
    return os.path.basename(p)

# ADDON_NAME = __package__
ADDON_NAME = _get_name()


def is_enabled():
    """Check if addon is enabled"""
    import addon_utils
    return addon_utils.check(ADDON_NAME) == (True, True)

def is_registered():
    """Check if addon is fully registered, this will not be the case when dependencies are missing"""
    from . import global_data
    return global_data.registered

def check():
    """Check if the addon is functional"""
    return is_enabled() and is_registered()

def get_version():
    from . import bl_info
    return bl_info["version"]

def enable():
    """Enable the addon"""
    # Doesn't work for some reason...
    # import addon_utils
    # addon_utils.enable(ADDON_NAME)
    
    import bpy
    bpy.ops.preferences.addon_enable(module=ADDON_NAME)
