import logging

import bpy
from bpy.types import Operator, Context, Event
from bpy.props import FloatProperty, BoolProperty, EnumProperty
from mathutils import Vector, Quaternion

from ..model.types import SlvsWorkplane
from ..declarations import Operators
from ..stateful_operator.utilities.register import register_stateops_factory
from ..stateful_operator.state import state_from_args
from .base_3d import Operator3d
from .utilities import activate_sketch, switch_sketch_mode
from ..stateful_operator.utilities.geometry import get_evaluated_obj, get_mesh_element
from ..utilities.geometry import get_face_orientation
from ..model.group_entities import SlvsEntities, SlvsSketch


logger = logging.getLogger(__name__)

class ProjectionData:
    def __init__(self,
                sketcherEntities: SlvsEntities, 
                sketch: SlvsSketch,
                objectTranslation: bpy.types.TransformOrientation,
                workplaneOrigin: tuple[float, float, float],
                workplaneNormal: Vector,
                quat: Quaternion):
        
        self.sketcherEntities = sketcherEntities
        self.sketch = sketch
        self.objectTranslation = objectTranslation
        self.workplaneOrigin = workplaneOrigin
        self.workplaneNormal = workplaneNormal
        self.quat = quat # I forgot what quat was... Should've added more comments

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


# TODO: Auto align view with sketch after creation
# TODO: Make it auto enter sketch
# TODO: Make the properties work!
class View3D_OT_slvs_add_sketch_face(Operator, Operator3d):
    """Add a workplane and start sketch on mesh face"""
 
    bl_idname = Operators.AddSketchFace
    bl_label = "Add sketch on mesh face"
    bl_options = {"REGISTER", "UNDO"}

    # Can't get default to work. idk why
    projectDist: FloatProperty(
        name="Project distance",
        subtype="DISTANCE",
        unit="LENGTH",
        default=0.001,
        step=0.01,
        # precision=get_prefs().decimal_precision,
    )

    # # Idk why it doesn't work correctly
    # connectLines: BoolProperty(name="Connect lines", description="May cause performance issues, idk", default=True)
    connectLines = True
    
    projectFrom: EnumProperty(
        name="My Search",
        items=(
            ('FACE', "Face", ""),
            ('MESH', "Mesh", ""),
            ('ALL', "All meshes", ""),
        ),
        default='ALL' # Maybe should be 'MESH' instead for performance issues. Idk
    )

    states = (
        state_from_args(
            "Face",
            description="Pick a mesh face to use as workplane's and sketch's surface.",
            use_create=False,
            pointer="face",
            types=(bpy.types.MeshPolygon,),
            interactive=True,
        ),
        state_from_args(
            "Additional projection distance",
            description="Additional projection distance (default + extra)",
            property="projectDist",
            interactive=True,
            no_event=True,
        ),
    )

    def main(self, context: Context):
        sse: SlvsEntities = context.scene.sketcher.entities

        # Gets info about clicked object
        obj_name, clicked_face_index = self.get_state_pointer(index=0, implicit=True)
        clicked_obj = get_evaluated_obj(context, bpy.data.objects[obj_name])
        clicked_mesh = clicked_obj.data
        clicked_face: bpy.types.MeshPolygon = clicked_mesh.polygons[clicked_face_index]
        
        # Gets face rotation
        obj_translation: bpy.types.TransformOrientation = clicked_obj.matrix_world
        quat = get_face_orientation(clicked_mesh, clicked_face) # Quternion
        quat.rotate(obj_translation)
        
        # Creates the workplane
        workplane_origin: tuple[float, float, float] = obj_translation @ clicked_face.center
        origin = sse.add_point_3d(workplane_origin)
        nm = sse.add_normal_3d(quat)
        workplane = sse.add_workplane(origin, nm)

        # Workplane normal in world coordinates
        workplane_normal = quat @ Vector((0.0, 0.0, 1.0))
        
        # Creates the sketch
        sketch = sse.add_sketch(workplane)
        sse.add_point_2d((0.0, 0.0), sketch, fixed = True) # Add face centrum point

        # activate_sketch(context, sketch.slvs_index, self) # This hides the pop-up with the options for the projection. Idk why, so it is just like this
        # self.target = sketch

        limitDist = 0.001 + self.projectDist; # Should just be the project dist, but couldn't get default in property to work

        # Prepares the data needed for the projection
        projectionData = ProjectionData(sse, sketch, obj_translation, workplane_origin, workplane_normal, quat)

        if self.projectFrom == 'FACE':
            logger.error("Project face is not implemented yet")
        elif self.projectFrom == 'MESH':
                self.ProjectFromMeshes(projectionData, [clicked_obj,], limitDist, self.connectLines)
        elif self.projectFrom == 'ALL': # ALL doesn't actually work. I don't think its important to fix atm
                allMeshesInScene = [o for o in context.scene.objects if o.type == 'MESH']
                self.ProjectFromMeshes(projectionData, allMeshesInScene, limitDist, self.connectLines)

        context.area.tag_redraw() # Force re-draw of UI (Blender doesn't update after tool usage)
        return True
    
    def ProjectFromMeshes(self, projectionData: ProjectionData,
                           meshes: list[bpy.types.Mesh],
                           maxDist: float,
                           connectLines: bool = True):
        sse = projectionData.sketcherEntities
        
        addedPoints = {}
        for clicked_mesh in meshes:
            vertices = clicked_mesh.data.vertices;
            for vertex in vertices:
                # Make vertex relative to plane
                vertex_world = projectionData.objectTranslation @ vertex.co;
                translated = vertex_world - projectionData.workplaneOrigin;
                
                # Projection to plane
                distance_to_plane = translated.dot(projectionData.workplaneNormal);
                projection = translated - distance_to_plane * projectionData.workplaneNormal;

                # If vertex is too far from sketch, then don't create sketch point
                if abs(distance_to_plane) > maxDist:
                    continue;

                ## Used ChatGPT, quaternion rotations is too hard.
                # To 2D projection relative to the workplane
                # Use the workplane orientation (quat) to project into 2D
                local_projection = projection.copy();
                local_projection.rotate(projectionData.quat.conjugated());
                x, y, _ = local_projection;

                point = sse.add_point_2d((x, y), projectionData.sketch, fixed = True, index_reference = True);
                addedPoints[vertex.index] = point;

            if (connectLines != True):
                continue;

            # Takes the edges of the object and checks if the earlier added sketch points are used in the edges. If yes, then create line from first point to second point
            compareSet = set(addedPoints.keys())
            edges = clicked_mesh.data.edges;
            for edge in edges:
                if (set(edge.vertices).issubset(compareSet) != True): continue;

                p1, p2 = [addedPoints[x] for x in edge.vertices];
                sse.add_line_2d(p1, p2, projectionData.sketch, fixed = True, index_reference = True);
        pass
        

register, unregister = register_stateops_factory((View3D_OT_slvs_add_sketch,View3D_OT_slvs_add_sketch_face))
