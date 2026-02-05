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


def group_as_dict(group) -> Dict:
    """Get values from a property group as a dict using RNA type system."""
    EXCLUDE = {'name', 'rna_type'}
    prop_dict = {}

    for prop in group.rna_type.properties:
        key = prop.identifier
        if key in EXCLUDE:
            continue

        value = getattr(group, key)
        prop_type = prop.type
        
        # Handle collection properties (store as list of dicts)
        if prop_type == 'COLLECTION':
            items_list = []
            for item in value:
                item_dict = {}
                for item_prop in item.rna_type.properties:
                    k = item_prop.identifier
                    if k in EXCLUDE:
                        continue
                    v = getattr(item, k)
                    # Store arrays properly (check if property supports is_array)
                    if hasattr(item_prop, 'is_array') and item_prop.is_array:
                        item_dict[k] = list(v) if v else []
                    else:
                        item_dict[k] = v
                items_list.append(item_dict)
            prop_dict[key] = items_list
        # Handle pointer to other property groups (recursive)
        elif prop_type == 'POINTER':
            if value is not None:
                prop_dict[key] = group_as_dict(value)
        # Handle arrays/vectors
        elif prop_type in ('INT', 'FLOAT') and hasattr(prop, 'is_array') and prop.is_array:
            prop_dict[key] = list(value) if value else []
        # Everything else store directly
        else:
            prop_dict[key] = value

    return prop_dict


def dict_to_group(group, data: Dict):
    """Restore a property group from a dictionary using RNA type system."""
    EXCLUDE = {'name', 'rna_type'}

    for prop in group.rna_type.properties:
        key = prop.identifier
        if key in EXCLUDE or key not in data:
            continue

        value = data[key]
        prop_type = prop.type

        # Handle collection properties
        if prop_type == 'COLLECTION':
            collection = getattr(group, key)
            collection.clear()
            if isinstance(value, list):
                for item_data in value:
                    new_item = collection.add()
                    if isinstance(item_data, dict):
                        for k, v in item_data.items():
                            if hasattr(new_item, k):
                                # Check if this is an array property
                                item_prop = new_item.rna_type.properties.get(k)
                                if item_prop and hasattr(item_prop, 'is_array') and item_prop.is_array:
                                    # Convert to tuple/list of correct size
                                    if isinstance(v, (list, tuple)):
                                        setattr(new_item, k, v[:item_prop.array_length])
                                    else:
                                        setattr(new_item, k, v)
                                else:
                                    setattr(new_item, k, v)

        # Handle pointer to other property groups (recursive)
        elif prop_type == 'POINTER':
            if isinstance(value, dict):
                ptr_group = getattr(group, key)
                if ptr_group is not None:
                    dict_to_group(ptr_group, value)

        # Handle arrays/vectors
        elif prop_type in ('INT', 'FLOAT') and hasattr(prop, 'is_array') and prop.is_array:
            # Ensure correct array length
            if isinstance(value, (list, tuple)):
                setattr(group, key, value[:prop.array_length])
            else:
                setattr(group, key, value)

        # Restore simple properties
        else:
            setattr(group, key, value)


def scene_to_dict(scene: Scene) -> Dict:
    """Returns a dictionary which represents the relevant contents of the given scene"""
    sketcher = scene.sketcher
    
    return {
        'entities': group_as_dict(sketcher.entities),
        'constraints': group_as_dict(sketcher.constraints),
    }


def scene_from_dict(scene: Scene, elements: Dict):
    """Constructs a scene from a dictionary"""
    sketcher = scene.sketcher
    
    # Restore entities
    if 'entities' in elements:
        dict_to_group(sketcher.entities, elements['entities'])
    
    # Restore constraints
    if 'constraints' in elements:
        dict_to_group(sketcher.constraints, elements['constraints'])


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
