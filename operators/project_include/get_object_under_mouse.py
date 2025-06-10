import bpy
import bpy_extras
from bpy.types import Context, Event


def get_object_under_mouse(
    context: Context, event: Event, return_index: bool = False
) -> tuple[bpy.types.MeshPolygon | bpy.types.Mesh | None, int | None]:
    region = context.region
    rv3d = context.space_data.region_3d
    coord = (event.mouse_region_x, event.mouse_region_y)

    view_vector = bpy_extras.view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
    ray_origin = bpy_extras.view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

    depsgraph = context.view_layer.depsgraph
    hit, location, normal, face_index, obj, matrix = context.scene.ray_cast(
        depsgraph, ray_origin, view_vector
    )
    if hit:
        if getattr(event, "shift", False):
            return _handle_shift(
                context=context,
                obj=obj,
                face_index=face_index,
                return_index=return_index,
            )
        else:
            if hit:
                return obj, None

    return None, None


def _handle_shift(
    context: Context, obj: bpy.types.Object, face_index: int, return_index: bool = False
) -> tuple[bpy.types.MeshPolygon | bpy.types.Mesh, int | None]:
    depsgraph = context.view_layer.depsgraph
    # Get the evaluated mesh for up-to-date data with modifiers
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()

    if return_index:
        return obj, face_index

    if face_index != -1 and 0 <= face_index < len(mesh.polygons):
        face = mesh.polygons[face_index]
        return face, None
