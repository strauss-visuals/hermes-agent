"""Hardline floor: equivalent spellings of the same catastrophic command stay blocked."""

import pytest

from tools.approval import detect_hardline_command


@pytest.mark.parametrize(
    "command",
    [
        # trailing slash / dot components name the same directory
        "rm -rf /etc/",
        "rm -rf /usr/",
        "rm -rf /home/",
        "rm -rf /boot//",
        "rm -rf /home/.",
        "rm -rf /home/*/",
        'rm -rf "/etc/"',
        "rm -rf ~/.",
        "rm -rf ~/./",
        "rm -rf $HOME/",
        "rm -rf ${HOME}/.",
        "rm -rf /*/",
        # wrapper prefixes that carry their own flags/operands
        "sudo -u root rm -rf /",
        "sudo -nu root shutdown now",
        "sudo -u root shutdown now",
        "env -i rm -rf /",
        "env -u FOO BAR=1 rm -rf /",
        "timeout 5 rm -rf /",
        "timeout -s KILL 5s rm -rf /",
        "nice rm -rf /",
        "nice -n 5 rm -rf /",
        "command rm -rf /",
        "doas rm -rf /",
        "busybox rm -rf /",
        "sudo env -i timeout 3 rm -rf /",
        # command word spelled to dodge aliases / PATH lookup
        "\\rm -rf /",
        "/bin/rm -rf /",
        "/usr/sbin/reboot",
    ],
)
def test_equivalent_spellings_are_hardline(command):
    assert detect_hardline_command(command)[0] is True


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /etc/foo",
        "rm -rf /home/user/project/",
        "rm -rf /usr/local/share/foo/",
        "rm -rf ~/project/",
        "rm -rf ./build/",
        "sudo -u root ls /etc/",
        "timeout 5 ls /etc/",
        'git commit -m "sudo -u root rm -rf /"',
        "echo sudo -u root reboot",
    ],
)
def test_unrelated_commands_are_not_hardline(command):
    assert detect_hardline_command(command)[0] is False


def test_long_flag_runs_do_not_backtrack():
    # Possessive wrapper/flag matching: adversarial inputs stay linear.
    detect_hardline_command("sudo " + "-u -u " * 400 + "x")
    detect_hardline_command("rm -rf /" + "/" * 5000 + "x")
