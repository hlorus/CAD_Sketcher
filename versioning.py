import bpy
import logging
from . import get_addon_version_tuple

logger = logging.getLogger(__name__)


def write_addon_version(context):
    version = get_addon_version_tuple()

    logger.debug("Writing addon version: " + str(version))

    # NOTE: Version is written to every scene because there's no global
    # place we can put this value
    for scene in bpy.data.scenes:
        scene.sketcher.version = version


def recalc_pointers(scene):
    """Updates type index of entities keeping local index as is"""

    # TODO: Move to utilities.data_handling
    from .model.utilities import update_pointers

    msg = ""
    entities = list(scene.sketcher.entities.all)
    for e in reversed(entities):
        i = e.slvs_index
        # scene.sketcher.entities._set_index(e)
        scene.sketcher.entities.recalc_type_index(e)

        if i != e.slvs_index:
            msg += "\n - {}: {} -> {}".format(e, i, e.slvs_index)
            update_pointers(scene, i, e.slvs_index)

    if msg:
        logger.debug("Update entity indices:" + msg)


def copy_modifiers(source_obj, target_obj):
    """Copy modifiers from source object to target object"""
    if not source_obj or not target_obj:
        return

    # Clear existing modifiers on target
    while target_obj.modifiers:
        target_obj.modifiers.remove(target_obj.modifiers[0])

    # Copy modifiers from source to target
    for mod in source_obj.modifiers:
        new_mod = target_obj.modifiers.new(name=mod.name, type=mod.type)
        # Copy attributes that are common to all modifier types
        for attr in dir(mod):
            if attr.startswith('__') or attr in {'rna_type', 'type', 'name', 'bl_rna'}:
                continue
            try:
                if hasattr(new_mod, attr):
                    setattr(new_mod, attr, getattr(mod, attr))
            except (AttributeError, TypeError):
                # Skip attributes that can't be copied
                pass


def do_versioning(self):

    logger.debug("Check versioning")

    # Current blender version
    current_version = bpy.context.preferences.version
    # blender version this file was saved with
    file_version = bpy.data.version
    # Current addon version
    current_addon_version = get_addon_version_tuple()
    # "Blender Version: ", current_version,
    # "\nFile Blender Version: ", file_version,
    # "\nAddon Version: ", current_addon_version,
    # "\nFile Addon Version", file_addon_version,

    # NOTE: Versioning is done per scene

    msg = "\nUpdate existing file to version {}".format(current_addon_version)
    context = bpy.context

    for scene in bpy.data.scenes:
        props = scene.sketcher

        if not props.is_property_set("version"):
            continue

        # Scene addon version
        version = props.version[:]

        if version > current_addon_version:
            logger.warning(
                "Scene {} was saved with a newer version of the addon".format(
                    scene.name
                )
            )
            continue

        msg += "\n  - Update scene <{}> from version {}".format(scene.name, version)

        # if version <= (0, 11, 0):
        # apply some changes that were introduced in v(0, 11, 0)

        # if version <= (1, 0, 0):
        # ...
        if version < (0, 23, 0):
            entities = scene.sketcher.entities
            entities.origin_axis_X = None
            entities.origin_plane_YZ = None
            entities.ensure_origin_elements(context)

        if version < (0, 26, 0):
            for c in context.scene.sketcher.constraints.angle:
                if not c.setting:
                    continue
                if c.is_reference:
                    continue

                msg += (
                    "\n Make supplementary angle constraint reference only: {}".format(
                        repr(c)
                    )
                )
                c.is_reference = True

        if version < (0, 27, 4):
            # update distance constraints on only a line
            # to distance constraints on the endpoints of that line.
            from .model.line_2d import SlvsLine2D
            from .model.distance import SlvsDistance
            from .model.point_2d import SlvsPoint2D
            from .model.sketch import SlvsSketch

            for c in context.scene.sketcher.constraints.dimensional:
                if len(c.dependencies()) != 2:
                    continue
                if not (isinstance(c, SlvsDistance) and
                        isinstance(c.dependencies()[0], SlvsLine2D) and
                        isinstance(c.dependencies()[1], SlvsSketch)):
                    continue

                line_dependencies = c.dependencies()[0].dependencies()
                if len(line_dependencies) != 3:
                    continue
                if (isinstance(line_dependencies[0], SlvsPoint2D) and
                        isinstance(line_dependencies[1], SlvsPoint2D)):
                    setattr(c, "entity1", line_dependencies[0])
                    setattr(c, "entity2", line_dependencies[1])

        if version < (0, 28, 0):
            # Handle old 'MESH' and 'BEZIER' convertion types
            msg += "\n Update sketch conversion type to 'CURVE' for sketches:"

            # Dictionary to temporarily store objects and their modifiers
            old_objects = {}

            # First pass: store old objects and change conversion type
            for sketch in context.scene.sketcher.entities.sketches:
                if sketch.convert_type == 'NONE':
                    continue

                # Store references to the old objects
                sketch_id = str(sketch.slvs_index)
                old_objects[sketch_id] = {
                    'mesh_obj': sketch.target_object,
                    'curve_obj': sketch.target_curve_object,
                    'sketch': sketch
                }

                # Clear links to objects but don't delete them yet
                if sketch.target_object:
                    sketch.target_object.sketch_index = -1
                    sketch.target_object = None

                if sketch.target_curve_object:
                    sketch.target_curve_object.sketch_index = -1
                    sketch.target_curve_object = None

                # Change the conversion type
                sketch.convert_type = 'CURVE'

                msg += " {}".format(str(sketch))

            # Second pass: process each sketch individually
            for sketch_id, objects in old_objects.items():
                sketch = objects['sketch']

                # Force creation of converted object for this sketch
                bpy.ops.view3d.slvs_update(solve=False)

                # Ensure the new object is created
                if sketch.target_curve_object:
                    # Try to copy from mesh object first, then curve object
                    if objects['mesh_obj']:
                        copy_modifiers(objects['mesh_obj'], sketch.target_curve_object)
                    elif objects['curve_obj']:
                        copy_modifiers(objects['curve_obj'], sketch.target_curve_object)

                    logger.info(f"Copied modifiers to new object for sketch {sketch_id}")
                else:
                    logger.warning(f"Failed to create new object for sketch {sketch_id}")

            # Unlink and rename old objects instead of deleting them
            for sketch_id, objects in old_objects.items():
                # Process mesh object
                if objects['mesh_obj']:
                    old_obj = objects['mesh_obj']
                    # Unlink from all collections
                    for collection in old_obj.users_collection:
                        collection.objects.unlink(old_obj)
                    # Rename to indicate it's an old version
                    old_obj.name = f"OLD_{old_obj.name}_{sketch_id}"

                # Process curve object
                if objects['curve_obj']:
                    old_obj = objects['curve_obj']
                    # Unlink from all collections
                    for collection in old_obj.users_collection:
                        collection.objects.unlink(old_obj)
                    # Rename to indicate it's an old version
                    old_obj.name = f"OLD_{old_obj.name}_{sketch_id}"

    logger.warning(msg)
