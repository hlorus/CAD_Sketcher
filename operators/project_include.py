import logging
import math
from typing import Protocol, Union

import bgl
import blf
import bpy
import bpy_extras
import gpu
from bpy.props import BoolProperty
from bpy.types import Context, MeshPolygon, Operator, TransformOrientation
from gpu_extras.batch import batch_for_shader
from mathutils import Quaternion, Vector

from ..declarations import Operators
from ..model.group_entities import SlvsEntities, SlvsNormal3D, SlvsPoint3D, SlvsSketch
from ..model.workplane import SlvsWorkplane
from ..stateful_operator.state import state_from_args
from ..stateful_operator.utilities.geometry import get_evaluated_obj
from ..stateful_operator.utilities.register import register_stateops_factory
from ..utilities.geometry import get_face_orientation
from .base_2d import Operator2d

logger = logging.getLogger(__name__)


def get_object_under_mouse(context, event):
    region = context.region
    rv3d = context.space_data.region_3d
    coord = (event.mouse_region_x, event.mouse_region_y)

    view_vector = bpy_extras.view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    ray_origin = bpy_extras.view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

    result, location, normal, index, obj, matrix = context.scene.ray_cast(
        context.view_layer.depsgraph, ray_origin, view_vector
    )
    return obj if result else None


def project_vertex_to_workplane(vertex_world, origin, wp_quat):
    """
    Project a world-space vertex to a workplane defined by origin and quaternion.

    Returns the (x, y) coordinates in the workplane’s local space.
    """
    relative = vertex_world - origin
    # Rotate into workplane local space (inverse rotation)
    local = wp_quat.conjugated() @ relative
    return Vector((local.x, local.y))


class ProjectionData:
    def __init__(
        self,
        sketcher_entities: SlvsEntities,
        sketch: SlvsSketch,
        object_translation: TransformOrientation,
    ):

        self.sketcher_entities = sketcher_entities
        self.sketch = sketch
        self.object_translation = object_translation

    @property
    def wp(self) -> SlvsWorkplane:
        wp: SlvsWorkplane = self.sketch.wp
        return wp

    @property
    def workplane_origin(self) -> SlvsPoint3D:
        slvs_point3d: SlvsPoint3D = self.wp.p1
        return slvs_point3d.location

    @property
    def workplane_quaternion(self) -> Quaternion:
        return self.wp.nm.orientation


class ObjectInterfaceProtocol(Protocol):
    def get_verticies(self) -> list[bpy.types.MeshVertex]:
        pass

    def get_edges(self) -> list[bpy.types.MeshEdges]:
        pass


class ObjectInterface:

    obj: bpy.types.Object

    def __init__(self, obj: bpy.types.Object):
        self.obj = obj

    def get_verticies(self) -> list[bpy.types.MeshVertex]:
        return self.obj.data.vertices

    def get_edges(self) -> list[bpy.types.MeshEdges]:
        return self.obj.data.edges


class FaceInterface:

    obj: bpy.types.Object
    face_index: int

    def __init__(self, obj: bpy.types.Object, face_index: int):
        self.obj = obj
        self.face_index = face_index

    def get_verticies(self) -> list[bpy.types.MeshVertex]:
        return [
            self.obj.data.vertices[vertex_index] for vertex_index in self._face.vertices
        ]

    def get_edges(self) -> list[bpy.types.MeshEdges]:
        edges_with_nones = [
            self._get_edge(edge_key=edge_key) for edge_key in self._face.edge_keys
        ]

        return [x for x in edges_with_nones if x is not None]

    @property
    def _face(self) -> MeshPolygon:
        return self.obj.data.polygons[self.face_index]

    def _get_edge(self, edge_key: tuple[int, int]) -> Union[None, bpy.types.MeshEdge]:
        for edge in self.obj.data.edges:
            if edge.key == edge_key:
                return edge

        return None


class View3D_OT_slvs_project_include(Operator, Operator2d):
    """Add a circle to the active sketch"""

    bl_idname = Operators.ProjectInclude
    bl_label = "Project a mesh onto the current sketch"
    bl_options = {"REGISTER", "UNDO"}
    _last_obj = None

    # continuous_draw: BoolProperty(name="Continuous Draw", default=True)

    states = (
        state_from_args(
            "Face",
            description="Pick a mesh face to project onto the sketch's surface.",
            use_create=False,
            pointer="face",
            types=(MeshPolygon,),
            interactive=True,
        ),
    )

    def main(self, context: Context):

        sse: SlvsEntities = context.scene.sketcher.entities

        # Gets info about clicked object
        obj_name, clicked_face_index = self.get_state_pointer(index=0, implicit=True)
        clicked_obj = get_evaluated_obj(context, bpy.data.objects[obj_name])

        # clicked_mesh = clicked_obj.data
        # clicked_face: MeshPolygon = clicked_mesh.polygons[clicked_face_index]

        # Gets face rotation
        obj_translation: TransformOrientation = clicked_obj.matrix_world
        projection_data = ProjectionData(
            # FOCUS HERE
            sketcher_entities=sse,
            sketch=self.sketch,
            object_translation=obj_translation,
        )
        # add code here

        # print(ctrl_held)

        if self.event.shift:
            self.ProjectFromMeshes(
                projection_data,
                [
                    ObjectInterface(clicked_obj),
                ],
                # self.connectLines,
            )
        else:
            self.ProjectFromMeshes(
                projection_data,
                [
                    FaceInterface(clicked_obj, clicked_face_index),
                ],
                # self.connectLines,
            )

        context.area.tag_redraw()  # Force re-draw of UI (Blender doesn't update after tool usage)
        return True

    def ProjectFromMeshes(
        self,
        projection_data: ProjectionData,
        object_interfaces: list[ObjectInterfaceProtocol],
        connect_lines: bool = True,
    ):
        sse = projection_data.sketcher_entities

        addedPoints = {}

        for object_interface in object_interfaces:
            for vertex in object_interface.get_verticies():
                x, y = project_vertex_to_workplane(
                    # FOCUS HERE
                    vertex_world=projection_data.object_translation @ vertex.co,
                    origin=projection_data.workplane_origin,
                    wp_quat=projection_data.workplane_quaternion,
                )

                point = sse.add_point_2d(
                    (x, y), projection_data.sketch, fixed=True, index_reference=True
                )
                addedPoints[vertex.index] = point

            if not connect_lines:
                continue

            # Takes the edges of the object and checks if
            # the earlier added sketch points are used in the edges.
            # If yes, then create line from first point to second point
            compareSet = set(addedPoints.keys())

            for edge in object_interface.get_edges():
                if not set(edge.vertices).issubset(compareSet):
                    continue

                p1, p2 = [addedPoints[x] for x in edge.vertices]
                sse.add_line_2d(
                    p1, p2, projection_data.sketch, fixed=True, index_reference=True
                )
        pass

    # def modal(self, context, event):
    #     if event.type in {"ESC", "RIGHTMOUSE"}:
    #         if self._last_obj:
    #             self._last_obj.select_set(False)
    #         return {"CANCELLED"}

    #     if event.type == "MOUSEMOVE":
    #         obj = get_object_under_mouse(context, event)
    #         if obj is not None and obj.type == "MESH":
    #             pass
    #             if obj != self._last_obj:
    #                 # Unhighlight previous
    #                 if self._last_obj:
    #                     pass

    #                 # Highlight current
    #                 # obj.select_set(True)
    #                 _debug_circle(obj, context)
    #                 self._last_obj = obj
    #         else:
    #             if self._last_obj:
    #                 # self._last_obj.select_set(False)
    #                 self._last_obj = None

    # return {"PASS_THROUGH"}

    # return Operator2d.modal(self, context, event)

    # def invoke(self, context, event):
    #     context.window_manager.modal_handler_add(self)
    #     return super().invoke(context, event)


register, unregister = register_stateops_factory((View3D_OT_slvs_project_include,))

if __name__ == "__main__":
    register()
