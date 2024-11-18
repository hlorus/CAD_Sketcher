import logging
import math
from typing import Union

import bpy
import bmesh
from bpy.types import Mesh, Scene, Object, Operator

from .model.base_entity import SlvsGenericEntity
from .model.line_2d import SlvsLine2D
from .model.arc import SlvsArc
from .model.circle import SlvsCircle

from .utilities.bezier import set_handles
from .utilities.walker import EntityWalker
from .assets_manager import load_asset
from . import global_data

logger = logging.getLogger(__name__)



def _ensure_attrribute(attributes, name, type, domain):
    attr = attributes.get(name)
    if not attr:
        attributes.new(name, type, domain)
        attr = attributes.get(name)
    return attr

def set_attribute(attributes, name, index, value):
    attributes.get(name).data[index].value = value


def _conv_bezier_line2d(
    entity: SlvsLine2D,
    spline: bpy.types.CurveSlice,
    startpoint: bpy.types.CurvePoint,
    endpoint: bpy.types.CurvePoint,
    invert_direction: bool,
    set_startpoint: bool = False
) -> bpy.types.CurvePoint:
    locations = [entity.p1.co.to_3d(), entity.p2.co.to_3d()]
    if invert_direction:
        locations.reverse()

    if set_startpoint:
        startpoint.position = locations[0]
    endpoint.position = locations[1]

    attributes = spline.id_data.attributes
    attributes["handle_right"].data[startpoint.index].vector = locations[0]
    attributes["handle_left"].data[endpoint.index].vector = locations[1]
    return endpoint


# Lookup table for entity to bezier conversion functions
bezier_conversion_lookup = {
    # (type, func),
    SlvsLine2D: _conv_bezier_line2d,
    # SlvsArc: _conv_bezier_arc,
    # SlvsCircle: _conv_beier_circle,
}



class BezierConverter(EntityWalker):
    def __init__(self, scene, sketch):
        super().__init__(scene, sketch)

    def to_bezier(self, curve_data: bpy.types.Curve):
        # Add all curve slices
        curve_data.add_curves([self._get_point_count(p[0]) for p in self.paths])
        curve_data.set_types(type="BEZIER")
        self._enusre_attributes(curve_data)

        # Go through all curve slices
        for spline_path_index, spline_path in enumerate(self.paths):
            path_segments = spline_path[0]
            curveSlice: bpy.types.CurveSlice = curve_data.curves[spline_path_index]
            is_cyclic = self.is_cyclic_path(path_segments)

            # Set curve attributes
            set_attribute(curve_data.attributes, "resolution", spline_path_index, self.sketch.curve_resolution)
            set_attribute(curve_data.attributes, "cyclic", spline_path_index, is_cyclic)
            # set_attribute(curve_data.attributes, "curve_type", spline_path_index, 2)

            segment_count = self._get_segment_count(path_segments)
            # amount = self._get_point_count(path_segments)

            startpoint = curveSlice.points[0]
            # set_handles(startpoint)
            previous_point = startpoint


            # Loop over segments and set points
            last_index = len(path_segments) - 1
            index = 0
            for i, segment in enumerate(path_segments):
                invert_direction = spline_path[1][i]

                # TODO: rename to seg_count and segment_counts
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


                # Set handle types
                set_attribute(curve_data.attributes, "handle_type_right", previous_point.index, 3)
                set_attribute(curve_data.attributes, "handle_type_left", end.index, 3)


                # conv_func = bezier_conversion_lookup.get(segment.__class__)
                # assert(conv_func)
                # conv_func(segment, curveSlice, previous_point, end, invert_direction, **kwargs)

                # Call entities' to_bezier method
                previous_point = segment.to_bezier(
                    curveSlice, previous_point, end, invert_direction, **kwargs
                )
                index += sub_segment_count


    @classmethod
    def _enusre_attributes(cls, curve_data):
        attributes = curve_data.attributes
        _ensure_attrribute(attributes, "cyclic", "BOOLEAN", "CURVE")
        _ensure_attrribute(attributes, "curve_type", "INT8", "CURVE")
        _ensure_attrribute(attributes, "handle_type_left", "INT8", "POINT")
        _ensure_attrribute(attributes, "handle_type_right", "INT8", "POINT")
        _ensure_attrribute(attributes, "handle_left", "FLOAT_VECTOR", "POINT")
        _ensure_attrribute(attributes, "handle_right", "FLOAT_VECTOR", "POINT")
        _ensure_attrribute(attributes, "resolution", "INT", "CURVE")



    @classmethod
    def _set_attribute(cls, curve_data, name, index, value):
        curve_data.attributes.get(name).data[index].value = value


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


def _cleanup_data(sketch, mode: str):
    if sketch.target_object and mode != "MESH":
        sketch.target_object.sketch_index = -1
        bpy.data.objects.remove(sketch.target_object, do_unlink=True)
        sketch.target_object = None
    if sketch.target_curve_object and mode != "BEZIER":
        sketch.target_curve_object.sketch_index = -1
        bpy.data.objects.remove(sketch.target_curve_object, do_unlink=True)
        sketch.target_curve_object = None


def _link_unlink_object(scene: Scene, ob: Object, keep: bool):
    objects = scene.collection.objects
    exists = ob.name in objects

    if exists:
        if not keep:
            objects.unlink(ob)
    elif keep:
        objects.link(ob)



def update_geometry(scene: Scene, operator: Operator, sketch=None):
    coll = (sketch,) if sketch else scene.sketcher.entities.sketches
    for sketch in coll:
        data = bpy.data
        name = sketch.name

        # Create object
        if not sketch.target_object:
            curve = data.hair_curves.new(name)
            sketch.target_object = data.objects.new(name, curve)

        # Update object properties
        sketch.target_object.matrix_world = sketch.wp.matrix_basis
        sketch.target_object.sketch_index = sketch.slvs_index
        sketch.target_object.name = sketch.name

        # Link object
        _link_unlink_object(scene, sketch.target_object, True)

        # Add GN modifier
        modifier = sketch.target_object.modifiers.new("Convert", "NODES")
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
        conv.to_bezier(curve)



def update_convertor_geometry(scene: Scene, sketch=None):
    coll = (sketch,) if sketch else scene.sketcher.entities.sketches
    for sketch in coll:
        mode = sketch.convert_type
        if sketch.convert_type == "NONE":
            _cleanup_data(sketch, mode)
            continue

        data = bpy.data
        name = sketch.name

        # Create curve object
        if not sketch.target_curve_object:
            curve = bpy.data.objects.data.curves.new(name, "CURVE")
            object = bpy.data.objects.new(name, curve)
            sketch.target_curve_object = object
        else:
            # Clear curve data
            sketch.target_curve_object.data.splines.clear()

        # Convert geometry to curve data
        conv = BezierConverter(scene, sketch)

        # TODO: Avoid re-converting sketches where nothing has changed!
        logger.info("Convert sketch {} to {}: ".format(sketch, mode.lower()))
        curve_data = sketch.target_curve_object.data
        conv.to_bezier(curve_data)
        data = curve_data

        # Link / unlink curve object
        _link_unlink_object(scene, sketch.target_curve_object, mode == "BEZIER")

        if mode == "MESH":
            # Set curve resolution
            for spline in sketch.target_curve_object.data.splines:
                spline.resolution_u = sketch.curve_resolution

            # Create mesh data
            temp_mesh = sketch.target_curve_object.to_mesh()
            mesh = mesh_from_temporary(
                temp_mesh,
                name,
                existing_mesh=(
                    sketch.target_object.data if sketch.target_object else None
                ),
            )
            sketch.target_curve_object.to_mesh_clear()

            # Create mesh object
            if not sketch.target_object:
                mesh_object = bpy.data.objects.new(name, mesh)
                scene.collection.objects.link(mesh_object)
                sketch.target_object = mesh_object
            else:
                sketch.target_object.data = mesh

        _cleanup_data(sketch, mode)

        target_ob = (
            sketch.target_object if mode == "MESH" else sketch.target_curve_object
        )
        target_ob.matrix_world = sketch.wp.matrix_basis

        target_ob.sketch_index = sketch.slvs_index

        # Update object name
        target_ob.name = sketch.name
