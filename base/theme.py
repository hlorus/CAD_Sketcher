import bpy
from bpy.props import PointerProperty, FloatVectorProperty, FloatProperty
from bpy.types import PropertyGroup


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
        default=(0, 0, 0, 0.8),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    highlight: FloatVectorProperty(
        name="Highlight",
        subtype="COLOR",
        default=(0.65, 0.65, 0.65, 0.5),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    selected: FloatVectorProperty(
        name="Selected",
        subtype="COLOR",
        default=(0.9, 0.582, 0.29, 0.7),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    selected_highlight: FloatVectorProperty(
        name="Selected Highlight",
        subtype="COLOR",
        default=(1.0, 0.647, 0.322, 0.95),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    inactive: FloatVectorProperty(
        name="Inactive",
        subtype="COLOR",
        default=(0, 0, 0, 0.4),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    inactive_selected: FloatVectorProperty(
        name="Inactive Selected",
        subtype="COLOR",
        default=(0.9, 0.582, 0.29, 0.2),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    fixed: FloatVectorProperty(
        name="Fixed",
        subtype="COLOR",
        default=(0.0, 0.55, 0.0, 0.7),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )


class ThemeSettingsConstraint(PropertyGroup):
    default: FloatVectorProperty(
        name="Default",
        subtype="COLOR",
        default=(0.90, 0.54, 0.54, 0.7),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    highlight: FloatVectorProperty(
        name="Highlight",
        subtype="COLOR",
        default=(1.0, 0.6, 0.6, 0.95),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    failed: FloatVectorProperty(
        name="Failed",
        subtype="COLOR",
        default=(0.95, 0.0, 0.0, 0.8),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    failed_highlight: FloatVectorProperty(
        name="Failed Highlight",
        subtype="COLOR",
        default=(0.0, 0.55, 0.0, 0.7),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    reference: FloatVectorProperty(
        name="Reference Measurement",
        subtype="COLOR",
        default=(0.5, 0.5, 1.0, 0.7),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    reference_highlight: FloatVectorProperty(
        name="Reference Highlight",
        subtype="COLOR",
        default=(0.6, 0.6, 1.0, 0.95),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    text: FloatVectorProperty(
        name="Text",
        subtype="COLOR",
        default=(0.90, 0.90, 0.90, 1.0),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )

    text_highlight: FloatVectorProperty(
        name="Text Highlight",
        subtype="COLOR",
        default=(1.0, 1.0, 1.0, 1.0),
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
