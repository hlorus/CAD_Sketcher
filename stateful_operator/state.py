from collections import namedtuple

OperatorState = namedtuple(
    "OperatorState",
    (
        "name",  # The name to display in the interface
        "description",  # Text to be displayed in statusbar
        # Operator property this state acts upon
        # Can also be a list of property names or a callback that returns
        # a set of properties dynamically. When not explicitly set to None the
        # operators state_property function will be called.
        "property",
        # Optional: A state can reference an element, pointer attribute set the name of property function
        # if set this will be passed to main func,
        # state_func should fill main property and create_element should fill this property
        # maybe this could just store it in a normal attr, should work as long as the same operator instance is used, test!
        "pointer",
        "types",  # Types the pointer property can accept
        "no_event",  # Trigger state without an event
        "interactive",  # Always evaluate state and confirm by user input
        "use_create",  # Enables or Disables creation of the element
        "state_func",  # Function to get the state property value from mouse coordinates
        "allow_prefill",  # Define if state should be filled from selected entities when invoked
        "parse_selection",  # Prefill Function which chooses entity to use for this stat
        "pick_element",
        "create_element",
        # TODO: Implement!
        "use_interactive_placemenet",  # Create new state element based on mouse coordinates
        "check_pointer",
        "optional",  # Operator can be run before this state's pointer/property is submitted
    ),
)
del namedtuple


def state_from_args(name: str, **kwargs):
    """
    Use so each state can avoid defining all members of the named tuple.
    """
    kw = {
        "name": name,
        "description": "",
        "property": "",
        "pointer": None,
        "types": (),
        "no_event": False,
        "interactive": False,
        "use_create": True,
        "state_func": None,
        "allow_prefill": True,
        "parse_selection": None,
        "pick_element": None,
        "create_element": None,
        "use_interactive_placemenet": True,
        "check_pointer": None,
        "optional": False,
    }
    kw.update(kwargs)
    return OperatorState(**kw)
