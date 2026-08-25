import logging

import bpy
from bpy.props import IntProperty
from bpy.types import Context
import math
from mathutils import Vector, Matrix

logger = logging.getLogger(__name__)


def slvs_entity_pointer(cls, name, **kwargs):
    index_prop = name + "_i"
    annotations = {}
    if hasattr(cls, "__annotations__"):
        annotations = cls.__annotations__.copy()
    annotations[index_prop] = IntProperty(name=name + " index", default=-1, **kwargs)
    setattr(cls, "__annotations__", annotations)

    @property
    def func(self):
        index = getattr(self, index_prop)
        return None if index == -1 else bpy.context.scene.sketcher.entities.get(index)
    setattr(cls, name, func)

    @func.setter
    def setter(self, entity):
        index = entity.slvs_index if entity else -1
        setattr(self, index_prop, index)

    setattr(cls, name, setter)


def tag_update(self, context: Context):
    self.tag_update()


def round_v(vec, ndigits=None):
    values = []
    for v in vec:
        values.append(round(v, ndigits=ndigits))
    return Vector(values)


def get_connection_point(seg_1, seg_2):
    points = seg_1.connection_points()
    for p in seg_2.connection_points():
        if p in points:
            return p


# NOTE: When tweaking, it's necessary to constrain a point that is only temporary available
# and has no SlvsPoint representation
def make_coincident(solvesys, point_handle, e2, wp, group, entity_type=None):
    from .categories import LINE, CURVE, POINT
    from .workplane import SlvsWorkplane

    kwargs = {}
    if wp:
        kwargs["workplane"] = wp

    return solvesys.coincident(group, point_handle, e2.py_data, **kwargs)


def update_pointers(scene, index_old, index_new):
    """Replaces all references to an entity index with its new index"""
    logger.debug("Update references {} -> {}".format(index_old, index_new))
    # NOTE: this should go through all entity pointers and update them if necessary.
    # It might be possible to use the msgbus to notify and update the IntProperty pointers

    for o in scene.sketcher.all:
        if not hasattr(o, "update_pointers"):
            continue
        o.update_pointers(index_old, index_new)

    scene.sketcher.purge_stale_data()