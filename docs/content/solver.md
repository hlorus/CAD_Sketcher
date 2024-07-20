The extension utilizes the solver from [solvespace](https://solvespace.com/index.pl) which
takes a set of entities with an initial position and a set of constraints which
describe geometric relationships between entities. When the solver runs it will try
to adjust entity locations to satisfy the constraints.

## Failure
![Solver Failure](images/solver_failure.png){align=right}

It's common that the solver fails to find a solution to satisfy all constraints. There
are multiple reasons why the solver might fail. Whenever this happens the active sketch
will be marked in the sidebar. It will have one of the following states:

- Okay
- Inconsistent
- Didnt Converge
- Too Many Unknowns
- Unknown Failure


<!-- ## Best Practices

## Workflow

## Tips & Tricks -->
