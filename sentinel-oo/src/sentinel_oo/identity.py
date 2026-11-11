"""What built this service, and what it is carrying.

Three things that are tied together: the image tag, the commit it was built
from, and a checksum over the contracts and vocabulary inside it. Any one of
the three should recover the other two, which is what makes a run reproducible
a year later.

All three come from the environment rather than being read at run time, because
they are properties of the image and an image does not change once built.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

NOT_SET = "unset"


@dataclass(frozen=True)
class BuildIdentity:
    image_tag: str = NOT_SET
    git_commit: str = NOT_SET
    rules_checksum: str = NOT_SET

    @classmethod
    def from_env(cls, env: dict | None = None) -> "BuildIdentity":
        env = os.environ if env is None else env
        return cls(
            image_tag=env.get("SENTINEL_IMAGE_TAG", NOT_SET),
            git_commit=env.get("SENTINEL_GIT_COMMIT", NOT_SET),
            rules_checksum=env.get("SENTINEL_RULES_CHECKSUM", NOT_SET),
        )

    def describe(self) -> str:
        return (
            f"image {self.image_tag}, commit {self.git_commit}, "
            f"rules {self.rules_checksum}"
        )
