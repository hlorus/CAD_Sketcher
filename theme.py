import bpy
from bpy.props import PointerProperty, FloatVectorProperty, FloatProperty
from bpy.types import PropertyGroup


def update(self, context):
    for area in context.screen.areas:
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
    hovered: FloatVectorProperty(
        name="Hovered",
        subtype="COLOR",
        default=(1.0, 1.0, 1.0, 0.5),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    selected: FloatVectorProperty(
        name="Selected",
        subtype="COLOR",
        default=(1.0, 0.647, 0.322, 0.8),
        size=4,
        min=0.0,
        max=1.0,
        update=update,
    )
    selected_hovered: FloatVectorProperty(
        name="Selected",
        subtype="COLOR",
        default=(1.0, 0.647, 0.322, 0.5),
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


class ThemeSettingsConstraint(PropertyGroup):
    default: FloatVectorProperty(
        name="Default",
        subtype="COLOR",
        default=(1.0, 0.5, 0.5),
        size=3,
        min=0.0,
        max=1.0,
        update=update,
    )
    alpha: FloatProperty(name="Alpha", default=0.7, min=0.0, max=1.0, update=update)
    highlight: FloatVectorProperty(
        name="Highlight",
        subtype="COLOR",
        default=(1.0, 1.0, 1.0),
        size=3,
        min=0.0,
        max=1.0,
        update=update,
    )
    alpha_highlight: FloatProperty(
        name="Alpha Highlight", default=0.7, min=0.0, max=1.0, update=update
    )


class ThemeSettings(PropertyGroup):
    entity: PointerProperty(name="Entity", type=ThemeSettingsEntity)
    constraint: PointerProperty(name="Constraint", type=ThemeSettingsConstraint)


def register():
    bpy.utils.register_class(ThemeSettingsEntity)
    bpy.utils.register_class(ThemeSettingsConstraint)
    bpy.utils.register_class(ThemeSettings)


def unregister():
    bpy.utils.unregister_class(ThemeSettingsEntity)
    bpy.utils.unregister_class(ThemeSettingsConstraint)
    bpy.utils.unregister_class(ThemeSettings)
