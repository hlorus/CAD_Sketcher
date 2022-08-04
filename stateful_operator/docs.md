
# StatefulOperator Doc

## Operator Methods

main(self, context) -> succeede(bool)
  function which creates the actual result of the operator,
  e.g. the main function of an add_line operator creates the line

register_properties(cls) -> None
  can be used to store implicit pointer properties and pointer fallback properties

get_state_pointer(self, index=None) -> result(ANY)
  method for pointer access, either of active state or by state index

set_state_pointer(self, value, index=None) -> succeede(bool)
  method to set state pointer, either of active state or by state index

check_props(self) -> succeede(bool)
  additional poll function to check if all necessary operator properties
  are set and the main function can be called

init(self, context, event) -> None

fini(self, context, succeede) -> None

check_pointer(self, prop_name) -> is_set(bool)
  check if a state pointer is set

gather_selection(self, context) -> selected(list(ANY))
  gather the currently selected elements that are later used to fill state pointers with


## State Definition

state_func(self, context, coords) property_value(ANY)
  method to get the value for the state property from mouse coordinates

pick_element(self, context, coords) -> element or its implicit props
  method to pick a matching element from mouse coordinates, either return the
  element or its implicit prop values, has to set the type of the picked element

create_element(self, context, value, state, state_data) -> element or its implicit props
  method to create state element when no existing element gets picked,
  has to set the type of the created element