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
import io
import json
import shutil
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

    __slots__ = ("_entities", "_context", "_by_id", "_checksum", "_root_id", "_folder")

    def __init__(self, context: Any, entities: list[dict],
                 folder: "Path | None" = None):
        # Where the data files are, when they are anywhere.
        #
        # None is the honest answer for a crate that arrived as bytes, which
        # is every crate posted to the web interface: the description came
        # and the data did not. A check on the data must be able to tell
        # that from a crate whose files are all present, rather than
        # passing because it looked at nothing.
        self._folder = Path(folder) if folder is not None else None

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

    @property
    def folder(self) -> "Path | None":
        """Where the data files are, or None if the data never arrived."""
        return self._folder

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
        return Crate(_thaw(self._context), kept + list(incoming.values()),
                     folder=self._folder)

    # ------------------------------------------------------------ in and out

    @classmethod
    def from_bytes(cls, data: bytes, folder: "Path | None" = None) -> "Crate":
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
        return cls(parsed.get("@context"), graph, folder=folder)

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
        # The folder holding the metadata file is where its data files are.
        return cls.from_bytes(data, folder=path.parent)

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


def describe(crate) -> str:
    """What is in a crate, as the list somebody needs to write a contract.

    A requirement names an entity type and a value, and both names have to
    match what is actually in the crate. Until 11 November 2026 there was no
    way to find out what those were: the service could check a crate, list
    its contracts and print a contract in plain words, and could not say
    what a crate contains. The only options were to read the raw JSON of a
    file with a hundred or more entities, or write a throwaway script.

    Found twice. Once by walking through what a new user does, where it is
    the second thing they do. Once by a deployment trial, where the
    tutorial's first step reads as though it provides this and does not.

    It also catches the commonest mistake before it is made. Types are
    compared as plain text, so a crate saying `CoatingRecipe` against a
    contract saying `Recipe` means every requirement matches nothing and
    passes in silence.
    """
    from collections import Counter

    from .rules import named_values_of, types_of, values_of

    kinds = Counter()
    values_by_kind: dict[str, Counter] = {}

    for entity in crate:
        for kind in types_of(entity):
            kinds[kind] += 1
            seen = values_by_kind.setdefault(kind, Counter())
            # Every PropertyValue this entity points at, which is how a
            # crate following Process Run Crate records most numbers and
            # strings.
            for key in entity:
                if key.startswith("@"):
                    continue
                for reference in values_of(entity, key):
                    target = crate.get(reference)
                    if target is None:
                        continue
                    if "PropertyValue" not in types_of(target):
                        continue
                    name = str(target.get("name", "")).strip()
                    if name:
                        seen[name] += 1

    lines = [
        f"{len(list(crate))} entities.",
        "",
        "Entity types, as a contract must spell them in `applies_to`:",
        "",
    ]
    for kind, count in sorted(kinds.items(), key=lambda p: (-p[1], p[0])):
        lines.append(f"  {kind:34} {count:4}")
        for name, seen in sorted(values_by_kind.get(kind, {}).items()):
            lines.append(f"      named value: {name!r} on {seen} of them")

    lines += [
        "",
        "A requirement names one of those types and either a property "
        "written on it",
        "or one of its named values. The names must match exactly: they are "
        "compared",
        "as plain text, so a contract saying `Recipe` against a crate saying",
        "`CoatingRecipe` matches nothing and passes in silence.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- zipped

# A handover is the data, not a description of it. The next process in the
# workflow needs the files, so a crate has to be able to arrive and leave
# whole, over the one interface a pipeline uses.
#
# Until 11 November 2026 `POST /check` took the description and returned the
# description, and whoever sent it had to put the data and the record back
# together by hand. It also meant no contract could check the data over the
# web, because the data was never there.

MAX_ZIP_BYTES = 512 * 1024 * 1024
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024


def unpack(data: bytes, into: "Path") -> "Crate":
    """Read a zipped crate into a folder and return it, data and all.

    Refuses a zip that would write outside the folder it was given. An
    archive can name an entry `../../somewhere/else`, and a service that
    unpacks whatever it is sent is a service that writes wherever it is
    told. This is the one place that matters, because the bytes come from
    whoever sent the handover.
    """
    import zipfile

    if len(data) > MAX_ZIP_BYTES:
        raise CrateMalformed(
            f"the zip is {len(data) // (1024 * 1024)} MB, over the "
            f"{MAX_ZIP_BYTES // (1024 * 1024)} MB limit"
        )

    into = Path(into)
    into.mkdir(parents=True, exist_ok=True)
    root = into.resolve()

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise CrateMalformed(f"not a readable zip: {exc}") from exc

    total = 0
    with archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            total += member.file_size
            if total > MAX_UNPACKED_BYTES:
                raise CrateMalformed(
                    "the zip unpacks to more than "
                    f"{MAX_UNPACKED_BYTES // (1024 * 1024 * 1024)} GB"
                )
            target = (root / member.filename).resolve()
            if root not in target.parents and target != root:
                raise CrateMalformed(
                    f"the zip contains {member.filename!r}, which would be "
                    "written outside the folder it was unpacked into"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(target, "wb") as sink:
                shutil.copyfileobj(source, sink)

    # The metadata file may be at the top, or inside one folder, which is how
    # most tools zip a directory.
    here = root / METADATA_FILE
    if not here.is_file():
        found = sorted(root.glob(f"*/{METADATA_FILE}"))
        if not found:
            raise CrateMalformed(
                f"the zip holds no {METADATA_FILE}, so it is not a crate"
            )
        here = found[0]
    return Crate.from_path(here)


def pack(crate: "Crate") -> bytes:
    """The whole crate as a zip: the record and every data file beside it.

    This is what the next process in the workflow receives, so it must be
    complete. A reply holding only the description would leave somebody to
    reunite it with the data by hand, which is the thing this exists to
    stop.
    """
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(METADATA_FILE, crate.to_json())
        if crate.folder is not None:
            for path in sorted(Path(crate.folder).rglob("*")):
                if not path.is_file():
                    continue
                name = path.relative_to(crate.folder).as_posix()
                if name == METADATA_FILE:
                    # The one written above, which carries the record. The
                    # one on disk does not.
                    continue
                archive.write(path, name)
    return buffer.getvalue()
