from bpy.types import Context, UIList

from ... import global_data
from ...utilities.preferences import get_prefs
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
            # selection circle — full when all members are selected
            indices = [m.entity_index for m in group.members if m.entity_index != -1]
            all_sel = bool(indices) and all(i in global_data.selected for i in indices)
            op = row.operator(
                "view3d.slvs_select_group",
                text="",
                emboss=False,
                icon="RADIOBUT_ON" if all_sel else "RADIOBUT_OFF",
            )
            op.group_index = index
            row.prop(group, "name", text="", emboss=True)
            tag_vals = group.tag_values()
            summary = (
                (
                    tag_vals[0]
                    if len(tag_vals) == 1
                    else f"{tag_vals[0]} +{len(tag_vals)-1}"
                )
                if tag_vals
                else "—"
            )
            row.label(text=summary)
            row.label(text=str(len(group.members)))
            # inline delete
            op = row.operator(
                "view3d.slvs_remove_sketch_group",
                text="",
                emboss=False,
                icon="X",
            )
            op.group_index = index
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
            sketch = context.scene.sketcher.active_sketch
            if sketch is not None:
                # context menu for tag GUID details
                props = row.operator(
                    "view3d.slvs_group_tag_context_menu",
                    text="",
                    emboss=False,
                    icon="OUTLINER_DATA_GP_LAYER",
                )
                props.group_index = sketch.active_group_index
                props.tag_index = index
                if get_prefs().ifc_integration:
                    op = row.operator(
                        "view3d.slvs_tag_group_from_preset",
                        text="",
                        icon="VIEWZOOM",
                    )
                    op.group_index = sketch.active_group_index
                    op.tag_index = index
                # inline delete
                op = row.operator(
                    "view3d.slvs_remove_group_tag",
                    text="",
                    emboss=False,
                    icon="X",
                )
                op.group_index = sketch.active_group_index
                op.tag_index = index
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
        sketch = context.scene.sketcher.active_sketch
        g_idx = sketch.active_group_index if sketch is not None else -1
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
                # context menu for entity details
                props = row.operator(
                    "view3d.slvs_group_member_context_menu",
                    text="",
                    emboss=False,
                    icon="OUTLINER_DATA_GP_LAYER",
                )
                props.highlight_hover = True
                props.highlight_active = True
                props.highlight_members = True
                props.group_index = g_idx
                props.member_index = index
                props.index = member.entity_index
            else:
                row.label(text="(missing)", icon="ERROR")
            # inline delete (works for both valid and missing members)
            op = row.operator(
                "view3d.slvs_unassign_from_group",
                text="",
                emboss=False,
                icon="X",
            )
            op.group_index = g_idx
            op.member_index = index
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

    @classmethod
    def poll(cls, context: Context):
        return context.scene.sketcher.active_sketch is not None

    def draw(self, context: Context):
        layout = self.layout
        sketch = context.scene.sketcher.active_sketch

        g_idx = sketch.active_group_index
        group = sketch.groups[g_idx] if 0 <= g_idx < len(sketch.groups) else None

        # Path-type indicator at top of panel for quick feedback
        if group is not None:
            _PATH_LABEL = {
                "CLOSED_PATH": ("Group is a closed path", "PROP_ON"),
                "OPEN_PATH": ("Group is an open path", "PROP_CON"),
                "NOT_PATH": ("Group is not a path", "PROP_OFF"),
            }
            pt = group.path_type(context.scene.sketcher.entities)
            pt_text, pt_icon = _PATH_LABEL[pt]
            layout.label(text=pt_text, icon=pt_icon)
            layout.separator()

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
