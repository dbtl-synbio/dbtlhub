"""The crate.

An RO-Crate, held immutably. This is the authority for content: the graph the
service builds later is derived from it, always, and is never the source.

Immutable means every method that changes anything returns a new `Crate` and
leaves the original exactly as it was. That is what lets the service show what
it was sent at the end of a run, and what keeps the recorded checksum of the
input correct without anybody having to remember it separately.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator

METADATA_FILE = "ro-crate-metadata.json"


class CrateMalformed(Exception):
    """The bytes are not a well-formed RO-Crate.

    Raised rather than letting a JSON library exception escape, so a caller
    can tell "this is not a crate" from "something broke inside".
    """


def _canonical(context: Any, entities: list[dict]) -> bytes:
    """One byte string for a crate's content, independent of how it was laid out.

    Entities are sorted by identifier and keys are sorted within each entity,
    so reformatting a file or reordering its graph does not change the
    checksum. Changing any value does.
    """
    ordered = sorted(entities, key=lambda e: str(e.get("@id", "")))
    return json.dumps(
        {"@context": context, "@graph": ordered},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _freeze(value: Any) -> Any:
    """Return a read-only view of nested dictionaries and lists.

    Without this, `crate.get("#x")["name"] = "other"` would quietly edit the
    crate through the returned reference, and the immutability the rest of the
    design rests on would be a claim rather than a fact.
    """
    if isinstance(value, dict):
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def as_plain(value: Any) -> Any:
    """A frozen entity turned back into ordinary dictionaries and lists.

    Needed by anything that writes an entity back out, because the frozen
    form cannot be serialised. Public because the model adapter has to show
    an entity to a model and discovered this the hard way.
    """
    return _thaw(value)


def _thaw(value: Any) -> Any:
    """The inverse of `_freeze`, for writing back out to JSON."""
    if isinstance(value, (dict, MappingProxyType)):
        return {k: _thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(v) for v in value]
    return value


class Crate:
    """An RO-Crate. Immutable."""

    __slots__ = ("_entities", "_context", "_by_id", "_checksum", "_root_id")

    def __init__(self, context: Any, entities: list[dict]):
        seen: set[str] = set()
        for entity in entities:
            # A string in the graph passes an `"@id" in entity` test whenever it
            # happens to contain those three characters, and then indexing it
            # raises a TypeError out of this class. Nothing but CrateMalformed
            # may leave here, so the type is checked first.
            if not isinstance(entity, dict):
                raise CrateMalformed(
                    f"@graph contains a {type(entity).__name__}, not an entity"
                )
            if "@id" not in entity:
                raise CrateMalformed("an entity has no @id")
            identifier = entity["@id"]
            if not isinstance(identifier, str):
                raise CrateMalformed(
                    f"an entity has a non-text @id: {identifier!r}"
                )
            if identifier in seen:
                raise CrateMalformed(
                    f"two entities share the identifier {identifier!r}. "
                    "A last-one-wins merge would silently drop one of them."
                )
            seen.add(identifier)

        descriptor = next(
            (e for e in entities if e.get("@id") == METADATA_FILE), None
        )
        if descriptor is None:
            raise CrateMalformed(
                f"no {METADATA_FILE} descriptor entity. This is valid JSON but "
                "it is not an RO-Crate."
            )
        if "about" not in descriptor:
            raise CrateMalformed(
                f"the {METADATA_FILE} descriptor does not say what it is about, "
                "so the root of the crate cannot be found."
            )

        # Resolved now rather than when something first asks for it. A crate
        # whose descriptor points at a root that is not there is structurally
        # broken, and nothing below a structural failure can be trusted, so it
        # must fail at the point of reading rather than inside whatever
        # happens to touch it first.
        about = descriptor["about"]
        if isinstance(about, list):
            about = about[0] if about else None
        target = about.get("@id") if isinstance(about, dict) else about
        if not isinstance(target, str) or not any(
            e.get("@id") == target for e in entities
        ):
            raise CrateMalformed(
                f"the descriptor is about {target!r}, which is not in the crate"
            )
        self._root_id = target

        self._context = _freeze(context)
        self._entities = tuple(_freeze(e) for e in entities)
        self._by_id = MappingProxyType({e["@id"]: e for e in self._entities})
        self._checksum = "sha256:" + hashlib.sha256(
            _canonical(_thaw(self._context), [_thaw(e) for e in self._entities])
        ).hexdigest()

    # ---------------------------------------------------------------- reading

    @property
    def context(self) -> Any:
        return self._context

    @property
    def entities(self) -> tuple:
        """Read-only. Appending to this does not change the crate."""
        return self._entities

    def __len__(self) -> int:
        return len(self._entities)

    def __iter__(self) -> Iterator:
        return iter(self._entities)

    def checksum(self) -> str:
        return self._checksum

    def get(self, identifier: str):
        """The entity with this identifier, or None.

        An identifier written with a leading hash and the same identifier
        written without one refer to the same entity in practice, so both are
        tried before giving up.
        """
        if identifier in self._by_id:
            return self._by_id[identifier]
        if identifier.startswith("#"):
            return self._by_id.get(identifier[1:])
        return self._by_id.get("#" + identifier)

    @property
    def descriptor(self):
        return self._by_id[METADATA_FILE]

    @property
    def root(self):
        """The root data entity, which the descriptor points at.

        Resolved when the crate was read, so this cannot fail here.
        """
        return self._by_id[self._root_id]

    # ---------------------------------------------------------------- writing

    def with_entity(self, entity: dict) -> "Crate":
        """A new crate with this entity added, or replacing one of the same id."""
        return self.with_entities([entity])

    def with_entities(self, entities: list[dict]) -> "Crate":
        """A new crate with several entities added or replaced, in one step.

        Later entries win over earlier ones with the same identifier, which is
        how a second run replaces the service entity the first one wrote.
        """
        for entity in entities:
            if not isinstance(entity, dict) or "@id" not in entity:
                raise CrateMalformed(
                    "an entity being added has no @id, so nothing could refer "
                    f"to it: {entity!r}"
                )
        incoming = {e["@id"]: dict(e) for e in entities}
        kept = [_thaw(e) for e in self._entities if e["@id"] not in incoming]
        return Crate(_thaw(self._context), kept + list(incoming.values()))

    # ------------------------------------------------------------ in and out

    @classmethod
    def from_bytes(cls, data: bytes) -> "Crate":
        try:
            parsed = json.loads(data)
        except (ValueError, UnicodeDecodeError) as exc:
            raise CrateMalformed(f"not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise CrateMalformed("the top level of a crate must be an object")
        if "@graph" not in parsed:
            raise CrateMalformed("no @graph. This is JSON but not an RO-Crate.")
        graph = parsed["@graph"]
        if not isinstance(graph, list):
            raise CrateMalformed("@graph must be a list of entities")
        return cls(parsed.get("@context"), graph)

    @classmethod
    def from_path(cls, path: str | Path) -> "Crate":
        """Read a crate from its metadata file, or from the folder holding it."""
        path = Path(path)
        if path.is_dir():
            path = path / METADATA_FILE
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise CrateMalformed(f"cannot read {path}: {exc}") from exc
        return cls.from_bytes(data)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            {
                "@context": _thaw(self._context),
                "@graph": [_thaw(e) for e in self._entities],
            },
            indent=indent,
            ensure_ascii=False,
        ) + "\n"

    def save(self, path: str | Path) -> Path:
        """Write the crate out, to a file or into a folder.

        A path that is an existing folder, or that does not end in .json, is
        treated as a folder and the metadata file is written inside it. Testing
        only whether the folder already exists is not enough: a folder that has
        yet to be created would then be written as a file with no extension.
        """
        path = Path(path)
        if path.is_dir() or path.suffix.lower() != ".json":
            path = path / METADATA_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    def __repr__(self) -> str:
        return f"<Crate {len(self._entities)} entities {self._checksum[:14]}...>"
