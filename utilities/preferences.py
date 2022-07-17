import bpy

from .register import get_name

def get_prefs():
    return bpy.context.preferences.addons[get_name()].preferences

def get_scale():
    return bpy.context.preferences.system.ui_scale * get_prefs().entity_scale

def is_experimental():
    return get_prefs().show_debug_settings

def use_experimental(setting, fallback):
    """Ensure experimental setting is unused when not in experimental mode"""
    if not is_experimental():
        return fallback
    prefs = get_prefs()
    return getattr(prefs, setting)