import logging
import math
from typing import Union, Any, List

import bpy
import bmesh
from bpy.types import Mesh, Scene, Object, Operator

from .assets_manager import load_asset
from . import global_data

logger = logging.getLogger(__name__)


class BezierHandleType:
    FREE = 0
    AUTO = 1
    VECTOR = 2
    ALIGN = 3

def _ensure_attrribute(attributes, name, type, domain):
    """Ensure an attribute exists or create it if missing"""
    attr = attributes.get(name)
    if not attr:
        attributes.new(name, type, domain)
        attr = attributes.get(name)
    return attr

def set_attribute(attributes, name: str, value: Any, index:int=None):
    """Set an attribute value either for given index or for all"""

    attribute = attributes.get(name)

    if index is None:
        attribute.data.foreach_set("value", (value,) * len(attribute.data))
    else:
        attribute.data[index].value = value


class DirectConverter:
    """Converts entities directly to splines without entity walking"""

    def __init__(self, scene, sketch):
        self.scene = scene
        self.sketch = sketch
        self.entities = self._get_entities()

    def _get_entities(self) -> List:
        """Get all drawable entities from the sketch"""
        sketch_index = self.sketch.slvs_index
        entities = []

        for entity in self.scene.sketcher.entities.all:
            if not hasattr(entity, "sketch") or entity.sketch_i != sketch_index:
                continue
            if not entity.is_path():
                continue
            entities.append(entity)

        return entities

    def to_bezier(self, curve_data: bpy.types.Curve):
        """Convert entities to bezier curves, with one spline per entity"""

        # Calculate point counts for each entity
        point_counts = []
        for entity in self.entities:
            if hasattr(entity, "bezier_point_count"):
                point_counts.append(entity.bezier_point_count())
            elif hasattr(entity, "bezier_segment_count"):
                # For entities that only define segment count, add 1 for non-cyclic
                is_cyclic = entity.is_closed() if hasattr(entity, "is_closed") else False
                point_counts.append(entity.bezier_segment_count() + (0 if is_cyclic else 1))
            else:
                # Default to 2 points for simple entities like lines
                point_counts.append(2)

        # Add all curve slices
        curve_data.add_curves(point_counts)
        curve_data.set_types(type="BEZIER")
        self._ensure_attributes(curve_data)

        # Set default handle types (individual entities will override these as needed)
        set_attribute(curve_data.attributes, "handle_type_right", BezierHandleType.FREE)
        set_attribute(curve_data.attributes, "handle_type_left", BezierHandleType.FREE)

        # Process each entity
        for entity_index, entity in enumerate(self.entities):
            curve_slice = curve_data.curves[entity_index]
            is_cyclic = entity.is_closed() if hasattr(entity, "is_closed") else False

            # Set curve attributes
            set_attribute(curve_data.attributes, "resolution", self.sketch.curve_resolution, entity_index)
            set_attribute(curve_data.attributes, "cyclic", is_cyclic, entity_index)
            set_attribute(curve_data.attributes, "construction", entity.construction, entity_index)

            # Setup points for the to_bezier call
            start_point = curve_slice.points[0]
            end_point = curve_slice.points[-1] if not is_cyclic else curve_slice.points[0]

            # For entities with multiple segments
            midpoints = []
            if len(curve_slice.points) > 2:
                midpoints = [curve_slice.points[i] for i in range(1, len(curve_slice.points))]

            # Setup kwargs for to_bezier call
            kwargs = {
                "set_startpoint": True,  # Always set startpoint for direct conversion
            }
            if midpoints:
                kwargs["midpoints"] = midpoints

            # Store entity slvs_index as attribute on points
            entity_index_attr = curve_data.attributes.get("entity_index")
            if entity_index_attr:
                for point_idx in range(len(curve_slice.points)):
                    if point_idx < len(entity_index_attr.data):
                        entity_index_attr.data[point_idx].value = entity.slvs_index

            # Store entity slvs_index as attribute on segments/edges
            segment_entity_index_attr = curve_data.attributes.get("segment_entity_index")
            if segment_entity_index_attr:
                edge_count = len(curve_slice.points) - (0 if is_cyclic else 1)
                for edge_idx in range(edge_count):
                    if edge_idx < len(segment_entity_index_attr.data):
                        segment_entity_index_attr.data[edge_idx].value = entity.slvs_index

            # Call the entity's to_bezier method
            entity.to_bezier(
                curve_slice,
                start_point,
                end_point,
                False,  # No invert_direction needed with direct conversion
                **kwargs
            )

    @classmethod
    def _ensure_attributes(cls, curve_data):
        """Ensure all required attributes are present"""
        # Note: Each entity type can override the handle types as needed

        attributes = curve_data.attributes
        _ensure_attrribute(attributes, "cyclic", "BOOLEAN", "CURVE")
        _ensure_attrribute(attributes, "curve_type", "INT8", "CURVE")
        _ensure_attrribute(attributes, "handle_type_left", "INT8", "POINT")
        _ensure_attrribute(attributes, "handle_type_right", "INT8", "POINT")
        _ensure_attrribute(attributes, "handle_left", "FLOAT_VECTOR", "POINT")
        _ensure_attrribute(attributes, "handle_right", "FLOAT_VECTOR", "POINT")
        _ensure_attrribute(attributes, "resolution", "INT", "CURVE")
        _ensure_attrribute(attributes, "entity_index", "INT", "POINT")
        _ensure_attrribute(attributes, "segment_entity_index", "INT", "CURVE")
        _ensure_attrribute(attributes, "construction", "BOOLEAN", "CURVE")


def mesh_from_temporary(mesh: Mesh, name: str, existing_mesh: Union[bool, None] = None):
    bm = bmesh.new()
    bm.from_mesh(mesh)

    bmesh.ops.dissolve_limit(
        bm, angle_limit=math.radians(0.1), verts=bm.verts, edges=bm.edges
    )

    if existing_mesh:
        existing_mesh.clear_geometry()
        new_mesh = existing_mesh
    else:
        new_mesh = bpy.data.meshes.new(name)
    bm.to_mesh(new_mesh)
    bm.free()
    return new_mesh


def _link_unlink_object(scene: Scene, ob: Object, keep: bool):
    objects = scene.collection.objects
    exists = ob.name in objects

    if exists:
        if not keep:
            objects.unlink(ob)
    elif keep:
        objects.link(ob)


CONVERT_MODIFIER_NAME = "CAD Sketcher Convert"

def _ensure_convert_modifier(ob):
    """Get or create the convert modifier"""
    modifier = ob.modifiers.get(CONVERT_MODIFIER_NAME)
    if not modifier:
        modifier = ob.modifiers.new(CONVERT_MODIFIER_NAME, "NODES")
    return modifier

def update_geometry(scene: Scene, operator: Operator, sketch=None):
    coll = (sketch,) if sketch else scene.sketcher.entities.sketches
    for sketch in coll:
        data = bpy.data
        name = sketch.name

        # Create object
        if not sketch.target_object:
            curve = data.hair_curves.new(name)
            sketch.target_object = data.objects.new(name, curve)
        else:
            sketch.target_object.data.remove_curves()

        # Update object properties
        sketch.target_object.matrix_world = sketch.wp.matrix_basis
        sketch.target_object.sketch_index = sketch.slvs_index
        sketch.target_object.name = sketch.name

        # Link object
        _link_unlink_object(scene, sketch.target_object, True)

        # Add GN modifier
        modifier = _ensure_convert_modifier(sketch.target_object)
        if not modifier:
            operator.report({"ERROR"}, "Cannot add modifier to object")
            return {"CANCELLED"}

        # Ensure the convertor nodegroup is loaded
        if not load_asset(global_data.LIB_NAME, "node_groups", "CAD Sketcher Convert"):
            operator.report({"ERROR"}, "Cannot load asset 'CAD Sketcher Convert' from library")
            return {"CANCELLED"}

        # Set the nodegroup
        modifier.node_group = data.node_groups["CAD Sketcher Convert"]

        # Convert geometry to curve data using direct conversion
        conv = DirectConverter(scene, sketch)
        conv.to_bezier(sketch.target_object.data)
