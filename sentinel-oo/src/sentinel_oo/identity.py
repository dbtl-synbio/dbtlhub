"""What built this service, and what it is carrying.

Three things that are tied together: the image tag, the commit it was built
from, and a checksum over the code that decides verdicts. Any one of the three
should recover the other two, which is what makes a run reproducible a year
later.

When the service runs from a built image, all three are stamped into the image
at build time and read from the environment, because they are properties of
the image and an image does not change once built.

**When it runs from source, they are worked out here instead.** Until
11 November 2026 all three read `unset` in that case, which went into the
lasting record inside every checked crate. A reader a year later could not
tell `unset` apart from a fault, and a crate checked that way did not say
which code had checked it. Found by the session testing the model on a rented
machine with graphics hardware, which ran the service from source.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

NOT_SET = "unset"

# What the image tag says when there is no image. Spelled as a sentence
# because it is read by people, in a record, long after the run.
FROM_SOURCE = "none: run from source, not from a built image"

HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class BuildIdentity:
    image_tag: str = NOT_SET
    git_commit: str = NOT_SET
    rules_checksum: str = NOT_SET

    @classmethod
    def from_env(cls, env: dict | None = None) -> "BuildIdentity":
        env = os.environ if env is None else env
        image_tag = env.get("SENTINEL_IMAGE_TAG") or ""
        git_commit = env.get("SENTINEL_GIT_COMMIT") or ""
        rules_checksum = env.get("SENTINEL_RULES_CHECKSUM") or ""

        if image_tag and git_commit and rules_checksum:
            return cls(image_tag, git_commit, rules_checksum)

        # Running from source, or from an image built without the stamps.
        # Whatever is missing is worked out from the source itself, so the
        # record never says `unset`.
        return cls(
            image_tag=image_tag or FROM_SOURCE,
            git_commit=git_commit or commit_of_the_source(),
            rules_checksum=rules_checksum or checksum_of_the_code(),
        )

    def describe(self) -> str:
        return (
            f"image {self.image_tag}, commit {self.git_commit}, "
            f"rules {self.rules_checksum}"
        )


@lru_cache(maxsize=1)
def commit_of_the_source() -> str:
    """Which commit this source is at, and whether it has been edited since.

    A crate checked by edited code must say so. "4d2a1c9 with uncommitted
    changes" is a different statement from "4d2a1c9", and the second one
    would be a claim nobody could check.
    """
    try:
        at = subprocess.run(
            ["git", "-C", str(HERE), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if at.returncode != 0:
            return "not known: this source is not in a git repository"
        commit = at.stdout.strip()

        changed = subprocess.run(
            ["git", "-C", str(HERE), "status", "--porcelain", "--", str(HERE)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if changed.returncode == 0 and changed.stdout.strip():
            return f"{commit} with uncommitted changes"
        return commit
    except (OSError, subprocess.SubprocessError):
        # No git on this machine, which is normal inside a container. The
        # record says that rather than nothing.
        return "not known: git could not be run here"


@lru_cache(maxsize=1)
def checksum_of_the_code() -> str:
    """A checksum over the service's own source files.

    Not a substitute for a commit. Two machines at the same commit with the
    same edits produce the same checksum, which is what makes it worth
    recording: it says what the code was, where a commit says only where it
    came from.
    """
    digest = hashlib.sha256()
    for path in sorted(HERE.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return f"sha256:{digest.hexdigest()[:16]} over the service's source files"
