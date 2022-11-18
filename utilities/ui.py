import bpy
from bpy.types import Context


def show_ui_message_popup(
    message: str = "", title: str = "Sketcher Warning", icon: str = "INFO"
):
    """
    Trigger a ui popup message
    NOTE: Perhaps better located in ui.py, but would currently require circular
          dependency with operators.py
    """

    lines = message.split("\n")

    def draw(self, context: Context):
        layout = self.layout
        for line_str in lines:
            row = layout.row()
            row.label(text=line_str)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)
