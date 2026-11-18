"""Tool progress preserves the executor's canonical call identity."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hermes_cli.stream_json import StreamJsonEmitter
from run_agent import AIAgent


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setattr("hermes_cli.plugins.discover_plugins", lambda: None)
    definitions = [{
        "type": "function",
        "function": {
            "name": "fixture_reader",
            "description": "Inert offline test reader",
            "parameters": {"type": "object"},
        },
    }]
    with (
        patch("model_tools.get_tool_definitions", return_value=definitions),
        patch("model_tools.check_toolset_requirements", return_value={}),
        patch("agent.process_bootstrap.OpenAI"),
    ):
        return AIAgent(
            api_key="fixture-key",
            base_url="http://127.0.0.1:1/v1",
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
        )


def _assistant_message():
    return SimpleNamespace(
        content="",
        tool_calls=[
            SimpleNamespace(
                id=call_id,
                type="function",
                function=SimpleNamespace(
                    name="fixture_reader",
                    arguments=json.dumps({"value": value}),
                ),
            )
            for call_id, value in (("call-one", "alpha"), ("call-two", "beta"))
        ],
    )


@pytest.mark.parametrize("parallel", [False, True])
def test_tool_progress_carries_dispatch_id_into_jsonl(agent, capsys, monkeypatch, parallel):
    emitter = StreamJsonEmitter(model="fixture-model", session_id="fixture-session")
    emitter.attach(agent)
    capsys.readouterr()
    dispatched = {}

    def dispatch(name, args, task_id, *, tool_call_id, **kwargs):
        dispatched[tool_call_id] = args["value"]
        return json.dumps({"success": True, "value": args["value"]})

    monkeypatch.setattr("model_tools.handle_function_call", dispatch)
    execute = (
        agent._execute_tool_calls_concurrent if parallel
        else agent._execute_tool_calls_sequential
    )
    messages = []
    execute(_assistant_message(), messages, "fixture-task")

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    expected = {"call-one": "alpha", "call-two": "beta"}
    assert dispatched == expected
    assert {row["tool_call_id"] for row in messages if row["role"] == "tool"} == expected.keys()
    starts = [event for event in events if event["type"] == "tool_use"]
    results = [event for event in events if event["type"] == "tool_result"]
    assert len(starts) == len(results) == len(expected)
    assert {event["tool_call_id"]: event["input"]["value"] for event in starts} == expected
    assert {
        event["tool_call_id"]: json.loads(event["output"])["value"]
        for event in results
    } == expected


@pytest.mark.parametrize("custom_signature", [False, True])
def test_legacy_progress_subscriber_still_receives_events(
    agent, monkeypatch, custom_signature,
):
    events = []

    def progress(event, name, preview, args, /, *, duration=None, is_error=None, result=None):
        events.append((event, name, args, is_error, result))

    class UninspectableProgress:
        @property
        def __signature__(self):
            raise RuntimeError("custom signature unavailable")

        def __call__(self, *args, **kwargs):
            progress(*args, **kwargs)

    agent.tool_progress_callback = UninspectableProgress() if custom_signature else progress
    monkeypatch.setattr("model_tools.handle_function_call", lambda *a, **kw: '{"success":true}')
    message = _assistant_message()
    message.tool_calls.pop()
    agent._execute_tool_calls_sequential(message, [], "fixture-task")

    assert events == [
        ("tool.started", "fixture_reader", {"value": "alpha"}, None, None),
        ("tool.completed", "fixture_reader", None, False, '{"success":true}'),
    ]


@pytest.mark.parametrize("blocked", [True, False])
def test_progress_does_not_project_blocked_or_uncommitted_result(
    agent, capsys, monkeypatch, blocked,
):
    StreamJsonEmitter(model="fixture-model").attach(agent)
    capsys.readouterr()
    dispatch_calls = []

    def dispatch(*args, **kwargs):
        dispatch_calls.append(kwargs["tool_call_id"])
        return '{"success":true}'

    monkeypatch.setattr("model_tools.handle_function_call", dispatch)
    if blocked:
        monkeypatch.setattr(
            "hermes_cli.plugins._dispatch_pre_tool_call_hooks",
            lambda *args, **kwargs: ("Blocked by fixture policy", None),
        )
    else:
        monkeypatch.setattr(agent, "_flush_messages_to_session_db", lambda messages: False)
    message = _assistant_message()
    message.tool_calls.pop()
    agent._execute_tool_calls_sequential(message, [], "fixture-task")

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert dispatch_calls == ([] if blocked else ["call-one"])
    assert [event["type"] for event in events] == ([] if blocked else ["tool_use"])
