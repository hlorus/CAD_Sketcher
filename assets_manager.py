import glob
from pathlib import Path

import bpy

from .utilities.register import get_path


def load_asset(asset_type, asset):
    """Load a bundled asset (e.g. a node group) into the current file.

    Reads straight from the add-on's ``resources/*.blend``. Returns True if the
    asset is loaded or already present.
    """

    # Check if the asset is already present in file
    if asset in [a.name for a in getattr(bpy.data, asset_type)]:
        return True

    fp = (Path(get_path()) / "resources").as_posix()

    for file in glob.glob(fp + "/*.blend"):
        with bpy.data.libraries.load(file, assets_only=True) as (data_from, data_to):
            coll = getattr(data_from, asset_type)
            if not asset in coll:
                continue
            getattr(data_to, asset_type).append(asset)

        group = getattr(bpy.data, "node_groups").get(asset)
        group.use_fake_user = True

        return True
    return False
