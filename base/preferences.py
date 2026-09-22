import logging
import math

import bpy
from bl_ui.utils import PresetPanel
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
)
from bpy.types import AddonPreferences, Menu, Panel

from .. import units
from ..utilities.boolean_nodes import SOLVER_ITEMS
from ..utilities.register import get_name, get_path
from ..utilities.view import update_cb
from . import theme

log_levels = [
    ("CRITICAL", "Critical", "", 0),
    ("ERROR", "Error", "", 1),
    ("WARNING", "Warning", "", 2),
    ("INFO", "Info", "", 3),
    ("DEBUG", "Debug", "", 4),
    ("NOTSET", "Notset", "", 5),
]

logger = logging.getLogger(__name__)


def on_logging_level_update(self, context):
    level = self.logging_level
    logger.info("setting log level: {}".format(level))
    logger.setLevel(level)


# Presets


class SKETCHER_PT_theme_presets(PresetPanel, Panel):
    bl_label = "Theme Presets"
    preset_subdir = "bgs/theme"
    preset_operator = "script.execute_preset"
    preset_add_operator = "bgs.theme_preset_add"


class SKETCHER_MT_theme_presets(Menu):
    bl_label = "Theme Presets"
    preset_subdir = "bgs/theme"
    preset_operator = "script.execute_preset"
    draw = Menu.draw_preset


class Preferences(AddonPreferences):
    path = get_path()
    bl_idname = get_name()

    theme_settings: PointerProperty(type=theme.ThemeSettings)

    show_debug_settings: BoolProperty(
        name="Show Debug Settings",
        default=False,
    )
    show_theme_settings: BoolProperty(
        name="Show Theme Settings",
        description="Expand this box to show various theme settings",
        default=False,
    )
    logging_level: EnumProperty(
        name="Logging Level",
        items=log_levels,
        update=on_logging_level_update,
        default=2,
    )
    hide_inactive_constraints: BoolProperty(
        name="Hide inactive Constraints", default=True, update=update_cb
    )
    all_entities_selectable: BoolProperty(
        name="Make all Entities Selectable", update=update_cb
    )
    force_redraw: BoolProperty(name="Force Entity Redraw", default=True)
    hide_legacy_drawing: BoolProperty(
        name="Hide Legacy Drawing",
        description="Hide entity-based drawing (shows only native curve overlay)",
        default=False,
    )
    part_duplicate_shortcut: BoolProperty(
        name="Duplicate Parts with Shift+D",
        description=(
            "Make Shift+D copy a whole part (its workplanes, sketches and "
            "cutters) when the selection belongs to one. Blender's duplicate "
            "still applies to everything else, and to all of it when this is off"
        ),
        default=True,
    )
    constraint_grid_view: BoolProperty(
        name="Constraint Grid View",
        description="Show the constraint tools as a compact icon grid instead of a list",
        default=True,
    )

    decimal_precision: IntProperty(
        name="Decimal Precision",
        description="Number of digits after the comma",
        default=3,
        min=0,
        soft_max=7,
    )
    imperial_precision: units.imperial_precision_prop
    angle_precision: IntProperty(
        name="Angle Precision",
        min=0,
        max=5,
        default=0,
        description="Angle decimal precision",
    )

    auto_hide_objects: BoolProperty(
        name="Auto Fade Objects",
        description="Fade curves/meshes while in sketch mode",
        default=True,
    )
    entity_scale: FloatProperty(
        name="Entity Scale", default=1.0, min=0.1, soft_max=3.0, update=theme.update
    )
    workplane_size: FloatProperty(
        name="Workplane Size", default=0.4, soft_min=0.1, soft_max=1.0
    )
    gizmo_scale: FloatProperty(
        name="Icon Scale", default=18.0, min=1.0, soft_max=25.0, update=theme.update
    )
    group_constraint_icons: BoolProperty(
        name="Group Constraint Icons",
        description=(
            "Show the constraint icons on one element, or close together, as one "
            "icon with a count that expands while hovered"
        ),
        default=True,
        update=update_cb,
    )
    text_size: IntProperty(name="Text Size", default=15, min=5, soft_max=25)
    arrow_scale: FloatProperty(name="Arrow Scale", default=1, min=0.2, soft_max=3)
    use_align_view: BoolProperty(
        name="Align View",
        description="Automatically align view to workplane when activating a sketch.",
        default=True,
    )
    curve_angular_resolution: FloatProperty(
        name="Curve Resolution",
        description=(
            "Maximum angle per edge when arcs and circles are meshed, used for new "
            "sketches. Change it per sketch on its CAD Sketcher Convert modifier"
        ),
        subtype="ANGLE",
        default=math.radians(7.5),
        min=math.radians(0.1),
        max=math.radians(90),
    )
    boolean_solver: EnumProperty(
        name="Boolean Solver",
        description=(
            "Solver used for new booleans (the Boolean tool, and Extrude/Revolve "
            "when they boolean their result). Change it per boolean on its "
            "CAD Sketcher Boolean modifier"
        ),
        items=SOLVER_ITEMS,
        default="Exact",
    )
    show_whats_new: BoolProperty(
        name="Show What's New on Update",
        description="Show a summary of the changes after CAD Sketcher is updated",
        default=True,
    )

    def draw(self, context):
        layout = self.layout

        # Quick links in two columns of three (learn/code | feedback/community).
        # Kept clear of info already in Blender's manifest header above.
        # Centered, with a fixed block width so the buttons keep a sensible
        # minimum size instead of stretching or shrinking with the panel.
        outer = layout.row()
        outer.alignment = "CENTER"
        cols = outer.row()
        cols.ui_units_x = 32  # fixed width for the two-column block
        left = cols.column(align=True)
        left.operator("view3d.slvs_whats_new", text="What's New", icon="INFO")
        left.operator(
            "wm.url_open", text="Documentation", icon="HELP"
        ).url = "https://hlorus.github.io/CAD_Sketcher/"
        left.operator(
            "wm.url_open", text="Source Code", icon="FILE_SCRIPT"
        ).url = "https://github.com/hlorus/CAD_Sketcher"
        cols.separator(factor=0.25)  # thin gap between the two columns
        right = cols.column(align=True)
        right.operator(
            "wm.url_open", text="Report a Bug", icon="ERROR"
        ).url = (
            "https://github.com/hlorus/CAD_Sketcher/issues/new?template=bug-report.yml"
        )
        right.operator(
            "wm.url_open", text="Request a Feature", icon="OUTLINER_OB_LIGHT"
        ).url = "https://github.com/hlorus/CAD_Sketcher/discussions/106"
        right.operator(
            "wm.url_open", text="Discord", icon="COMMUNITY"
        ).url = "https://discord.gg/GzpJsShgxa"

        layout.use_property_split = True

        box = layout.box()
        box.label(text="Interface")
        col = box.column(align=True)
        col.prop(self, "auto_hide_objects")
        col.prop(self, "use_align_view")

        col.prop(self, "entity_scale")
        col.prop(self, "workplane_size")
        col.prop(self, "gizmo_scale")
        col.prop(self, "group_constraint_icons")
        col.prop(self, "text_size")
        col.prop(self, "arrow_scale")

        box = layout.box()
        box.label(text="Geometry")
        col = box.column(align=True)
        col.prop(self, "curve_angular_resolution")
        col.prop(self, "boolean_solver")

        box = layout.box()
        box.label(text="Units")
        col = box.column(align=True)
        col.prop(self, "decimal_precision")
        col.prop(self, "imperial_precision")
        col.prop(self, "angle_precision")

        box = layout.box()
        box.label(text="Advanced")
        col = box.column(align=True)
        col.prop(self, "show_whats_new")
        col.prop(self, "show_debug_settings")
        col.prop(self, "logging_level")

        box = layout.box()
        row = box.row()
        row.use_property_split = False

        subrow = row.row()
        subrow.alignment = "LEFT"
        subrow.prop(
            self,
            "show_theme_settings",
            text="Theme",
            emboss=False,
            icon="TRIA_DOWN" if self.show_theme_settings else "TRIA_RIGHT",
        )

        subrow = row.row()
        subrow.alignment = "RIGHT"
        SKETCHER_PT_theme_presets.draw_panel_header(subrow)

        if self.show_theme_settings:
            row = box.row()

            row = box.row()
            flow = row.grid_flow(
                row_major=False,
                columns=0,
                even_columns=True,
                even_rows=False,
                align=False,
            )

            def list_props_recursiv(base):
                for prop in base.rna_type.properties:
                    prop_name = prop.identifier
                    if prop_name in ("name", "rna_type"):
                        continue

                    row = flow.row()
                    if type(prop) == bpy.types.PointerProperty:
                        row.label(text=prop.name)
                        list_props_recursiv(getattr(base, prop_name))
                    else:
                        row.prop(base, prop_name)

            list_props_recursiv(self.theme_settings)


classes = (
    SKETCHER_MT_theme_presets,
    SKETCHER_PT_theme_presets,
    Preferences,
)


def register():
    from bpy.utils import register_class

    for cls in classes:
        register_class(cls)


def unregister():
    from bpy.utils import unregister_class

    for cls in reversed(classes):
        unregister_class(cls)
