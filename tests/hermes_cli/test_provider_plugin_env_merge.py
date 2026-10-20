"""A provider listed on models.dev AND registered as a plugin profile must recognise the plugin's
documented API-key env vars, whatever name models.dev uses for its own. models.dev data drifts under
the plugin (CommandCode now lists ``CMD_API_KEY`` while the plugin reads ``COMMANDCODE_API_KEY``)."""

from agent.models_dev import ProviderInfo
from hermes_cli import providers


def _drifted_models_dev(monkeypatch, env):
    info = ProviderInfo(id="commandcode", name="CommandCode", env=env, api="https://api.commandcode.ai/v1")
    monkeypatch.setattr(providers, "_models_dev_info", lambda canonical, allow_network=True: info)


def test_plugin_key_env_var_is_recognised_next_to_models_dev_name(monkeypatch):
    _drifted_models_dev(monkeypatch, ("CMD_API_KEY",))

    pdef = providers.resolve_provider_full("commandcode", {}, [])

    assert pdef is not None and pdef.source == "models.dev"
    assert pdef.api_key_env_vars[0] == "CMD_API_KEY"  # models.dev keeps priority
    assert "COMMANDCODE_API_KEY" in pdef.api_key_env_vars


def test_url_shaped_plugin_env_vars_are_not_added_as_keys(monkeypatch):
    _drifted_models_dev(monkeypatch, ("CMD_API_KEY",))

    pdef = providers.get_provider("commandcode")

    assert not any(v.endswith(("_BASE_URL", "_URL")) for v in pdef.api_key_env_vars)


def test_no_duplicates_when_models_dev_already_names_the_plugin_var(monkeypatch):
    _drifted_models_dev(monkeypatch, ("COMMANDCODE_API_KEY",))

    pdef = providers.get_provider("commandcode")

    assert list(pdef.api_key_env_vars).count("COMMANDCODE_API_KEY") == 1
