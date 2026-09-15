import bpy

prefs = next(
    a for a in bpy.context.preferences.addons if a.module.endswith("CAD_Sketcher")
).preferences
theme = prefs.theme_settings
entity = theme.entity
constraint = theme.constraint

entity.default = (0.0, 0.0, 0.0, 0.800000011920929)
entity.highlight = (0.6499999761581421, 0.6499999761581421, 0.6499999761581421, 0.5)
entity.selected = (
    0.8999999761581421,
    0.5820000171661377,
    0.28999999165534973,
    0.699999988079071,
)
entity.selected_highlight = (
    1.0,
    0.6470000147819519,
    0.32199999690055847,
    0.949999988079071,
)
entity.inactive = (0.0, 0.0, 0.0, 0.4000000059604645)
entity.inactive_selected = (
    0.8999999761581421,
    0.5820000171661377,
    0.28999999165534973,
    0.20000000298023224,
)
entity.fixed = (0.0, 0.55, 0.0, 0.7)
# Opaque, saturated constraint colors so constraints stand out on the viewport.
constraint.default = (1.0, 0.0, 0.6, 1.0)
constraint.highlight = (1.0, 0.35, 0.8, 1.0)
constraint.failed = (1.0, 0.2, 0.0, 1.0)
constraint.failed_highlight = (1.0, 0.45, 0.15, 1.0)
constraint.reference = (0.0, 0.45, 1.0, 1.0)
constraint.reference_highlight = (0.4, 0.7, 1.0, 1.0)
constraint.text = (0.8999999761581421, 0.8999999761581421, 0.8999999761581421, 1.0)
constraint.text_highlight = (1.0, 1.0, 1.0, 1.0)
