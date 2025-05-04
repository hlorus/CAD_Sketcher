import logging
import math
from typing import Union

import bpy
import bmesh
from bpy.types import Mesh, Scene, Object

from .utilities.bezier import set_handles
from .utilities.walker import EntityWalker

logger = logging.getLogger(__name__)


class BezierConverter(EntityWalker):
    def __init__(self, scene, sketch):
        super().__init__(scene, sketch)

    def to_bezier(self, curve_data):
        curve_data.fill_mode = "FRONT" if self.sketch.fill_shape else "NONE"

        for spline_path in self.paths:
            path_segments = spline_path[0]
            s = curve_data.splines.new("BEZIER")

            is_cyclic = self.is_cyclic_path(path_segments)
            if is_cyclic:
                s.use_cyclic_u = True

            segment_count = [
                seg.bezier_segment_count()
                if hasattr(seg, "bezier_segment_count")
                else 1
                for seg in path_segments
            ]
            amount = sum(segment_count)

            if not is_cyclic:
                amount += 1
            # NOTE: There's  already one point in a new spline
            s.bezier_points.add(amount - 1)

            startpoint = s.bezier_points[0]
            set_handles(startpoint)
            previous_point = startpoint

            last_index = len(path_segments) - 1
            index = 0
            for i, segment in enumerate(path_segments):
                # Fix for missing direction information
                if len(spline_path) < 2 or len(spline_path[1]) <= i:
                    invert_direction = False
                    logger.warning(f"Missing direction information for segment {i}, assuming False")
                else:
                    invert_direction = spline_path[1][i]

                # TODO: rename to seg_count and segment_counts
                sub_segment_count = segment_count[i]

                if i == last_index and is_cyclic:
                    end = s.bezier_points[0]
                else:
                    end = s.bezier_points[index + sub_segment_count]

                midpoints = (
                    [
                        s.bezier_points[index + i + 1]
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

                previous_point = segment.to_bezier(
                    s, previous_point, end, invert_direction, **kwargs
                )
                index += sub_segment_count


def mesh_from_temporary(mesh: Mesh, name: str, existing_mesh: Union[bool, None] = None):
    bm = bmesh.new()
    bm.from_mesh(mesh)
    
    # Flag to identify if we're dealing with a circle/arc
    # Identify circular shapes by checking if there are vertices with many connections
    # Most circle/arc vertices will have exactly 2 connections
    circular_shape = False
    vertex_count = len(bm.verts)
    edge_count = len(bm.edges)
    
    # Heuristic for circular shapes - circles tend to have a specific ratio of edges to vertices
    if vertex_count > 8 and edge_count >= vertex_count:
        # Check the curvature - if we have consistent curvature, likely a circle/arc
        # For a circle, each vertex would have a similar angle with its neighbors
        angles = []
        for edge in bm.edges:
            if not edge.is_boundary:
                continue
            
            for vert in (edge.verts[0], edge.verts[1]):
                if len(vert.link_edges) == 2:
                    edges = list(vert.link_edges)
                    vec1 = edges[0].other_vert(vert).co - vert.co
                    vec2 = edges[1].other_vert(vert).co - vert.co
                    if vec1.length > 0 and vec2.length > 0:
                        angle = vec1.angle(vec2)
                        angles.append(angle)
        
        # Check if angles are consistent (circles have consistent internal angles)
        if angles and len(angles) > 4:
            avg_angle = sum(angles) / len(angles)
            # Check if avg_angle is not close to 180 degrees (straight line)
            if abs(avg_angle - math.pi) > 0.1:
                circular_shape = True
    
    # If it doesn't appear to be a circle/arc, apply the original removal process
    if not circular_shape:
        # First pass: dissolve vertices that are nearly collinear (handles most cases)
        bmesh.ops.dissolve_limit(
            bm, angle_limit=math.radians(0.1), verts=bm.verts, edges=bm.edges
        )
        
        # Second pass: specifically target line segments with multiple unnecessary vertices
        edges_to_dissolve = []
        for edge in bm.edges:
            if not edge.is_boundary:
                continue
            
            # Check if vertex is connected to exactly 2 edges and is nearly collinear
            for vert in (edge.verts[0], edge.verts[1]):
                if len(vert.link_edges) == 2:
                    edges = list(vert.link_edges)
                    vec1 = edges[0].other_vert(vert).co - vert.co
                    vec2 = edges[1].other_vert(vert).co - vert.co
                    if vec1.length > 0 and vec2.length > 0:
                        # Check if the two edges are nearly collinear
                        angle = vec1.angle(vec2)
                        if abs(angle - math.pi) < 0.01:  # Very close to 180 degrees
                            edges_to_dissolve.append(vert)
        
        # Dissolve unnecessary vertices
        if edges_to_dissolve:
            bmesh.ops.dissolve_verts(bm, verts=edges_to_dissolve)
    else:
        # For circular shapes, use a more conservative approach
        # Only remove truly collinear vertices with a much stricter threshold
        edges_to_dissolve = []
        for edge in bm.edges:
            if not edge.is_boundary:
                continue
            
            for vert in (edge.verts[0], edge.verts[1]):
                if len(vert.link_edges) == 2:
                    edges = list(vert.link_edges)
                    vec1 = edges[0].other_vert(vert).co - vert.co
                    vec2 = edges[1].other_vert(vert).co - vert.co
                    if vec1.length > 0 and vec2.length > 0:
                        # Only dissolve if practically a straight line (much stricter threshold)
                        angle = vec1.angle(vec2)
                        if abs(angle - math.pi) < 0.001:  # 0.057 degrees - extremely close to 180 degrees
                            edges_to_dissolve.append(vert)
        
        # Dissolve only truly unnecessary vertices
        if edges_to_dissolve:
            bmesh.ops.dissolve_verts(bm, verts=edges_to_dissolve)

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
