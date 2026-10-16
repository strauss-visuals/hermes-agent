"""Plugin catalog edge cases: malformed input degrades to "skip / unknown", never an exception."""

from __future__ import annotations

import json
import shutil
import subprocess as sp
import threading

import pytest

from hermes_cli import plugin_catalog as pc
from hermes_cli import plugin_catalog_presence as presence_mod

SHA = "38fe0fb53eff98d477f807432e965429e665ca33"


def _mapping(name="good", **over):
    data = {"name": name, "repo": "https://github.com/owner/repo", "sha": SHA, "description": "d",
            "maintainer": "owner", "tier": "community"}
    data.update(over)
    return data


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(pc, "_live_fetch_failed_until", 0.0)

    def offline(*_a, **_k):
        raise OSError("offline")

    import httpx
    monkeypatch.setattr(httpx, "get", offline)
    return tmp_path


# ── malformed values ─────────────────────────────────────────────────────────

def test_unparseable_urls_do_not_raise():
    assert pc.is_allowed_image_url("https://[bad/x.png") is False
    entry = pc.entry_from_mapping(_mapping(image="https://[bad/x.png", screenshots=["https://[bad/y.png"]), "t")
    assert entry is not None and entry.image == "" and entry.screenshots == []
    assert pc.match_removed("https://[x", [pc.RemovedEntry(name="evil", repo="https://github.com/evil/bad")]) is None
    assert pc.find_removed("https://[x") is None


@pytest.mark.parametrize("over", [{"name": "foo\n"}, {"sha": SHA + "\n"}])
def test_trailing_newline_is_not_a_valid_identifier(over):
    # sha is stripped on load; name is not, and `$` would have accepted "foo\n".
    entry = pc.entry_from_mapping(_mapping(**over), "t")
    assert (entry is None) == ("name" in over)


@pytest.mark.parametrize("subdir", ["../x", "a/../b", "a//b", "./a", "a b", "a;b"])
def test_traversing_subdir_is_rejected(subdir):
    assert pc.entry_from_mapping(_mapping(subdir=subdir), "t") is None


def test_valid_subdir_and_platforms_survive():
    entry = pc.entry_from_mapping(_mapping(subdir="plugins/x", platforms=["linux", "macos"]), "t")
    assert entry is not None and entry.install_identifier.endswith("#plugins/x")
    assert pc.entry_from_mapping(_mapping(platforms=["beos"]), "t") is None


def test_list_fields_keep_only_strings():
    entry = pc.entry_from_mapping(_mapping(known_issues=["real", 3, 1.5, None]), "t")
    assert entry is not None and entry.known_issues == ["real"]


# ── live cache shape ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("payload", ["[]", "{}", '{"entries": 3}', "null", '"x"'])
def test_wrong_shaped_live_cache_reads_as_no_cache(home, payload):
    cache = pc._live_cache_path()
    cache.parent.mkdir(parents=True)
    cache.write_text(payload)

    assert pc.fetch_live_catalog() is None
    assert pc.live_removed_list() == []
    assert isinstance(pc.cached_removed_entries(), list)
    assert pc.load_catalog_live() == pc.load_catalog()


def test_right_shaped_live_cache_is_served(home):
    cache = pc._live_cache_path()
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"entries": [_mapping("live-one")], "removed": [{"name": "gone"}]}))

    assert [e.name for e in pc.load_catalog_live()] == ["live-one"]
    assert [r.name for r in pc.live_removed_list()] == ["gone"]


# ── newer checkout supplies entries the doc lacks ────────────────────────────

def _merge_setup(monkeypatch, *, tree_newer):
    live = {"entries": [_mapping("both"), _mapping("live-only")], "generated_at": "2026-01-01T00:00:00+00:00"}
    tree = [pc.entry_from_mapping(_mapping(n), "t") for n in ("both", "tree-only")]
    monkeypatch.setattr(pc, "fetch_live_catalog", lambda **_: live)
    monkeypatch.setattr(pc, "load_catalog", lambda *_a, **_k: tree)
    monkeypatch.setattr(pc, "in_tree_catalog_time", lambda: 2e9 if tree_newer else 1.0)


def test_newer_checkout_adds_entries_missing_from_the_doc(monkeypatch):
    _merge_setup(monkeypatch, tree_newer=True)
    assert [e.name for e in pc.load_catalog_live()] == ["both", "live-only", "tree-only"]


def test_older_checkout_does_not_resurrect_entries(monkeypatch):
    _merge_setup(monkeypatch, tree_newer=False)
    assert [e.name for e in pc.load_catalog_live()] == ["both", "live-only"]


# ── presence ─────────────────────────────────────────────────────────────────

def _fx_entry(name="fx"):
    return pc.entry_from_mapping(_mapping(name, repo=f"https://github.com/fx/{name}"), name)


@pytest.mark.parametrize("extensions", [[], "x", {"com.nousresearch.hermes": None},
                                        {"com.nousresearch.hermes": []}, {"com.nousresearch.hermes": {"servers": []}}])
def test_malformed_extensions_are_unknown(monkeypatch, extensions):
    monkeypatch.setattr(presence_mod, "_pinned_manifest", lambda *_a: {"extensions": extensions})
    assert presence_mod.presence(_fx_entry()) == presence_mod.UNKNOWN


def test_probe_failure_is_unknown_not_an_error(monkeypatch):
    manifest = {"extensions": {"com.nousresearch.hermes": {"servers": {"srv": {}}}}}
    monkeypatch.setattr(presence_mod, "_pinned_manifest", lambda *_a: manifest)

    class Decl:
        declaration, liveness = object(), None

    monkeypatch.setattr("hermes_cli.agent_plugins._server_declarations", lambda *_a: {"srv": Decl()})

    def boom(*_a):
        raise RuntimeError("resolver blew up")

    monkeypatch.setattr(presence_mod, "_server_presence", boom)
    assert presence_mod.presence(_fx_entry()) == presence_mod.UNKNOWN


def test_onboarding_probes_run_concurrently(monkeypatch):
    entries = [pc.entry_from_mapping(_mapping(n, onboarding=True), n) for n in ("a", "b", "c")]
    monkeypatch.setattr(presence_mod, "_onboarding_catalog", lambda: entries)
    barrier = threading.Barrier(3, timeout=5)  # a serial prober would time the barrier out

    def probe(_entry):
        barrier.wait()
        return presence_mod.UNKNOWN

    monkeypatch.setattr(presence_mod, "presence", probe)
    assert [row["name"] for row in presence_mod.onboarding_entries()] == ["a", "b", "c"]


def test_disclosure_keeps_every_sentence_after_the_marker():
    text = "Does things.  Disclosure — calls your provider.  Also queries searxng. And fetches thumbnails."
    assert presence_mod._disclosure(text) == "calls your provider. Also queries searxng. And fetches thumbnails."
    assert presence_mod._disclosure("No marker here.") == ""


# ── installed-plugin bookkeeping ─────────────────────────────────────────────

def test_ordinary_url_install_never_loads_the_live_catalog(monkeypatch, tmp_path):
    from hermes_cli import plugins_cmd_catalog as cat

    def forbidden(_name):
        raise AssertionError("live catalog must not be consulted for a non-handoff source")

    monkeypatch.setattr(cat, "get_live_catalog_entry", forbidden)
    assert cat._adopt_handoff_install(tmp_path, {"source": "https://github.com/someone/else.git#sub"}) is None


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_local_changes_reads_rename_records_as_pairs(tmp_path):
    from hermes_cli import plugins_cmd_catalog as cat

    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
           "PATH": __import__("os").environ["PATH"], "HOME": str(tmp_path)}

    def git(*args):
        sp.run(["git", *args], cwd=tmp_path, check=True, env=env, capture_output=True)

    git("init", "-q")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "x.json").write_text("{}\n")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    git("mv", "data/x.json", "data/y.json")
    (tmp_path / "note.txt").write_text("user file\n")

    local, modified = cat._local_changes(tmp_path)

    assert local == ["note.txt"]
    assert sorted(modified) == ["data/x.json", "data/y.json"]
