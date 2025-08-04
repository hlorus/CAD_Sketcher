import bpy
from bpy.types import Context, Event

from ..base_2d import Operator2d
from .get_object_under_mouse import get_object_under_mouse

highlight_name = "HighlightFace"


def clear_highlight(context: Context):
    prev_highlight = context.scene.objects.get(highlight_name)
    if prev_highlight:
        bpy.data.objects.remove(prev_highlight, do_unlink=True)


def handle_highlight(self: Operator2d, context: Context, event: Event):
    clear_highlight(context=context)

    obj, face_index = get_object_under_mouse(context, event, return_index=True)

    if not obj:
        return  # Nothing to highlight

    mesh = obj.data
    if face_index is not None:
        faces = [mesh.polygons[face_index]]
    else:
        faces = list(mesh.polygons)

    # Build vertices and face indices for all faces
    verts = []
    faces_indices = []
    vert_idx = 0
    for face in faces:
        face_verts = [obj.matrix_world @ mesh.vertices[i].co for i in face.vertices]
        verts.extend(face_verts)
        faces_indices.append(list(range(vert_idx, vert_idx + len(face_verts))))
        vert_idx += len(face_verts)

    if not verts or not faces_indices:
        return

    mesh_data = bpy.data.meshes.new(highlight_name)
    mesh_data.from_pydata(verts, [], faces_indices)
    mesh_data.update()

    highlight_obj = bpy.data.objects.new(highlight_name, mesh_data)
    context.collection.objects.link(highlight_obj)

    # Set highlight material (reuse or create)
    mat_name = "HighlightMaterial"
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.25, 1, 0, 1)  # Yellow
            bsdf.inputs["Alpha"].default_value = 1
        mat.blend_method = "BLEND"
    mesh_data.materials.append(mat)

    highlight_obj.hide_select = True
    highlight_obj.hide_render = True
