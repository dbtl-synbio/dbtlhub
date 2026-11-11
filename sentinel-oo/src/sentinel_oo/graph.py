"""The graph of one checked crate: boxes and the lines between them.

A crate is a set of things that point at each other. A plate well points at
the construct that goes in it; that construct points at the protein it was
designed from; a step points at the files it read and the files it produced.
Draw each thing as a box and each pointer as a line and you have a picture
of the whole handover, with the check that was run on it included.

This module does the rearranging. **It works nothing out.** Everything here
is already written inside the crate, which is why no store of graphs is
needed: the durable record is the crate, and the crate travels to whoever
asked for it.

Two callers, deliberately:

  * `GET /graph/{run}` on the running service, for an agent or a notebook
    that wants the picture without unpacking anything.
  * Anybody holding a checked crate, by importing this and calling
    `of(crate)`. That still works when the service that made it has gone,
    which is the whole point of putting the record in the crate.

Written 11 November 2026. The address `GET /graph/{run}` had existed since
the interface was designed and had always answered "not built yet", because
the original plan put the graph in a store that was never written. The store
is not needed.
"""

from __future__ import annotations

from .crate import as_plain

# What a box is for, as far as a picture is concerned. The service writes
# its record at known identifiers, so these are read off the identifier
# rather than guessed from the content.
RUN_PREFIX = "#sentinel-oo/run/"
SERVICE_ID = "#sentinel-oo"

# Properties that are about the packaging rather than the content. They are
# still returned, marked, so a drawing can leave them out: `hasPart` from
# the root to every file in the crate turns any picture into a star with
# the root in the middle and nothing else visible.
PACKAGING = frozenset({"hasPart", "mentions", "about", "conformsTo"})


def _one_type(entity) -> str:
    """The entity's type, as one string a picture can colour by.

    `additionalType` wins where it exists. RO-Crate has no term for a plate
    well or an expression construct, so a crate types those entities as
    something general and says what they really are in `additionalType`. A
    picture that showed `CreativeWork` four times would be telling the
    reader nothing.
    """
    extra = entity.get("additionalType")
    if isinstance(extra, str) and extra:
        return extra
    kind = entity.get("@type")
    if isinstance(kind, (list, tuple)):
        return "/".join(str(k) for k in kind) if kind else "Thing"
    return str(kind) if kind else "Thing"


def _name(entity) -> str:
    for key in ("name", "identifier", "@id"):
        value = entity.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return str(entity.get("@id", ""))


def _role(identifier: str, entity, run: str | None) -> str:
    """What this box is, in the story the picture tells.

    A drawing uses this to make the few things that matter stand out: the
    check itself, what it found, and anything a model recovered. Everything
    else is the handover.
    """
    if identifier == SERVICE_ID:
        return "the service"
    if identifier.startswith(f"{SERVICE_ID}/ran-by/"):
        return "who asked"

    if identifier.startswith(RUN_PREFIX):
        rest = identifier[len(RUN_PREFIX):]
        this_run, _, tail = rest.partition("/")
        if run is not None and this_run != run:
            # Another run's record, left in the crate by an earlier check.
            # A crate checked twice carries both, and saying which is which
            # is more useful than hiding one.
            return "an earlier check"
        if not tail:
            return "the check"
        if tail.startswith("about/"):
            return "what was checked"
        if tail == "found/verdict":
            return "the verdict"
        if tail.startswith("found/"):
            return "a finding"
        if tail.startswith("changed/"):
            return "a change made"
        return "part of the check"

    if "/recovered/" in identifier:
        return "a value a model recovered"
    if str(entity.get("@type")) == "PropertyValue":
        return "a recorded value"
    if "File" in str(entity.get("@type")):
        return "a file"
    return "the handover"


def _references(entity):
    """Every pointer this entity makes, as (property, target identifier).

    A pointer is `{"@id": "..."}`, on its own or in a list. Anything else is
    a value rather than a pointer, and belongs in a box rather than on a
    line.
    """
    for key, value in entity.items():
        if key in ("@id", "@type", "@context"):
            continue
        for item in (value if isinstance(value, (list, tuple)) else [value]):
            plain = as_plain(item)
            if isinstance(plain, dict) and isinstance(plain.get("@id"), str):
                yield key, plain["@id"]


def of(crate, run: str | None = None) -> dict:
    """The crate as boxes and lines.

    `run` is the identifier of one check, used only to tell this check's own
    record apart from an earlier one's in a crate that has been checked more
    than once. Leave it out and every check in the crate is shown.
    """
    nodes = []
    seen = set()
    for entity in crate:
        identifier = str(entity.get("@id", ""))
        if not identifier:
            continue
        seen.add(identifier)
        node = {
            "id": identifier,
            "type": _one_type(entity),
            "name": _name(entity),
            "role": _role(identifier, entity, run),
        }
        value = entity.get("value")
        if isinstance(value, str):
            # Short enough to put in a tooltip rather than make the reader
            # fetch the entity.
            node["value"] = value if len(value) <= 300 else value[:300] + " ..."
        nodes.append(node)

    edges = []
    missing = {}
    for entity in crate:
        source = str(entity.get("@id", ""))
        if not source:
            continue
        for prop, target in _references(entity):
            if target not in seen and target not in missing:
                # A pointer at something this crate does not describe. Shown
                # rather than dropped, because one of the example crates is
                # broken by exactly that and a picture that hid it would hide
                # the fault.
                #
                # Two different things, though, and calling both missing
                # would be wrong. A web address names something that lives
                # elsewhere on purpose: the standard a crate follows, the
                # licence it carries, a file kept in a repository. A plain
                # name like `sequencing-report.pdf` is a claim that the thing
                # is in this crate, and if nothing describes it the claim is
                # false.
                elsewhere = target.startswith(("http://", "https://"))
                missing[target] = {
                    "id": target,
                    "type": ("named by web address, not described here"
                             if elsewhere else "not described in this crate"),
                    "name": target,
                    "role": "elsewhere" if elsewhere else "missing",
                }
            edges.append({
                "from": source,
                "to": target,
                "property": prop,
                "packaging": prop in PACKAGING,
            })

    nodes.extend(missing.values())

    verdict = None
    for entity in crate:
        if str(entity.get("@id", "")).endswith("/found/verdict"):
            if run is None or f"{RUN_PREFIX}{run}/" in str(entity.get("@id")):
                verdict = entity.get("value")

    roles = {}
    for node in nodes:
        roles[node["role"]] = roles.get(node["role"], 0) + 1

    return {
        "run": run,
        "verdict": verdict,
        "nodes": nodes,
        "edges": edges,
        "counts": {
            "nodes": len(nodes),
            "edges": len(edges),
            "missing": sum(1 for m in missing.values()
                           if m["role"] == "missing"),
            "elsewhere": sum(1 for m in missing.values()
                             if m["role"] == "elsewhere"),
            "by_role": roles,
        },
        "how_to_read_it": (
            "Each node is a thing the crate describes; each edge is a "
            "pointer from one to another, named by the property that "
            "carries it. Edges marked packaging join the crate to its own "
            "parts and can be left out of a drawing without losing the "
            "story. A node whose role is missing is pointed at by a plain "
            "name and described nowhere, which is a fault in the crate "
            "rather than in the picture. A node whose role is elsewhere is "
            "named by a web address, which says it lives somewhere else on "
            "purpose, such as the standard the crate follows or its licence."
        ),
    }
