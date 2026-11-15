"""`scripts/make_earthdata_secret.py` passes the login to Modal and never prints it."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_earthdata_secret.py"
USER, PASSWORD = "some_user", "p@ss w0rd-XYZ"


@pytest.fixture
def script(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("make_earthdata_secret", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    netrc = tmp_path / "_netrc"
    netrc.write_text(f'machine urs.earthdata.nasa.gov login {USER} password "{PASSWORD}"\n'
                     "machine example.com login other password nope\n", encoding="utf-8")
    monkeypatch.setattr(mod, "netrc_path", lambda: netrc)
    return mod


def test_reads_the_earthdata_entry(script):
    assert script.read_login(script.netrc_path()) == (USER, PASSWORD)


def test_command_is_an_argument_list(script):
    cmd = script.build_command(USER, PASSWORD, force=False)
    assert cmd[-3:] == ["earthdata", f"EARTHDATA_USERNAME={USER}", f"EARTHDATA_PASSWORD={PASSWORD}"]
    assert isinstance(cmd, list) and "--force" not in cmd
    assert script.build_command(USER, PASSWORD, force=True)[-1] == "--force"


def test_main_never_prints_the_login(script, monkeypatch, capsys):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout=f"made {USER} {PASSWORD}", stderr="")

    monkeypatch.setattr(script.subprocess, "run", fake_run)
    assert script.main(["--force"]) == 0
    out = capsys.readouterr()
    assert USER not in out.out + out.err and PASSWORD not in out.out + out.err
    assert calls[0][-1] == "--force" and f"EARTHDATA_PASSWORD={PASSWORD}" in calls[0]


def test_failure_message_hides_the_login(script, monkeypatch, capsys):
    monkeypatch.setattr(
        script.subprocess, "run",
        lambda cmd, **kw: SimpleNamespace(returncode=2, stdout="", stderr=f"bad {USER}/{PASSWORD}"),
    )
    assert script.main([]) == 2
    out = capsys.readouterr().out
    assert USER not in out and PASSWORD not in out and "exit 2" in out
