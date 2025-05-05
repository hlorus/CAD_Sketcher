import bpy
import logging
from bpy.utils import register_tool, unregister_tool

from .add_arc2d import VIEW3D_T_slvs_add_arc2d
from .add_circle2d import VIEW3D_T_slvs_add_circle2d
from .add_line2d import VIEW3D_T_slvs_add_line2d
from .add_line3d import VIEW3D_T_slvs_add_line3d
from .add_point2d import VIEW3D_T_slvs_add_point2d
from .add_point3d import VIEW3D_T_slvs_add_point3d
from .add_rectangle import VIEW3D_T_slvs_add_rectangle
from .add_workplane import VIEW3D_T_slvs_add_workplane
from .add_workplane_face import VIEW3D_T_slvs_add_workplane_face
from .bevel import VIEW3D_T_slvs_bevel
from .offset import VIEW3D_T_slvs_offset
from .select import VIEW3D_T_slvs_select
from .trim import VIEW3D_T_slvs_trim

logger = logging.getLogger(__name__)

tools = (
    (VIEW3D_T_slvs_select, {"separator": True, "group": False}),
    (VIEW3D_T_slvs_add_point2d, {"separator": True, "group": True}),
    (
        VIEW3D_T_slvs_add_point3d,
        {
            "after": {VIEW3D_T_slvs_add_point2d.bl_idname},
        },
    ),
    (VIEW3D_T_slvs_add_line2d, {"separator": False, "group": True}),
    (
        VIEW3D_T_slvs_add_line3d,
        {
            "after": {VIEW3D_T_slvs_add_line2d.bl_idname},
        },
    ),
    (VIEW3D_T_slvs_add_circle2d, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_add_arc2d, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_add_rectangle, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_trim, {"separator": True, "group": False}),
    (VIEW3D_T_slvs_bevel, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_offset, {"separator": False, "group": False}),
    (VIEW3D_T_slvs_add_workplane_face, {"separator": True, "group": True}),
    (
        VIEW3D_T_slvs_add_workplane,
        {"after": {VIEW3D_T_slvs_add_workplane_face.bl_idname}},
    ),
)


def register():
    if bpy.app.background:
        return

    for tool in tools:
        register_tool(tool[0], **tool[1])


# Custom safe tool unregistration function to work around Blender's bug
def safe_unregister_tool(tool_cls):
    """
    Safely unregisters a tool, working around potential Blender bugs.
    """
    space_type = tool_cls.bl_space_type
    context_mode = tool_cls.bl_context_mode

    # Handle case where tool doesn't have _bl_tool attribute
    if not hasattr(tool_cls, "_bl_tool"):
        logger.info(f"Tool {tool_cls.bl_idname} has no _bl_tool attribute, skipping")
        return

    try:
        from bl_ui.space_toolsystem_common import ToolSelectPanelHelper
        cls = ToolSelectPanelHelper._tool_class_from_space_type(space_type)
        if cls is None:
            logger.warning(f"Space type {space_type} has no toolbar")
            return
            
        tools = cls._tools[context_mode]
        tool_def = tool_cls._bl_tool
        
        # Try manual removal from tools list without using index method
        found = False
        for i, item in enumerate(tools):
            if item == tool_def:
                del tools[i]
                found = True
                break
                
        if not found:
            # Look inside tuples for the tool
            for i, item in enumerate(tools):
                if isinstance(item, tuple):
                    item_clean = list(item)
                    for j, sub_item in enumerate(item_clean):
                        if sub_item == tool_def:
                            del item_clean[j]
                            found = True
                            break
                    if found:
                        if item_clean:
                            tools[i] = tuple(item_clean)
                        else:
                            del tools[i]
                        break
                        
        # Clean up the tool reference regardless of whether it was found
        if hasattr(tool_cls, "_bl_tool"):
            # Handle keymap if present
            keymap_data = tool_def.keymap
            if keymap_data is not None:
                from bpy import context
                wm = context.window_manager
                keyconfigs = wm.keyconfigs
                for kc in (keyconfigs.default, keyconfigs.addon):
                    if kc is None:
                        continue
                    km = kc.keymaps.get(keymap_data[0])
                    if km is not None:
                        try:
                            kc.keymaps.remove(km)
                        except:
                            logger.warning(f"Failed to remove keymap {keymap_data[0]} from {kc.name}")
                
            del tool_cls._bl_tool
            
    except Exception as e:
        logger.error(f"Error safely unregistering tool {tool_cls.bl_idname}: {str(e)}")
        # Still try to clean up the tool reference
        if hasattr(tool_cls, "_bl_tool"):
            del tool_cls._bl_tool


def unregister():
    if bpy.app.background:
        return

    for tool in reversed(tools):
        try:
            # Check if the tool has already been unregistered
            if not hasattr(tool[0], "_bl_tool"):
                logger.info(f"Tool {tool[0].bl_idname} already unregistered, skipping")
                continue
                
            # Use our safe custom unregister function instead
            safe_unregister_tool(tool[0])
        except Exception as e:
            # Log any unexpected errors but continue unregistering
            logger.error(f"Error unregistering tool {tool[0].bl_idname}: {str(e)}")
            # Clean up the tool reference to prevent future errors
            if hasattr(tool[0], "_bl_tool"):
                del tool[0]._bl_tool
