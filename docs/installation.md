## Addon installation
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

## Dependency installation
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

### Installation fails
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
