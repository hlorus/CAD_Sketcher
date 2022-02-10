Constraints are used to restrict the movement of entities and define their
final locations. A constraint can usually be created between diffrent entity types,
check the corresponding operator's tooltip to find out what's supported.

## Active
A constraint is considered to be active when the sketch it belongs to is set as the active
sketch or, for constraints that don't belong to a sketch, when no sketch is active.

## Failure
Whenever the [solver](solver.md) fails to find a solution for the given system it
will try to mark constraints that are causing the failure. Those constraints
will be colored red, additionally the failed sketch will be marked.

## Types
Constraint types follow the implementation of
[solvespace](https://solvespace.readthedocs.io/en/latest/constraints/index.html)

### Geometric Constraints
::: geometry_sketcher.class_defines.SlvsCoincident

::: geometry_sketcher.class_defines.SlvsVertical

::: geometry_sketcher.class_defines.SlvsHorizontal

>**Note:** It’s good to use horizontal and vertical constraints whenever possible. These constraints are very simple to solve, and will not lead to convergence problems. Whenever possible, define the workplanes so that lines are horizontal and vertical within those workplanes.


::: geometry_sketcher.class_defines.SlvsParallel

::: geometry_sketcher.class_defines.SlvsPerpendicular

::: geometry_sketcher.class_defines.SlvsEqual

::: geometry_sketcher.class_defines.SlvsTangent

::: geometry_sketcher.class_defines.SlvsMidpoint

::: geometry_sketcher.class_defines.SlvsRatio

### Dimensional Constraints
::: geometry_sketcher.class_defines.SlvsDistance

::: geometry_sketcher.class_defines.SlvsDiameter

::: geometry_sketcher.class_defines.SlvsAngle
