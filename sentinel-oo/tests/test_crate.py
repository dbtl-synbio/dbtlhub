"""Section 16.2 of the specification."""

from __future__ import annotations

import json

import pytest

from sentinel_oo import Crate, CrateMalformed

from conftest import minimal_crate_dict


def test_reads_published_crate(published):
    assert len(published) > 0
    assert published.root["@id"] == "./"


def test_rejects_malformed_json():
    with pytest.raises(CrateMalformed):
        Crate.from_bytes(b"{ this is not json")


def test_rejects_json_that_is_not_a_crate():
    with pytest.raises(CrateMalformed):
        Crate.from_bytes(json.dumps({"hello": "world"}).encode())


def test_rejects_crate_with_no_descriptor():
    body = {"@context": [], "@graph": [{"@id": "./", "@type": "Dataset"}]}
    with pytest.raises(CrateMalformed):
        Crate.from_bytes(json.dumps(body).encode())


def test_rejects_duplicate_entity_id():
    doubled = minimal_crate_dict(
        extra=[
            {"@id": "#a", "@type": "Thing", "name": "first"},
            {"@id": "#a", "@type": "Thing", "name": "second"},
        ]
    )
    with pytest.raises(CrateMalformed) as caught:
        Crate.from_bytes(json.dumps(doubled).encode())
    assert "#a" in str(caught.value)


def test_with_entity_returns_new_object(minimal):
    after = minimal.with_entity({"@id": "#new", "@type": "Thing"})
    assert after is not minimal


def test_with_entity_leaves_original_unchanged(minimal):
    before_length = len(minimal)
    before_checksum = minimal.checksum()
    minimal.with_entity({"@id": "#new", "@type": "Thing"})
    assert len(minimal) == before_length
    assert minimal.checksum() == before_checksum


def test_entities_cannot_be_mutated_in_place(minimal):
    with pytest.raises((AttributeError, TypeError)):
        minimal.get("./")["name"] = "renamed"
    assert minimal.get("./")["name"] == "a small crate"


def test_checksum_stable_across_reads(published_bytes):
    assert (
        Crate.from_bytes(published_bytes).checksum()
        == Crate.from_bytes(published_bytes).checksum()
    )


def test_checksum_independent_of_key_order(published_bytes):
    """A pretty printer must not invalidate a blessing."""
    parsed = json.loads(published_bytes)
    reordered = {
        "@graph": list(reversed(parsed["@graph"])),
        "@context": parsed["@context"],
    }
    assert (
        Crate.from_bytes(json.dumps(reordered).encode()).checksum()
        == Crate.from_bytes(published_bytes).checksum()
    )


def test_checksum_changes_on_any_edit(minimal):
    after = minimal.with_entity(
        {"@id": "./", "@type": "Dataset", "name": "a different name"}
    )
    assert after.checksum() != minimal.checksum()


def test_round_trip_preserves_context(published, tmp_path):
    written = published.save(tmp_path)
    again = Crate.from_path(written)
    assert again.context == published.context
    assert len(again.context) == 2
    assert again.checksum() == published.checksum()


def test_get_unknown_id_returns_none(minimal):
    assert minimal.get("#nothing-like-this") is None


def test_get_resolves_local_and_absolute_ids(minimal):
    with_hash = minimal.with_entity({"@id": "#thing", "@type": "Thing"})
    assert with_hash.get("#thing") is not None
    assert with_hash.get("thing") is not None


def test_from_path_accepts_a_folder(tmp_path, minimal):
    minimal.save(tmp_path)
    assert Crate.from_path(tmp_path).checksum() == minimal.checksum()


def test_save_to_a_folder_that_does_not_exist_yet(tmp_path, minimal):
    """Found by running it: a folder that has yet to be created was written
    out as a single file with no extension."""
    target = tmp_path / "not-created-yet"
    written = minimal.save(target)
    assert written.name == "ro-crate-metadata.json"
    assert written.parent == target
    assert Crate.from_path(target).checksum() == minimal.checksum()


def test_save_to_a_named_json_file(tmp_path, minimal):
    written = minimal.save(tmp_path / "somewhere" / "mine.json")
    assert written.name == "mine.json"


# ---------------------------------------------------------- found by probing
# Each of these was a real escape: an exception from a library reached the
# caller instead of CrateMalformed, which is the one thing this class promises.


def test_a_string_in_the_graph_is_refused():
    body = minimal_crate_dict()
    body["@graph"].append("not an entity")
    with pytest.raises(CrateMalformed):
        Crate.from_bytes(json.dumps(body).encode())


def test_a_string_containing_the_text_at_id_is_refused():
    """`"@id" in entity` is true of any string containing those characters,
    and indexing the string then raised a TypeError out of the class."""
    body = minimal_crate_dict()
    body["@graph"].append("x@idx")
    with pytest.raises(CrateMalformed):
        Crate.from_bytes(json.dumps(body).encode())


def test_a_non_text_id_is_refused():
    body = minimal_crate_dict()
    body["@graph"].append({"@id": 7, "@type": "Thing"})
    with pytest.raises(CrateMalformed):
        Crate.from_bytes(json.dumps(body).encode())


def test_adding_an_entity_with_no_id_is_refused(minimal):
    """Nothing could ever refer to it, so it is not an entity."""
    with pytest.raises(CrateMalformed):
        minimal.with_entity({"@type": "Thing", "name": "anonymous"})


def test_adding_several_entities_one_of_which_has_no_id(minimal):
    with pytest.raises(CrateMalformed):
        minimal.with_entities([{"@id": "#fine"}, {"@type": "Thing"}])


def test_descriptor_about_written_as_a_plain_string(minimal):
    """Crates in the wild write `about` both ways."""
    body = minimal_crate_dict()
    for entity in body["@graph"]:
        if entity["@id"] == "ro-crate-metadata.json":
            entity["about"] = "./"
    assert Crate.from_bytes(json.dumps(body).encode()).root["@id"] == "./"


def test_descriptor_about_an_absent_entity_is_refused():
    body = minimal_crate_dict()
    for entity in body["@graph"]:
        if entity["@id"] == "ro-crate-metadata.json":
            entity["about"] = {"@id": "#nowhere"}
    with pytest.raises(CrateMalformed):
        Crate.from_bytes(json.dumps(body).encode()).root
