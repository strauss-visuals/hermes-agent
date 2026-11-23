"""Machine teardown must join detached owned processes before profile cleanup."""

from pathlib import Path

import psutil
import pytest

from tests.e2e.core.windows_update import _machine


class _DetachedProcess:
    pid = 12345

    def __init__(self) -> None:
        self.exited = False
        self.waited = False
        self.timeout = False

    def kill(self) -> None:
        pass

    def wait(self, timeout: float) -> None:
        assert timeout > 0
        self.waited = True
        if self.timeout:
            raise psutil.TimeoutExpired(timeout, pid=self.pid)
        self.exited = True


def _machine_for(process: _DetachedProcess) -> _machine.Machine:
    machine = _machine.Machine.__new__(_machine.Machine)
    machine.root = Path("C:/machine")
    machine.profile_name = "hermes-e2e-0123456789ab"
    machine.base_url = "http://127.0.0.1"
    machine.profiles_root = Path("C:/profiles")
    machine._spawned = []
    machine.owned_processes = lambda: [process]
    machine._hkcu = {}
    machine._profile_owned = True
    machine._profile_token = "owner-token"
    return machine


def test_teardown_waits_for_detached_owned_process_before_profile_removal(monkeypatch) -> None:
    process = _DetachedProcess()
    machine = _machine_for(process)

    def remove_profile(*_args) -> None:
        assert process.waited and process.exited

    monkeypatch.setattr(_machine, "_restore_hkcu_path", lambda _previous: None)
    monkeypatch.setattr(_machine, "remove_owned_profile", remove_profile)
    monkeypatch.setenv(_machine.OPT_IN_ENV, "1")
    monkeypatch.delenv("HERMES_E2E_ARTIFACTS", raising=False)

    machine.teardown()

    assert process.waited and process.exited


def test_teardown_keeps_profile_when_owned_process_does_not_exit(monkeypatch) -> None:
    process = _DetachedProcess()
    process.timeout = True
    machine = _machine_for(process)
    removed = False

    def remove_profile(*_args) -> None:
        nonlocal removed
        removed = True

    monkeypatch.setattr(_machine, "_restore_hkcu_path", lambda _previous: None)
    monkeypatch.setattr(_machine, "remove_owned_profile", remove_profile)
    monkeypatch.setenv(_machine.OPT_IN_ENV, "1")
    monkeypatch.delenv("HERMES_E2E_ARTIFACTS", raising=False)

    with pytest.raises(RuntimeError, match="did not exit"):
        machine.teardown()

    assert not removed
