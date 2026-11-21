"""Owned fake-profile cleanup on real Windows; no installer, registry or service."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from tests.e2e.core.windows_update._profile_cleanup import (
    PROFILE_OWNER_MARKER,
    remove_owned_profile,
)

pytestmark = [pytest.mark.platforms("windows"), pytest.mark.integration]


def _profile(root: Path, name: str = "hermes-e2e-0123456789ab") -> Path:
    profile = root / name
    profile.mkdir(parents=True)
    (profile / PROFILE_OWNER_MARKER).write_text("owned-token", encoding="ascii")
    return profile


def test_owned_profile_cleanup_reclaims_readonly_git_pack(tmp_path: Path) -> None:
    root = tmp_path / "Profiles"
    profile = _profile(root)
    pack = profile / "AppData/Local/hermes/hermes-agent/.git/objects/pack/pack-test.idx"
    pack.parent.mkdir(parents=True)
    pack.write_bytes(b"synthetic git pack index")
    pack.chmod(stat.S_IREAD)
    neighbour = root / "another-profile"
    neighbour.mkdir()
    sentinel = neighbour / "keep.txt"
    sentinel.write_text("untouched", encoding="ascii")

    remove_owned_profile(profile, root, "owned-token")

    assert not profile.exists()
    assert sentinel.read_text(encoding="ascii") == "untouched"


@pytest.mark.parametrize("case", ["wrong-token", "wrong-name", "wrong-parent"])
def test_profile_cleanup_refuses_unowned_or_unsafe_profiles(tmp_path: Path, case: str) -> None:
    root = tmp_path / "Profiles"
    parent = tmp_path / "elsewhere" if case == "wrong-parent" else root
    name = "real-user" if case == "wrong-name" else "hermes-e2e-0123456789ab"
    profile = _profile(parent, name)
    token = "not-owned" if case == "wrong-token" else "owned-token"

    with pytest.raises(RuntimeError, match="refusing (unsafe|unowned) E2E profile cleanup"):
        remove_owned_profile(profile, root, token)

    assert (profile / PROFILE_OWNER_MARKER).read_text(encoding="ascii") == "owned-token"


def test_profile_cleanup_preserves_locked_file_failure(tmp_path: Path) -> None:
    root = tmp_path / "Profiles"
    profile = _profile(root)
    locked = profile / "locked.txt"
    locked.write_text("still in use", encoding="ascii")

    with locked.open("rb"):
        with pytest.raises(PermissionError):
            remove_owned_profile(profile, root, "owned-token")
        assert locked.exists()
