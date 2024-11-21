import logging
import math
from typing import Union, Any

import bpy
import bmesh
from bpy.types import Mesh, Scene, Object, Operator

from .utilities.walker import EntityWalker
from .assets_manager import load_asset
from . import global_data

logger = logging.getLogger(__name__)


class BezierHandleType:
    FREE = 0
    AUTO = 1
    VECTOR = 2
    ALIGN = 3

def _ensure_attrribute(attributes, name, type, domain):
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



class BezierConverter(EntityWalker):
    def __init__(self, scene, sketch):
        super().__init__(scene, sketch)

    def to_bezier(self, curve_data: bpy.types.Curve):
        # Add all curve slices
        curve_data.add_curves([self._get_point_count(p[0]) for p in self.paths])
        curve_data.set_types(type="BEZIER")
        self._enusre_attributes(curve_data)

        # Set handle types
        set_attribute(curve_data.attributes, "handle_type_right", BezierHandleType.FREE)
        set_attribute(curve_data.attributes, "handle_type_left", BezierHandleType.FREE)

        # Go through all curve slices
        for spline_path_index, spline_path in enumerate(self.paths):
            path_segments = spline_path[0]
            curveSlice: bpy.types.CurveSlice = curve_data.curves[spline_path_index]
            is_cyclic = self.is_cyclic_path(path_segments)

            # Set curve attributes
            set_attribute(curve_data.attributes, "resolution", self.sketch.curve_resolution, spline_path_index)
            set_attribute(curve_data.attributes, "cyclic", is_cyclic, spline_path_index)

            segment_count = self._get_segment_count(path_segments)

            startpoint = curveSlice.points[0]
            previous_point = startpoint


            # Loop over segments and set points
            last_index = len(path_segments) - 1
            index = 0
            for i, segment in enumerate(path_segments):
                invert_direction = spline_path[1][i]

                sub_segment_count = segment_count[i]

                if i == last_index and is_cyclic:
                    end = curveSlice.points[0]
                else:
                    end = curveSlice.points[index + sub_segment_count]

                midpoints = (
                    [
                        curveSlice.points[index + i + 1]
                        for i in range(sub_segment_count - 1)
                    ]
                    if sub_segment_count
                    else []
                )
                kwargs = {}
                if i == 0:
                    kwargs["set_startpoint"] = True
                if sub_segment_count > 1:
                    kwargs["midpoints"] = midpoints

                # Call entities' to_bezier method
                previous_point = segment.to_bezier(
                    curveSlice, previous_point, end, invert_direction, **kwargs
                )
                index += sub_segment_count


    @classmethod
    def _enusre_attributes(cls, curve_data):
        """Ensure all required attributes are present"""

        attributes = curve_data.attributes
        _ensure_attrribute(attributes, "cyclic", "BOOLEAN", "CURVE")
        _ensure_attrribute(attributes, "curve_type", "INT8", "CURVE")
        _ensure_attrribute(attributes, "handle_type_left", "INT8", "POINT")
        _ensure_attrribute(attributes, "handle_type_right", "INT8", "POINT")
        _ensure_attrribute(attributes, "handle_left", "FLOAT_VECTOR", "POINT")
        _ensure_attrribute(attributes, "handle_right", "FLOAT_VECTOR", "POINT")
        _ensure_attrribute(attributes, "resolution", "INT", "CURVE")



    @classmethod
    def _get_segment_count(cls, path_segments):
        segment_count = [
                    seg.bezier_segment_count()
                    if hasattr(seg, "bezier_segment_count")
                    else 1
                    for seg in path_segments
                ]
        return segment_count

    @classmethod
    def _get_point_count(cls, path_segments):
        segment_count = cls._get_segment_count(path_segments)
        amount = sum(segment_count)

        is_cyclic = cls.is_cyclic_path(path_segments)
        if not is_cyclic:
            amount += 1
        return amount


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


def _ensure_convert_modifier(ob):
    """Get or create the convert modifier"""
    modifier = ob.modifiers.get("Convert")
    if not modifier:
        modifier = ob.modifiers.new("Convert", "NODES")
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

        # Convert geometry to curve data
        conv = BezierConverter(scene, sketch)
        conv.to_bezier(sketch.target_object.data)


