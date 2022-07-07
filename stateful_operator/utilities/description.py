def _format_types(types):
    entity_names = ", ".join([e.__name__ for e in types])
    return "[" + entity_names + "]"

def state_desc(name, desc, types):
    type_desc = ""
    if types:
        type_desc = "Types: " + _format_types(types)
    return " ".join((name + ":", desc, type_desc))

def stateful_op_desc(base, *state_descs):
    states = ""
    length = len(state_descs)
    for i, state in enumerate(state_descs):
        states += " - {}{}".format(
            state, ("  \n" if i < length - 1 else "")
        )
    desc = "{}  \n  \nStates:  \n{}".format(base, states)
    return desc