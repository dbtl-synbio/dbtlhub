"""The two ways in: sections 16.13 and 16.14 of the specification.

Both are thin adapters over the same orchestrator and neither holds any
behaviour. These tests check the wiring, the shapes of the answers, and the
two rules that govern the agent interface specifically.
"""

from __future__ import annotations

import io
import json

import pytest

from sentinel_oo import BuildIdentity, ProvenanceWriter, RunStore, Sentinel
from sentinel_oo.agent_interface import TOOLS, AgentInterface
from sentinel_oo.agent_interface import serve as serve_agent
from sentinel_oo.api import Api
from sentinel_oo.contract import ContractRegistry
from sentinel_oo.rules import ContractChecks

from conftest import BROKEN, CONTRACTS, PUBLISHED


def a_service(writer):
    return Sentinel(
        provenance=writer,
        rules=ContractChecks(),
        registry=ContractRegistry.from_dir(CONTRACTS),
        build=BuildIdentity("test", "0000000", "none"),
    )


@pytest.fixture
def api(writer):
    return Api(a_service(writer), RunStore(limit=5))


@pytest.fixture
def agent(writer):
    return AgentInterface(a_service(writer), RunStore(limit=5))


@pytest.fixture
def crate_bytes():
    return PUBLISHED.read_bytes()


# ------------------------------------------------------- the web interface


def test_check_returns_the_crate_and_a_run_identifier(api, crate_bytes):
    status, body = api.dispatch("POST", "/check/mixing_to_coating", crate_bytes)
    assert status == 200
    assert body["verdict"] == "ACCEPTED"
    assert body["run"]
    # The example crate has 28 entities going in. The returned crate carries
    # the service's record as well, so it has more.
    assert len(body["crate"]["@graph"]) > 28


def test_a_malformed_body_is_the_callers_fault(api):
    status, body = api.dispatch("POST", "/check/mixing_to_coating", b"{ no")
    assert status == 400
    assert "not a crate" in body["error"]


def test_an_unknown_contract_names_the_known_ones(api, crate_bytes):
    status, body = api.dispatch("POST", "/check/desgin_to_build", crate_bytes)
    assert status == 404
    assert "mixing_to_coating" in body["detail"]


def test_a_refusal_still_returns_a_crate(api, writer):
    """The transport must not turn a refusal into an error with no body."""
    broken = BROKEN / "dangling-reference" / "ro-crate-metadata.json"
    status, body = api.dispatch("POST", "/check/mixing_to_coating",
                                broken.read_bytes())
    assert status == 200
    assert body["verdict"] == "REFUSED"
    assert body["findings"]
    assert body["crate"]["@graph"]


def test_contracts_lists_versions_and_a_checksum(api):
    status, body = api.dispatch("GET", "/contracts", b"")
    assert status == 200
    assert {c["name"] for c in body["contracts"]} >= {"mixing_to_coating"}
    assert body["checksum"].startswith("sha256:")


def test_a_contract_comes_back_whole(api):
    """Everything a producing team needs to check itself before being
    checked, without having to read the YAML.

    The four optional fields and `expects` used to be left out, so a caller
    could not see which values are restricted, what range a number must be
    in, which values a model may be asked to recover, or what the contract
    is for. Noticed on 11 November 2026 while writing the API manual.
    """
    status, body = api.dispatch("GET", "/contracts/mixing_to_coating", b"")
    assert status == 200
    assert body["expects"], "a caller cannot see what the contract is for"

    by_name = {r["name"]: r for r in body["requirements"]}

    restricted = by_name["drying_atmosphere_is_dry"]
    assert restricted["one_of"] == ["dry"]

    ranged = by_name["recipe_thickness_is_in_range"]
    assert ranged["between"] == [5, 500]

    narrowed = by_name["slot_names_a_real_recipe"]
    assert narrowed["of_type"] == "CoatingRecipe"

    assert by_name["drying_atmosphere_is_recorded"]["repairable"] is True
    assert by_name["declares_a_profile"]["repairable"] is False


def test_one_contract_comes_back_in_plain_words(api):
    status, body = api.dispatch("GET", "/contracts/mixing_to_coating", b"")
    assert status == 200
    assert body["summary"]
    assert len(body["requirements"]) == len(
        [r for r in body["requirements"] if r["message"]]
    )


def test_a_run_is_held_and_listed(api, crate_bytes):
    _, body = api.dispatch("POST", "/check/mixing_to_coating", crate_bytes)
    status, runs = api.dispatch("GET", "/runs", b"")
    assert status == 200
    assert body["run"] in runs["runs"]


def test_a_run_that_was_never_held_is_not_found(api):
    status, body = api.dispatch("GET", "/graph/nosuchrun", b"")
    assert status == 404


def test_the_graph_says_it_is_not_built_rather_than_pretending(api, crate_bytes):
    _, body = api.dispatch("POST", "/check/mixing_to_coating", crate_bytes)
    status, answer = api.dispatch("GET", f"/graph/{body['run']}", b"")
    assert status == 501
    assert "not built yet" in answer["error"]


def test_health_reports_the_build_and_the_engine(api):
    status, body = api.dispatch("GET", "/health", b"")
    assert status == 200
    assert body["alive"] is True
    assert body["model_engine"] == "none"


def test_the_wrong_method_says_so(api):
    status, body = api.dispatch("POST", "/health", b"")
    assert status == 405


def test_every_method_a_caller_might_try_reaches_the_dispatcher(api):
    """Otherwise the server answers some requests with HTML.

    Found on 11 November 2026 while writing the API manual. The test above
    calls the dispatcher directly, so it passed while `PUT /health` over real
    HTTP returned status 501 and a page of HTML from Python's base handler,
    which never reaches this code at all. A service that returns JSON to
    every request except a few must not be documented as returning JSON.

    This cannot be checked by making a real request, because every test here
    runs with sockets disabled, which is the right trade: the suite needs no
    network and this invariant is structural anyway.
    """
    from sentinel_oo.api import make_handler

    handler = make_handler(api)
    missing = [
        method for method in ("GET", "POST", "PUT", "PATCH", "DELETE")
        if not hasattr(handler, f"do_{method}")
    ]
    assert missing == [], (
        "these HTTP methods never reach the dispatcher, so the server "
        "answers them with HTML instead of JSON: " + ", ".join(missing)
    )


def test_an_unknown_path_lists_the_known_ones(api):
    status, body = api.dispatch("GET", "/nowhere", b"")
    assert status == 404
    assert "/health" in body["known"]


def test_the_openapi_document_is_generated_from_the_routes(api):
    """Written separately it would drift. The project outline promises an
    OpenAPI service, and a document that does not match the code is a promise
    kept on paper only."""
    _, document = api.dispatch("GET", "/openapi.json", b"")
    assert set(document["paths"]) == {r.path for r in api.routes}
    for route in api.routes:
        assert route.method.lower() in document["paths"][route.path]


# ----------------------------------------------------- the agent interface


def test_the_crate_is_never_returned_to_an_agent(agent, tmp_path):
    """The rule this interface exists for.

    The published crate is tens of kilobytes of JSON. Putting it into a
    coordinator's context spends the context and tells it nothing it can act
    on.
    """
    answer = agent.check_handover(
        "mixing_to_coating", str(PUBLISHED.parent), str(tmp_path)
    )
    assert "crate" not in answer
    assert "@graph" not in json.dumps(answer)
    assert answer["checked_package_written_to"]
    assert len(json.dumps(answer)) < 4000


def test_an_agent_is_told_the_findings_came_from_a_contract(agent, tmp_path):
    """A contract's sentences reach a coordinator's context. The field name
    has to say what they are, or a contract author could address the
    coordinator directly."""
    answer = agent.check_handover(
        "mixing_to_coating", str(BROKEN / "dangling-reference"), str(tmp_path)
    )
    assert answer["verdict"] == "REFUSED"
    assert answer["findings"]
    assert "message_from_contract" in answer["findings"][0]


def test_tool_descriptions_do_not_come_from_contract_files(agent):
    """Adding or editing a contract changes no tool name and no description.
    If it did, a contract author would be writing the coordinator's
    instructions."""
    before = json.dumps(TOOLS)
    agent.sentinel.registry = ContractRegistry.from_dir(CONTRACTS)
    assert json.dumps(TOOLS) == before
    for tool in TOOLS:
        assert "mixing_to_coating" not in json.dumps(tool)
        assert "coating_to_inspection" not in json.dumps(tool)


def test_an_unknown_handover_lists_the_known_ones(agent, tmp_path):
    answer = agent.check_handover("nope", str(PUBLISHED.parent), str(tmp_path))
    assert "mixing_to_coating" in answer["detail"]


def test_reading_a_contract_gives_plain_words(agent):
    answer = agent.read_contract("mixing_to_coating")
    assert "requirements_in_plain_words_from_the_contract" in answer


def test_a_dropped_run_says_so(agent):
    assert agent.get_run_graph("nosuchrun")["error"] == "no such run"


# -------------------------------------------------------- the protocol


def drive(agent, requests: list[dict]) -> list[dict]:
    text = "\n".join(json.dumps(r) for r in requests) + "\n"
    out = io.StringIO()
    serve_agent(agent, stdin=io.StringIO(text), stdout=out)
    return [json.loads(line) for line in out.getvalue().splitlines() if line]


def test_initialize_then_list_then_call(agent, tmp_path):
    answers = drive(agent, [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "list_handovers", "arguments": {}}},
    ])
    # The notification gets no answer, which the protocol requires.
    assert [a["id"] for a in answers] == [1, 2, 3]
    assert answers[0]["result"]["serverInfo"]["name"] == "sentinel-oo"
    assert {t["name"] for t in answers[1]["result"]["tools"]} == {
        "check_handover", "list_handovers", "read_contract", "get_run_graph"
    }
    payload = json.loads(answers[2]["result"]["content"][0]["text"])
    assert {h["name"] for h in payload["handovers"]} >= {"mixing_to_coating"}


def test_the_default_output_folder_is_somewhere_writable(agent, tmp_path, monkeypatch):
    """Found on 11 November 2026 by calling the running container.

    The default used to be a folder beside the input. In a container the
    crates are mounted read only, which is how they should be mounted, so
    writing beside them raised and the agent got an error rather than a
    verdict. No test covered the default path at all, which is how an
    unimported `os` also survived in this file for several minutes.
    """
    monkeypatch.setenv("SENTINEL_OUT", str(tmp_path / "somewhere"))
    answer = agent.call_tool("check_handover", {
        "handover": "mixing_to_coating",
        "crate_path": str(PUBLISHED.parent),
    })
    assert "error" not in answer, answer
    written = answer["checked_package_written_to"]
    assert str(tmp_path) in written, written
    # The reply always says where it went, so nobody has to guess which
    # candidate was chosen.
    assert (tmp_path / "somewhere").exists()


def test_a_destination_that_cannot_be_written_is_an_error_with_a_hint(
    agent, tmp_path, monkeypatch
):
    """What the agent sees when the destination cannot be written.

    The blocker is a path underneath a regular file, which cannot be made
    into a directory by anybody. An earlier version of this test used a
    path it assumed nobody could create, and the container caught it: the
    test stage runs as root, root created it happily, and the test failed
    there while passing on this machine.
    """
    monkeypatch.setenv("SENTINEL_OUT", str(tmp_path))
    blocker = tmp_path / "a-file-not-a-folder"
    blocker.write_text("this is a file")

    answer = agent.call_tool("check_handover", {
        "handover": "mixing_to_coating",
        "crate_path": str(PUBLISHED.parent),
        "out_path": str(blocker / "underneath"),
    })
    assert answer["error"] == "the checked package could not be written"
    assert "out_path" in answer["hint"]
    # The verdict is still reported. The crate was checked; only the saving
    # failed, and losing the answer as well would be gratuitous.
    assert answer["verdict"]


def test_a_wrong_argument_name_is_an_error_not_a_crash(agent, tmp_path):
    """The caller is a model, and models get argument names wrong.

    Found on 11 November 2026 while writing the API manual, by calling the
    running container with `out_dir` where the tool declares `out_path`. A
    TypeError propagated out of the tool, out of the handler, out of the
    read loop, and killed the process. The agent got no answer at all, not
    even an error, and the service was gone.
    """
    answer = agent.call_tool("check_handover", {
        "handover": "mixing_to_coating",
        "crate_path": str(PUBLISHED.parent),
        "out_dir": str(tmp_path),          # the tool declares out_path
    })
    assert answer["error"] == "wrong arguments"
    # It says what the tool does take, which turns a dead end into one more
    # attempt rather than a guess.
    assert "out_path" in answer["expected"]
    assert "crate_path" in answer["required"]


def test_a_tool_that_raises_does_not_take_the_service_down(agent, monkeypatch):
    """Anything at all, not only a bad argument."""

    def explode(*args, **kwargs):
        raise RuntimeError("something nobody predicted")

    monkeypatch.setattr(agent, "list_handovers", explode)
    answer = agent.call_tool("list_handovers", {})
    assert answer["error"] == "the tool failed"
    assert "something nobody predicted" in answer["detail"]


def test_a_failure_in_the_handler_still_answers(agent, monkeypatch):
    """The last line of defence, around the read loop itself."""
    import io

    def explode(request):
        raise RuntimeError("a fault above the tools")

    monkeypatch.setattr(agent, "handle", explode)
    out = io.StringIO()
    serve_agent(
        agent,
        stdin=io.StringIO('{"jsonrpc":"2.0","id":7,"method":"ping"}\n'),
        stdout=out,
    )
    answered = json.loads(out.getvalue().strip())
    assert answered["id"] == 7
    assert "a fault above the tools" in answered["error"]["message"]


def test_an_unknown_method_is_an_error_not_a_crash(agent):
    answers = drive(agent, [
        {"jsonrpc": "2.0", "id": 9, "method": "wibble"},
    ])
    assert answers[0]["error"]["code"] == -32601


def test_a_line_that_is_not_json_is_answered(agent):
    out = io.StringIO()
    serve_agent(agent, stdin=io.StringIO("{ not json\n"), stdout=out)
    assert json.loads(out.getvalue())["error"]["code"] == -32700


def test_a_failing_tool_is_marked_as_an_error(agent):
    answers = drive(agent, [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "read_contract", "arguments": {"handover": "nope"}}},
    ])
    assert answers[0]["result"]["isError"] is True
