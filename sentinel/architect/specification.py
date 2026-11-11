"""Ingredient 2 of the Architect: what was agreed, and what the process requires.

This implements the `Specification` protocol in `architect/contract.py`.

Two kinds of statement live in a specification and the whole module is built to
keep them apart:

    AGREED     what the researcher decided - the objective, the target, the
               equipment on hand, the budget, how big a library this round can
               be. Negotiable by definition: that is what a consultation is.

    REQUIRED   what the process requires of anybody - that a measurement
               carries its unit and its method, that an ordered sequence has a
               recorded origin, that a prediction states its uncertainty. The
               researcher did not decide these and cannot waive them.

They are two separate stores, not two flags on one store, and `agree()` refuses
a key that names a process requirement. That refusal is the point of the
module: if the two can be written through the same door, somebody eventually
negotiates a requirement away by accident - usually under deadline, usually by
agreeing something that sounds like a preference ("we'll record units later")
and is in fact the thing the handover is checked against.

The required side is never restated here. It is read out of the real files:

    framework/contracts/profiles/<profile>.json     what this use case requires
    framework/contracts/<handover>.schema.json      what every use case requires

So when a profile gains a required measurement, or a contract gains a check,
this module reports it without being edited. Restating them in Python would
produce a second source of truth that drifts, and a specification that is
confidently wrong about what the process requires is worse than none.

No network, no LLM, standard library only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, TYPE_CHECKING

try:  # imported as part of the package, from the repository root
    from architect.contract import HANDOVERS, PHASES
except ImportError:  # run as a script: python3 architect/specification.py
    from contract import HANDOVERS, PHASES

REPO = Path(__file__).resolve().parent.parent
CONTRACT_DIR = REPO / "framework" / "contracts"
PROFILE_DIR = CONTRACT_DIR / "profiles"


def _now() -> str:
    """An instant in the form every contract's `produced_at` pattern accepts."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
#  The refusal
# --------------------------------------------------------------------------- #
class RequirementNotNegotiable(ValueError):
    """Raised when something tries to set a process requirement as if agreed.

    The message says which requirement, where it comes from, and what the
    caller should do instead - a bare "invalid key" would send somebody looking
    for a typo when the real answer is "that is not yours to decide".
    """

    def __init__(self, key: str, canonical: str, source: str, why: str) -> None:
        super().__init__(
            f"'{key}' is a process requirement, not an agreement.\n"
            f"  it is {canonical}\n"
            f"  stated in: {source}\n"
            f"  why it is not negotiable: {why}\n"
            f"  a run may be refused for breaking it, and the researcher cannot "
            f"waive it by agreeing otherwise. If the requirement itself is "
            f"wrong, change the profile or the contract - that is a group "
            f"decision with a reviewer, not a line in one specification."
        )
        self.key = key
        self.canonical = canonical
        self.source = source
        self.why = why


# --------------------------------------------------------------------------- #
#  The two stores
# --------------------------------------------------------------------------- #
@dataclass
class AgreedValue:
    """One thing the researcher decided, with who decided it and when.

    Attribution is not bookkeeping. Six weeks later the only way to settle
    "who said 96 wells?" is to have written it down at the time, and a
    specification that cannot answer that cannot be defended.
    """
    key: str
    value: Any
    set_by: str
    at: str = field(default_factory=_now)
    note: str = ""

    def to_json(self) -> dict:
        return {"key": self.key, "value": self.value, "set_by": self.set_by,
                "at": self.at, "note": self.note}

    @classmethod
    def from_json(cls, raw: dict) -> "AgreedValue":
        return cls(key=raw["key"], value=raw.get("value"),
                   set_by=raw.get("set_by", "unattributed"),
                   at=raw.get("at", ""), note=raw.get("note", ""))


@dataclass
class Limit:
    """A limit this run has to respect, in the contracts' own `limits` shape.

    `as_envelope()` emits exactly the five fields the contracts define -
    quantity, value, unit, from, stated_by - and nothing else, because the
    handover packages are validated against that shape and an extra key is a
    validation failure rather than a helpful addition.

    `applies_to` is ours and stays here: it is how one specification says that
    a limit belongs to a particular phase. Empty means "wherever it is
    checked", which is the normal case.
    """
    quantity: str
    value: float
    unit: str
    from_crate: str
    stated_by: str = ""
    applies_to: tuple[str, ...] = ()

    def as_envelope(self) -> dict:
        envelope = {"quantity": self.quantity, "value": self.value,
                    "unit": self.unit, "from": self.from_crate}
        if self.stated_by:
            envelope["stated_by"] = self.stated_by
        return envelope

    def to_json(self) -> dict:
        return {**self.as_envelope(), "applies_to": list(self.applies_to)}

    @classmethod
    def from_json(cls, raw: dict) -> "Limit":
        return cls(quantity=raw["quantity"], value=raw["value"],
                   unit=raw.get("unit", "dimensionless"),
                   from_crate=raw.get("from", ""),
                   stated_by=raw.get("stated_by", ""),
                   applies_to=tuple(raw.get("applies_to", ())))


@dataclass
class Read:
    """A crate this specification was built from, in the `reads` shape.

    The contracts say limits are "lifted out of the crates named in reads", so
    a limit whose crate is not read here is a number with no origin - which
    `unresolved()` reports.
    """
    crate: str
    role: str = "constraints"  # constraints | context | upstream
    checksum: str = ""

    def as_envelope(self) -> dict:
        envelope = {"crate": self.crate, "role": self.role}
        if self.checksum:
            envelope["checksum"] = self.checksum
        return envelope

    @classmethod
    def from_json(cls, raw: dict) -> "Read":
        return cls(crate=raw["crate"], role=raw.get("role", "constraints"),
                   checksum=raw.get("checksum", ""))


@dataclass
class Requirement:
    """One thing the process requires, resolved from a file on disk.

    `source` is the file and the place in it. A requirement that cannot say
    where it comes from is indistinguishable from an opinion, and an opinion is
    exactly the thing that may be negotiated.
    """
    key: str
    statement: str
    why: str
    source: str
    handover: str = ""
    fix_hint: str = ""

    def to_json(self) -> dict:
        return {"key": self.key, "statement": self.statement, "why": self.why,
                "source": self.source, "handover": self.handover,
                "fix_hint": self.fix_hint}


# --------------------------------------------------------------------------- #
#  Reading the real files
# --------------------------------------------------------------------------- #
_file_cache: dict[Path, dict] = {}


def _load(path: Path) -> dict:
    """Read a JSON file once per process. The file is the source of truth; the
    cache only avoids re-reading it inside one run."""
    if path not in _file_cache:
        if not path.exists():
            raise FileNotFoundError(f"missing: {path}")
        _file_cache[path] = json.loads(path.read_text())
    return _file_cache[path]


def load_profile(name: str) -> dict:
    return _load(PROFILE_DIR / f"{name}.json")


def load_contract(handover: str) -> dict:
    return _load(CONTRACT_DIR / f"{handover}.schema.json")


def available_profiles() -> list[str]:
    return sorted(p.stem for p in PROFILE_DIR.glob("*.json"))


def _measurement_shape(node: Any, found: list[list[str]]) -> None:
    """Collect the required-field lists of every measurement object in a schema.

    A measurement is recognised by its own shape - an object that requires
    quantity, value and method - rather than by where it sits, so this keeps
    working when a contract moves or adds one. This is how "a measurement
    carries its unit" and "a prediction states its uncertainty" are read out of
    the contracts instead of being asserted here.

    `method` is part of the test and not decoration: the `limits` envelope also
    requires quantity and value, and a limit is not a measurement. Mistaking
    one for the other would report a limit's missing method as a defect.
    """
    if isinstance(node, dict):
        required = node.get("required")
        if (isinstance(required, list) and "quantity" in required
                and "value" in required and "method" in required):
            found.append([str(r) for r in required])
        for value in node.values():
            _measurement_shape(value, found)
    elif isinstance(node, list):
        for item in node:
            _measurement_shape(item, found)


def _checks(contract: dict) -> list[dict]:
    return [c for c in contract.get("x-dbtl-checks", []) if isinstance(c, dict)]


def _limited_quantities(handover: str) -> set[str]:
    """Quantities this handover is checked against a stated limit for.

    Read from the contract's own `within_limits` checks, so a new one is picked
    up without touching this file.
    """
    return {c["quantity"] for c in _checks(load_contract(handover))
            if c.get("kind") == "within_limits" and c.get("quantity")}


# --------------------------------------------------------------------------- #
#  What the researcher is expected to have decided
# --------------------------------------------------------------------------- #
# These are agreements, every one of them negotiable - the list says only that
# a run which has not answered them cannot finish, which is what unresolved()
# is for.
NEEDED_AGREEMENTS: tuple[tuple[str, str], ...] = (
    ("profile", "which use case this is; nothing can say what the process "
                "requires until this is answered"),
    ("objective", "what the run is for, in the researcher's words"),
    ("target", "what is being made or measured"),
    ("equipment", "the instruments actually on hand this round"),
    ("budget", "what this round may cost, so a panel can be sized"),
)

# Short names a researcher would plausibly type for a process requirement.
# They are here so the refusal is pointed ("that is the measurement shape")
# rather than a confusing miss on an exact key.
_ALIASES: dict[str, str] = {
    "measurement.unit": "unit",
    "measurement.units": "unit",
    "unit": "unit",
    "units": "unit",
    "measurement.method": "method",
    "method": "method",
    "sequence.origin": "origin",
    "provenance": "origin",
    "origin": "origin",
    "traceability": "origin",
    "prediction.uncertainty": "uncertainty",
    "uncertainty": "uncertainty",
    "error_bars": "uncertainty",
}

# Namespaces that belong to the required side. Anything under them is refused
# wholesale, so a requirement nobody listed by name is still protected.
_RESERVED_PREFIXES: tuple[str, ...] = (
    "requires.", "required.", "process.", "contract.", "measurement.",
    "provenance.", "prediction.", "sequence.",
) + tuple(f"{h}." for h in HANDOVERS.values())


class Specification:
    """What was agreed, plus what the process requires regardless.

    Implements the `Specification` protocol: `agreed`, `limits`,
    `requirements_for`, `limits_for`, `unresolved`.

    `agreed` and `limits` are read-only views on purpose. The protocol declares
    them as attributes, and a plain mutable dict would be a second way in that
    skips the refusal in `agree()` - so what comes back is a copy, and writing
    to it changes nothing.
    """

    def __init__(self, profile: str | None = None, *, run_id: str = "",
                 set_by: str = "researcher") -> None:
        self._agreed: dict[str, AgreedValue] = {}
        self._limits: list[Limit] = []
        self._reads: list[Read] = []
        self._imposed: dict[str, Requirement] = {}
        self.run_id = run_id
        if profile is not None:
            # The profile is itself a decision - which use case we are in - so
            # it belongs on the agreed side. What it then pulls in from disk
            # does not.
            self.agree("profile", profile, set_by=set_by,
                       note="selects which profile's requirements apply")

    # ---------------------------------------------------------------- views --
    @property
    def agreed(self) -> dict[str, Any]:
        return {k: v.value for k, v in self._agreed.items()}

    @property
    def attribution(self) -> dict[str, dict]:
        """The same agreements with who set them and when."""
        return {k: v.to_json() for k, v in self._agreed.items()}

    @property
    def limits(self) -> list[dict]:
        return [limit.as_envelope() for limit in self._limits]

    @property
    def reads(self) -> list[dict]:
        return [read.as_envelope() for read in self._reads]

    @property
    def profile_name(self) -> str | None:
        name = self._agreed.get("profile")
        return str(name.value) if name and name.value else None

    # ------------------------------------------------------- the agreed side --
    def agree(self, key: str, value: Any, *, set_by: str = "researcher",
              at: str = "", note: str = "") -> "Specification":
        """Record something the researcher decided.

        Refuses any key that names a process requirement. This is the one
        guard the module exists for: the agreed side is the only side with a
        setter, so the only way a requirement could be waived is through here,
        and here it is refused with the reason.
        """
        self._refuse_if_required(key)
        self._agreed[key] = AgreedValue(key=key, value=value, set_by=set_by,
                                        at=at or _now(), note=note)
        return self

    def state_limit(self, quantity: str, value: float, unit: str, *,
                    from_crate: str, stated_by: str = "",
                    applies_to: Iterable[str] = ()) -> "Specification":
        """Record a limit this run has to respect.

        A limit is not a requirement and not a preference: it is this round's
        equipment and this round's budget, which is why the contracts carry it
        in the package rather than in the profile. It changes between rounds and
        it is negotiable - raising it is a real option a phase can take.
        """
        # Kept as an int when it came in as one: 96 wells is a count, and
        # printing it as 96.0 invites somebody to read it as a measurement.
        number = (value if isinstance(value, int) and not isinstance(value, bool)
                  else float(value))
        self._limits.append(Limit(quantity=quantity, value=number,
                                  unit=unit or "dimensionless",
                                  from_crate=from_crate, stated_by=stated_by,
                                  applies_to=tuple(applies_to)))
        return self

    def declare_read(self, crate: str, *, role: str = "constraints",
                     checksum: str = "") -> "Specification":
        """Name a crate this specification was built from."""
        self._reads.append(Read(crate=crate, role=role, checksum=checksum))
        return self

    # ----------------------------------------------------- the required side --
    def impose(self, key: str, statement: str, *, why: str,
               source: str) -> "Specification":
        """Add a process requirement that is not in a file yet.

        Deliberately a different door from `agree()`, and deliberately
        demanding a `source`: a requirement with no stated origin is an opinion
        with a strong voice. Use it for a rule the group has settled but not
        yet written into a profile - then write it into the profile.
        """
        self._imposed[key] = Requirement(key=key, statement=statement, why=why,
                                         source=source)
        return self

    def _refuse_if_required(self, key: str) -> None:
        alias = _ALIASES.get(key.strip().lower())
        if alias:
            canonical, source, why = _ALIAS_DETAIL[alias]
            raise RequirementNotNegotiable(key, canonical, source, why)

        lowered = key.strip().lower()
        for prefix in _RESERVED_PREFIXES:
            if lowered.startswith(prefix):
                raise RequirementNotNegotiable(
                    key,
                    f"a name in the reserved '{prefix.rstrip('.')}' namespace",
                    "framework/contracts/*.schema.json and "
                    "framework/contracts/profiles/*.json",
                    "that namespace holds what the process requires of "
                    "anybody; it is read from the contracts and the profile, "
                    "and nothing agreed in one run may shadow it")

        if key in self._imposed:
            req = self._imposed[key]
            raise RequirementNotNegotiable(key, req.statement, req.source,
                                           req.why)

        # The last line of defence: the key is one the files themselves
        # declare, e.g. 'design_to_build.quantity.predicted_activity'. Keys are
        # resolved for the active profile only, because a requirement of a use
        # case we are not in is not this run's business.
        if self.profile_name:
            protected = self._requirement_keys()
            if key in protected:
                req = protected[key]
                raise RequirementNotNegotiable(key, req.statement, req.source,
                                               req.why)

    def _requirement_keys(self) -> dict[str, Requirement]:
        """Every requirement of the active profile, by key, read from disk."""
        out: dict[str, Requirement] = {}
        for phase in PHASES:
            for req in self.requirements_for(phase)["requirements"]:
                out[req["key"]] = Requirement(**req)
        out.update(self._imposed)
        return out

    # ------------------------------------------------------------ the protocol --
    def requirements_for(self, phase: str) -> dict:
        """What the process requires of whoever runs this phase.

        Assembled from the profile and from the handover contract, never from
        text in this file, so it cannot drift from what the sentinel will
        actually check.
        """
        if phase not in PHASES:
            raise ValueError(f"no such phase: {phase!r}; expected one of "
                             f"{', '.join(PHASES)}")
        profile_name = self.profile_name
        if not profile_name:
            # Honest emptiness. Without a profile there is no answer to give,
            # and inventing a generic one would be the drift this module is
            # built to avoid.
            return {"phase": phase, "handover": HANDOVERS[phase],
                    "profile": None, "requirements": [],
                    "unanswerable": "no profile agreed yet, so nothing can be "
                                    "said about what this phase requires"}

        handover = HANDOVERS[phase]
        profile = load_profile(profile_name)
        contract = load_contract(handover)
        prof_src = f"framework/contracts/profiles/{profile_name}.json"
        cont_src = f"framework/contracts/{handover}.schema.json"
        reqs: list[Requirement] = []

        # 1. The structure of the handover itself.
        for field_name in contract.get("required", []):
            reqs.append(Requirement(
                key=f"{handover}.required.{field_name}",
                statement=f"the {handover} package carries '{field_name}'",
                why=contract.get("properties", {}).get(field_name, {})
                    .get("description", "")
                    or "the contract lists it as required",
                source=f"{cont_src}#/required", handover=handover))

        # 2. The measurement shape, read out of the contract's own objects.
        #    This is where "a number on its own is not a measurement" lives,
        #    and where learn_to_design's demand for uncertainty appears without
        #    being special-cased.
        shapes: list[list[str]] = []
        _measurement_shape(contract, shapes)
        for shape in {tuple(sorted(s)) for s in shapes}:
            reqs.append(Requirement(
                key=f"{handover}.measurement.{'+'.join(shape)}",
                statement="every measurement carries " + ", ".join(shape),
                why="a bare number cannot be compared, converted or refitted; "
                    "quantity, value, unit and method travel together",
                source=f"{cont_src} (measurement object)", handover=handover))

        # 3. The checks a schema cannot express - uniqueness, cross-references,
        #    provenance chains, limits. Message and fix hint come from the
        #    contract verbatim so the Architect says what the sentinel says.
        for check in _checks(contract):
            reqs.append(Requirement(
                key=f"{handover}.check.{check.get('code', 'unnamed')}",
                statement=check.get("message", check.get("kind", "")),
                why=f"check kind '{check.get('kind')}' on "
                    f"{check.get('of', handover)}",
                source=f"{cont_src}#/x-dbtl-checks", handover=handover,
                fix_hint=check.get("fix_hint", "")))

        # 4. Quantities this use case is incomplete without.
        for want in (profile.get("required_quantities") or {}).get(handover, []):
            reqs.append(Requirement(
                key=f"{handover}.quantity.{want['quantity']}",
                statement=f"{want['quantity']} in {want.get('unit', '?')}",
                why=want.get("method_hint", "")
                    or "the profile declares this handover incomplete without it",
                source=f"{prof_src}#/required_quantities/{handover}",
                handover=handover))

        # 5. Provenance this use case is incomplete without.
        prov = (profile.get("required_provenance") or {}).get(handover) or {}
        for entity in prov.get("entities", []):
            kind = entity.get("type") or " or ".join(entity.get("one_of", []))
            props = list(entity.get("requires", []))
            # A profile may also demand a measurement on a provenance entity -
            # bioprospecting wants the storage temperature on a BioSample,
            # because -20 instead of -80 for a month decides whether the
            # material still exists. It is required like any other property.
            for want in entity.get("measurements", []):
                props.append(f"{want['quantity']} in {want.get('unit', '?')}")
            if props:
                reqs.append(Requirement(
                    key=f"{handover}.provenance.{kind}",
                    statement=f"a {kind} states " + ", ".join(props),
                    why=entity.get("why", ""),
                    source=f"{prof_src}#/required_provenance/{handover}",
                    handover=handover))
            else:
                reqs.append(Requirement(
                    key=f"{handover}.provenance.{kind}",
                    statement=f"the crate contains a {kind}",
                    why=entity.get("why", ""),
                    source=f"{prof_src}#/required_provenance/{handover}",
                    handover=handover))

        # 6. Values the crate may state honestly that the receiving phase has
        #    to act on - a flag, not a defect in the crate.
        for rule in (profile.get("accepted_values") or {}).get(handover, []):
            reqs.append(Requirement(
                key=f"{handover}.value.{rule['property']}",
                statement=f"{rule['property']} is one of "
                          f"{', '.join(rule.get('accept', []))} "
                          f"(severity: {rule.get('severity', 'error')})",
                why=rule.get("why", ""),
                source=f"{prof_src}#/accepted_values/{handover}",
                handover=handover))

        # 7. Requirements imposed in this run and not yet in a file.
        for req in self._imposed.values():
            reqs.append(req)

        return {
            "phase": phase,
            "handover": handover,
            "profile": profile_name,
            "contract": contract.get("$id", handover),
            "patterns": profile.get("patterns", {}),
            "limited_quantities": sorted(_limited_quantities(handover)),
            "requirements": [r.to_json() for r in reqs],
        }

    def limits_for(self, phase: str) -> list[dict]:
        """The limits this phase has to respect, in the contracts' own shape.

        Exactly the `limits` envelope: quantity, value, unit, from, stated_by.
        A limit scoped to particular phases is returned only for those. An
        unscoped limit is returned for the phase whose contract checks it, and
        for every phase if no contract checks it at all - a budget constrains
        everyone.
        """
        if phase not in PHASES:
            raise ValueError(f"no such phase: {phase!r}")
        here = _limited_quantities(HANDOVERS[phase])
        anywhere = set().union(*(_limited_quantities(h)
                                 for h in HANDOVERS.values()))
        out = []
        for limit in self._limits:
            if limit.applies_to:
                if phase in limit.applies_to:
                    out.append(limit.as_envelope())
            elif limit.quantity in here or limit.quantity not in anywhere:
                out.append(limit.as_envelope())
        return out

    def unresolved(self) -> list[str]:
        """What still has no answer.

        A run may start with items on this list - that is deliberate, because
        waiting for a complete specification is how nothing ever starts. It may
        not finish with them, and this is what gets read back at the researcher
        when a handover is refused for a gap that was known on day one.
        """
        gaps: list[str] = []

        for key, why in NEEDED_AGREEMENTS:
            held = self._agreed.get(key)
            if held is None or held.value in (None, "", [], {}):
                gaps.append(f"not agreed: {key} - {why}")

        if not self.profile_name:
            # Everything below reads the profile. Stop rather than guess.
            return gaps

        # A quantity some contract checks against a limit, with no limit
        # stated. The check cannot run, which means a panel too big for the
        # receiving phase passes.
        stated = {limit.quantity for limit in self._limits}
        for handover in HANDOVERS.values():
            for quantity in sorted(_limited_quantities(handover) - stated):
                gaps.append(
                    f"no limit stated for {quantity}, which the {handover} "
                    f"contract checks against one - so the check cannot run")

        # A limit has to come out of a crate that was read. One that does not
        # is a number with no origin, and nobody can go and look it up.
        read_names = {read.crate for read in self._reads}
        for limit in self._limits:
            if not limit.from_crate:
                gaps.append(f"limit {limit.quantity} does not say which crate "
                            f"it came out of")
            elif limit.from_crate not in read_names:
                gaps.append(
                    f"limit {limit.quantity} comes 'from' {limit.from_crate}, "
                    f"which is not in reads - the contracts require limits to "
                    f"be lifted out of a crate that was read")

        if not self._reads:
            gaps.append("no crate declared in reads - either an existing crate "
                        "is adopted, or the researcher seeds one; a first round "
                        "with neither has nothing to respect")

        # Open questions the profile itself records. A profile that says a
        # decision is the group's to make is telling us this specification is
        # not finished, and the Architect should not quietly pick a side.
        profile = load_profile(self.profile_name)
        for key, note in (profile.get("patterns") or {}).items():
            if key.startswith("_note"):
                gaps.append(f"open in profile {self.profile_name}: {note}")
        if profile.get("review"):
            gaps.append(f"open in profile {self.profile_name} (review): "
                        f"{profile['review']}")
        for entity in ((profile.get("required_provenance") or {})
                       .get("design_to_build") or {}).get("entities", []):
            if entity.get("one_of"):
                gaps.append(
                    f"dialect not settled: the crate may state origin as "
                    f"{' or '.join(entity['one_of'])}; which one this run "
                    f"uses is a group decision")

        return gaps

    # ------------------------------------------------------------- handover --
    def to_seed(self) -> dict:
        """The `reads` and `limits` blocks a Design handover would carry.

        This is how a specification is handed straight to a phase agent: the
        agent does not need the conversation, it needs the two blocks its own
        contract defines - what was read, and what it has to respect. Both come
        back in the contracts' shape, ready to be dropped into a package.
        """
        return {"reads": [read.as_envelope() for read in self._reads],
                "limits": self.limits_for("design")}

    # ---------------------------------------------------------------- JSON --
    def to_json(self) -> dict:
        """Plain JSON, with every agreed value carrying who set it and when.

        The required side is not serialised: it lives in the profile and the
        contracts, and writing a copy of it into the saved specification would
        create exactly the frozen second source of truth this module refuses.
        Only `imposed` is written, because it has no file yet.
        """
        return {
            "kind": "dbtl:specification/0.1.0",
            "run_id": self.run_id,
            "agreed": [v.to_json() for v in self._agreed.values()],
            "limits": [limit.to_json() for limit in self._limits],
            "reads": [read.as_envelope() for read in self._reads],
            "imposed": [r.to_json() for r in self._imposed.values()],
        }

    @classmethod
    def from_json(cls, raw: dict) -> "Specification":
        spec = cls(run_id=raw.get("run_id", ""))
        for item in raw.get("agreed", []):
            value = AgreedValue.from_json(item)
            # Straight into the store: these were already checked by agree()
            # when they were first made, and a reload is not a renegotiation.
            spec._agreed[value.key] = value
        spec._limits = [Limit.from_json(x) for x in raw.get("limits", [])]
        spec._reads = [Read.from_json(x) for x in raw.get("reads", [])]
        for item in raw.get("imposed", []):
            spec._imposed[item["key"]] = Requirement(**item)
        return spec

    def __repr__(self) -> str:
        return (f"Specification(profile={self.profile_name!r}, "
                f"agreed={len(self._agreed)}, limits={len(self._limits)}, "
                f"unresolved={len(self.unresolved())})")


# Detail for the short names a researcher might use for a requirement. The
# sources are the real files; the text is only what makes the refusal readable.
_ALIAS_DETAIL: dict[str, tuple[str, str, str]] = {
    "unit": (
        "part of the measurement shape: quantity, value, unit, method",
        "framework/contracts/build_to_test.schema.json (measurement object)",
        "a number without its unit cannot be compared with the next round's or "
        "converted; 'dimensionless' is written rather than the field omitted"),
    "method": (
        "part of the measurement shape: quantity, value, unit, method",
        "framework/contracts/build_to_test.schema.json (measurement object)",
        "two instruments disagree, and a value whose instrument is unknown "
        "cannot be pooled with one whose is"),
    "origin": (
        "the provenance chain from an ordered sequence back to a physical "
        "sample",
        "framework/contracts/design_to_build.schema.json#/x-dbtl-checks "
        "(broken_provenance_chain)",
        "a sequence with no recorded origin cannot be re-collected and, under "
        "the Nagoya Protocol, cannot be shown to have been collected legally"),
    "uncertainty": (
        "required on every prediction in the Learn -> Design handover",
        "framework/contracts/learn_to_design.schema.json "
        "(predictions[].uncertainty)",
        "a ranked list of point estimates tells Design nothing about where to "
        "spend a plate, so a point prediction cannot be used to choose"),
}


if TYPE_CHECKING:  # the class satisfies the protocol in architect/contract.py
    from architect.contract import Specification as _Protocol

    def _conforms(spec: _Protocol) -> None: ...
    _conforms(Specification("bioprospecting"))


# --------------------------------------------------------------------------- #
#  A specification for the bioprospecting use case
# --------------------------------------------------------------------------- #
def _demo() -> None:
    rule = "-" * 78

    spec = Specification("bioprospecting", run_id="BP-round-1",
                         set_by="Anil Wipat")
    spec.agree("objective",
               "find a thermostable esterase in the hot-spring metagenome",
               set_by="Anil Wipat")
    spec.agree("target", "esterase activity on p-nitrophenyl butyrate",
               set_by="Anil Wipat")
    spec.agree("equipment", ["Opentrons OT-2", "Agilent TapeStation 4200",
                             "BMG CLARIOstar Plus"],
               set_by="Anil Wipat", note="all three on site this round")
    # 'budget' is left unagreed on purpose, so unresolved() has something true
    # to report.

    spec.declare_read("crate://bp/seed-round-1", role="constraints",
                      checksum="sha256:seed-r1")
    spec.declare_read("crate://bp/field-collection-2026", role="upstream")
    spec.state_limit("library_size", 96, "dimensionless",
                     from_crate="crate://bp/seed-round-1",
                     stated_by="Build: one OT-2 plate per round")
    spec.state_limit("budget_eur", 4000, "EUR",
                     from_crate="crate://bp/seed-round-1",
                     stated_by="Anil Wipat")

    print(rule)
    print("AGREED - the researcher decided these, and may change any of them")
    print(rule)
    for key, record in spec.attribution.items():
        print(f"  {key:<12} = {record['value']}")
        print(f"  {'':<12}   set by {record['set_by']} at {record['at']}"
              + (f" ({record['note']})" if record["note"] else ""))

    print()
    print(rule)
    print("REQUIRED - the process requires these of anybody, read from the "
          "profile\n           and the contracts, not from this file")
    print(rule)
    for phase in PHASES:
        block = spec.requirements_for(phase)
        reqs = block["requirements"]
        # Grouped by family - the part of the key after the handover name -
        # because 28 lines of "the package carries X" hides the three that
        # matter: the measurement shape, the provenance chain, the quantities
        # this use case is incomplete without.
        families: dict[str, list[dict]] = {}
        for req in reqs:
            tail = req["key"].split(".")
            families.setdefault(tail[1] if len(tail) > 1 else "other",
                                []).append(req)
        print(f"\n  {phase} -> {block['handover']}  ({len(reqs)} requirements, "
              f"contract {block['contract']})")
        for family, group in families.items():
            print(f"    {family} ({len(group)})")
            for req in group if family != "required" else group[:1]:
                print(f"      - {req['statement'][:68]}")
                print(f"          {req['source']}")
            if family == "required" and len(group) > 1:
                print(f"      ... and {len(group) - 1} more required fields")

    print()
    print(rule)
    print("THE REFUSAL - what happens when the two are confused")
    print(rule)
    attempts = ("measurement.unit", "prediction.uncertainty",
                "design_to_build.quantity.fragment_size",
                "test_to_learn.check.unusable_reading")
    for index, attempt in enumerate(attempts):
        try:
            spec.agree(attempt, "skip for this round", set_by="whoever")
        except RequirementNotNegotiable as refused:
            print(f"\n  agree({attempt!r}, 'skip for this round')")
            if index == 0:  # the first one in full; the rest in one line each
                for line in str(refused).splitlines():
                    print(f"    {line}")
            else:
                print(f"    refused: {refused.canonical}")
                print(f"    stated in: {refused.source}")
        else:
            raise AssertionError(f"{attempt} was accepted as an agreement")
    for attempt in attempts:
        assert attempt not in spec.agreed, "a refusal must not store anything"

    print()
    print(rule)
    print("LIMITS - in the contracts' own 'limits' shape")
    print(rule)
    for phase in PHASES:
        print(f"  {phase:<7} {spec.limits_for(phase)}")

    print()
    print(rule)
    print("UNRESOLVED - the run may start; it may not finish")
    print(rule)
    for gap in spec.unresolved():
        print(f"  - {gap[:120]}")

    print()
    print(rule)
    print("to_seed() - handed straight to a Design phase agent")
    print(rule)
    print(json.dumps(spec.to_seed(), indent=2))

    print()
    print(rule)
    print("JSON round trip")
    print(rule)
    again = Specification.from_json(json.loads(json.dumps(spec.to_json())))
    print(f"  before: {spec!r}")
    print(f"  after:  {again!r}")
    assert again.agreed == spec.agreed
    assert again.limits == spec.limits
    assert again.to_seed() == spec.to_seed()
    assert again.unresolved() == spec.unresolved()
    print("  identical: agreed, limits, to_seed(), unresolved()")
    print(f"\n  profiles on disk: {', '.join(available_profiles())}")


if __name__ == "__main__":
    _demo()
