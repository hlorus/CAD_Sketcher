from typing import Protocol, Union

import bpy
from bpy.types import MeshPolygon


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
