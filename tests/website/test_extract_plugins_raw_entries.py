"""``plugin-catalog.json`` generation: raw YAML entries must be JSON-safe and unreadable files logged."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

EXTRACT = Path(__file__).resolve().parents[2] / "website" / "scripts" / "extract-plugins.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("extract_plugins_raw", EXTRACT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HEAD = "name: dated\nrepo: https://github.com/o/r\nsha: 38fe0fb53eff98d477f807432e965429e665ca33\n"


def test_unquoted_yaml_date_serialises(mod, tmp_path):
    (tmp_path / "dated.yaml").write_text(HEAD + "added: 2026-10-14\n")

    entries = mod.load_raw_entries(tmp_path)

    assert entries[0]["added"] == "2026-10-14"
    json.dumps(entries)


def test_unparseable_yaml_is_skipped_with_a_log_line(mod, tmp_path, capsys):
    (tmp_path / "broken.yaml").write_text("name: [unclosed\n")
    (tmp_path / "dated.yaml").write_text(HEAD)

    assert [e["name"] for e in mod.load_raw_entries(tmp_path)] == ["dated"]
    assert "broken.yaml" in capsys.readouterr().err
