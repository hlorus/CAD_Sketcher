import logging

from bpy.props import EnumProperty
from ..model.sketch_ref import get_active_sketch
from bpy.types import Context

from .. import global_data

logger = logging.getLogger(__name__)


def select_all(context: Context):
    sketch = get_active_sketch(context)
    if not sketch or not sketch.target_object or not sketch.target_object.data:
        return

    curve_data = sketch.target_object.data
    n = len(curve_data.curves)
    cid_attr = curve_data.attributes.get("curve_id")
    vis_attr = curve_data.attributes.get("visible")
    if not cid_attr:
        return

    for i in range(n):
        if vis_attr and not vis_attr.data[i].value:
            continue
        cid = cid_attr.data[i].value
        if cid and cid not in global_data.selected:
            global_data.selected.append(cid)


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
