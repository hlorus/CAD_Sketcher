import bpy
from bpy.props import PointerProperty, FloatVectorProperty, FloatProperty
from bpy.types import PropertyGroup

# Color constants for entities
ENTITY_COLOR_DEFAULT = (0.0, 0.0, 0.0, 0.8)
ENTITY_COLOR_HIGHLIGHT = (0.65, 0.65, 0.65, 0.5)
ENTITY_COLOR_SELECTED = (0.9, 0.582, 0.29, 0.7)
ENTITY_COLOR_SELECTED_HIGHLIGHT = (1.0, 0.647, 0.322, 0.95) 
ENTITY_COLOR_INACTIVE = (0.0, 0.0, 0.0, 0.4)
ENTITY_COLOR_INACTIVE_SELECTED = (0.9, 0.582, 0.29, 0.2)
ENTITY_COLOR_FIXED = (0.0, 0.55, 0.0, 0.7)

# Color constants for constraints
CONSTRAINT_COLOR_DEFAULT = (0.90, 0.54, 0.54, 0.7)
CONSTRAINT_COLOR_HIGHLIGHT = (1.0, 0.6, 0.6, 0.95)
CONSTRAINT_COLOR_FAILED = (0.95, 0.0, 0.0, 0.8)
CONSTRAINT_COLOR_FAILED_HIGHLIGHT = (0.0, 0.55, 0.0, 0.7)
CONSTRAINT_COLOR_REFERENCE = (0.5, 0.5, 1.0, 0.7)
CONSTRAINT_COLOR_REFERENCE_HIGHLIGHT = (0.6, 0.6, 1.0, 0.95)
CONSTRAINT_COLOR_TEXT = (0.90, 0.90, 0.90, 1.0)
CONSTRAINT_COLOR_TEXT_HIGHLIGHT = (1.0, 1.0, 1.0, 1.0)


def update(self, context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            area.tag_redraw()
            area.spaces[0].show_gizmo = True


class ThemeSettingsEntity(PropertyGroup):
    default: FloatVectorProperty(
        name="Default",
        subtype="COLOR",
        default=ENTITY_COLOR_DEFAULT,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    highlight: FloatVectorProperty(
        name="Highlight",
        subtype="COLOR",
        default=ENTITY_COLOR_HIGHLIGHT,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    selected: FloatVectorProperty(
        name="Selected",
        subtype="COLOR",
        default=ENTITY_COLOR_SELECTED,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    selected_highlight: FloatVectorProperty(
        name="Selected Highlight",
        subtype="COLOR",
        default=ENTITY_COLOR_SELECTED_HIGHLIGHT,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    inactive: FloatVectorProperty(
        name="Inactive",
        subtype="COLOR",
        default=ENTITY_COLOR_INACTIVE,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    inactive_selected: FloatVectorProperty(
        name="Inactive Selected",
        subtype="COLOR",
        default=ENTITY_COLOR_INACTIVE_SELECTED,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    fixed: FloatVectorProperty(
        name="Fixed",
        subtype="COLOR",
        default=ENTITY_COLOR_FIXED,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )


class ThemeSettingsConstraint(PropertyGroup):
    default: FloatVectorProperty(
        name="Default",
        subtype="COLOR",
        default=CONSTRAINT_COLOR_DEFAULT,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    highlight: FloatVectorProperty(
        name="Highlight",
        subtype="COLOR",
        default=CONSTRAINT_COLOR_HIGHLIGHT,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    failed: FloatVectorProperty(
        name="Failed",
        subtype="COLOR",
        default=CONSTRAINT_COLOR_FAILED,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    failed_highlight: FloatVectorProperty(
        name="Failed Highlight",
        subtype="COLOR",
        default=CONSTRAINT_COLOR_FAILED_HIGHLIGHT,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    reference: FloatVectorProperty(
        name="Reference Measurement",
        subtype="COLOR",
        default=CONSTRAINT_COLOR_REFERENCE,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    reference_highlight: FloatVectorProperty(
        name="Reference Highlight",
        subtype="COLOR",
        default=CONSTRAINT_COLOR_REFERENCE_HIGHLIGHT,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    text: FloatVectorProperty(
        name="Text",
        subtype="COLOR",
        default=CONSTRAINT_COLOR_TEXT,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    text_highlight: FloatVectorProperty(
        name="Text Highlight",
        subtype="COLOR",
        default=CONSTRAINT_COLOR_TEXT_HIGHLIGHT,
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )


class ThemeSettings(PropertyGroup):
    entity: PointerProperty(name="Entity", type=ThemeSettingsEntity)
    constraint: PointerProperty(name="Constraint", type=ThemeSettingsConstraint)


def register():
    bpy.utils.register_class(ThemeSettingsEntity)
    bpy.utils.register_class(ThemeSettingsConstraint)
    bpy.utils.register_class(ThemeSettings)


def unregister():
    bpy.utils.unregister_class(ThemeSettings)
    bpy.utils.unregister_class(ThemeSettingsConstraint)
    bpy.utils.unregister_class(ThemeSettingsEntity)
