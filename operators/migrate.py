import logging

import bpy
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators

logger = logging.getLogger(__name__)


class VIEW3D_OT_slvs_migrate_legacy(Operator):
    """Update a file that was saved by an older version of CAD Sketcher.

    Applies whatever this particular file needs, and nothing it doesn't, so it is
    safe to run at any time. Manual rather than automatic because updating can
    restructure the file, which opening it should never do unasked.

    Each version's steps live behind their own check (see the utilities they call
    into); keeping them in one operator means users have one button to press
    rather than one per release."""

    bl_idname = Operators.MigrateLegacy
    bl_label = "Update File"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        from ..utilities.migrate import migrate_scene, scene_needs_migration
        from ..versioning import do_versioning

        migrated = scene_needs_migration(context)
        if migrated:
            # Patch old entity data forward to the current schema first, then
            # convert it to curves (do_versioning used to run on file load).
            do_versioning()
            summary = migrate_scene(context)
            logger.info("Converted legacy sketches: %s", summary)

        # Rebuild a baked revolve node group so existing revolves pick up fixes.
        # build_revolve_node_group preserves each modifier's settings across the
        # rebuild (see utilities.revolve_nodes).
        try:
            from ..utilities.revolve_nodes import (
                REVOLVE_NODE_GROUP,
                build_revolve_node_group,
            )

            if bpy.data.node_groups.get(REVOLVE_NODE_GROUP) is not None:
                build_revolve_node_group()
        except Exception:
            self.report({"WARNING"}, "Revolve node group upgrade failed")

        # Sketches that predate parts: adopt them so they can be moved as parts.
        # After the conversion above, so sketches it just created are included.
        # Bodies first: a part is anchored in the mesh its sketches are realised
        # on, so they have to exist before membership is settled.
        from ..utilities.body import migrate_bodies
        from ..utilities.collections import (
            dissolve_legacy_sketch_collections,
            sync_part_collections,
        )
        from ..utilities.part import migrate_parts

        bodies = migrate_bodies(context, context.scene)

        adopted = migrate_parts(context.scene)
        # The per-sketch collections older files were saved with are dissolved
        # here rather than on load, so opening a file leaves its outliner alone.
        dissolved = dissolve_legacy_sketch_collections(context.scene)
        if bodies or adopted or dissolved:
            sync_part_collections(context.scene)

        # One result, in the user's terms: which steps ran is an implementation
        # detail, and the log carries the detail if anyone needs it.
        if migrated or bodies or adopted or dissolved:
            self.report({"INFO"}, "File updated")
        else:
            self.report({"INFO"}, "File is already up to date")
        return {"FINISHED"}


register, unregister = register_classes_factory((VIEW3D_OT_slvs_migrate_legacy,))
