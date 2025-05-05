import bpy

from .register import get_name


def get_prefs():
    addon_name = get_name()
    if addon_name in bpy.context.preferences.addons:
        return bpy.context.preferences.addons[addon_name].preferences
    # Return None or default values if addon prefs not found yet
    # This prevents KeyError during early calls or specific contexts
    # Depending on usage, returning None might require checks in calling functions
    # Or, return a default object/dict if feasible.
    # For now, returning None to signal unavailability.
    print(f"Warning: Could not find addon preferences for '{addon_name}'. Returning None.")
    return None


def get_scale():
    prefs = get_prefs()
    if prefs:
        return bpy.context.preferences.system.ui_scale * prefs.entity_scale
    # Return a default scale if prefs are not available
    return bpy.context.preferences.system.ui_scale


def is_experimental():
    prefs = get_prefs()
    # Default to False if prefs are not available
    return prefs.show_debug_settings if prefs else False


def use_experimental(setting, fallback):
    """Ensure experimental setting is unused when not in experimental mode"""
    prefs = get_prefs()
    if not prefs or not prefs.show_debug_settings:
        return fallback
    return getattr(prefs, setting, fallback) # Use getattr with fallback
