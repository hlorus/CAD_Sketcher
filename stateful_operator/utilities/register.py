from typing import List, Type

from bpy.utils import register_class, unregister_class

from ..logic import StatefulOperatorLogic
from . import continuation


def _register_stateop(cls: Type[StatefulOperatorLogic]):
    if hasattr(cls, "register_properties"):
        cls.register_properties()
    register_class(cls)
    if getattr(cls, "accepts_chain", False):
        continuation.register_accepting(cls.bl_idname)


def register_stateops_factory(classes: List[Type[StatefulOperatorLogic]]):
    def register():
        for cls in classes:
            _register_stateop(cls)

    def unregister():
        for cls in reversed(classes):
            continuation.unregister_accepting(cls.bl_idname)
            unregister_class(cls)

    return register, unregister
