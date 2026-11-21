"""Delete only a harness-owned disposable Windows test profile."""

from __future__ import annotations

import os
import re
import shutil
import stat
from collections.abc import Callable
from pathlib import Path

PROFILE_OWNER_MARKER = ".hermes-e2e-owner"


def _retry_readonly_file(function: Callable[[str], object], path: str, error: BaseException) -> None:
    """Retry a read-only regular file once; preserve every other removal error."""
    if not isinstance(error, PermissionError) or function is not os.unlink:
        raise error
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & stat.S_IWRITE:
        raise error
    os.chmod(path, metadata.st_mode | stat.S_IWRITE, follow_symlinks=False)
    function(path)


def remove_owned_profile(profile: Path, profiles_root: Path, token: str) -> None:
    """Keep the existing ownership checks before reclaiming a fake profile."""
    if (profile.parent.resolve() != profiles_root.resolve()
            or not re.fullmatch(r"(?:[^\\/]+ )?hermes-e2e-[0-9a-f]{12}", profile.name)
            or profile.is_symlink() or profile.is_junction()):
        raise RuntimeError(f"refusing unsafe E2E profile cleanup: {profile}")
    if not profile.exists():
        return
    marker = profile / PROFILE_OWNER_MARKER
    if (marker.is_symlink() or marker.is_junction()
            or marker.read_text(encoding="ascii") != token):
        raise RuntimeError(f"refusing unowned E2E profile cleanup: {profile}")
    # Git pack files are read-only on Windows. Plain rmtree leaves these
    # multi-GB installs behind, so later journeys exhaust the system drive.
    shutil.rmtree(profile, onexc=_retry_readonly_file)
