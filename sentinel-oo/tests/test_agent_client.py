"""The agent interface, driven by a client from outside the process.

Everything else about this interface is tested by calling its methods. That
checks what it computes and nothing about what it is: a program another
agent starts, writes lines to, and reads lines back from. The first team to
point a real client at it would have found whatever is wrong with that part,
which is what this file is for.

**Nothing here imports the service.** It starts `python -m sentinel_oo
--agent-interface` as a subprocess and speaks JSON-RPC 2.0 over its standard
input and output, which is what the Model Context Protocol asks for. If a
line of output is not JSON, or an answer never comes, these tests fail.

Added 11 November 2026, from the list of everything found while building.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PRODUCT = Path(__file__).resolve().parents[1]
PLATE = PRODUCT / "examples" / "plate-test"
CONTRACTS = PRODUCT / "examples" / "contracts"

PROTOCOL_VERSION = "2025-06-18"


class Client:
    """A minimal client: start the server, send requests, read answers.

    Deliberately written from the protocol rather than from the service's
    own code, so that it fails if the service stops speaking the protocol.
    """

    def __init__(self, contracts: Path):
        self.process = subprocess.Popen(
            [sys.executable, "-m", "sentinel_oo", "--agent-interface",
             "--contracts", str(contracts)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
            cwd=str(PRODUCT),
            env={"PYTHONPATH": str(PRODUCT / "src"), "PATH": "/usr/bin:/bin",
                 "SENTINEL_MODEL_URL": ""},
        )
        self.next_id = 0

    def send(self, method: str, params: dict | None = None,
             notify: bool = False):
        request = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            request["params"] = params
        if not notify:
            self.next_id += 1
            request["id"] = self.next_id
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        if notify:
            return None

        line = self.process.stdout.readline()
        if not line:
            raise AssertionError(
                "the server closed without answering. Its error output was:\n"
                + self.process.stderr.read()
            )
        return json.loads(line)

    def close(self):
        try:
            self.process.stdin.close()
            self.process.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.process.kill()


@pytest.fixture
def client():
    started = Client(CONTRACTS)
    yield started
    started.close()


@pytest.fixture
def ready(client):
    """A client that has been through the opening exchange, as a real one
    must before it may call anything."""
    client.send("initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "a test client", "version": "1"},
    })
    client.send("notifications/initialized", {}, notify=True)
    return client


# ------------------------------------------------------- the opening exchange


def test_it_answers_initialize(client):
    answer = client.send("initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "a test client", "version": "1"},
    })
    assert answer["jsonrpc"] == "2.0"
    assert answer["id"] == 1
    assert answer["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert answer["result"]["serverInfo"]["name"] == "sentinel-oo"
    assert "tools" in answer["result"]["capabilities"]


def test_a_notification_gets_no_answer_and_does_not_stop_it(ready):
    """The protocol says a request with no id is a notification. A server
    that answered one would put the client's replies out of step from then
    on."""
    answer = ready.send("ping")
    assert answer["result"] == {}


# ------------------------------------------------------------ the tools


def test_it_lists_its_tools(ready):
    tools = ready.send("tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert names == {"check_handover", "list_handovers", "read_contract",
                     "get_run_graph"}
    for tool in tools:
        assert tool["description"].strip()
        assert tool["inputSchema"]["type"] == "object"


def test_every_tool_says_which_arguments_it_needs(ready):
    """A client builds its call from this and nothing else."""
    for tool in ready.send("tools/list")["result"]["tools"]:
        schema = tool["inputSchema"]
        for required in schema.get("required", []):
            assert required in schema["properties"], (
                f"{tool['name']} requires {required} and does not describe it"
            )


def _call(client, name, arguments):
    answer = client.send("tools/call", {"name": name, "arguments": arguments})
    content = answer["result"]["content"]
    assert content[0]["type"] == "text"
    return json.loads(content[0]["text"]), answer["result"].get("isError")


def test_a_client_can_find_out_what_this_instance_checks(ready):
    found, error = _call(ready, "list_handovers", {})
    assert not error
    names = {h["name"] for h in found["handovers"]}
    assert "design_to_build" in names


def test_a_client_can_read_a_contract(ready):
    found, error = _call(ready, "read_contract",
                         {"handover": "design_to_build"})
    assert not error
    assert found["name"] == "design_to_build"
    assert found["version"] == "0.11.0"
    # The field is named for what it holds: the contract in plain words,
    # which is what a producing team is sent.
    plain = found["requirements_in_plain_words_from_the_contract"]
    assert "requirement(s)" in plain
    assert "PlateWell" in plain


def test_a_client_can_check_a_handover_and_is_told_the_verdict(ready):
    found, error = _call(ready, "check_handover", {
        "handover": "design_to_build",
        "crate_path": str(PLATE / "valid"),
    })
    assert not error, found
    assert found["verdict"] == "ACCEPTED"
    assert found["run"]


def test_a_refused_handover_comes_back_as_a_verdict_not_an_error(ready):
    """A refusal is the service working. A client that treated it as a
    failure would retry it forever."""
    found, error = _call(ready, "check_handover", {
        "handover": "design_to_build",
        "crate_path": str(PLATE / "invalid" / "missing-conformsto"),
    })
    assert not error, found
    assert found["verdict"] == "REFUSED"
    assert found["findings"]


# ------------------------------------------- what a client gets wrong first


def test_an_unknown_tool_is_an_error_a_client_can_read(ready):
    found, error = _call(ready, "check_everything", {})
    assert error is True
    assert "known" in found


def test_a_missing_argument_is_an_error_a_client_can_read(ready):
    found, error = _call(ready, "check_handover", {"handover": "design_to_build"})
    assert error is True
    assert "expected" in found or "error" in found


def test_an_unknown_method_gets_a_json_rpc_error(ready):
    answer = ready.send("tools/run", {"name": "check_handover"})
    assert answer["error"]["code"] == -32601
    assert "tools/run" in answer["error"]["message"]


def test_a_bad_line_does_not_bring_the_server_down(ready):
    """A client with a bug writes something that is not JSON. The server
    must answer and stay up, because the next line may be fine."""
    ready.process.stdin.write("this is not json\n")
    ready.process.stdin.flush()
    answer = json.loads(ready.process.stdout.readline())
    assert answer["error"]["code"] == -32700

    still_there = ready.send("ping")
    assert still_there["result"] == {}
