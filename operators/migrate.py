import bpy
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from ..declarations import Operators


class VIEW3D_OT_slvs_migrate_legacy(Operator):
    """Convert sketches saved by older CAD Sketcher versions to the native-curve
    model and upgrade a bundled revolve node group to the current build.

    Run this on files made with an entity-based (pre native-curve) version --
    their sketches don't appear until migrated. Migration used to run
    automatically on every file load; it is manual so it never costs anything
    for users who don't need it."""

    bl_idname = Operators.MigrateLegacy
    bl_label = "Migrate Legacy Sketches"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        from ..utilities.migrate import migrate_scene, scene_needs_migration

        migrated = scene_needs_migration(context)
        if migrated:
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

        if not migrated:
            self.report({"INFO"}, "No legacy sketches to migrate")
        return {"FINISHED"}


register, unregister = register_classes_factory((VIEW3D_OT_slvs_migrate_legacy,))
