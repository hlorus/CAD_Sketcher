#
# Welcome to the official documentation of CAD Sketcher

## What is CAD Sketcher?

CAD Sketcher is a constraint-based sketcher extension for [Blender](https://www.blender.org/download/) that allows to create precise 2d shapes by defining a set of geometric constraints like tangent, distance, angle, equal and more. Sketches stay editable and support a fully non-destructive workflow.

## Overview

CAD Sketcher integrates the solver of Solvespace and closely follows its design.
Therefore the [Solvespace Documentation](https://solvespace.readthedocs.io/en/latest/) is generally also relevant.

In order to have a parametric representation of a geometric system where curves
are independent of resolution, CAD Sketcher introduces a set of [Entities](entities.md).

Those Entities can be both in 2d and 3d. CAD Sketcher isn't strictly limited to but mainly
focuses on 2d entities. In order to group a set of 2d entities we use [Sketches](entities.md#SlvsSketch).

The final position and dimensions of a drawn shape is defined by [Constraints](constraints.md).

In order to have entities follow the defined constraints,
a [Solver](solver.md) is needed.

To further process the resulting geometry CAD Sketcher uses [Converters](integration.md)
to get native Blender geometry types which then allow further modifications with native tools.

<!-- Check the [Workflow](solver.md#Workflow) section to see how it's intended to be used. -->

## Links
- [Releases](https://github.com/hlorus/CAD_Sketcher/releases) - Get the extension
- [Bug Report](https://github.com/hlorus/CAD_Sketcher/wiki/Advanced#Report-a-Bug) - Report a bug
- [Github Issues](https://github.com/hlorus/CAD_Sketcher/issues) - Suggest features and follow the development
- [Discord](https://discord.gg/GzpJsShgxa) - A place for discussions
- [Contribute](advanced.md#contribute) - Looking to help out in some way?

<!-- ## Resources
-

## Tutorials
-

## What's New
Check the release logs on [github](https://github.com/hlorus/CAD_Sketcher/releases).

## FAQ
- -->
