import pickle
from typing import Union, Optional
from pathlib import Path
from typing import Dict

from bpy.types import Scene

from .utilities.index import breakdown_index, assemble_index


def dict_extend(original_dict, other):
    """Similar to native update() but extends values "+=" when key is in both dictionaries"""

    for key, value in other.items():
        if key in original_dict:
            original_dict[key] += value
            continue
        original_dict[key] = value


# Format of scene dict:
# {
#   'entities': {
#       'points3D': [{}, {}],
#       'normals3D': [{}, {}],
# }


def apply_dict(parent, d: Dict):
    """Applies values from a dictionary to members of a IDPropertyGroup"""
    for key, value in d.items():
        if not isinstance(value, dict):
            parent[key] = value
            continue

        # Handle dictionaries recursivley
        apply_dict(parent[key], value)


def scene_to_dict(scene: Scene) -> Dict:
    """Returns a dictionary which represents the relevant contents of the given scene"""
    original = scene["sketcher"].to_dict()
    elements = {key: original[key] for key in ("entities", "constraints")}
    return elements


def scene_from_dict(scene: Scene, elements: Dict):
    """Constructs a scene from a dictionary"""
    original = scene["sketcher"].to_dict()
    original.update(elements)
    apply_dict(scene["sketcher"], original)


def _extend_element_dict(scene, elements):
    """Returns dictionary representation of scene with extended entities and constraints"""
    scene_dict = scene_to_dict(scene)

    fix_pointers(elements)

    for key in ("entities", "constraints"):
        dict_extend(scene_dict[key], elements[key])

    return scene_dict


def fix_pointers(elements: Dict):
    """Go through all properties and offset entity pointers"""

    import bpy

    offsets = bpy.context.scene.sketcher.entities.collection_offsets()
    indices = _get_indices(elements)

    # Create pointer map {old_ptr: new_ptr,}
    index_mapping = {}
    for type_index, local_indices in indices.items():
        offset = offsets[type_index]

        for i in range(len(local_indices)):
            old_index = local_indices[i]
            if old_index in index_mapping.keys():
                continue

            index_mapping[assemble_index(type_index, old_index)] = assemble_index(
                type_index, offset + i
            )

    _replace_indices(elements, index_mapping)


def iter_elements_dict(element_dict):
    """Iterate through every property in elements dictionary"""
    for element_key in ("entities", "constraints"):
        for element_coll, elems in element_dict[element_key].items():
            if not isinstance(elems, list):
                continue
            for elem in elems:
                yield elem


def _replace_indices(elements, mapping: dict):
    """Go through all indices and replace indices based on index mapping"""

    for elem in iter_elements_dict(elements):
        for prop in elem.keys():
            if not prop.endswith("_i") and prop != "slvs_index":
                continue

            value = elem[prop]
            if value not in mapping.keys():
                continue

            elem[prop] = mapping[value]


def _get_indices(elements):
    """Collect and sort slvs_index's of all entities"""
    indices = {}

    for elem in iter_elements_dict(elements):
        if "slvs_index" not in elem.keys():
            continue

        slvs_index = elem["slvs_index"]

        type_index, local_index = breakdown_index(slvs_index)

        if local_index not in indices.setdefault(type_index, []):
            indices[type_index].append(local_index)

    [l.sort() for l in indices.values()]
    return indices


def save(file: Union[str, Path], scene: Optional[Scene] = None):
    """Saves CAD Sketcher data of scene into file"""
    if not scene:
        import bpy

        scene = bpy.context.scene

    with open(file, "wb") as picklefile:
        pickler = pickle.Pickler(picklefile)

        # Convert to dict to avoid pickling PropertyGroup instances
        dict = scene_to_dict(scene)
        pickler.dump(dict)
        picklefile.close()


def load(file: Union[str, Path], scene: Optional[Scene] = None):
    """Overwrites scene with entities and constraints stored in file"""
    if not scene:
        import bpy

        scene = bpy.context.scene

    with open(file, "rb") as picklefile:
        unpickler = pickle.Unpickler(picklefile)
        load_dict = unpickler.load()

        scene_from_dict(scene, load_dict)


def paste(context, dictionary):
    scene = context.scene

    final_dict = _extend_element_dict(
        scene,
        {
            "entities": dictionary["entities"],
            "constraints": dictionary["constraints"],
        },
    )
    scene_from_dict(scene, final_dict)
