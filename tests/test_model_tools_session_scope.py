"""Regression: explicit session toolsets scope actual direct dispatch, not only schemas.

The fixtures are no-op registry handlers. They never invoke terminal, network,
credentials, file tools, connectors, delegates, a provider, or a live Hermes home.
This is defense-in-depth, not an OS isolation boundary.
"""

import json

import pytest

import model_tools
from tools.registry import registry


@pytest.fixture
def tool_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        json.dumps({"tools": {"tool_search": {"enabled": "off"}}}), encoding="utf-8"
    )
    scope = str(tmp_path)
    seen = []
    allowed = "scoped_reader_no_effect"
    rejected = "unlisted_handler_no_effect"

    for name, toolset in ((allowed, "scoped_reader"), (rejected, "scope_other")):
        registry.register(
            name=name, toolset=toolset,
            schema={
                "name": name, "description": "No-effect session scope test",
                "parameters": {"type": "object", "properties": {}},
            },
            handler=lambda _args, _name=name: (
                seen.append(_name) or json.dumps({"executed": _name})
            ),
            scope=scope,
        )
    try:
        yield allowed, rejected, seen
    finally:
        for name in (allowed, rejected):
            current = registry.snapshot_registration(name, scope=scope)
            if current:
                assert registry.restore_registration(name, current, None, scope=scope)


def call(name, toolsets, *, disabled=None):
    return model_tools.handle_function_call(
        name, {}, enabled_toolsets=toolsets, disabled_toolsets=disabled,
        skip_pre_tool_call_hook=True,
        skip_tool_request_middleware=True,
        skip_tool_execution_middleware=True,
    )


def test_explicit_session_toolsets_reject_unlisted_registered_handler(tool_fixture):
    allowed, rejected, seen = tool_fixture
    result = call(rejected, ["scoped_reader"])
    assert "not available in this session" in result
    assert seen == []
    success = call(allowed, ["scoped_reader"])
    assert json.loads(success)["executed"] == allowed
    assert seen == [allowed]


def test_explicit_empty_toolsets_deny_all_without_a_plugin_hook(tool_fixture):
    allowed, _, seen = tool_fixture
    assert "not available in this session" in call(allowed, [])
    assert seen == []


def test_explicit_disabled_toolset_wins_over_enabled(tool_fixture):
    allowed, rejected, seen = tool_fixture
    result = call(rejected, ["scoped_reader", "scope_other"], disabled=["scope_other"])
    assert "not available in this session" in result
    assert seen == []


def test_unadvertised_tool_search_bridge_denied_when_off(tool_fixture):
    _, _, seen = tool_fixture
    assert "not available in this session" in call("tool_call", ["scoped_reader"])
    assert seen == []


def test_scope_verification_failure_does_not_dispatch(tool_fixture, monkeypatch):
    allowed, _, seen = tool_fixture

    def fail_scope(*_args, **_kwargs):
        raise RuntimeError("Synthetic scope lookup failure")

    monkeypatch.setattr(model_tools, "_select_tool_names", fail_scope)
    result = call(allowed, ["scoped_reader"])
    assert "scope verification failed" in result
    assert seen == []


def test_legacy_unscoped_call_remains_compatible(tool_fixture):
    _, rejected, seen = tool_fixture
    result = call(rejected, None)
    assert json.loads(result)["executed"] == rejected
    assert seen == [rejected]
