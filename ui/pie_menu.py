import bpy
from bpy.types import Menu

from ..declarations import BLENDER_SELECT_TOOL, Operators, WorkSpaceTools
from ..model.sketch_ref import get_active_sketch, get_sketches
from ..stateful_operator.constants import Operators as StatefulOps

PIE_MENU_ID = "VIEW3D_MT_slvs_pie"
PIE_SHORTCUT = ("M", True, True)


def _invoke_tool(layout, text, tool_name, operator, icon="NONE"):
    props = layout.operator(StatefulOps.InvokeTool.value, text=text, icon=icon)
    props.tool_name = tool_name.value
    props.operator = operator.value
    return props


def _tool_set(layout, text, tool_name, icon="NONE"):
    props = layout.operator("wm.tool_set_by_id", text=text, icon=icon)
    props.name = tool_name.value if hasattr(tool_name, "value") else tool_name
    return props


def _call_pie(layout, text, menu_id):
    props = layout.operator("wm.call_menu_pie", text=text)
    props.name = menu_id
    return props


def _sketch_slot(layout, context):
    sketch = get_active_sketch(context)
    if sketch:
        props = layout.operator(
            Operators.SetActiveSketch,
            text=f"Leave {sketch.name}",
            icon="BACK",
        )
        props.sketch_name = ""
        return

    _invoke_tool(
        layout,
        "Add Sketch",
        WorkSpaceTools.AddSketch,
        Operators.AddSketch,
        icon="ADD",
    )


class VIEW3D_MT_slvs_pie(Menu):
    bl_label = "CAD Sketcher"
    bl_idname = PIE_MENU_ID

    def draw(self, context):
        pie = self.layout.menu_pie()
        sketch = get_active_sketch(context)
        sketch_active = sketch is not None

        # West / East / South: the most-used drawing tools.
        slot = pie.row()
        slot.enabled = sketch_active
        _invoke_tool(slot, "Line", WorkSpaceTools.AddLine2D, Operators.AddLine2D)

        slot = pie.row()
        slot.enabled = sketch_active
        _invoke_tool(slot, "Circle", WorkSpaceTools.AddCircle2D, Operators.AddCircle2D)

        slot = pie.row()
        slot.enabled = sketch_active
        _invoke_tool(
            slot,
            "Rectangle",
            WorkSpaceTools.AddRectangle,
            Operators.AddRectangle,
        )

        # North: constraints live in a second radial pie so the main menu stays fast.
        slot = pie.row()
        slot.enabled = sketch_active
        _call_pie(slot, "Constraints", VIEW3D_MT_slvs_constraints_pie.bl_idname)

        # North-West / North-East: less common drawing primitives.
        slot = pie.row()
        slot.enabled = sketch_active
        _invoke_tool(slot, "Point", WorkSpaceTools.AddPoint2D, Operators.AddPoint2D)

        slot = pie.row()
        slot.enabled = sketch_active
        _invoke_tool(slot, "Arc", WorkSpaceTools.AddArc2D, Operators.AddArc2D)

        # South-West: context-sensitive sketch entry/exit plus sketch switching.
        slot = pie.row()
        slot.menu(VIEW3D_MT_slvs_sketch_menu.bl_idname, text="Sketch")

        # South-East: selection, modifiers, construction geometry and helpers.
        slot = pie.row()
        slot.menu(VIEW3D_MT_slvs_more_menu.bl_idname, text="More")


class VIEW3D_MT_slvs_constraints_pie(Menu):
    bl_label = "CAD Sketcher Constraints"
    bl_idname = "VIEW3D_MT_slvs_constraints_pie"

    def draw(self, context):
        pie = self.layout.menu_pie()

        pie.operator(Operators.AddCoincident, text="Coincident")
        pie.operator(Operators.AddEqual, text="Equal")
        pie.operator(Operators.AddHorizontal, text="Horizontal")
        pie.operator(Operators.AddVertical, text="Vertical")
        pie.operator(Operators.AddParallel, text="Parallel")
        pie.operator(Operators.AddPerpendicular, text="Perpendicular")
        pie.menu(VIEW3D_MT_slvs_dimension_menu.bl_idname, text="Dimensions")
        pie.menu(
            VIEW3D_MT_slvs_more_constraints_menu.bl_idname,
            text="More Constraints",
        )


class VIEW3D_MT_slvs_dimension_menu(Menu):
    bl_label = "Dimensional Constraints"
    bl_idname = "VIEW3D_MT_slvs_dimension_menu"

    def draw(self, context):
        layout = self.layout

        layout.operator(Operators.AddDistance, text="Distance")

        props = layout.operator(Operators.AddDistance, text="Horizontal Distance")
        props.align = "HORIZONTAL"

        props = layout.operator(Operators.AddDistance, text="Vertical Distance")
        props.align = "VERTICAL"

        layout.operator(Operators.AddAngle, text="Angle")
        layout.operator(Operators.AddDiameter, text="Diameter")

        props = layout.operator(Operators.AddDiameter, text="Radius")
        props.setting = True


class VIEW3D_MT_slvs_more_constraints_menu(Menu):
    bl_label = "More Geometric Constraints"
    bl_idname = "VIEW3D_MT_slvs_more_constraints_menu"

    def draw(self, context):
        layout = self.layout

        layout.operator(Operators.AddTangent, text="Tangent")
        layout.operator(Operators.AddMidPoint, text="Midpoint")
        layout.operator(Operators.AddRatio, text="Ratio")
        layout.operator(Operators.AddSymmetry, text="Symmetry")
        layout.operator(Operators.MergePoints, text="Merge Points")


class VIEW3D_MT_slvs_sketch_menu(Menu):
    bl_label = "Sketch"
    bl_idname = "VIEW3D_MT_slvs_sketch_menu"

    def draw(self, context):
        layout = self.layout
        active = get_active_sketch(context)

        _sketch_slot(layout, context)
        layout.separator()

        for sketch in get_sketches(context):
            target = sketch.target_object
            if not target:
                continue
            row = layout.row()
            row.enabled = not active or active.target_object != target
            props = row.operator(
                Operators.SetActiveSketch,
                text=target.name,
                icon="CURVE_DATA",
            )
            props.sketch_name = target.name


class VIEW3D_MT_slvs_more_menu(Menu):
    bl_label = "CAD Sketcher More"
    bl_idname = "VIEW3D_MT_slvs_more_menu"

    def draw(self, context):
        layout = self.layout
        sketch_active = get_active_sketch(context) is not None

        row = layout.row()
        if sketch_active:
            _tool_set(row, "Select", WorkSpaceTools.Select)
        else:
            _tool_set(row, "Select", BLENDER_SELECT_TOOL)

        layout.separator()

        row = layout.row()
        row.enabled = sketch_active
        _invoke_tool(row, "Trim", WorkSpaceTools.Trim, Operators.Trim)

        row = layout.row()
        row.enabled = sketch_active
        _invoke_tool(row, "Bevel", WorkSpaceTools.Bevel, Operators.Bevel)

        row = layout.row()
        row.enabled = sketch_active
        _invoke_tool(row, "Offset", WorkSpaceTools.Offset, Operators.Offset)

        row = layout.row()
        row.enabled = sketch_active
        row.prop(context.scene.sketcher, "use_construction", text="Construction")

        row = layout.row()
        row.enabled = sketch_active
        props = row.operator(Operators.AlignView, text="Align View")
        props.use_active = True

        layout.separator()
        layout.label(text="Node Tools")

        _invoke_tool(
            layout,
            "Extrude",
            WorkSpaceTools.Extrude,
            Operators.NodeExtrude,
        )
        _invoke_tool(
            layout,
            "Revolve",
            WorkSpaceTools.Revolve,
            Operators.NodeRevolve,
        )
        _invoke_tool(
            layout,
            "Linear Array",
            WorkSpaceTools.ArrayLinear,
            Operators.NodeArrayLinear,
        )


classes = (
    VIEW3D_MT_slvs_pie,
    VIEW3D_MT_slvs_constraints_pie,
    VIEW3D_MT_slvs_dimension_menu,
    VIEW3D_MT_slvs_more_constraints_menu,
    VIEW3D_MT_slvs_sketch_menu,
    VIEW3D_MT_slvs_more_menu,
)

addon_keymaps = []


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    wm = bpy.context.window_manager
    if not wm.keyconfigs.addon:
        return

    km = wm.keyconfigs.addon.keymaps.new(name="Object Mode", space_type="EMPTY")
    kmi = km.keymap_items.new(
        "wm.call_menu_pie",
        PIE_SHORTCUT[0],
        "PRESS",
        ctrl=PIE_SHORTCUT[1],
        shift=PIE_SHORTCUT[2],
    )
    kmi.properties.name = PIE_MENU_ID
    addon_keymaps.append((km, kmi))


def unregister():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
