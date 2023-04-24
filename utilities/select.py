import logging

from bpy.props import EnumProperty
from bpy.types import Context

from .. import global_data
from ..utilities.data_handling import entities_3d

logger = logging.getLogger(__name__)


def select_all(context: Context):
    sketch = context.scene.sketcher.active_sketch
    if sketch:
        logger.debug(
            f"Selecting all sketcher entities in sketch : {sketch.name} (slvs_index: {sketch.slvs_index})"
        )
        generator = sketch.sketch_entities(context)
    else:
        logger.debug(f"Selecting all sketcher entities")
        generator = entities_3d(context)

    for e in generator:
        if e.selected:
            continue
        if not e.is_selectable(context):
            continue
        e.selected = True


def deselect_all(context: Context):
    logger.debug("Deselecting all sketcher entities")
    global_data.selected.clear()


mode_property = EnumProperty(
    name="Mode",
    items=[
        ("SET", "Set", "Set new selection", "SELECT_SET", 1),
        ("EXTEND", "Extend", "Add to existing selection", "SELECT_EXTEND", 2),
        (
            "SUBTRACT",
            "Subtract",
            "Subtract from existing selection",
            "SELECT_SUBTRACT",
            3,
        ),
        ("TOGGLE", "Toggle", "Toggle selection", "RADIOBUT_OFF", 4),
    ],
)
