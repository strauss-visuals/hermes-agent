"""Snapshot extraction must not write outside the skills tree on any supported Python."""

import io
import tarfile

import pytest

from agent import curator_backup


def _archive(tmp_path, members):
    path = tmp_path / "snap.tar.gz"
    with tarfile.open(path, "w:gz") as tf:
        for info, data in members:
            tf.addfile(info, io.BytesIO(data) if data is not None else None)
    return path


def _file(name, data=b"x"):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    return info, data


def _symlink(name, target):
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE
    info.linkname = target
    return info, None


def test_regular_snapshot_extracts(tmp_path):
    dest = tmp_path / "skills"
    dest.mkdir()
    archive = _archive(tmp_path, [_file("alpha/SKILL.md", b"hi")])
    with tarfile.open(archive) as tf:
        curator_backup._extract_snapshot(tf, dest)
    assert (dest / "alpha" / "SKILL.md").read_bytes() == b"hi"


@pytest.mark.parametrize("name", ["/abs/file", "a/../../escape"])
def test_unsafe_names_are_refused(tmp_path, name):
    dest = tmp_path / "skills"
    dest.mkdir()
    archive = _archive(tmp_path, [_file(name)])
    with tarfile.open(archive) as tf, pytest.raises(tarfile.TarError):
        curator_backup._extract_snapshot(tf, dest)


def test_symlink_escape_is_refused_without_extraction_filters(tmp_path, monkeypatch):
    """Python 3.11.0-3.11.3 has no ``filter=``; links there must be rejected, not extracted."""
    monkeypatch.delattr(tarfile, "data_filter", raising=False)
    dest = tmp_path / "skills"
    dest.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    archive = _archive(tmp_path, [_symlink("link", "../outside"), _file("link/pwned")])
    with tarfile.open(archive) as tf, pytest.raises(tarfile.TarError):
        curator_backup._extract_snapshot(tf, dest)
    assert not (outside / "pwned").exists()


def test_symlink_escape_is_refused_with_extraction_filters(tmp_path):
    if not hasattr(tarfile, "data_filter"):
        pytest.skip("interpreter has no tarfile extraction filters")
    dest = tmp_path / "skills"
    dest.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    archive = _archive(tmp_path, [_symlink("link", "../outside"), _file("link/pwned")])
    with tarfile.open(archive) as tf, pytest.raises(tarfile.TarError):
        curator_backup._extract_snapshot(tf, dest)
    assert not (outside / "pwned").exists()
