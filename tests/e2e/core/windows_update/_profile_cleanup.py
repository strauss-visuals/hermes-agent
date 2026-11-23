"""Delete only a harness-owned disposable Windows test profile."""

from __future__ import annotations

import os
import re
import shutil
import stat
import sys
from collections.abc import Callable
from pathlib import Path

PROFILE_OWNER_MARKER = ".hermes-e2e-owner"


def _is_junction(path: Path) -> bool:
    """Detect junctions on supported Python versions, failing closed on Windows."""
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None:
        return is_junction()
    if os.name != "nt":
        return False
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", None)
    if reparse_point is None:
        return True
    return bool(getattr(metadata, "st_file_attributes", 0) & reparse_point)


def _retry_readonly_file(
    function: Callable[[str], object],
    path: str,
    error_info: BaseException | tuple[object, BaseException, object],
) -> None:
    """Retry a read-only regular file once; preserve every other removal error."""
    error = error_info[1] if isinstance(error_info, tuple) else error_info
    if not isinstance(error, PermissionError) or function is not os.unlink:
        raise error
    metadata = os.lstat(path)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & stat.S_IWRITE:
        raise error
    writable_mode = metadata.st_mode | stat.S_IWRITE
    if os.chmod in os.supports_follow_symlinks:
        os.chmod(path, writable_mode, follow_symlinks=False)
    else:
        os.chmod(path, writable_mode)
    function(path)


def remove_owned_profile(profile: Path, profiles_root: Path, token: str) -> None:
    """Keep the existing ownership checks before reclaiming a fake profile."""
    if (
        profile.parent.resolve() != profiles_root.resolve()
        or not re.fullmatch(r"(?:[^\\/]+ )?hermes-e2e-[0-9a-f]{12}", profile.name)
        or profile.is_symlink()
        or _is_junction(profile)
    ):
        raise RuntimeError(f"refusing unsafe E2E profile cleanup: {profile}")
    if not profile.exists():
        return
    marker = profile / PROFILE_OWNER_MARKER
    if (
        marker.is_symlink()
        or _is_junction(marker)
        or marker.read_text(encoding="ascii") != token
    ):
        raise RuntimeError(f"refusing unowned E2E profile cleanup: {profile}")
    # Git pack files are read-only on Windows. Plain rmtree leaves these
    # multi-GB installs behind, so later journeys exhaust the system drive.
    if sys.version_info >= (3, 12):
        shutil.rmtree(profile, onexc=_retry_readonly_file)
    else:
        shutil.rmtree(profile, onerror=_retry_readonly_file)
