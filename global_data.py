import sys
from enum import Enum
import logging
import bpy

from mathutils import Vector

registered = False

PYPATH = sys.executable

entities = {}
batches = {}

offscreen = None
offscreen_debug = None
redraw_selection_buffer = True

hover = -1
hover_index = -1
ignore_list = []
selected = []

# Allows to highlight a constraint gizmo,
# Value gets unset in the preselection gizmo
highlight_constraint = None

highlight_entity = None
highlight_entities = set()

# Variables for overlapping entity selection
hover_stack = []  # List of entity indices at current mouse position
hover_stack_index = -1  # Current index in the hover stack

Z_AXIS = Vector((0, 0, 1))

draw_handle = None
draw_handler = None

COPY_BUFFER = {}

# Cache data
entity_lookup = {}
constraint_lookup = {}

# Visual state
hide_coincident = False

# Undo data storage
last_operator_data = None

# Entity unique identifiers
next_entity_id = 0

# Context state
_in_restricted_context = False

# Batch storage for restricted contexts
_entity_batches = {}

logger = logging.getLogger(__name__)

def in_restricted_context():
    """Check if we're in a context where property writes are restricted."""
    # This is a simplification - in reality you might need more complex logic
    # but this pattern allows you to have a central place to manage this check
    return _in_restricted_context

def set_restricted_context(state):
    """Set the restricted context state."""
    global _in_restricted_context
    _in_restricted_context = state
    
def safe_set_property(obj, key, value):
    """Safely set a property on an object, accounting for restricted contexts.
    
    Returns True if the property was set, False otherwise.
    """
    if in_restricted_context():
        logger.debug(f"Skipping property write {key}={value} in restricted context")
        return False
    
    try:
        if isinstance(key, str) and hasattr(obj, key):
            setattr(obj, key, value)
        else:
            obj[key] = value
        return True
    except Exception as e:
        logger.debug(f"Could not set property {key}: {e}")
        return False
        
def safe_clear_dirty(entity):
    """Safely clear the is_dirty flag on an entity."""
    if not hasattr(entity, "is_dirty"):
        return
    
    if in_restricted_context():
        # Just skip setting the flag in restricted contexts
        return
    
    try:
        entity.is_dirty = False
    except Exception as e:
        # This is a fallback - ideally we'd handle this properly with context detection
        logger.debug(f"Could not clear dirty flag: {e}")

def safe_create_batch(entity, batch_func, *args, **kwargs):
    """Create and store batches safely, even in restricted contexts.
    
    Args:
        entity: The entity to create a batch for
        batch_func: Function to call to create the batch
        *args, **kwargs: Arguments to pass to batch_func
    
    Returns:
        The created batch
    """
    global _entity_batches
    
    # Create a unique key for this entity
    key = getattr(entity, "slvs_index", id(entity))
    
    if in_restricted_context():
        # In restricted context, store the batch in our dictionary
        batch = batch_func(*args, **kwargs)
        _entity_batches[key] = batch
        logger.debug(f"Created batch for entity {key} in restricted context")
        return batch
    else:
        # In normal context, we can set the _batch property directly
        try:
            batch = batch_func(*args, **kwargs)
            entity._batch = batch
            # Also store in our dictionary for consistency
            _entity_batches[key] = batch
            return batch
        except Exception as e:
            logger.debug(f"Error creating batch: {e}")
            return None

def get_batch(entity):
    """Get the batch for an entity, whether from the entity itself or our storage"""
    key = getattr(entity, "slvs_index", id(entity))
    
    # First try to get from the entity itself if we're not in restricted context
    if not in_restricted_context() and hasattr(entity, "_batch"):
        return entity._batch
        
    # Otherwise try from our storage
    return _entity_batches.get(key)
    
def clear_batches():
    """Clear the batch storage"""
    global _entity_batches
    _entity_batches = {}

class WpReq(Enum):
    """Workplane requirement options"""

    OPTIONAL, FREE, NOT_FREE = range(3)


solver_state_items = [
    (
        "OKAY",
        "Okay",
        "Successfully solved sketch.",
        "CHECKMARK",
        0,  # SLVS_RESULT_OKAY
    ),
    (
        "INCONSISTENT",
        "Inconsistent",
        (
            f"Cannot solve sketch because of inconsistent constraints, check through the failed constraints "
            f"and remove the ones that contradict each other."
        ),
        "ERROR",
        1,  # SLVS_RESULT_INCONSISTENT
    ),
    (
        "DIDNT_CONVERGE",
        "Didnt Converge",
        "Cannot solve sketch, system didn't converge.",
        "ERROR",
        2,  # SLVS_RESULT_DIDNT_CONVERGE
    ),
    (
        "TOO_MANY_UNKNOWNS",
        "Too Many Unknowns",
        "Cannot solve sketch because of too many unknowns.",
        "ERROR",
        3,  # SLVS_RESULT_TOO_MANY_UNKNOWNS
    ),
    (
        "INIT_ERROR",
        "Initialize Error",
        "Solver failed to initialize.",
        "ERROR",
        4,  # SLVS_RESULT_INIT_ERROR
    ),
    (
        "REDUNDANT_OK",
        "Redundant Constraints",
        (
            f"Some constraints seem to be redundant, this might cause an error once the constraints are no longer consistent. "
            f"Check through the marked constraints and only keep what's necessary."
        ),
        "INFO",
        5,  # SLVS_RESULT_REDUNDANT_OK
    ),
    (
        "UNKNOWN_FAILURE",
        "Unknown Failure",
        "Cannot solve sketch because of unknown failure.",
        "ERROR",
        6,
    ),
]

# Name of the asset library used for CAD Sketcher assets
LIB_NAME = "CAD Sketcher Assets"