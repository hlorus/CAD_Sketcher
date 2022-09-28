import pickle
from typing import Union, Optional
from pathlib import Path

from bpy.types import Scene


def scene_to_dict(scene):
    return scene["sketcher"].to_dict()


def scene_from_dict(scene, dictionary):
    scene["sketcher"].update(dictionary)


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
        scene_from_dict(scene, unpickler.load())
