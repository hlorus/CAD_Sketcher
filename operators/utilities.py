from typing import Generator

from bpy.types import Context

from .. import global_data
from ..class_defines import SlvsGenericEntity

def entities_3d(context: Context) -> Generator[SlvsGenericEntity, None, None]:
    for entity in context.scene.sketcher.entities.all:
        if hasattr(entity, "sketch"):
            continue
        yield entity

def select_all(context: Context):
    sketch = context.scene.sketcher.active_sketch
    if sketch:
        generator = sketch.sketch_entities(context)
    else:
        generator = entities_3d(context)

    for e in generator:
        if e.selected:
            continue
        if not e.is_visible(context):
            continue
        if not e.is_active(context.scene.sketcher.active_sketch):
            continue
        e.selected = True

def deselect_all(context: Context):
    global_data.selected.clear()

# NOTE: The draw handler has to be registered before this has any effect, currently it's possible that
# entities are first created with an entity that was hovered in the previous state
# Not sure if it's possible to force draw handlers...
# Also note that a running modal operator might prevent redraws, avoid returning running_modal
def ignore_hover(entity):
    ignore_list = global_data.ignore_list
    ignore_list.append(entity.slvs_index)

# TODO: could probably check entity type only through index, instead of getting the entity first...
def get_hovered(context: Context, *types):
    hovered = global_data.hover
    entity = None

    if hovered != -1:
        entity = context.scene.sketcher.entities.get(hovered)
        if type(entity) in types:
            return entity
    return None