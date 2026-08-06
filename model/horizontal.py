import logging

from bpy.props import StringProperty
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory

from ..curve_solver import Solver
from ..global_data import WpReq
from .base_constraint import GenericConstraint
from .line_2d import SlvsLine2D
from .point_2d import SlvsPoint2D
from .utilities import slvs_entity_pointer

logger = logging.getLogger(__name__)


# NOTE: this could also support constraining two points
class SlvsHorizontal(GenericConstraint, PropertyGroup):
    """Forces a line segment to be horizontal. It applies in 2D Space only because
    the meaning of horizontal or vertical is defined by the workplane.
    """

    type = "HORIZONTAL"
    label = "Horizontal"
    signature = ((SlvsLine2D, SlvsPoint2D), (SlvsPoint2D,))

    curve_id_1: StringProperty(name="Curve ID 1", default="")
    curve_id_2: StringProperty(name="Curve ID 2", default="")

    @classmethod
    def get_types(cls, index, entities):
        if index == 1:
            # return None if first entity is line
            if entities[0] and entities[0].is_line():
                return None

        return cls.signature[index]

    def needs_wp(self):
        return WpReq.NOT_FREE

    def create_slvs_data(self, solvesys, group=Solver.group_fixed):
        wp = self.get_workplane()

        kwargs = {}
        if self.entity1.is_point():
            kwargs["entityB"] = self.entity2.py_data

        return solvesys.horizontal(group, self.entity1.py_data, wp, **kwargs)

    def create_slvs_data_from_curves(self, solvesys, handle_map, wp, group):
        """Create solvespace constraint from curve_id handles."""
        h1 = handle_map.get(self.curve_id_1)
        if h1 is None:
            return None

        # The solver form depends on the first entity's *type*, not merely on
        # whether a second curve id is stored: a line is constrained on its own,
        # a point needs a valid partner point. Old/corrupt files can leave a
        # point-based constraint without a resolvable partner -- feeding that to
        # the single-line form makes solvespace treat a point as a line and
        # crash Blender (issue #342), so skip anything we can't build cleanly.
        ref1 = self.ref(1)
        kwargs = {}
        if ref1 and ref1.is_line():
            pass  # single-line form
        elif ref1 and ref1.is_point():
            h2 = handle_map.get(self.curve_id_2) if self.curve_id_2 else None
            if h2 is None:
                self.failed = True
                return None
            kwargs["entityB"] = h2
        else:
            self.failed = True
            return None

        return solvesys.horizontal(group, h1, wp, **kwargs)

    def placements(self):
        return (self.ref(1),)


slvs_entity_pointer(SlvsHorizontal, "entity1")
slvs_entity_pointer(SlvsHorizontal, "entity2")
slvs_entity_pointer(SlvsHorizontal, "sketch")

register, unregister = register_classes_factory((SlvsHorizontal,))
