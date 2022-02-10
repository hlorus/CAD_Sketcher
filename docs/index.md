## What is Geometry Sketcher?

Geometry Sketcher is a constraint-based sketcher addon for [Blender](https://www.blender.org/download/) that allows to create precise 2d shapes by defining a set of geometric constraints like tangent, distance, angle, equal and more. Sketches stay editable and support a fully non-destructive workflow.

## Overview

Geometry Sketcher integrats the solver of Solvespace and closley follows it's design.
Therefor the [Solvespace Documentation](https://solvespace.readthedocs.io/en/latest/) is generally also relevant.

In order to have a parametric representation of a geometric system where curves
are independent of resolution, BGS introduces a set of [Entities](entities.md).

Those Entities can be both in 2d and 3d. BGS isn't strictly limited to but mainly
focuses on 2d entities. In order to group a set of 2d entities we use [Sketches](entities.md#SlvsSketch).

The final position and dimensions of a drawn shape is defined by [Constraints](constraints.md).

In order to have entities follow the defiend constraints
a [Solver](solver.md) is needed.

To further process the resulting geometry BGS uses [Converters](integration.md)
to get native Blender geometry types which then allow further modifications with native tools.

Check the [Workflow](solver.md#Workflow) section to see how it's intended to be used.

## Installation
### Addon installation
=== "ZIP File"
    - Download the [ZIP archive](https://github.com/hlorus/geometry_sketcher/archive/refs/heads/main.zip) from github (do not unpack it after downloading)
    - Open Blender and go to: Edit > Preferences > Add-ons > Press "Install..." button
    - Browse to the location of the ZIP and select it, then press "Install Add-on"
    - Enable the addon by pressing the checkbox
=== "Git"
    You can get the latest state of the addon and easily update it with git

    - Get [Git](https://git-scm.com/)
    - In blender, set the scripts-path under Preferences->File Paths->Data->Scripts (e.g. ~/blender_scripts)
    - Open your scripts_folder

        ``` sh linenums="1"
        cd ~/blender_scripts
        ```
    - Create an addons folder
        ``` sh linenums="2"
        mkdir addons
        cd addons
        ```
    - Clone the addon repository
        ``` sh linenums="4"
        git clone https://github.com/hlorus/geometry_sketcher.git
        ```
    - Blender will now automatically load addons from that path


### Dependency installation
Geometry sketcher heavily depends on the [solvespace python module](https://pypi.org/project/py-slvs/) and won't be functional without it.

Inside the addon's preferences check the "Solver Module" tab to see if the module is already available, otherwise follow one of the guides below.

> :warning: **Supported Blender Installation:** Blender can be installed through package managers, installing external python packages with such installations might not be possible.
>
> It's recommended to use the addon with Blender installed from the official website.

=== "Install from PyPi"
    - Press "Install from PyPi"
    - Wait for the process to finish

=== "Install from local file"
    - Download the appropriate *.whl file [here](https://pypi.org/project/py-slvs/#files) (make sure the python version matches the one from your blender installation)
    - Choose the file in the filepath selector
    - Press "Install from local File"

#### Installation fails
There are multiple reasons why the installation might fail. Try the following:

- If you're on windows start blender as administrator when installing the dependency
- If you've installed blender through a package manager try again with a version from [blender.org](https://www.blender.org/download/)
- Check the application's output in the system console for any warnings or hints to find out why it's failing
- Ask for help

## Updating

=== "Manual"

    - Simply redo the installation steps with the latest addon version
    - Delete the old version from the addons list under Edit > Preferences > Add-ons

=== "Git"

    If you've cloned the addon with git you can easily update it:

    - Open the addon folder in a terminal
        ``` sh linenums="1"
        cd ~/BLENDER_SCRIPTS_PATH/geometry_sketcher
        ```
    - Pull the changes
        ``` sh linenums="2"
        git pull
        ```

## Preferences
Access the addon preferences in blender under Edit > Preferences > Add-ons > Geometry Sketcher.

Check the [User Interface section for details](user_interface.md#preferences).

## Resources
-

## Tutorials
-

## What's New
Check the release logs on [github](https://github.com/hlorus/geometry_sketcher/releases).

## FAQ

How can i select entities under constraints?

- Constraints are displayed as gizmos, disable gizmos overlay.

## Feedback

- Report a Bug: [Report a Bug](https://github.com/hlorus/geometry_sketcher/wiki/Advanced#Report-a-Bug)
- Request a feature: [Feature Request](https://github.com/hlorus/geometry_sketcher/issues/new?assignees=&labels=feature+request&template=feature_request.md&title=%5BREQUEST%5D)
- Discord: [BGS Discord](https://discord.gg/GzpJsShgxa)

## Contribute

Help is always welcome. There are multiple ways to support the project.

### Testing
Just grab the latest version, play around, provide feedback and redo!

### Documentation

### Developing

### Donate
