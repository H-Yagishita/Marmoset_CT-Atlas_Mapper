from __future__ import annotations

import os
import sys
from pathlib import Path


def application_root() -> Path:
    """Return the source checkout or the directory beside the packaged executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundled_config_root() -> Path:
    """Return config bundled inside a PyInstaller build or the source checkout."""
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS) / "config"
    return application_root() / "config"


def bundled_asset_root() -> Path:
    """Return UI assets bundled by PyInstaller or stored in the checkout."""
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS) / "assets"
    return application_root() / "assets"


def user_state_root() -> Path:
    """Per-user writable state/cache directory used by the public build."""
    override = os.environ.get("MARM_ATLAS_STATE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "MarmosetAtlasMapper"
    return Path.home() / ".marmoset_atlas_mapper"


def configured_resource_root() -> Path:
    """Root containing data/: the application folder unless explicitly overridden."""
    override = os.environ.get("MARM_ATLAS_RESOURCE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return application_root()
