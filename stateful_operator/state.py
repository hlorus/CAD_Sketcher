from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple


@dataclass(frozen=True)
class OperatorState:
    # The name to display in the interface
    name: str

    # Text to be displayed in statusbar
    description: Any = ""

    # Operator property this state acts upon.
    # Can also be a list of property names or a callable that returns
    # a set of properties dynamically. When not explicitly set to None the
    # operator's state_property method will be called.
    property: Any = ""

    # Optional: A state can reference an element via a pointer attribute.
    # If set, state_func fills the main property and create_element fills this pointer.
    pointer: Optional[str] = None

    # Types the pointer property can accept
    types: Tuple = ()

    # Trigger state without an event
    no_event: bool = False

    # Always evaluate state and confirm by user input
    interactive: bool = False

    # Enables or disables creation of the element
    use_create: bool = True

    # Callback (or string name) to get the state property value from mouse coordinates
    state_func: Any = None

    # Define if state should be filled from selected entities when invoked
    allow_prefill: bool = True

    # Prefill callback which chooses an entity to use for this state
    parse_selection: Any = None

    pick_element: Any = None
    create_element: Any = None
    check_pointer: Any = None

    # Operator can be run before this state's pointer/property is submitted
    optional: bool = False


def state_from_args(name: str, **kwargs) -> OperatorState:
    """Create an OperatorState, with all fields optional except name."""
    return OperatorState(name=name, **kwargs)
