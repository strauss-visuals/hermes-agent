"""``_locate_real_git`` must find git-core under whichever MSYS2 environment directory the installed
Git for Windows uses. Current releases keep it under ``ucrt64`` (Git 2.56 on windows-latest has no
``mingw64`` at all), so a locator that only knew the older names reported "no real git"."""

import pytest

from hermes_cli import update_cmd_git


def _install(root, env_dir):
    exe = root / "Git" / env_dir / "libexec" / "git-core" / "git.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    return exe


@pytest.fixture
def program_files(tmp_path, monkeypatch):
    root = tmp_path / "Program Files"
    root.mkdir()
    monkeypatch.setattr(update_cmd_git, "_PROGRAM_FILES_DIRS", (str(root),))
    monkeypatch.setattr(update_cmd_git, "_portable_git_candidates", list)
    monkeypatch.setattr(update_cmd_git, "_probe_fork_bomb", lambda argv: False)
    return root


@pytest.mark.parametrize("env_dir", ["ucrt64", "mingw64", "mingw32", "clangarm64"])
def test_finds_git_core_under_every_layout(program_files, env_dir):
    exe = _install(program_files, env_dir)

    assert update_cmd_git._locate_real_git() == exe


def test_newer_layout_wins_when_both_are_installed(program_files):
    new = _install(program_files, "ucrt64")
    _install(program_files, "mingw64")

    assert update_cmd_git._locate_real_git() == new


def test_a_candidate_that_hits_the_trampoline_guard_is_skipped(program_files, monkeypatch):
    broken = _install(program_files, "ucrt64")
    healthy = _install(program_files, "mingw64")
    monkeypatch.setattr(update_cmd_git, "_probe_fork_bomb", lambda argv: argv[0] == str(broken))  # True = guard message seen

    assert update_cmd_git._locate_real_git() == healthy


def test_nothing_installed_is_none(program_files):
    assert update_cmd_git._locate_real_git() is None
