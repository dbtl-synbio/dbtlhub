"""The returned crate must still be a valid RO-Crate.

This is the invariant from section 16.1 that cannot be checked by reading our
own code, because the thing it asserts is what somebody else's tool thinks. So
it runs `rocrate-validator`, a third party program that knows nothing about
this service.

It skips when that program is not installed, which keeps the suite runnable on
a bare machine. In the container it is installed, so there it always runs. The
first time it was run by hand it found a real fault: the service entity had no
`url`, which RO-Crate 1.3 requires of any SoftwareApplication.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

VALIDATOR = shutil.which("rocrate-validator")

needs_validator = pytest.mark.skipif(
    VALIDATOR is None,
    reason="rocrate-validator is not installed on this machine",
)


def validate(folder) -> list[dict]:
    """Run the validator over a folder and return the issues it reports."""
    report = folder / "validation.json"
    subprocess.run(
        [
            VALIDATOR, "validate",
            "--metadata-only",
            "--output-format", "json",
            "--output-file", str(report),
            str(folder),
        ],
        capture_output=True,
        check=False,
    )
    if not report.exists():
        pytest.fail("the validator produced no report")
    parsed = json.loads(report.read_text())
    report.unlink()
    return parsed.get("issues", [])


@needs_validator
def test_the_crate_we_were_given_is_valid(published, tmp_path):
    """If this ever fails, the fault is in the example crate and not in us.

    It is here so that a failure of the test below can be read correctly.
    """
    published.save(tmp_path)
    assert validate(tmp_path) == []


@needs_validator
def test_the_crate_we_return_is_still_valid(published, sentinel, tmp_path):
    run = sentinel.check(published)
    run.crate.save(tmp_path)
    issues = validate(tmp_path)
    assert issues == [], "writing the record broke the crate: " + "; ".join(
        i.get("message", "") for i in issues
    )


@needs_validator
def test_two_records_in_one_crate_are_still_valid(published, sentinel, tmp_path):
    """A crate is checked at more than one handover over its life, so the
    second record must not break what the first one wrote."""
    once = sentinel.check(published)
    twice = sentinel.check(once.crate)
    twice.crate.save(tmp_path)
    assert validate(tmp_path) == []


def test_service_entity_has_a_url(published, writer):
    """The cheap version of the above, which runs with nothing installed.

    RO-Crate 1.3 requires a SoftwareApplication to have a `url`. Leaving it out
    is what the validator caught on 10 November 2026.
    """
    from sentinel_oo.provenance import SERVICE_ID

    from test_provenance import a_blessing

    after = writer.write(published, a_blessing())
    assert after.get(SERVICE_ID)["url"].startswith("http")
