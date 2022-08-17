from typing import Type, List

from bpy.utils import register_class, unregister_class

from ..logic import StatefulOperatorLogic


def _register_stateop(cls: Type[StatefulOperatorLogic]):
    if hasattr(cls, "register_properties"):
        cls.register_properties()
    register_class(cls)


def register_stateops_factory(classes: List[Type[StatefulOperatorLogic]]):
    def register():
        for cls in classes:
            _register_stateop(cls)

    def unregister():
        for cls in reversed(classes):
            unregister_class(cls)

    return register, unregister
