# Geometry Sketcher
Constraint-based sketcher addon for [Blender](https://www.blender.org/download/) that allows to create precise 2d shapes by defining a set of geometric constraints like tangent, distance, angle, equal and more. Sketches stay editable and support a fully non-destructive workflow.

Minimum version: Blender 2.92

Discussion and feedback: [Discord](https://discord.gg/GzpJsShgxa)

> :warning: **Experimental addon:** This is still work in progress, don't use it on production files without a backup.


## Addon installation

- Download the [ZIP archive](https://github.com/hlorus/geometry_sketcher/archive/refs/heads/main.zip) from github (do not unpack it after downloading)
- Open Blender and go to: Edit > Preferences > Add-ons > Press "Install..." button
- Browse to the location of the ZIP and select it, then press "Install Add-on"
- Enable the addon by pressing the checkbox



## Dependency installation
Geometry sketcher heavily depends on the [solvespace python module](https://pypi.org/project/py-slvs/) and won't be fully funtional without it.

- Inside the addon's preferences check the "Solver Module" tab to see if the module is already available
- Either press "Install from PyPi"
- Or download the appropriate *.whl file [here](https://pypi.org/project/py-slvs/#files) and press "Install from local File"



