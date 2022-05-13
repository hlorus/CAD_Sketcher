import bpy
from . import global_data
from bpy.app.handlers import persistent
import logging

logger = logging.getLogger(__name__)

_custom_handlers = {}


# Addon events / handlers
#
# Example usage:
#   Post event:
#       from .event_system import post_event
#       post_event(Events.SketchEnterPre)
#
#   Add handler:
#       from .event_system import add_handler
#       add_handler(Events.SketchEnterPre, my_callback)


events = (
    "SketchEnterPre",
    "SketchLeavePre",
    # "SketchUpdate",
    # "EntityCreate",
    # "EntityUpdate",
    # "EntityDelete",
    # "ConstraintCreate",
    # "ConstraintUpdate",
    # "ConstraintDelete",
    )

class Events:
    SKETCH_LEAVE = "SKETCH_LEAVE"
    ENTITY_CREATE = "ENTITY_CREATE"
    CONSTRAINT_CREATE = "CONSTRAINT_CREATE"
    ENTITY_DELETE = "ENTITY_DELETE"
    CONSTRAINT_DELETE = "CONSTRAINT_DELETE"

def add_handler(event: str, callback):
    """Add handler to addon events"""
    logger.debug("Register handler: " + event)
    global _custom_handlers
    _custom_handlers.setdefault(event, list()).append(callback)

def post_event(event: str, data):
    if event not in events:
        raise AttributeError("No valid event: " + event)
    logger.debug("Trigger event: " + event)
    for callback in _custom_handlers.get(event, tuple()):
        callback(data)
