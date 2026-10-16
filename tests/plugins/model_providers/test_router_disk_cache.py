"""Router efforts disk mirror: the hot-path cache-only lookup must survive an on-disk mirror."""

import json
import sys
import time

import pytest


@pytest.fixture
def router_mod(monkeypatch):
    from providers import get_provider_profile

    profile = get_provider_profile("router")
    assert profile is not None
    mod = sys.modules[type(profile).__module__]
    monkeypatch.setattr(mod, "_efforts_cache", None)
    monkeypatch.setattr(mod, "_disk_checked", False)
    monkeypatch.setattr(mod, "_warm_efforts_async", lambda: None)
    return mod


def _write_mirror(mod, ts):
    path = mod._disk_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ts": ts, "efforts": {"grok-4.6": ["low", "high"]}}), encoding="utf-8")


def test_fresh_disk_mirror_is_served_from_cache_only(router_mod):
    _write_mirror(router_mod, time.time())
    assert router_mod._efforts_cache_only() == {"grok-4.6": ["low", "high"]}


def test_stale_disk_mirror_is_served_and_triggers_refresh(router_mod, monkeypatch):
    warmed = []
    monkeypatch.setattr(router_mod, "_warm_efforts_async", lambda: warmed.append(1))
    _write_mirror(router_mod, time.time() - router_mod._DISK_TTL_SECONDS - 60)
    assert router_mod._efforts_cache_only() == {"grok-4.6": ["low", "high"]}
    assert warmed == [1]


def test_unparseable_ts_is_treated_as_stale_not_discarded(router_mod, monkeypatch):
    warmed = []
    monkeypatch.setattr(router_mod, "_warm_efforts_async", lambda: warmed.append(1))
    _write_mirror(router_mod, "garbage")
    assert router_mod._efforts_cache_only() == {"grok-4.6": ["low", "high"]}
    assert warmed == [1]
