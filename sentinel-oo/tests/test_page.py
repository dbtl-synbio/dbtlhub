"""PROTOTYPE, 12 November 2026: the page for people, and the widened run list.

The page holds no behaviour of its own. It reads the JSON addresses the
service already answers, so the tests that matter are that it is served,
that it asks only for addresses that exist, that it cannot be used to read
any other file, and that the run list carries what the page shows.
"""

from __future__ import annotations

import re

import pytest

from sentinel_oo import RunStore
from sentinel_oo.api import PAGE_DIR, Api, Page

from conftest import PUBLISHED
from test_interfaces import a_service


@pytest.fixture
def api(writer):
    return Api(a_service(writer), RunStore(limit=5))


def test_the_home_address_is_a_page(api):
    status, body = api.dispatch("GET", "/", b"")
    assert status == 200
    assert isinstance(body, Page)
    assert body.content_type.startswith("text/html")
    assert b"<title>sentinel-oo</title>" in body.body


def test_the_drawing_library_is_served_from_the_package(api):
    status, body = api.dispatch("GET", "/page/cytoscape.min.js", b"")
    assert status == 200
    assert body.content_type.startswith("text/javascript")
    assert b"Cytoscape Consortium" in body.body[:400]


@pytest.mark.parametrize("name", ["..", "...", "api.py", "nosuchfile.js",
                                  ".hidden"])
def test_no_other_file_can_be_read_through_the_page_address(api, name):
    status, body = api.dispatch("GET", f"/page/{name}", b"")
    assert status == 404
    assert not isinstance(body, Page)


def test_a_path_with_a_slash_is_not_a_page_file(api):
    status, _ = api.dispatch("GET", "/page/../api.py", b"")
    assert status == 404


def test_every_address_the_page_asks_for_is_one_the_service_answers(api):
    """The page and the route table are separate files, so they can drift.
    Every fetched path in the page, with its variable parts filled in, must
    match a GET route."""
    html = (PAGE_DIR / "index.html").read_text(encoding="utf-8")
    asked = set(re.findall(r'getJSON\(\s*[`"](/[^`"$]*)', html))
    asked |= set(re.findall(r'src="(/[^"]+)"', html))
    assert {"/health", "/contracts", "/runs", "/graph/", "/contracts/",
            "/page/cytoscape.min.js"} <= asked
    gets = [r for r in api.routes if r.method == "GET"]
    for path in asked:
        filled = path + "x" if path.endswith("/") else path
        assert any(r.regex.match(filled) for r in gets), path


def test_the_page_never_inserts_crate_text_as_html():
    """A crate is somebody else's data. The page builds every element with
    text nodes, so a crate holding markup cannot run anything."""
    html = (PAGE_DIR / "index.html").read_text(encoding="utf-8")
    assert "innerHTML" not in html
    assert "insertAdjacentHTML" not in html
    assert "document.write" not in html


def test_the_run_list_carries_what_the_page_shows(api):
    _, body = api.dispatch("POST", "/check/mixing_to_coating",
                           PUBLISHED.read_bytes())
    status, runs = api.dispatch("GET", "/runs", b"")
    assert status == 200
    assert runs["runs"] == [body["run"]]          # unchanged for old readers
    [recent] = runs["recent"]
    assert recent["run"] == body["run"]
    assert recent["crate"]                        # the crate's own name
    assert recent["verdict"] == body["verdict"]
    assert recent["contract"] == "mixing_to_coating"
    assert recent["contract_version"]
    assert recent["started"] and recent["ended"]
    assert recent["findings"] == len(body["findings"])
    assert recent["model"] == "none configured"


def test_the_newest_run_comes_first_in_the_recent_list(api):
    first = api.dispatch("POST", "/check/mixing_to_coating",
                         PUBLISHED.read_bytes())[1]["run"]
    second = api.dispatch("POST", "/check/mixing_to_coating",
                          PUBLISHED.read_bytes())[1]["run"]
    _, runs = api.dispatch("GET", "/runs", b"")
    assert [r["run"] for r in runs["recent"]] == [second, first]


def test_the_page_routes_appear_in_the_openapi_document(api):
    _, document = api.dispatch("GET", "/openapi.json", b"")
    assert "/" in document["paths"]
    assert "/page/{file}" in document["paths"]
