"""Section 16.10 of the specification."""

from __future__ import annotations

from sentinel_oo import BuildIdentity
from sentinel_oo.provenance import SERVICE_ID, now
from sentinel_oo.blessing import Blessing, ContractSource


def a_blessing(**over) -> Blessing:
    fields = dict(
        run_id="testrun00001",
        build=BuildIdentity("test", "0000000", "none"),
        input_checksum="sha256:deadbeef",
        started=now(),
        ended=now(),
        contract_source=ContractSource.NONE,
        verdict=None,
    )
    fields.update(over)
    return Blessing(**fields)


def actions(crate):
    return [e for e in crate if "CreateAction" in str(e.get("@type", ""))]


def test_adds_exactly_one_action(published, writer):
    before = len(actions(published))
    after = writer.write(published, a_blessing())
    assert len(actions(after)) == before + 1


def test_adds_the_instrument(published, writer):
    after = writer.write(published, a_blessing())
    instrument = after.get(SERVICE_ID)
    assert instrument is not None
    assert instrument["@type"] == "SoftwareApplication"
    # RO-Crate 1.3 wants both. Leaving `version` out is a real validator
    # finding from 10 November 2026, not a guess.
    assert instrument["softwareVersion"] == "0.1.0-test"
    assert instrument["version"] == "0.1.0-test"


def test_existing_entities_untouched_except_root_mentions(published, writer):
    """The writer alters exactly one property of one entity, and nothing else.

    The exception is the root's `mentions`, which has to gain the action or the
    action is unreachable from the root. That was one of the six faults found
    in this very crate after it had already passed validation.
    """
    after = writer.write(published, a_blessing())
    for before_entity in published:
        after_entity = after.get(before_entity["@id"])
        assert after_entity is not None, "an entity went missing"
        if before_entity["@id"] == published.root["@id"]:
            changed = {
                k for k in set(before_entity) | set(after_entity)
                if before_entity.get(k) != after_entity.get(k)
            }
            assert changed == {"mentions"}, f"root also changed {changed}"
        else:
            assert dict(after_entity) == dict(before_entity)


def test_action_is_reachable_from_the_root(published, writer):
    after = writer.write(published, a_blessing(run_id="abc123"))
    mentioned = {m["@id"] for m in after.root["mentions"]}
    assert f"{SERVICE_ID}/run/abc123" in mentioned


def test_records_build_identity(published, writer):
    after = writer.write(
        published,
        a_blessing(build=BuildIdentity("v1.2.3", "abc9999", "sha256:rules")),
    )
    values = {e["name"]: e["value"] for e in after if e.get("@type") == "PropertyValue"}
    assert values["service image tag"] == "v1.2.3"
    assert values["service commit"] == "abc9999"
    assert values["rules checksum"] == "sha256:rules"


def test_records_contract_source_distinctly(published, writer):
    from_registry = writer.write(
        published, a_blessing(contract_source=ContractSource.REGISTRY)
    )
    from_sender = writer.write(
        published,
        a_blessing(contract_source=ContractSource.SUPPLIED_BY_REQUESTER),
    )

    def source_of(crate):
        return next(
            e["value"] for e in crate
            if e.get("@type") == "PropertyValue" and e["name"] == "contract source"
        )

    assert source_of(from_registry) != source_of(from_sender)


def test_records_the_input_checksum(published, writer):
    after = writer.write(published, a_blessing(input_checksum="sha256:aaa"))
    values = {e["name"]: e["value"] for e in after if e.get("@type") == "PropertyValue"}
    assert values["checksum of the crate as received"] == "sha256:aaa"


def test_verdict_is_a_result_not_an_object(published, writer):
    """A verdict is produced by the check, so it belongs in `result`.

    Putting a result in `object` was one of the six faults found on
    10 November 2026.
    """
    after = writer.write(published, a_blessing(run_id="xyz"))
    action = next(e for e in actions(after) if e["@id"].endswith("/run/xyz"))
    results = {r["@id"] for r in action["result"]}
    objects = {o["@id"] for o in action["object"]}
    verdict_id = f"{SERVICE_ID}/run/xyz/found/verdict"
    assert verdict_id in results
    assert verdict_id not in objects


def test_not_checked_is_not_the_same_as_accepted(published, writer):
    after = writer.write(published, a_blessing(verdict=None))
    verdict = next(
        e["value"] for e in after
        if e.get("@type") == "PropertyValue" and e["name"] == "verdict"
    )
    assert "NOT CHECKED" in verdict
    assert "ACCEPTED" not in verdict


def test_writing_twice_gives_two_records(published, writer):
    once = writer.write(published, a_blessing(run_id="first0000001"))
    twice = writer.write(once, a_blessing(run_id="second000001"))
    assert len(actions(twice)) == len(actions(once)) + 1
    assert len(twice.root["mentions"]) == len(once.root["mentions"]) + 1


def test_finding_says_where_it_failed_in_a_followable_form(published, writer):
    """The prose description is not enough on its own.

    Process Run Crate says no structure may be assumed of a description, so a
    location recorded only there cannot be relied on by anything but a reader.
    """
    from sentinel_oo.contract import Requirement
    from sentinel_oo.rules import Violation

    requirement = Requirement(
        name="example", applies_to="root", property="whatever",
        named_value=None,
        must="be recorded", severity="refuse", message="no"
    )
    violation = Violation(requirement=requirement, node="./", message="no")
    after = writer.write(published, a_blessing(violations=(violation,)))

    finding = next(
        e for e in after
        if e.get("@type") == "PropertyValue"
        and str(e.get("name", "")).startswith("refuse:")
    )
    assert finding["about"]["@id"] == "./"


def test_a_finding_never_adds_a_dangling_reference(published, writer):
    """A record must not invent a reference while complaining about a crate."""
    from sentinel_oo.contract import Requirement
    from sentinel_oo.rules import Violation

    requirement = Requirement(
        name="example", applies_to="root", property="whatever",
        named_value=None,
        must="be recorded", severity="refuse", message="no"
    )
    violation = Violation(requirement=requirement, node="#not-in-the-crate",
                          message="no")
    after = writer.write(published, a_blessing(violations=(violation,)))

    finding = next(
        e for e in after
        if e.get("@type") == "PropertyValue"
        and str(e.get("name", "")).startswith("refuse:")
    )
    assert "about" not in finding
    assert "#not-in-the-crate" in finding["description"]
