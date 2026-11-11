"""The deployment program, for the parts that need no Docker.

`deploy.py` is a program rather than a library, and most of what it does is
run `docker`, which these tests do not. What they do cover is the part that
decides *where* a deployment goes and refuses before anything is built,
because that is where a mistake is silent: a deployment pointed at the
wrong machine, or at a folder that means nothing on the machine it is going
to, looks exactly like a healthy one until a handover is judged against
nothing.

Added 11 November 2026 with `--host`, which deploys to another machine.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from conftest import CONTRACTS

HERE = Path(__file__).resolve().parent.parent


def _deploy_module():
    """Load deploy.py by path. It sits beside the package rather than in
    it, because it is the thing a person runs, not something the service
    imports."""
    spec = importlib.util.spec_from_file_location("deploy", HERE / "deploy.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["deploy"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def deploy(monkeypatch):
    """A fresh copy of the program, with the environment put back after.

    `--host` works by setting DOCKER_HOST, which every later `docker` call
    reads. A test that left it set would send a later test's commands to a
    machine that does not exist.
    """
    monkeypatch.delenv("DOCKER_HOST", raising=False)
    return _deploy_module()


# ------------------------------------------------ nothing is built too early


def test_check_only_reads_the_contracts_and_builds_nothing(deploy, capsys):
    code = deploy.main([str(CONTRACTS), "--check-only"])
    printed = capsys.readouterr().out
    assert code == 0
    assert "mixing_to_coating" in printed
    assert "checksum over all of them" in printed
    assert "Nothing was built or started" in printed


def test_a_broken_contract_folder_stops_before_anything_runs(deploy, capsys,
                                                             tmp_path):
    bad = tmp_path / "contracts"
    bad.mkdir()
    (bad / "wrong.yaml").write_text("contract: x\nversion: 1\nrequires: []\n")
    code = deploy.main([str(bad)])
    printed = capsys.readouterr()
    assert code == 1
    assert "DEPLOYMENT STOPPED" in printed.err


# -------------------------------------------------- deploying somewhere else


def test_host_sends_every_docker_command_to_that_machine(deploy, monkeypatch):
    """The mechanism is Docker's own: an address in DOCKER_HOST. Nothing
    here invents a connection, which is why an ssh:// address uses the key
    the person already has."""
    seen = {}

    def nothing_runs(command, timeout=900):
        seen["env"] = deploy.os.environ.get("DOCKER_HOST")
        raise deploy.Failed("stopped on purpose by the test")

    monkeypatch.setattr(deploy, "run", nothing_runs)
    code = deploy.main([str(CONTRACTS), "--host", "ssh://you@gpu-box.example",
                        "--model-url", ""])
    assert code == 1
    assert seen["env"] == "ssh://you@gpu-box.example"


def test_a_local_folder_of_crates_is_refused_when_deploying_elsewhere(
        deploy, capsys):
    """A mount names a path on the machine the Docker daemon runs on. Taking
    this silently would mount whatever sat at that path there, or nothing."""
    code = deploy.main([str(CONTRACTS), "--host", "ssh://you@gpu-box.example",
                        "--crates", str(CONTRACTS)])
    printed = capsys.readouterr()
    assert code == 1
    assert "means nothing" in printed.err


def test_without_host_nothing_is_sent_anywhere(deploy, monkeypatch):
    """The ordinary deployment is unchanged: no DOCKER_HOST is set, so
    docker talks to the daemon on this machine as it always did."""
    seen = {}

    def nothing_runs(command, timeout=900):
        seen["env"] = deploy.os.environ.get("DOCKER_HOST")
        raise deploy.Failed("stopped on purpose by the test")

    monkeypatch.setattr(deploy, "run", nothing_runs)
    deploy.main([str(CONTRACTS), "--model-url", ""])
    assert seen["env"] is None


# ------------------------------------------------- asking a remote instance


def test_a_remote_instance_is_asked_from_inside_its_own_container(
        deploy, monkeypatch):
    """The port is published on that machine's loopback interface, so there
    is nothing here to connect to. Publishing it wider to make the check
    possible would leave a service with no password open on that machine's
    network, which is the opposite of what step 4 of the work list fixed."""
    asked = {}

    class Answered:
        returncode = 0
        stdout = '{"ok": true}'
        stderr = ""

    def fake_run(command, timeout=900):
        asked["command"] = command
        return Answered()

    monkeypatch.setattr(deploy, "run", fake_run)
    answer = deploy.ask(8080, "/health", inside="sentinel-test")

    assert answer == {"ok": True}
    assert asked["command"][:3] == ["docker", "exec", "sentinel-test"]
    assert "127.0.0.1:8080/health" in " ".join(asked["command"])


def test_asking_a_remote_instance_that_does_not_answer_raises(deploy,
                                                              monkeypatch):
    class Refused:
        returncode = 1
        stdout = ""
        stderr = "Error: No such container: sentinel-test"

    monkeypatch.setattr(deploy, "run", lambda command, timeout=900: Refused())
    with pytest.raises(OSError, match="No such container"):
        deploy.ask(8080, "/health", inside="sentinel-test")
