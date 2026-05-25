from bpy.types import Context, UIList

from .. import declarations
from . import VIEW3D_PT_sketcher_base


class VIEW3D_UL_sketch_groups(UIList):
    """Upper list: one row per SketchGroup on the active sketch."""

    bl_idname = "VIEW3D_UL_sketch_groups"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index=0,
        flt_flag=0,
    ):
        group = item
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.prop(group, "name", text="", emboss=False)

            tag_sub = row.row(align=True)
            tag_sub.scale_x = 0.75
            tag_sub.prop(group, "tag", text="")
            if context.scene.sketcher.ifc_integration:
                op = tag_sub.operator(
                    "view3d.slvs_tag_group_from_preset",
                    text="",
                    icon="VIEWZOOM",
                )
                op.group_index = index

            row.prop(group, "guid", text="")
            row.label(text=str(len(group.members)))
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=group.name)


class VIEW3D_UL_group_members(UIList):
    """Lower list: one row per SketchGroupMember of the selected group."""

    bl_idname = "VIEW3D_UL_group_members"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index=0,
        flt_flag=0,
    ):
        member = item
        sse = context.scene.sketcher.entities
        entity = sse.get(member.entity_index)

        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            if entity is not None:
                row.label(text=entity.name, icon="SNAP_VERTEX")
            else:
                row.label(text="(missing)", icon="ERROR")
            row.prop(member, "guid", text="")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(
                text=entity.name if entity is not None else str(member.entity_index)
            )


class VIEW3D_PT_sketcher_groups(VIEW3D_PT_sketcher_base):
    """Groups panel: semantic groups of entities for IFC and other integrations."""

    bl_label = "Groups"
    bl_idname = declarations.Panels.SketcherGroups
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: Context):
        layout = self.layout
        sketch = context.scene.sketcher.active_sketch

        if sketch is None:
            layout.label(text="No active sketch", icon="INFO")
            return

        # ── Upper section: list of groups ──────────────────────────────
        row = layout.row()
        col_list = row.column()
        col_list.template_list(
            "VIEW3D_UL_sketch_groups",
            "",
            sketch,
            "groups",
            sketch,
            "active_group_index",
            rows=3,
        )
        col_ops = row.column(align=True)
        col_ops.operator("view3d.slvs_add_sketch_group", text="", icon="ADD")
        col_ops.operator("view3d.slvs_remove_sketch_group", text="", icon="REMOVE")

        layout.separator()

        # ── Lower section: members of the active group ──────────────────
        g_idx = sketch.active_group_index
        if 0 <= g_idx < len(sketch.groups):
            group = sketch.groups[g_idx]
            row2 = layout.row()
            col_members = row2.column()
            col_members.template_list(
                "VIEW3D_UL_group_members",
                "",
                group,
                "members",
                group,
                "active_member_index",
                rows=3,
            )
            col_ops2 = row2.column(align=True)
            assign_op = col_ops2.operator(
                "view3d.slvs_assign_to_group", text="", icon="PRESET_NEW"
            )
            assign_op.group_index = g_idx

            m_idx = group.active_member_index
            if 0 <= m_idx < len(group.members):
                unassign_op = col_ops2.operator(
                    "view3d.slvs_unassign_from_group", text="", icon="REMOVE"
                )
                unassign_op.group_index = g_idx
                unassign_op.member_index = m_idx
        else:
            col = layout.column()
            col.enabled = False
            col.label(text="Select a group above", icon="INFO")
