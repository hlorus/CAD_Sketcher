import logging
import math
from typing import Type, Union, Tuple

import bpy
from bpy.types import PropertyGroup
from bpy.props import CollectionProperty
from bpy.utils import register_classes_factory
from mathutils import Vector, Euler, Quaternion

from .. import global_data
from ..utilities.constants import QUARTER_TURN
from ..utilities.index import breakdown_index, assemble_index

from .base_entity import SlvsGenericEntity
from .utilities import slvs_entity_pointer, update_pointers
from .point_3d import SlvsPoint3D
from .line_3d import SlvsLine3D
from .normal_3d import SlvsNormal3D
from .workplane import SlvsWorkplane
from .sketch import SlvsSketch
from .point_2d import SlvsPoint2D
from .line_2d import SlvsLine2D
from .normal_2d import SlvsNormal2D
from .arc import SlvsArc
from .circle import SlvsCircle

logger = logging.getLogger(__name__)


# NOTE: currently limited to 16 items!
# See _set_index to see how their index is handled
_entity_types = (
    SlvsPoint3D,
    SlvsLine3D,
    SlvsNormal3D,
    SlvsWorkplane,
    SlvsSketch,
    SlvsPoint2D,
    SlvsLine2D,
    SlvsNormal2D,
    SlvsArc,
    SlvsCircle,
)

_entity_collections = (
    "points3D",
    "lines3D",
    "normals3D",
    "workplanes",
    "sketches",
    "points2D",
    "lines2D",
    "normals2D",
    "arcs",
    "circles",
)


def type_from_index(index: int) -> Type[SlvsGenericEntity]:
    if index < 0:
        return None

    type_index, _ = breakdown_index(index)

    if type_index >= len(_entity_types):
        return None
    return _entity_types[type_index]


class SlvsEntities(PropertyGroup):
    """Holds all Solvespace Entities"""

    @classmethod
    def _type_index(cls, entity: SlvsGenericEntity) -> int:
        return _entity_types.index(type(entity))

    def _set_index(self, entity: SlvsGenericEntity):
        """Create an index for the entity and assign it.
        Index breakdown

        | entity type index |  entity object index  |
        |:-----------------:|:---------------------:|
        |      4 bits       |       20 bits         |
        |            total: 3 Bytes                 |
        """
        type_index = self._type_index(entity)
        sub_list = getattr(self, _entity_collections[type_index])

        local_index = len(sub_list) - 1
        # TODO: handle this case better
        assert local_index < math.pow(2, 20)
        index = assemble_index(type_index, local_index)
        entity.slvs_index = index
        return index

    @staticmethod
    def _breakdown_index(index: int):
        return breakdown_index(index)

    @classmethod
    def recalc_type_index(cls, entity):
        _, local_index = cls._breakdown_index(entity.slvs_index)
        type_index = cls._type_index(entity)
        entity.slvs_index = type_index << 20 | local_index

    def type_from_index(self, index: int) -> Type[SlvsGenericEntity]:
        return type_from_index(index)

    def collection_name_from_index(self, index: int):
        if index < 0:
            return

        type_index, _ = self._breakdown_index(index)
        return _entity_collections[type_index]

    def _get_list_and_index(self, index: int):
        type_index, local_index = self._breakdown_index(index)
        if type_index < 0 or type_index >= len(_entity_collections):
            return None, local_index
        return getattr(self, _entity_collections[type_index]), local_index

    def get(self, index: int) -> SlvsGenericEntity:
        """Get entity by index

        Arguments:
            index: The global index of the entity.

        Returns:
            SlvsGenericEntity: Entity with the given global index or None if not found.
        """
        if index == -1:
            return None
        sub_list, i = self._get_list_and_index(index)
        if not sub_list or i >= len(sub_list):
            return None
        return sub_list[i]

    def remove(self, index: int):
        """Remove entity by index

        Arguments:
            index: The global index of the entity.
        """
        assert isinstance(index, int)

        if self.get(index).origin:
            return

        entity_list, i = self._get_list_and_index(index)
        entity_list.remove(i)

        # Put last item to removed index and update all pointers to it
        last_index = len(entity_list) - 1

        if last_index < 0:
            return
        if i > last_index:
            return

        if not i == last_index:  # second last item was deleted
            entity_list.move(last_index, i)

        new_item = entity_list[i]
        update_pointers(bpy.context.scene, new_item.slvs_index, index)
        new_item.slvs_index = index

    def _init_entity(self, entity, fixed, construction, index_reference, visible=True):
        """Initializes all shared entity properties"""

        entity["fixed"] = fixed
        entity["construction"] = construction
        entity["visible"] = visible

        index = self._set_index(entity)

        if index_reference:
            return index
        return entity

    def add_point_3d(
        self,
        co: Union[Tuple[float, float, float], Vector],
        fixed: bool = False,
        construction: bool = False,
        index_reference: bool = False,
    ) -> Union[SlvsPoint3D, int]:
        """Add a point in 3d space.

        Arguments:
            co: Location of the point in 3d space.

        Returns:
            SlvsPoint3D: The created point.
        """
        if not hasattr(co, "__len__") or len(co) != 3:
            raise TypeError("Argument co must be of length 3")

        p = self.points3D.add()
        p["location"] = Vector(co)
        return self._init_entity(p, fixed, construction, index_reference)

    def add_line_3d(
        self,
        p1: Union[SlvsPoint3D, int],
        p2: Union[SlvsPoint3D, int],
        fixed: bool = False,
        construction: bool = False,
        index_reference: bool = False,
    ) -> SlvsLine3D:
        """Add a line in 3d space.

        Arguments:
            p1: Line's startpoint.
            p2: Line's endpoint.

        Returns:
            SlvsLine3D: The created line.
        """
        line = self.lines3D.add()
        line["p1_i"] = p1 if isinstance(p1, int) else p1.slvs_index
        line["p2_i"] = p2 if isinstance(p2, int) else p2.slvs_index

        return self._init_entity(line, fixed, construction, index_reference)

    def add_normal_3d(
        self,
        quat: Tuple[float, float, float, float],
        fixed: bool = False,
        construction: bool = False,
        index_reference: bool = False,
    ) -> SlvsNormal3D:
        """Add a normal in 3d space.

        Arguments:
            quat: Quaternion which describes the orientation.

        Returns:
            SlvsNormal3D: The created normal.
        """
        nm = self.normals3D.add()
        nm["orientation"] = Quaternion(quat)

        return self._init_entity(nm, fixed, construction, index_reference)

    def add_workplane(
        self,
        p1: SlvsPoint3D,
        nm: SlvsGenericEntity,
        fixed: bool = False,
        construction: bool = False,
        index_reference: bool = False,
    ) -> SlvsWorkplane:
        """Add a workplane.

        Arguments:
            p1: Workplane's originpoint.
            nm: Workplane's normal.

        Returns:
            SlvsWorkplane: The created workplane.
        """
        wp = self.workplanes.add()
        wp["p1_i"] = p1 if isinstance(p1, int) else p1.slvs_index
        wp["nm_i"] = nm if isinstance(nm, int) else nm.slvs_index

        return self._init_entity(wp, fixed, construction, index_reference)

    def add_sketch(
        self,
        wp: SlvsWorkplane,
        fixed: bool = False,
        construction: bool = False,
        index_reference: bool = False,
    ) -> SlvsSketch:
        """Add a Sketch.

        Arguments:
            wp: Sketch's workplane.

        Returns:
            SlvsSketch: The created sketch.
        """
        sketch = self.sketches.add()
        sketch["wp_i"] = wp if isinstance(wp, int) else wp.slvs_index

        retval = self._init_entity(sketch, fixed, construction, index_reference)
        index = retval if index_reference else retval.slvs_index
        _, i = self._breakdown_index(index)
        sketch.name = "Sketch"
        return retval

    def add_point_2d(
        self,
        co: Tuple[float, float],
        sketch: SlvsSketch,
        fixed: bool = False,
        construction: bool = False,
        index_reference: bool = False,
    ) -> SlvsPoint2D:
        """Add a point in 2d space.

        Arguments:
            co: Coordinates of the point on the workplane.
            sketch: The sketch this point belongs to.

        Returns:
            SlvsPoint2D: The created point.
        """
        p = self.points2D.add()
        p["co"] = Vector(co)
        p["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index

        return self._init_entity(p, fixed, construction, index_reference)

    def add_line_2d(
        self,
        p1: SlvsPoint2D,
        p2: SlvsPoint2D,
        sketch: SlvsSketch,
        fixed: bool = False,
        construction: bool = False,
        index_reference: bool = False,
    ) -> SlvsLine2D:
        """Add a line in 2d space.

        Arguments:
            p1: Line's startpoint.
            p2: Line's endpoint.
            sketch: The sketch this line belongs to.

        Returns:
            SlvsLine2D: The created line.
        """
        line = self.lines2D.add()
        line["p1_i"] = p1 if isinstance(p1, int) else p1.slvs_index
        line["p2_i"] = p2 if isinstance(p2, int) else p2.slvs_index
        line["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index

        return self._init_entity(line, fixed, construction, index_reference)

    def add_normal_2d(
        self,
        sketch: SlvsSketch,
        fixed: bool = False,
        construction: bool = False,
        index_reference: bool = False,
    ) -> SlvsNormal2D:
        """Add a normal in 2d space.

        Arguments:
            sketch: The sketch this normal belongs to.

        Returns:
            SlvsNormal2D: The created normal.
        """
        nm = self.normals2D.add()
        nm["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index

        return self._init_entity(nm, fixed, construction, index_reference)

    def add_arc(
        self,
        nm: SlvsNormal2D,
        ct: SlvsPoint2D,
        p1: SlvsPoint2D,
        p2: SlvsPoint2D,
        sketch: SlvsSketch,
        invert: bool = False,
        fixed: bool = False,
        construction: bool = False,
        index_reference: bool = False,
    ) -> SlvsArc:
        """Add an arc in 2d space.

        Arguments:
            ct: Arc's centerpoint.
            p1: Arc's startpoint.
            p2: Arc's endpoint.
            sketch: The sketch this arc belongs to.
            nm: Arc's normal.

        Returns:
            SlvsArc: The created arc.
        """
        arc = self.arcs.add()
        arc["nm_i"] = nm if isinstance(nm, int) else nm.slvs_index
        arc["ct_i"] = ct if isinstance(ct, int) else ct.slvs_index
        arc["p1_i"] = p1 if isinstance(p1, int) else p1.slvs_index
        arc["p2_i"] = p2 if isinstance(p2, int) else p2.slvs_index
        arc["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index
        arc["invert_direction"] = invert

        return self._init_entity(arc, fixed, construction, index_reference)

    def add_circle(
        self,
        nm: SlvsNormal2D,
        ct: SlvsPoint2D,
        radius: float,
        sketch: SlvsSketch,
        fixed: bool = False,
        construction: bool = False,
        index_reference: bool = False,
    ) -> SlvsCircle:
        """Add a circle in 2d space.

        Arguments:
            ct: Circle's centerpoint.
            radius: Circle's radius.
            sketch: The sketch this circle belongs to.
            nm: Circle's normal.

        Returns:
            SlvsCircle: The created circle.
        """
        c = self.circles.add()
        c["nm_i"] = nm if isinstance(nm, int) else nm.slvs_index
        c["ct_i"] = ct if isinstance(ct, int) else ct.slvs_index
        c["radius"] = float(radius)
        c["sketch_i"] = sketch if isinstance(sketch, int) else sketch.slvs_index

        return self._init_entity(c, fixed, construction, index_reference)

    @property
    def all(self):
        for coll_name in _entity_collections:
            entity_coll = getattr(self, coll_name)
            for entity in entity_coll:
                yield entity

    @property
    def selected(self):
        """Return all selected entities, might include inactive entities"""
        context = bpy.context
        items = []
        for index in global_data.selected:
            if index is None:
                continue
            entity = self.get(index)
            items.append(entity)
        return [e for e in items if e.is_selectable(context)]

    @property
    def selected_all(self):
        """Return all selected entities, might include invisible entities"""
        context = bpy.context
        items = []
        for index in global_data.selected:
            if index is None:
                continue
            entity = self.get(index)
            items.append(entity)
        return [e for e in items if e.selected]

    @property
    def selected_active(self):
        """Returns all selected and active entities"""
        context = bpy.context
        active_sketch = context.scene.sketcher.active_sketch
        return [e for e in self.selected if e.is_active(active_sketch)]

    def ensure_origin_elements(self, context):
        def set_origin_props(e):
            e.fixed = True
            e.origin = True

        sse = context.scene.sketcher.entities
        # origin
        if not self.origin:
            p = sse.add_point_3d((0.0, 0.0, 0.0))
            set_origin_props(p)
            p.name = "OriginPoint3D"
            self.origin = p

        # axis
        pi_2 = QUARTER_TURN
        for label, name, angles in zip(
            ("OriginAxisX", "OriginAxisY", "OriginAxisZ"),
            ("origin_axis_X", "origin_axis_Y", "origin_axis_Z"),
            (Euler((pi_2, 0.0, pi_2)), Euler((pi_2, 0.0, 0.0)), Euler()),
        ):
            if getattr(self, name):
                continue
            nm = sse.add_normal_3d(Euler(angles).to_quaternion())
            set_origin_props(nm)
            setattr(self, name, nm)
            nm.name = label

        # workplanes
        for label, nm_name, wp_name in (
            ("OriginWorkplaneYZ", "origin_axis_X", "origin_plane_YZ"),
            ("OriginWorkplaneXZ", "origin_axis_Y", "origin_plane_XZ"),
            ("OriginWorkplaneXY", "origin_axis_Z", "origin_plane_XY"),
        ):
            if getattr(self, wp_name):
                continue
            wp = sse.add_workplane(self.origin, getattr(self, nm_name))
            set_origin_props(wp)
            setattr(self, wp_name, wp)
            wp.name = label

    def collection_offsets(self):
        offsets = {}
        for i, key in enumerate(_entity_collections):
            offsets[i] = len(getattr(self, key))
        return offsets


if not hasattr(SlvsEntities, "__annotations__"):
    SlvsEntities.__annotations__ = {}
for entity_cls, list_name in zip(_entity_types, _entity_collections):
    SlvsEntities.__annotations__[list_name] = CollectionProperty(type=entity_cls)


slvs_entity_pointer(SlvsEntities, "origin")
slvs_entity_pointer(SlvsEntities, "origin_axis_X")
slvs_entity_pointer(SlvsEntities, "origin_axis_Y")
slvs_entity_pointer(SlvsEntities, "origin_axis_Z")
slvs_entity_pointer(SlvsEntities, "origin_plane_XY")
slvs_entity_pointer(SlvsEntities, "origin_plane_XZ")
slvs_entity_pointer(SlvsEntities, "origin_plane_YZ")


register, unregister = register_classes_factory((SlvsEntities,))
