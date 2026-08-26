# Registering the asset library calls bpy.ops and touches preferences, which
# isn't allowed from the restricted context during add-on register(). Defer it
# via a timer until a full context is available. (Draw handlers don't need this
# and are added directly in draw_handler.register().)

import bpy

from . import assets_manager


def startup_cb(*args):
    assets_manager.load()
    return None


def register():
    bpy.app.timers.register(startup_cb, first_interval=1, persistent=True)


def unregister():
    # The timer may not have fired yet (add-on disabled right after enabling);
    # cancel it so it can't run after the modules are gone.
    if bpy.app.timers.is_registered(startup_cb):
        bpy.app.timers.unregister(startup_cb)
