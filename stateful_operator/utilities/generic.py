import bpy
import bmesh
from bpy.types import Object
from mathutils.bvhtree import BVHTree


def to_list(val):
    if val is None:
        return []
    if type(val) in (list, tuple):
        return list(val)
    return [
        val,
    ]


def get_pointer_get_set(index: int):
    @property
    def func(self):
        return self.get_state_pointer(index=index)

    @func.setter
    def setter(self, value):
        self.set_state_pointer(value, index=index)

    return func, setter


def get_subclasses():
    """Get all classes that inherit from StatefulOperatorLogic"""
    from ..logic import StatefulOperatorLogic

    def _get_classes(cls_list):
        ret = []
        for c in cls_list:
            sub_classes = c.__subclasses__()
            if not len(sub_classes):
                continue
            ret.extend(_get_classes(sub_classes))
        return cls_list + ret

    return _get_classes(StatefulOperatorLogic.__subclasses__())


def bvhtree_from_object(object: Object) -> BVHTree:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    object_eval = object.evaluated_get(depsgraph)
    mesh = object_eval.to_mesh()

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.transform(object.matrix_world)

    bvhtree = BVHTree.FromBMesh(bm)
    object_eval.to_mesh_clear()
    bm.free()
    return bvhtree
