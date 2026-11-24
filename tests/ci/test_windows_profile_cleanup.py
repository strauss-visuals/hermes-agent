"""Owned fake-profile cleanup on real Windows; no installer, registry or service."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from tests.e2e.core.windows_update._profile_cleanup import (
    PROFILE_OWNER_MARKER,
    remove_owned_profile,
)
from tests.e2e.core.windows_update import _machine

# These bounded filesystem checks run in the ordinary native Windows unit lane.
pytestmark = pytest.mark.platforms("windows")


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


def test_failed_machine_stage_removes_its_owned_profile(monkeypatch, tmp_path: Path) -> None:
    profiles = tmp_path / "Profiles"
    profiles.mkdir()
    monkeypatch.setenv("HERMES_E2E_WINDOWS_INSTALL", "1")
    monkeypatch.setenv("HERMES_E2E_MACHINE_ROOT", str(tmp_path / "machines"))
    monkeypatch.setenv("HERMES_E2E_PROFILES_ROOT", str(profiles))

    def fail_staging(*_args, **_kwargs):
        raise RuntimeError("synthetic staging failure")

    monkeypatch.setattr(_machine, "harness_git", fail_staging)
    with pytest.raises(RuntimeError, match="synthetic staging failure"):
        _machine.new_machine(tmp_path / "fallback", "http://127.0.0.1:1", label="stage-failure")

    assert list(profiles.iterdir()) == []


def test_partial_owner_marker_write_leaves_only_a_small_pending_artifact(monkeypatch, tmp_path: Path) -> None:
    profiles = tmp_path / "Profiles"
    profiles.mkdir()
    monkeypatch.setenv("HERMES_E2E_WINDOWS_INSTALL", "1")
    monkeypatch.setenv("HERMES_E2E_MACHINE_ROOT", str(tmp_path / "machines"))
    monkeypatch.setenv("HERMES_E2E_PROFILES_ROOT", str(profiles))

    partial = []

    def fail_after_partial_write(marker, token: str) -> None:
        partial.append(token[:5])
        marker.write(partial[-1])
        marker.flush()
        raise RuntimeError("synthetic partial marker write")

    monkeypatch.setattr(_machine, "_write_profile_owner_marker", fail_after_partial_write)
    with pytest.raises(RuntimeError, match="synthetic partial marker write") as raised:
        _machine.new_machine(tmp_path / "fallback", "http://127.0.0.1:1", label="marker-failure")

    children = list(profiles.iterdir())
    assert len(children) == 1
    pending = children[0]
    assert pending.name.startswith(".hermes-e2e-pending-")
    assert not any(child.name.startswith("hermes-e2e-") for child in children)
    assert str(pending) in "\n".join(getattr(raised.value, "__notes__", []))
    pending_files = list(pending.iterdir())
    assert [path.name for path in pending_files] == [PROFILE_OWNER_MARKER]
    assert pending_files[0].read_text(encoding="ascii") == partial[0]
    assert pending_files[0].stat().st_size < 64


def test_final_profile_collision_preserves_existing_directory_and_pending_artifact(
    monkeypatch, tmp_path: Path,
) -> None:
    profiles = tmp_path / "Profiles"
    profiles.mkdir()
    monkeypatch.setenv("HERMES_E2E_WINDOWS_INSTALL", "1")
    monkeypatch.setenv("HERMES_E2E_MACHINE_ROOT", str(tmp_path / "machines"))
    monkeypatch.setenv("HERMES_E2E_PROFILES_ROOT", str(profiles))
    real_rename = _machine._rename_pending_profile
    collision_sentinel = profiles / "sentinel.txt"

    def race_final_name_collision(pending: Path, profile: Path, expected_identity,
                                  parent_handle, parent_volume, mark_owned) -> None:
        profile.mkdir()
        collision_sentinel.write_text("unowned", encoding="ascii")
        real_rename(pending, profile, expected_identity, parent_handle, parent_volume, mark_owned)

    monkeypatch.setattr(_machine, "_rename_pending_profile", race_final_name_collision)
    with pytest.raises(FileExistsError) as raised:
        _machine.new_machine(tmp_path / "fallback", "http://127.0.0.1:1", label="collision")

    assert collision_sentinel.read_text(encoding="ascii") == "unowned"
    pending_dirs = [path for path in profiles.iterdir() if path.name.startswith(".hermes-e2e-pending-")]
    assert len(pending_dirs) == 1
    pending = pending_dirs[0]
    assert str(pending) in "\n".join(getattr(raised.value, "__notes__", []))
    pending_files = list(pending.iterdir())
    assert [path.name for path in pending_files] == [PROFILE_OWNER_MARKER]
    assert pending_files[0].stat().st_size < 64


def test_swapped_pending_path_cannot_publish_or_delete_replacement(monkeypatch, tmp_path: Path) -> None:
    ancestor = tmp_path / "ancestor"
    profiles = ancestor / "Profiles"
    profiles.mkdir(parents=True)
    monkeypatch.setenv("HERMES_E2E_WINDOWS_INSTALL", "1")
    monkeypatch.setenv("HERMES_E2E_MACHINE_ROOT", str(tmp_path / "machines"))
    monkeypatch.setenv("HERMES_E2E_PROFILES_ROOT", str(profiles))
    real_publish = _machine._publish_profile_handle
    def try_swap_then_publish(set_info, source, parent, profile: Path) -> None:
        pending = next(profiles.glob(".hermes-e2e-pending-*"))
        with pytest.raises(PermissionError):
            pending.rename(pending.with_name(pending.name + ".held"))
        with pytest.raises(PermissionError):
            ancestor.rename(ancestor.with_name("ancestor-moved"))
        real_publish(set_info, source, parent, profile)

    def fail_staging(*_args, **_kwargs):
        raise RuntimeError("synthetic staging failure")

    monkeypatch.setattr(_machine, "_publish_profile_handle", try_swap_then_publish)
    monkeypatch.setattr(_machine, "harness_git", fail_staging)
    with pytest.raises(RuntimeError, match="synthetic staging failure"):
        _machine.new_machine(tmp_path / "fallback", "http://127.0.0.1:1", label="swap-pending")

    assert list(profiles.iterdir()) == []


def test_profiles_parent_reparse_point_fails_closed(monkeypatch, tmp_path: Path) -> None:
    ancestor = tmp_path / "ancestor"
    profiles = ancestor / "Profiles"
    profiles.mkdir(parents=True)
    real_is_junction = Path.is_junction
    monkeypatch.setattr(Path, "is_junction", lambda path: path == ancestor or real_is_junction(path))

    with pytest.raises(RuntimeError, match="profiles path is missing or contains a reparse point"):
        _machine._create_profile_from_pending(profiles / "hermes-e2e-test", "owned-token")

    assert list(profiles.iterdir()) == []


def test_missing_profiles_ancestor_fails_without_creating_it(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "Profiles"

    with pytest.raises(RuntimeError, match="profiles path is missing or contains a reparse point"):
        _machine._create_profile_from_pending(missing / "hermes-e2e-test", "owned-token")

    assert not missing.parent.exists()


def test_post_publish_identity_failure_still_cleans_owned_profile(monkeypatch, tmp_path: Path) -> None:
    profiles = tmp_path / "Profiles"
    profiles.mkdir()
    monkeypatch.setenv("HERMES_E2E_WINDOWS_INSTALL", "1")
    monkeypatch.setenv("HERMES_E2E_MACHINE_ROOT", str(tmp_path / "machines"))
    monkeypatch.setenv("HERMES_E2E_PROFILES_ROOT", str(profiles))
    real_identity = _machine._path_identity

    def lose_published_identity(path: Path, *, directory: bool):
        if path.parent == profiles and path.name.startswith("hermes-e2e-"):
            return None
        return real_identity(path, directory=directory)

    monkeypatch.setattr(_machine, "_path_identity", lose_published_identity)
    with pytest.raises(RuntimeError, match="published profile identity differs"):
        _machine.new_machine(tmp_path / "fallback", "http://127.0.0.1:1", label="post-publish-check")

    assert list(profiles.iterdir()) == []
