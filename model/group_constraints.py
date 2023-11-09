import logging
from typing import Union

from bpy.types import PropertyGroup
from bpy.props import CollectionProperty
from bpy.utils import register_classes_factory

from .base_entity import SlvsGenericEntity
from .sketch import SlvsSketch

from .base_constraint import GenericConstraint
from .distance import SlvsDistance
from .angle import SlvsAngle
from .diameter import SlvsDiameter
from .coincident import SlvsCoincident
from .equal import SlvsEqual
from .vertical import SlvsVertical
from .horizontal import SlvsHorizontal
from .parallel import SlvsParallel
from .perpendicular import SlvsPerpendicular
from .tangent import SlvsTangent
from .midpoint import SlvsMidpoint
from .ratio import SlvsRatio

logger = logging.getLogger(__name__)


class SlvsConstraints(PropertyGroup):

    _dimensional_constraints = (
        SlvsDistance,
        SlvsAngle,
        SlvsDiameter,
    )

    _geometric_constraints = (
        SlvsCoincident,
        SlvsEqual,
        SlvsParallel,
        SlvsHorizontal,
        SlvsVertical,
        SlvsTangent,
        SlvsMidpoint,
        SlvsPerpendicular,
        SlvsRatio,
    )

    _constraints = (
        SlvsCoincident,
        SlvsEqual,
        SlvsDistance,
        SlvsAngle,
        SlvsDiameter,
        SlvsParallel,
        SlvsHorizontal,
        SlvsVertical,
        SlvsTangent,
        SlvsMidpoint,
        SlvsPerpendicular,
        SlvsRatio,
    )

    __annotations__ = {
        cls.type.lower(): CollectionProperty(type=cls) for cls in _constraints
    }

    @classmethod
    def cls_from_type(cls, type: str):
        for constraint in cls._constraints:
            if type == constraint.type:
                return constraint
        return None

    def new_from_type(self, type: str) -> GenericConstraint:
        """Create a constraint by type.

        Arguments:
            type: Type of the constraint to be created.
        """
        name = type.lower()
        constraint_list = getattr(self, name)
        return constraint_list.add()

    def get_lists(self):
        lists = []
        for entity_list in self.rna_type.properties:
            name = entity_list.identifier
            if name in ("name", "rna_type"):
                continue
            lists.append(getattr(self, name))
        return lists

    def get_list(self, type: str):
        return getattr(self, type.lower())

    def get_from_type_index(self, type: str, index: int) -> GenericConstraint:
        """Get constraint by type and local index.

        Arguments:
            type: Constraint's type.
            index: Constraint's local index.

        Returns:
            GenericConstraint: Constraint with the given type and index or None if not found.
        """
        list = getattr(self, type.lower())
        if not list or index >= len(list):
            return None
        return list[index]

    def get_index(self, constr: GenericConstraint) -> int:
        """Get the index of a constraint in its collection.

        Arguments:
            constr: Constraint to get the index for.

        Returns:
            int: Index of the constraint or -1 if not found.
        """
        list = getattr(self, constr.type.lower())
        for i, item in enumerate(list):
            if item == constr:
                return i
        return -1

    def remove(self, constr: GenericConstraint):
        """Remove a constraint.

        Arguments:
            constr: Constraint to be removed.
        """
        i = self.get_index(constr)
        self.get_list(constr.type).remove(i)

    @property
    def dimensional(self):
        for constraint_type in self._dimensional_constraints:
            for entity in self.get_list(constraint_type.type):
                yield entity

    @property
    def geometric(self):
        for constraint_type in self._geometric_constraints:
            for entity in self.get_list(constraint_type.type):
                yield entity

    @property
    def all(self):
        for entity_list in self.get_lists():
            for entity in entity_list:
                yield entity

    def add_coincident(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: SlvsSketch = None,
    ) -> SlvsCoincident:
        """Add a coincident constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsCoincident: The created constraint.
        """

        if all([e.is_point() for e in (entity1, entity2)]):
            # TODO: Implicitly merge points
            return

        c = self.coincident.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index
        c["entity2_i"] = entity2 if isinstance(entity2, int) else entity2.slvs_index
        if sketch:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        return c

    def add_equal(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsEqual:
        """Add an equal constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsEqual: The created constraint.
        """
        c = self.equal.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index
        c["entity2_i"] = entity2 if isinstance(entity2, int) else entity2.slvs_index
        if sketch is not None:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        return c

    def add_distance(
        self,
        entity1: SlvsGenericEntity,
        entity2: Union[None, SlvsGenericEntity],
        sketch: Union[SlvsSketch, None] = None,
        init: bool = False,
        **settings,
    ) -> SlvsDistance:
        """Add a distance constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

        Returns:
            SlvsDistance: The created constraint.
        """
        c = self.distance.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index

        if entity2 is not None:
            c["entity2_i"] = entity2 if isinstance(entity2, int) else entity2.slvs_index
        if sketch is not None:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        if init:
            c.assign_init_props(**settings)
        else:
            c.assign_settings(**settings)
        return c

    def add_angle(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: SlvsSketch = None,
        init: bool = False,
        **settings,
    ) -> SlvsAngle:
        """Add an angle constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

        Returns:
            SlvsAngle: The created constraint.
        """
        c = self.angle.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index
        c["entity2_i"] = entity2 if isinstance(entity2, int) else entity2.slvs_index
        if sketch is not None:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        if init:
            c.assign_init_props(**settings)
        else:
            c.assign_settings(**settings)
        return c

    def add_diameter(
        self,
        entity1: SlvsGenericEntity,
        sketch: SlvsSketch = None,
        init: bool = False,
        **settings,
    ) -> SlvsDiameter:
        """Add a diameter constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

        Returns:
            SlvsDiameter: The created constraint.
        """
        c = self.diameter.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index
        if sketch:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        if init:
            c.assign_init_props(**settings)
        else:
            c.assign_settings(**settings)
        return c

    def add_parallel(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsParallel:
        """Add a parallel constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsParallel: The created constraint.
        """
        c = self.parallel.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index
        c["entity2_i"] = entity2 if isinstance(entity2, int) else entity2.slvs_index
        if sketch is not None:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        return c

    def add_horizontal(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity = None,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsHorizontal:
        """Add a horizontal constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsHorizontal: The created constraint.
        """
        c = self.horizontal.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index
        if entity2 is not None:
            c["entity2_i"] = entity2 if isinstance(entity2, int) else entity2.slvs_index
        if sketch is not None:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        return c

    def add_vertical(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity = None,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsVertical:
        """Add a vertical constraint.

        Arguments:
            entity1: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsVertical: The created constraint.
        """
        c = self.vertical.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index
        if entity2 is not None:
            c["entity2_i"] = entity2 if isinstance(entity2, int) else entity2.slvs_index
        if sketch is not None:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        return c

    def add_tangent(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsTangent:
        """Add a tangent constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsTangent: The created constraint.
        """
        c = self.tangent.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index
        c["entity2_i"] = entity2 if isinstance(entity2, int) else entity2.slvs_index
        if sketch is not None:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        return c

    def add_midpoint(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsMidpoint:
        """Add a midpoint constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsMidpoint: The created constraint.
        """
        c = self.midpoint.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index
        c["entity2_i"] = entity2 if isinstance(entity2, int) else entity2.slvs_index
        if sketch is not None:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        return c

    def add_perpendicular(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
    ) -> SlvsPerpendicular:
        """Add a perpendicular constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.

        Returns:
            SlvsPerpendicular: The created constraint.
        """
        c = self.perpendicular.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index
        c["entity2_i"] = entity2 if isinstance(entity2, int) else entity2.slvs_index
        if sketch is not None:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        return c

    def add_ratio(
        self,
        entity1: SlvsGenericEntity,
        entity2: SlvsGenericEntity,
        sketch: Union[SlvsSketch, None] = None,
        init: bool = False,
        **settings,
    ) -> SlvsRatio:
        """Add a ratio constraint.

        Arguments:
            entity1: -
            entity2: -
            sketch: The sketch this constraint belongs to.
            init: Initialize the constraint based on the given entities.

        Returns:
            SlvsRatio: The created constraint.
        """
        c = self.ratio.add()
        c["entity1_i"] = entity1 if isinstance(entity1, int) else entity1.slvs_index
        c["entity2_i"] = entity2 if isinstance(entity2, int) else entity2.slvs_index
        if sketch is not None:
            c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        if init:
            c.assign_init_props(**settings)
        else:
            c.assign_settings(**settings)
        return c


register, unregister = register_classes_factory((SlvsConstraints,))
