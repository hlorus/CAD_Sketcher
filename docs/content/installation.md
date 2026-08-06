## Installation
=== "Repository (recommended)"
    Adding CAD Sketcher as a remote repository lets Blender install and **update** it in-app.

    - Open Blender and go to: Edit > Preferences > Get Extensions
    - Open the repositories drop-down (arrow in the top right corner) and choose "Add Remote Repository"
    - Paste the URL below, enable "Check for Updates on Startup" and confirm

        ``` sh
        https://hlorus.github.io/CAD_Sketcher-extensions/stable/index.json
        ```
    - CAD Sketcher now appears in the extensions list, press "Install"

    > For rolling per-commit builds use the `latest` channel instead:
    > `https://hlorus.github.io/CAD_Sketcher-extensions/latest/index.json`
    >
    > To test builds that bundle **open pull requests** (not yet merged), see the
    > community-maintained [CAD_SketcherPR](https://github.com/falken10vdl/CAD_SketcherPR)
    > project (tracked in issue [#551](https://github.com/hlorus/CAD_Sketcher/issues/551)).
=== "Extension ZIP File"
    - Download the [ZIP archive](https://github.com/hlorus/CAD_Sketcher/archive/refs/heads/main.zip) from github (ensure it's a ZIP Archive, on Mac you might have to repack as it gets unzipped automatically)
    - Open Blender and go to: Edit > Preferences > Get Extensions > Extension Settings (Arrow in the top right corner) > Press "Install from Disk..." button
    - Browse to the location of the ZIP and select it, then press "Install from Disk"
=== "Legacy addon"
    - Download the [ZIP archive](https://github.com/hlorus/CAD_Sketcher/archive/refs/heads/main.zip) from github (ensure it's a ZIP Archive, on Mac you might have to repack as it gets unzipped automatically)
    - Open Blender and go to: Edit > Preferences > Add-ons > Press "Install..." button
    - Browse to the location of the ZIP and select it, then press "Install Add-on"
    - Enable the addon by pressing the checkbox
=== "Git"
    You can get the latest state of the addon and easily update it with git

    - Get [Git](https://git-scm.com/)
    - In Blender, add the scripts-path under Preferences->File Paths->Script Directories->Add (e.g. ~/blender_scripts)
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
        git clone https://github.com/hlorus/CAD_Sketcher.git
        ```
    - Blender will now automatically load addons from that path

## Dependency installation
CAD Sketcher heavily depends on the [solvespace python module](https://pypi.org/project/slvs/) and won't be functional without it. When installed as an Extension the module ships bundled as a wheel, so there's usually nothing to do here.

> **Python version compatibility:** the bundled solver provides wheels for Python **3.11, 3.12 and 3.13** — the versions embedded in official [blender.org](https://www.blender.org/download/) builds. If Blender reports something like *"This Python version (3.14) isn't compatible with (3.11)"* on install, it's running a **newer system Python** (common with distribution-packaged Blender on rolling distros such as Arch/CachyOS). Fix it by using an official build from [blender.org](https://www.blender.org/download/) — the **5.2 LTS** is a safe choice — instead of your distribution's package. Python 3.14 is not yet supported (waiting on an upstream `slvs` release).

Once the 3D View CAD Sketcher plugin is installed check its preferences for the "Solver Module" tab to see if the module is already available, otherwise follow one of the guides below.

=== "Blender 5.0 Extension"
    - If you install CAD Sketcher as a Blender Extension you can skip this step

=== "Install from PIP"
    - Press "Install from PIP"
    - Wait for the process to finish

=== "Install from local file"
    - Download the appropriate *.whl file [here](https://pypi.org/project/slvs/#files) (make sure the python version matches the one from your blender installation)
    - Choose the file in the filepath selector
    - Press "Install from local File"

### Extra step on Mac OS:
Due to an ongoing Blender bug, Mac OS users with Metal need to change their GPU Backend to OpenGL: Edit > Preferences > System > GPU Backend > Select "OpenGL". Remember to restart Blender after this.

### Installation fails
There are multiple reasons why the installation might fail. Try the following:

- If you're on windows start blender as administrator when installing the dependency
- If you've installed blender through a package manager try again with a version from [blender.org](https://www.blender.org/download/)
- Check the application's output in the system console for any warnings or hints to find out why it's failing
- Blender can be installed through package managers, installing external python packages with such installations might not be possible. Try to use the extension with Blender installed from the official website.
- Ask for help

## Updating

=== "Manual"

    - Delete the old version from the addons/extensions list under Edit > Preferences > Add-ons/Get Extensions
    - Simply redo the installation steps with the latest addon version

=== "Git"

    If you've cloned the addon with git you can easily update it:

    - Open the addon folder in a terminal
        ``` sh linenums="1"
        cd ~/BLENDER_SCRIPTS_PATH/CAD_Sketcher
        ```
    - Pull the changes
        ``` sh linenums="2"
        git pull
        ```
