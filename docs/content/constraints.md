Constraints are used to restrict the movement of entities and define their
final locations. A constraint can usually be created between different entity types,
check the corresponding operator's tooltip to find out what's supported.

## Active
A constraint is considered to be active when the sketch it belongs to is set as the active
sketch or, for constraints that don't belong to a sketch, when no sketch is active.

## Failure
Whenever the [solver](solver.md) fails to find a solution for the given system it
will try to mark constraints that are causing the failure. Those constraints
will be colored red, additionally the failed sketch will be marked.

## Types
>Constraint types follow the implementation of
[solvespace](https://solvespace.readthedocs.io/en/latest/constraints/index.html).

### Geometric Constraints
::: CAD_Sketcher.model.types.SlvsCoincident

::: CAD_Sketcher.model.types.SlvsVertical

::: CAD_Sketcher.model.types.SlvsHorizontal

>**Note:** It’s good to use horizontal and vertical constraints whenever possible. These constraints are very simple to solve, and will not lead to convergence problems. Whenever possible, define the workplanes so that lines are horizontal and vertical within those workplanes.


::: CAD_Sketcher.model.types.SlvsParallel

::: CAD_Sketcher.model.types.SlvsPerpendicular

::: CAD_Sketcher.model.types.SlvsEqual

::: CAD_Sketcher.model.types.SlvsTangent

::: CAD_Sketcher.model.types.SlvsMidpoint

::: CAD_Sketcher.model.types.SlvsRatio

### Dimensional Constraints
Adding a dimensional constraint places its label in the same step: pick the
geometry, then move the mouse to position the label and, optionally, type a value
before confirming. The label's position can be adjusted later by dragging its
gizmo.

::: CAD_Sketcher.model.types.SlvsDistance

::: CAD_Sketcher.model.types.SlvsDiameter

::: CAD_Sketcher.model.types.SlvsAngle

## Driven & Animated Dimensions
The value of a dimensional constraint (distance, diameter or angle) is stored as
a regular scene property and shown as an editable field in the **Constraints**
panel. Because it's an ordinary Blender property you can **right-click it** and
**Add Driver** or **Insert Keyframe**, just like any other value.

The sketch re-solves whenever the value changes — including on frame changes — so
the geometry follows a driven or animated dimension across the timeline. This
lets you, for example, drive one dimension from another property or animate a
dimension to create parametric motion.

> Reference dimensions (measurements) only report the current value and can't be
> driven or keyframed.
