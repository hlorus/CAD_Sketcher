import logging
import secrets
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
from .symmetry import SlvsSymmetry

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
        SlvsSymmetry,
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
        SlvsSymmetry,
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

    def _new_constraint_uid(self) -> str:
        return secrets.token_hex(8)

    def _ensure_unique_uid(self, uid: str) -> str:
        if uid and self.get_by_uid(uid):
            uid = ""
        while not uid:
            candidate = self._new_constraint_uid()
            if not self.get_by_uid(candidate):
                uid = candidate
        return uid

    def _init_constraint(self, constr: GenericConstraint) -> GenericConstraint:
        uid = getattr(constr, "constraint_uid", "")
        if not uid:
            uid = self._ensure_unique_uid(uid)
            constr.constraint_uid = uid
        if hasattr(constr, "value"):
            import bpy
            scene = bpy.context.scene
            if scene and hasattr(scene, "sketcher") and scene.sketcher:
                try:
                    scene.sketcher.create_constraint_value_endpoint(constr)
                except (RuntimeError, AttributeError):
                    pass
        return constr

    def ensure_constraint_uid(self, constr: GenericConstraint) -> str:
        uid = getattr(constr, "constraint_uid", "")
        if uid:
            return uid
        uid = self._ensure_unique_uid(uid)
        constr.constraint_uid = uid
        return uid

    def get_by_uid(self, uid: str) -> GenericConstraint:
        if not uid:
            return None
        for constraint in self.all:
            if getattr(constraint, "constraint_uid", "") == uid:
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

    def add_coincident(self, curve_id_1="", curve_id_2="") -> SlvsCoincident:
        c = self.coincident.add()
        c.curve_id_1 = curve_id_1
        c.curve_id_2 = curve_id_2
        return self._init_constraint(c)

    def add_equal(self, curve_id_1="", curve_id_2="") -> SlvsEqual:
        c = self.equal.add()
        c.curve_id_1 = curve_id_1
        c.curve_id_2 = curve_id_2
        return self._init_constraint(c)

    def add_distance(self, init=False, curve_id_1="", curve_id_2="", **settings) -> SlvsDistance:
        c = self.distance.add()
        c.curve_id_1 = curve_id_1
        c.curve_id_2 = curve_id_2
        self._init_constraint(c)
        if init:
            c.assign_init_props(**settings)
        else:
            c.assign_settings(**settings)
        return c

    def add_angle(self, init=False, curve_id_1="", curve_id_2="", **settings) -> SlvsAngle:
        c = self.angle.add()
        c.curve_id_1 = curve_id_1
        c.curve_id_2 = curve_id_2
        self._init_constraint(c)
        if init:
            c.assign_init_props(**settings)
        else:
            c.assign_settings(**settings)
        return c

    def add_diameter(self, init=False, curve_id_1="", **settings) -> SlvsDiameter:
        c = self.diameter.add()
        c.curve_id_1 = curve_id_1
        self._init_constraint(c)
        if init:
            c.assign_init_props(**settings)
        else:
            c.assign_settings(**settings)
        return c

    def _add_simple(self, collection_name, curve_id_1="", curve_id_2=""):
        c = getattr(self, collection_name).add()
        c.curve_id_1 = curve_id_1
        c.curve_id_2 = curve_id_2
        return self._init_constraint(c)

    def add_parallel(self, curve_id_1="", curve_id_2="") -> SlvsParallel:
        return self._add_simple("parallel", curve_id_1, curve_id_2)

    def add_horizontal(self, curve_id_1="", curve_id_2="") -> SlvsHorizontal:
        return self._add_simple("horizontal", curve_id_1, curve_id_2)

    def add_vertical(self, curve_id_1="", curve_id_2="") -> SlvsVertical:
        return self._add_simple("vertical", curve_id_1, curve_id_2)

    def add_tangent(self, curve_id_1="", curve_id_2="") -> SlvsTangent:
        return self._add_simple("tangent", curve_id_1, curve_id_2)

    def add_midpoint(self, curve_id_1="", curve_id_2="") -> SlvsMidpoint:
        return self._add_simple("midpoint", curve_id_1, curve_id_2)

    def add_perpendicular(self, curve_id_1="", curve_id_2="") -> SlvsPerpendicular:
        return self._add_simple("perpendicular", curve_id_1, curve_id_2)

    def add_ratio(self, init=False, curve_id_1="", curve_id_2="", **settings) -> SlvsRatio:
        c = self._add_simple("ratio", curve_id_1, curve_id_2)
        if init:
            c.assign_init_props(**settings)
        else:
            c.assign_settings(**settings)
        return c

    def add_symmetry(self, curve_id_1="", curve_id_2="", curve_id_3="") -> SlvsSymmetry:
        c = self.symmetry.add()
        c.curve_id_1 = curve_id_1
        c.curve_id_2 = curve_id_2
        c.curve_id_3 = curve_id_3
        return self._init_constraint(c)


import bpy
from bpy.props import PointerProperty

_register_classes, _unregister_classes = register_classes_factory((SlvsConstraints,))


def register():
    _register_classes()
    bpy.types.Curves.sketch_constraints = PointerProperty(type=SlvsConstraints)


def unregister():
    del bpy.types.Curves.sketch_constraints
    _unregister_classes()
