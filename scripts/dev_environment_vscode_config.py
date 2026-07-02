"""Setup CAD_Sketcher development environment and configure VS Code.

One-off setup (run once):
  1. Install the CAD_Sketcher extension in Blender.
  2. Run this script via the VS Code task "Configure CAD_Sketcher/vscode development environment",
     or directly:

         blender --background --python scripts/dev_environment_vscode_config.py

     This replaces the installed extension copy with a symlink to this repo and
     writes .vscode/settings.json with path mappings for the VS Code debugger.

Per-session workflow:
  1. Run the VS Code task "Launch Blender interactively" to start Blender with
     debugpy listening on port 5678.
  2. Run the "Interactive+debugger" launch configuration (F5) to attach the debugger.
  3. To restart Blender from within Blender, one can use bonsai's operator (F3 -> bim.restart_blender).
     Then re-run F5 to re-attach the debugger.

For automated testing:
  - Run the VS Code task "Run Blender+testing" to run the test suite headlessly.
    The "Pytest+debugger" launch configuration (F5) can be used to attach mid-test if needed.
"""

import json
import shutil
import sys
from pathlib import Path

import bpy

repo_path = Path(__file__).resolve().parent.parent

major, minor, _ = bpy.app.version
blender_version = f"{major}.{minor}"

if sys.platform == "win32":
    blender_config = (
        Path.home() / f"AppData/Roaming/Blender Foundation/Blender/{blender_version}"
    )
elif sys.platform == "darwin":
    blender_config = (
        Path.home() / f"Library/Application Support/Blender/{blender_version}"
    )
else:
    blender_config = Path.home() / f".config/blender/{blender_version}"

install_path = blender_config / "extensions/user_default/CAD_Sketcher"

assert install_path.exists() or install_path.is_symlink(), (
    f"CAD_Sketcher not found at expected path: {install_path}\n"
    "Make sure the addon is installed in Blender before running this script."
)

if install_path.is_symlink():
    current_target = install_path.resolve()
    if current_target == repo_path:
        print(f"Symlink already correct: {install_path} -> {repo_path}")
    else:
        print(f"Relinking: {install_path} -> {repo_path}  (was -> {current_target})")
        install_path.unlink()
        install_path.symlink_to(repo_path, target_is_directory=True)
else:
    print(f"Replacing installed copy with symlink: {install_path} -> {repo_path}")
    shutil.rmtree(install_path)
    install_path.symlink_to(repo_path, target_is_directory=True)

settings_path = repo_path / ".vscode" / "settings.json"
settings_path.parent.mkdir(parents=True, exist_ok=True)

settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
settings.update(
    {
        "cadSketcher.localRoot": repo_path.as_posix(),
        "cadSketcher.remoteRoot": install_path.as_posix(),
        "cadSketcher.blenderPath": Path(bpy.app.binary_path).parent.as_posix(),
    }
)
settings_path.write_text(json.dumps(settings, indent=2))

print("\n\nCAD_Sketcher/VSCode development environment configured successfully!\n\n")
print(f"  localRoot  : {repo_path}")
print(f"  remoteRoot : {install_path}")
