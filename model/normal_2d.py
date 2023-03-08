import logging

from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..solver import Solver
from .base_entity import SlvsGenericEntity
from .utilities import slvs_entity_pointer
from .base_entity import Entity2D


logger = logging.getLogger(__name__)


class SlvsNormal2D(Entity2D, PropertyGroup):
    """Representation of a normal in 2D Space.

    This entity isn't currently exposed to the user and gets created
    implicitly when needed.

    Arguments:
        sketch (SlvsSketch): The sketch to get the orientation from
    """

    def update(self):
        self.is_dirty = False

    def draw(self, context):
        pass

    def draw_id(self, context):
        pass

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        handle = solvesys.addNormal2d(self.wp.py_data, group=group)
        self.py_data = handle


slvs_entity_pointer(SlvsNormal2D, "sketch")

register, unregister = register_classes_factory((SlvsNormal2D,))
