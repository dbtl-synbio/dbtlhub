"""What the record says about the code that checked a crate.

Three facts go into every checked crate: which image the service was, which
commit it was built from, and a checksum over the code that decides
verdicts. They are stamped into the image at build time.

Running from source, all three used to read `unset`. That went into the
lasting record, where a reader a year later cannot tell `unset` apart from
something broken, and where the crate therefore does not say which code
checked it. Found on 11 November 2026 by the session testing the model on a
rented machine with graphics hardware, which ran the service from source.
"""

import subprocess

import pytest

from sentinel_oo import identity
from sentinel_oo.identity import BuildIdentity


@pytest.fixture(autouse=True)
def no_remembered_answers():
    """Both lookups remember their answer, so each test starts clean."""
    identity.commit_of_the_source.cache_clear()
    identity.checksum_of_the_code.cache_clear()
    yield
    identity.commit_of_the_source.cache_clear()
    identity.checksum_of_the_code.cache_clear()


# ------------------------------------------------- running from a built image


def test_a_built_image_uses_what_was_stamped_into_it():
    """An image does not change once built, so these are read rather than
    worked out."""
    built = BuildIdentity.from_env({
        "SENTINEL_IMAGE_TAG": "sentinel-oo:0.9.2",
        "SENTINEL_GIT_COMMIT": "4d2a1c9",
        "SENTINEL_RULES_CHECKSUM": "sha256:abc123",
    })
    assert built.image_tag == "sentinel-oo:0.9.2"
    assert built.git_commit == "4d2a1c9"
    assert built.rules_checksum == "sha256:abc123"


# ------------------------------------------------------- running from source


def test_nothing_in_the_record_says_unset():
    """The fault itself. Every one of the three said `unset`."""
    said = BuildIdentity.from_env({})
    assert identity.NOT_SET not in said.describe()


def test_it_says_plainly_that_there_is_no_image():
    said = BuildIdentity.from_env({})
    assert "run from source" in said.image_tag


def test_it_records_which_commit_the_source_is_at(monkeypatch):
    def git(command, **kwargs):
        wanted = "rev-parse" in command
        return subprocess.CompletedProcess(
            command, 0, stdout="4d2a1c9\n" if wanted else "", stderr=""
        )

    monkeypatch.setattr(identity.subprocess, "run", git)
    assert BuildIdentity.from_env({}).git_commit == "4d2a1c9"


def test_edited_code_says_so(monkeypatch):
    """A crate checked by edited code must say so. "4d2a1c9" on its own
    would be a claim nobody could check, because the files at that commit
    are not the files that ran."""
    def git(command, **kwargs):
        if "rev-parse" in command:
            return subprocess.CompletedProcess(command, 0, "4d2a1c9\n", "")
        return subprocess.CompletedProcess(
            command, 0, " M src/sentinel_oo/rules.py\n", ""
        )

    monkeypatch.setattr(identity.subprocess, "run", git)
    assert BuildIdentity.from_env({}).git_commit == (
        "4d2a1c9 with uncommitted changes"
    )


def test_no_git_repository_is_said_rather_than_left_blank(monkeypatch):
    monkeypatch.setattr(
        identity.subprocess, "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 128, "", "fatal: not a git repository"
        ),
    )
    assert "not in a git repository" in BuildIdentity.from_env({}).git_commit


def test_no_git_program_at_all_is_said_rather_than_left_blank(monkeypatch):
    """Normal inside a container, where the stamps are set anyway. The point
    is that the record says which of the two happened."""
    def missing(command, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(identity.subprocess, "run", missing)
    assert "git could not be run" in BuildIdentity.from_env({}).git_commit


def test_the_checksum_is_over_the_service_source_and_is_stable():
    once = identity.checksum_of_the_code()
    identity.checksum_of_the_code.cache_clear()
    again = identity.checksum_of_the_code()
    assert once == again
    assert once.startswith("sha256:")
    assert "source files" in once


def test_a_half_stamped_image_fills_in_the_rest(monkeypatch):
    """An image built without all three stamps is not trusted for the ones
    it does not carry."""
    def git(command, **kwargs):
        wanted = "rev-parse" in command
        return subprocess.CompletedProcess(
            command, 0, "4d2a1c9\n" if wanted else "", ""
        )

    monkeypatch.setattr(identity.subprocess, "run", git)
    said = BuildIdentity.from_env({"SENTINEL_IMAGE_TAG": "sentinel-oo:0.9.2"})
    assert said.image_tag == "sentinel-oo:0.9.2"
    assert said.git_commit == "4d2a1c9"
    assert said.rules_checksum.startswith("sha256:")


# -------------------------------------------- and it reaches the crate itself


def test_the_checked_crate_carries_which_code_checked_it(sentinel, minimal):
    """The crate is the lasting record. If this is not in there, nothing
    said above matters."""
    run = sentinel.check(minimal)
    text = run.crate.to_json()
    assert identity.NOT_SET not in run.blessing.build.describe()
    assert run.blessing.build.rules_checksum[:20] in text
