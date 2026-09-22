import bpy
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators


class VIEW3D_OT_slvs_migrate_legacy(Operator):
    """Bring a file saved by an older CAD Sketcher version up to date.

    Everything a file may need, in one pass and in order: sketches from an
    entity-based (pre native-curve) version are converted to curves, a bundled
    revolve node group is rebuilt, and sketches that predate parts are adopted
    into them. Each step checks whether it applies, so running it is always safe.

    Manual rather than automatic: migration used to run on every file load, and
    it costs nothing for users who don't need it this way. Adopting sketches into
    parts also restructures the object hierarchy, which opening a file should not
    do unasked."""

    bl_idname = Operators.MigrateLegacy
    bl_label = "Migrate File"
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
            self.report(
                {"INFO"},
                "Migrated legacy sketches: "
                f"{summary['sketches']} sketches, {summary['points']} points, "
                f"{summary['segments']} segments, "
                f"{summary['constraints']} constraints",
            )

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
        from ..utilities.collections import sync_part_collections
        from ..utilities.part import migrate_parts

        adopted = migrate_parts(context.scene)
        if adopted:
            sync_part_collections(context.scene)
            self.report({"INFO"}, "Sketches adopted into parts")

        if not migrated and not adopted:
            self.report({"INFO"}, "Nothing to migrate")
        return {"FINISHED"}


register, unregister = register_classes_factory((VIEW3D_OT_slvs_migrate_legacy,))
