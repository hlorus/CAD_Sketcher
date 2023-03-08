import bpy

prefs = bpy.context.preferences.addons["CAD_Sketcher"].preferences
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
constraint.default = (
    0.949999988079071,
    0.5699999928474426,
    0.5699999928474426,
    0.8999999761581421,
)
constraint.highlight = (0.949999988079071, 0.5699999928474426, 0.5699999928474426, 0.5)
constraint.failed = (0.949999988079071, 0.0, 0.0, 0.800000011920929)
constraint.failed_highlight = (1.0, 0.0, 0.0, 0.949999988079071)
constraint.text = (0.0, 0.0, 0.0, 1.0)
constraint.text_highlight = (0.5, 0.5, 0.5, 1.0)
