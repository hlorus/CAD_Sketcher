import bpy

from .register import get_name

# Import constants for default values
from ..base.preferences import DEFAULT_WORKPLANE_SIZE
from ..base.theme import (
    ENTITY_COLOR_DEFAULT, ENTITY_COLOR_HIGHLIGHT, ENTITY_COLOR_SELECTED,
    ENTITY_COLOR_SELECTED_HIGHLIGHT, ENTITY_COLOR_INACTIVE, ENTITY_COLOR_INACTIVE_SELECTED,
    ENTITY_COLOR_FIXED, CONSTRAINT_COLOR_DEFAULT, CONSTRAINT_COLOR_HIGHLIGHT,
    CONSTRAINT_COLOR_FAILED, CONSTRAINT_COLOR_FAILED_HIGHLIGHT, CONSTRAINT_COLOR_REFERENCE,
    CONSTRAINT_COLOR_REFERENCE_HIGHLIGHT, CONSTRAINT_COLOR_TEXT, CONSTRAINT_COLOR_TEXT_HIGHLIGHT
)

# Mock classes for theme settings with default values
class MockThemeEntity:
    default = ENTITY_COLOR_DEFAULT
    highlight = ENTITY_COLOR_HIGHLIGHT
    selected = ENTITY_COLOR_SELECTED
    selected_highlight = ENTITY_COLOR_SELECTED_HIGHLIGHT
    inactive = ENTITY_COLOR_INACTIVE
    inactive_selected = ENTITY_COLOR_INACTIVE_SELECTED
    fixed = ENTITY_COLOR_FIXED
    
class MockThemeConstraint:
    default = CONSTRAINT_COLOR_DEFAULT
    highlight = CONSTRAINT_COLOR_HIGHLIGHT
    failed = CONSTRAINT_COLOR_FAILED
    failed_highlight = CONSTRAINT_COLOR_FAILED_HIGHLIGHT
    reference = CONSTRAINT_COLOR_REFERENCE
    reference_highlight = CONSTRAINT_COLOR_REFERENCE_HIGHLIGHT
    text = CONSTRAINT_COLOR_TEXT
    text_highlight = CONSTRAINT_COLOR_TEXT_HIGHLIGHT
    
class MockTheme:
    entity = MockThemeEntity()
    constraint = MockThemeConstraint()
    
# Mock preferences class with default values
class MockPrefs:
    theme_settings = MockTheme()
    entity_scale = 1.0
    workplane_size = DEFAULT_WORKPLANE_SIZE
    gizmo_scale = 15.0
    text_size = 15
    arrow_scale = 1.0
    show_debug_settings = False
    hide_inactive_constraints = True
    all_entities_selectable = False
    force_redraw = True
    decimal_precision = 3
    angle_precision = 0
    auto_hide_objects = True
    use_align_view = True
    
    # Add any additional properties that are needed with their default values


def get_prefs():
    addon_name = get_name()
    if addon_name in bpy.context.preferences.addons:
        return bpy.context.preferences.addons[addon_name].preferences
        
    # If preferences aren't available yet, return our mock preferences object with defaults
    # This prevents AttributeError when accessing preferences during early initialization
    print(f"Warning: Could not find addon preferences for '{addon_name}'. Using defaults.")
    return MockPrefs()


def get_scale():
    prefs = get_prefs()
    return bpy.context.preferences.system.ui_scale * prefs.entity_scale


def is_experimental():
    prefs = get_prefs()
    return prefs.show_debug_settings


def use_experimental(setting, fallback):
    """Ensure experimental setting is unused when not in experimental mode"""
    prefs = get_prefs()
    if not prefs.show_debug_settings:
        return fallback
    return getattr(prefs, setting, fallback) # Use getattr with fallback
