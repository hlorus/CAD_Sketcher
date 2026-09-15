import bpy

prefs = next(
    a for a in bpy.context.preferences.addons if a.module.endswith("CAD_Sketcher")
).preferences
theme = prefs.theme_settings
entity = theme.entity
constraint = theme.constraint

entity.default = (0.0, 0.0, 0.0, 0.8999999761581421)
entity.highlight = (0.05000000074505806, 0.05000000074505806, 0.05000000074505806, 0.5)
entity.selected = (
    0.949999988079071,
    0.6143333315849304,
    0.30611106753349304,
    0.8999999761581421,
)
entity.selected_highlight = (
    0.949999988079071,
    0.6146500110626221,
    0.3059000074863434,
    0.5,
)
entity.inactive = (0.0, 0.0, 0.0, 0.20000000298023224)
entity.inactive_selected = (
    0.8999999761581421,
    0.5820000171661377,
    0.28999999165534973,
    0.20000000298023224,
)
entity.fixed = (0.0, 0.55, 0.0, 0.7)
# Opaque, saturated constraint colors that stand out on a light viewport; failed
# is orange-red so it stays distinct from the magenta default.
constraint.default = (0.9, 0.0, 0.65, 1.0)
constraint.highlight = (1.0, 0.0, 0.8, 1.0)
constraint.failed = (1.0, 0.2, 0.0, 1.0)
constraint.failed_highlight = (0.85, 0.05, 0.0, 1.0)
constraint.reference = (0.0, 0.3, 1.0, 1.0)
constraint.reference_highlight = (0.0, 0.15, 0.85, 1.0)
constraint.text = (0.1, 0.1, 0.1, 1.0)
constraint.text_highlight = (0.4, 0.4, 0.4, 1.0)
