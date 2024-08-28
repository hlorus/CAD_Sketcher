import logging

import bpy
from bpy.types import Operator, Context, Event
from mathutils import Vector

from ..model.types import SlvsWorkplane
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from .base_3d import Operator3d
from .utilities import activate_sketch, switch_sketch_mode
from ..stateful_operator.utilities.geometry import get_evaluated_obj, get_mesh_element
from ..utilities.geometry import get_face_orientation


logger = logging.getLogger(__name__)


# TODO:
# - Draw sketches
class View3D_OT_slvs_add_sketch(Operator, Operator3d):
    """Add a sketch"""

    bl_idname = Operators.AddSketch
    bl_label = "Add Sketch"
    bl_options = {"UNDO"}

    sketch_state1_doc = ["Workplane", "Pick a workplane as base for the sketch."]

    states = (
        state_from_args(
            sketch_state1_doc[0],
            description=sketch_state1_doc[1],
            pointer="wp",
            types=(SlvsWorkplane,),
            property=None,
            use_create=False,
        ),
    )

    def prepare_origin_elements(self, context):
        context.scene.sketcher.entities.ensure_origin_elements(context)
        return True

    def init(self, context: Context, event: Event):
        switch_sketch_mode(self, context, to_sketch_mode=True)
        self.prepare_origin_elements(context)
        bpy.ops.ed.undo_push(message="Ensure Origin Elements")
        context.scene.sketcher.show_origin = True
        return True

    def main(self, context: Context):
        sse = context.scene.sketcher.entities
        sketch = sse.add_sketch(self.wp)

        # Add point at origin
        # NOTE: Maybe this could create a reference entity of the main origin?
        p = sse.add_point_2d((0.0, 0.0), sketch)
        p.fixed = True

        activate_sketch(context, sketch.slvs_index, self)
        self.target = sketch
        return True

    def fini(self, context: Context, succeed: bool):
        context.scene.sketcher.show_origin = False
        if hasattr(self, "target"):
            logger.debug("Add: {}".format(self.target))

        if succeed:
            self.wp.visible = False
        else:
            switch_sketch_mode(self, context, to_sketch_mode=False)



class View3D_OT_slvs_add_sketch_face(Operator, Operator3d):
    """Add a workplane and start sketch on mesh face"""

    bl_idname = Operators.AddSketchFace
    bl_label = "Add sketch on mesh face"
    bl_options = {"REGISTER", "UNDO"}

    wp_face_state1_doc = (
        "Face",
        "Pick a mesh face to use as workplane's and sketch's surface.",
    )

    states = (
        state_from_args(
            wp_face_state1_doc[0],
            description=wp_face_state1_doc[1],
            use_create=False,
            pointer="face",
            types=(bpy.types.MeshPolygon,),
            interactive=True,
        ),
    )

    def main(self, context: Context):
        sse = context.scene.sketcher.entities

        obj_name, clicked_face_index = self.get_state_pointer(index=0, implicit=True)
        clicked_obj = get_evaluated_obj(context, bpy.data.objects[obj_name])
        clicked_mesh = clicked_obj.data
        clicked_face = clicked_mesh.polygons[clicked_face_index]
        
        obj_translation = clicked_obj.matrix_world
        quat = get_face_orientation(clicked_mesh, clicked_face) # Quternion
        quat.rotate(obj_translation)
        
        workplane_origin = obj_translation @ clicked_face.center
        print("1: " + str(obj_translation))
        print("2: " + str(clicked_face))
        print("2.1: " + str(clicked_face.center))
        origin = sse.add_point_3d(workplane_origin)
        nm = sse.add_normal_3d(quat)

        self.target = sse.add_workplane(origin, nm)
        
        context.area.tag_redraw() # Force re-draw of UI (Blender doesn't update after tool usage)

        meshes = [o for o in context.scene.objects if o.type == 'MESH']
        # print(meshes)

        # Workplane normal in world coordinates
        workplane_normal = quat @ Vector((0.0, 0.0, 1.0))
        
        sketch = sse.add_sketch(self.target)
        p = sse.add_point_2d((0.0, 0.0), sketch, fixed = True)

        activate_sketch(context, sketch.slvs_index, self)
        self.target = sketch

        # TODO: Only project selected mesh/face depending on checkbox
        # TODO: Option to not project after creating workplane
        # TODO: Option to choose if projected lines/points should be construction

        # Make these changable when creating face
        limitDist = 0.025;
        connectLines = True; # May cause performance issues. idk

        addedPoints = {}
        for clicked_mesh in meshes:
            vertices = clicked_mesh.data.vertices;
            for vertex in vertices:
                # Make vertex relative to plane
                vertex_world = obj_translation @ vertex.co;
                translated = vertex_world - workplane_origin;
                
                # Projection to plane
                distance_to_plane = translated.dot(workplane_normal);
                projection = translated - distance_to_plane * workplane_normal;
        
                if abs(distance_to_plane) > limitDist:
                    continue;
                # print(f"Vertex {vertex.index} distance to plane: {abs(distance_to_plane)}");

                ## Used ChatGPT, quaternion rotations is too hard.
                # To 2D projection relative to the workplane
                # Use the workplane orientation (quat) to project into 2D
                local_projection = projection.copy();
                local_projection.rotate(quat.conjugated());
                x, y, _ = local_projection;

                point = sse.add_point_2d((x, y), sketch, fixed = True, index_reference = True);
                addedPoints[vertex.index] = point;
                # print(point.location)

            if (connectLines != True):
                continue;

            compareSet = set(addedPoints.keys())
            # print(compareSet);
            edges = clicked_mesh.data.edges;
            for edge in edges:
                if (set(edge.vertices).issubset(compareSet) != True): continue;

                p1, p2 = [addedPoints[x] for x in edge.vertices];
                # print(p1.location);
                # print(p2.location);
                sse.add_line_2d(p1, p2, sketch, fixed = True, index_reference = True);

                # print(f"Edge {edge.index} vertices: {[str(edge.vertices[x]) for x in range(2)]}");
                # break;


                
        return True


register, unregister = register_stateops_factory((View3D_OT_slvs_add_sketch,View3D_OT_slvs_add_sketch_face))
