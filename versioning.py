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

    logger.debug(msg)
