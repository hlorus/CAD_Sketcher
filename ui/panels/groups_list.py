from bpy.types import Context, UIList

from ... import global_data
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
            # selection circle — full if all members are selected
            indices = [m.entity_index for m in group.members if m.entity_index != -1]
            all_sel = bool(indices) and all(i in global_data.selected for i in indices)
            op = row.operator(
                "view3d.slvs_select_group",
                text="",
                emboss=False,
                icon="RADIOBUT_ON" if all_sel else "RADIOBUT_OFF",
            )
            op.group_index = index
            row.prop(group, "name", text="", emboss=False)
            tag_vals = group.tag_values()
            if tag_vals:
                summary = (
                    tag_vals[0]
                    if len(tag_vals) == 1
                    else f"{tag_vals[0]} +{len(tag_vals)-1}"
                )
            else:
                summary = "—"
            row.label(text=summary)
            row.prop(group, "guid", text="")
            row.label(text=str(len(group.members)))
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=group.name)


class VIEW3D_UL_group_tags(UIList):
    """Middle list: one row per tag on the selected group."""

    bl_idname = "VIEW3D_UL_group_tags"

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
        tag = item
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row(align=True)
            row.prop(
                tag,
                "enabled",
                text="",
                emboss=False,
                icon="HIDE_OFF" if tag.enabled else "HIDE_ON",
            )
            row.prop(tag, "value", text="", emboss=True)
            if context.scene.sketcher.ifc_integration:
                sketch = context.scene.sketcher.active_sketch
                if sketch is not None:
                    op = row.operator(
                        "view3d.slvs_tag_group_from_preset",
                        text="",
                        icon="VIEWZOOM",
                    )
                    op.group_index = sketch.active_group_index
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=tag.value or "—")


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
                is_sel = member.entity_index in global_data.selected
                op = row.operator(
                    "view3d.slvs_select",
                    text="",
                    emboss=False,
                    icon="RADIOBUT_ON" if is_sel else "RADIOBUT_OFF",
                )
                op.index = member.entity_index
                op.mode = "TOGGLE"
                row.label(text=entity.name)
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

        g_idx = sketch.active_group_index
        group = sketch.groups[g_idx] if 0 <= g_idx < len(sketch.groups) else None

        # ── Section 1: group list ───────────────────────────────────────────────
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

        if group is None:
            layout.label(text="Select a group above", icon="INFO")
            return

        layout.separator()

        # ── Section 2: tag list for active group ──────────────────────────────────
        layout.label(text=f'Tags for "{group.name}":', icon="BOOKMARKS")
        row2 = layout.row()
        col_tags = row2.column()
        col_tags.template_list(
            "VIEW3D_UL_group_tags",
            "",
            group,
            "tags",
            group,
            "active_tag_index",
            rows=2,
        )
        col_tag_ops = row2.column(align=True)
        add_tag_op = col_tag_ops.operator(
            "view3d.slvs_add_group_tag", text="", icon="ADD"
        )
        add_tag_op.group_index = g_idx
        if 0 <= group.active_tag_index < len(group.tags):
            rm_tag_op = col_tag_ops.operator(
                "view3d.slvs_remove_group_tag", text="", icon="REMOVE"
            )
            rm_tag_op.group_index = g_idx

        layout.separator()

        # ── Section 3: member list for active group ─────────────────────────────────
        layout.label(text=f'Members of "{group.name}":', icon="SNAP_VERTEX")
        row3 = layout.row()
        col_members = row3.column()
        col_members.template_list(
            "VIEW3D_UL_group_members",
            "",
            group,
            "members",
            group,
            "active_member_index",
            rows=3,
        )
        col_ops2 = row3.column(align=True)
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
