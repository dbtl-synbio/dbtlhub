"""Ingredient 1 of the Architect: arriving at a first specification.

Two ways in, and both have to work.

    (a) The researcher has nothing. The Architect asks a short, ordered series
        of questions and ends with a specification.
    (b) The researcher already has a workflow - a file, a dict, a protocol.
        The Architect reads it, says back what it understood, says plainly
        what it could NOT read, and offers changes as questions.

Case (b) is not the lesser case. Most groups already have a protocol, and a
system that only works for somebody starting from nothing is a system nobody
starts. So the same slots are filled either way; only the source of each value
differs, and the source is recorded.

Four rules shape everything below.

1.  Questions, never silent edits. Nothing the researcher did not decide is
    written into `agreed` as if they had. A guess from an objective string or
    from an unfamiliar workflow key becomes the *recommended option* of a
    question, never a value.

2.  Ask in order of consequence. The profile decides what every later phase
    must do, so it is asked first. Whether a physical sample exists decides
    whether the Design -> Build provenance chain can exist at all, so it is
    asked second. The plate label is asked last.

3.  Ask only what cannot be derived. The profile already states which
    measurement a handover is incomplete without; that is stated back, not
    asked. Asking a researcher to choose something a contract has already
    fixed teaches them that the answers do not matter.

4.  Record where every value came from. `Provenance` carries who decided it,
    when, whether it came from the researcher, the uploaded workflow or a
    profile default, and - when a later answer overrides an earlier value -
    what it replaced. Without that, a default silently becomes a commitment,
    and six months later nobody can say whether 96 wells was a decision or an
    accident.

Standard library only. No network, no model call. Where a model would help,
there is a named method to override and a comment saying so.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:                      # run as a script or imported
    sys.path.insert(0, str(REPO_ROOT))

from architect.contract import (                        # noqa: E402
    HANDOVERS, PHASES, Answer, Question, Specification,
)

CONTRACT_DIR = REPO_ROOT / "framework" / "contracts"
PROFILE_DIR = CONTRACT_DIR / "profiles"
ASKED_BY = "architect.consultation"


def now() -> str:
    """One timestamp format for the whole module. Seconds are enough; the
    point of the time is to order decisions, not to measure them."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
#  Provenance
# --------------------------------------------------------------------------- #
class Source(str, Enum):
    """Where a value came from. Four sources, and they are not equivalent:
    a researcher's choice can be defended, a profile default cannot."""
    RESEARCHER = "researcher"            # somebody chose it, on the record
    WORKFLOW = "workflow"                # read out of the uploaded workflow
    PROFILE_DEFAULT = "profile_default"  # a default nobody has looked at yet
    CONTRACT = "contract"                # not a decision: the process requires it


@dataclass
class Provenance:
    """Who decided one value, when, and on what basis."""
    source: Source
    decided_by: str                 # a person, a file, or a profile name
    at: str = field(default_factory=now)
    locator: str = ""               # workflow key, profile path, option text
    note: str = ""
    supersedes: str = ""            # the value this replaced, and its source

    def line(self) -> str:
        bits = [f"{self.source.value} / {self.decided_by} / {self.at}"]
        if self.locator:
            bits.append(f"from {self.locator}")
        if self.supersedes:
            bits.append(f"replaced {self.supersedes}")
        if self.note:
            bits.append(f"note: {self.note}")
        return "; ".join(bits)

    def as_dict(self) -> dict:
        return {"source": self.source.value, "decided_by": self.decided_by,
                "at": self.at, "locator": self.locator, "note": self.note,
                "supersedes": self.supersedes}


# --------------------------------------------------------------------------- #
#  What a workflow reading produced
# --------------------------------------------------------------------------- #
@dataclass
class WorkflowReading:
    """The honest result of reading somebody else's workflow.

    `unread` matters more than `understood`. A list of keys the Architect did
    not interpret is something a researcher can correct in one minute. A
    confident partial reading is something they will only discover is wrong
    after a round of synthesis.
    """
    understood: dict[str, Any] = field(default_factory=dict)   # slot -> value
    from_key: dict[str, str] = field(default_factory=dict)     # slot -> workflow key
    unread: list[str] = field(default_factory=list)            # keys with no meaning here
    # Key recognised, value not: slot key -> the key and value as written. Held
    # against the slot rather than as free text so that answering the slot
    # closes it, instead of leaving a complaint in the specification forever.
    uninterpreted: dict[str, str] = field(default_factory=dict)
    kept: dict[str, Any] = field(default_factory=dict)         # carried verbatim, not a decision
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
#  The slot catalogue: everything the Architect may ask, in order
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Slot:
    key: str
    rank: int                       # 1 = changes what every later phase does
    headline: str
    detail: str
    options: tuple[tuple[str, Any], ...]     # (text the researcher reads, value)
    recommended: str | None
    because: str
    affects: tuple[str, ...]        # phases whose work changes with this answer
    needed_when: Callable[[dict], bool] | None = None   # relevance, given `agreed`


def _collected(agreed: dict) -> bool:
    """Access-and-benefit-sharing only bites if material was collected."""
    return agreed.get("material_origin") in ("held_collection", "to_be_collected")


SLOTS: tuple[_Slot, ...] = (
    _Slot(
        key="profile",
        rank=1,
        headline="Which use case does this run belong to?",
        detail=("The profile fixes the identifier formats, the measurements "
                "each handover is incomplete without, and the provenance every "
                "ordered sequence has to carry. Every later phase reads it, so "
                "nothing else can be settled first."),
        options=(
            ("Bioprospecting: pick candidate sequences out of a metagenome, "
             "synthesise them, screen the plate", "bioprospecting"),
            ("Biomanufacturing: optimise a pathway in a microbial host and "
             "measure the product titre", "biomanufacturing"),
        ),
        recommended=None,
        because=("The two profiles require different measurements and different "
                 "provenance. Choosing the wrong one does not fail now; it fails "
                 "at the first handover, after the work."),
        affects=PHASES,
    ),
    _Slot(
        key="material_origin",
        rank=2,
        headline="Where does the starting material come from?",
        detail=("The Design -> Build check follows every ordered sequence back, "
                "link by link, to a physical sample. If no physical sample is "
                "held or planned, that chain cannot be completed and the "
                "handover will be refused - which is worth knowing now rather "
                "than after the panel is designed."),
        options=(
            ("Field-collected material already in a freezer here, with its "
             "collection records", "held_collection"),
            ("Material still to be collected in this project; collection "
             "records get written as the collections happen", "to_be_collected"),
            ("Public accessions only, no physical sample held: record the panel "
             "as in-silico-only and raise the missing sample now",
             "public_accessions"),
        ),
        recommended=None,
        because=("This is the one answer that can make the first handover "
                 "impossible rather than merely incomplete."),
        affects=("design", "build"),
    ),
    _Slot(
        key="access_permit",
        rank=3,
        headline="How is the collection's access permit recorded?",
        detail=("Under the Nagoya Protocol a sequence from a located site has "
                "to be shown to have been collected legally. The crate can "
                "carry the permit, or it can carry the fact that there is none."),
        options=(
            ("Record a permit identifier on each collection site in the crate",
             "permit_recorded"),
            ("No permit applies (material from your own jurisdiction or a "
             "non-party); record that reason on the sites",
             "not_applicable_recorded"),
            ("Permit pending: mark the panel as not-for-publication until a "
             "permit identifier is recorded", "pending_marked"),
        ),
        recommended=None,
        because=("A missing permit is not a formatting problem; it decides "
                 "whether results can be published or shared at all."),
        affects=("design",),
        needed_when=_collected,
    ),
    _Slot(
        key="library_size",
        rank=4,
        headline="How many constructs may this round order?",
        detail=("Carried as a limit on the handover, so the check can compare "
                "the panel against it. Design then has to select within it and "
                "say which candidates it dropped - which is a scientific "
                "choice, not something an agent should make quietly."),
        options=(
            ("Up to 24 constructs this round", 24),
            ("Up to 96 constructs, one plate", 96),
            ("Up to 384 constructs, four plates", 384),
        ),
        recommended="Up to 96 constructs, one plate",
        because=("A limit stated before the design exists is a constraint. The "
                 "same number discovered after it exists is an argument."),
        affects=("design", "build"),
    ),
    _Slot(
        key="build_route",
        rank=5,
        headline="Who makes the DNA?",
        detail=("This decides what leaves the building. The order is a "
                "deliberately poor projection of the crate: a provider gets "
                "sequences and well positions and nothing else."),
        options=(
            ("An external synthesis provider: sequences leave the building, "
             "named in the order", "external_provider"),
            ("In-house synthesis and assembly: nothing leaves the building",
             "in_house"),
            ("Mixed: fragments ordered externally, assembly in-house", "mixed"),
        ),
        recommended="An external synthesis provider: sequences leave the "
                    "building, named in the order",
        because=("Anything in the order is something we have decided to send to "
                 "a third party. That decision should be explicit."),
        affects=("build",),
    ),
    _Slot(
        key="replicates",
        rank=6,
        headline="How many replicates per candidate in Test?",
        detail=("Learn cannot separate an effect from a pipetting error with "
                "one well. The number is recorded on every reading, so Learn "
                "knows what it is fitting."),
        options=(
            ("Three replicates per candidate", 3),
            ("Two replicates per candidate", 2),
            ("One well per candidate, recorded as replicates = 1 so Learn "
             "weights it accordingly", 1),
        ),
        recommended="Three replicates per candidate",
        because=("One replicate is a legitimate choice under a budget. One "
                 "replicate recorded as if it were three is not."),
        affects=("test", "learn"),
    ),
    _Slot(
        key="partial_policy",
        rank=7,
        headline="What happens to candidates whose coding sequence is not complete?",
        detail=("A gene called with open ends can run off the end of a contig, "
                "so a partial is a truncated enzyme. The crate records this "
                "honestly per protein; the question is what Build is told."),
        options=(
            ("Order only complete coding sequences; keep the partials in the "
             "crate, unordered", "complete_only"),
            ("Order the partials too, with the incompleteness flagged on the "
             "order line so Build accepts it knowingly", "order_flagged"),
        ),
        recommended="Order only complete coding sequences; keep the partials in "
                    "the crate, unordered",
        because=("A negative result on a protein that was never whole cannot be "
                 "told apart from a protein that does not work."),
        affects=("design", "build", "learn"),
    ),
    _Slot(
        key="order_format",
        rank=8,
        headline="In which format does the order go out?",
        detail="The handover schema accepts exactly these three.",
        options=(
            ("FASTA: sequence and identifier only", "fasta"),
            ("GenBank: sequence with feature annotation", "genbank"),
            ("SBOL: sequence with explicit part structure", "sbol"),
        ),
        recommended="FASTA: sequence and identifier only",
        because=("A richer format is only worth it if the provider reads it; "
                 "otherwise the annotation is lost and the crate is the record."),
        affects=("build",),
    ),
    _Slot(
        key="vocabulary_scope",
        rank=9,
        headline="Whose vocabulary aligns the local key names?",
        detail=("A key nobody has mapped is a key nobody can query, and the "
                "handover treats one as a failure rather than a warning. Local "
                "spellings - freezer_temp, gps_lat - have to resolve to agreed "
                "terms before the crate is written."),
        options=(
            ("The shared core vocabulary only; any unmapped key comes back to "
             "you as a question", "core_only"),
            ("This site's vocabulary file as well as the core one", "site_and_core"),
        ),
        recommended="This site's vocabulary file as well as the core one",
        because=("The phase that owns the words should resolve them: nobody "
                 "downstream can know what the technician meant."),
        affects=PHASES,
    ),
    _Slot(
        key="identifier_style",
        rank=10,
        headline="Which spelling of the design item identifier does this group use?",
        detail=("Three are in use. This changes a label and nothing else, which "
                "is why it is asked last - but two groups using two spellings "
                "cannot join their crates."),
        options=(
            ("CAND-001: a candidate selected for the panel", "CAND"),
            ("CON-001: a construct", "CON"),
            ("ENR-001: the protein the construct is based on", "ENR"),
        ),
        recommended="CAND-001: a candidate selected for the panel",
        because=("The profile notes all three spellings exist and that settling "
                 "one is a group decision, not an agent's."),
        affects=("design",),
    ),
    _Slot(
        key="container",
        rank=11,
        headline="Which container identifier does the order plate get?",
        detail=("Any identifier matching the profile's container pattern. Note "
                "that the simulated design pipeline's default, ORDPLATE-1, does "
                "not match that pattern - worth settling here rather than in a "
                "refusal."),
        options=(
            ("PLATE-1", "PLATE-1"),
            ("PLATE-2", "PLATE-2"),
        ),
        recommended="PLATE-1",
        because="A label, and labels are cheap to agree and expensive to merge.",
        affects=("build",),
    ),
)

SLOTS_BY_KEY: dict[str, _Slot] = {s.key: s for s in SLOTS}


def _build_option_index() -> dict[str, tuple[str, Any]]:
    """Map every option text to (slot key, value).

    `Answer` carries only the text that was chosen, so option texts have to be
    unique across the whole catalogue or an answer cannot be attributed. A
    duplicate is a programming error and should stop the import, not produce a
    specification that credits the answer to the wrong slot.
    """
    index: dict[str, tuple[str, Any]] = {}
    for slot in SLOTS:
        for text, value in slot.options:
            if text in index:
                raise RuntimeError(
                    f"two slots offer the same option text: {text!r} "
                    f"({index[text][0]} and {slot.key})")
            index[text] = (slot.key, value)
        if slot.recommended is not None:
            assert slot.recommended in [t for t, _ in slot.options], \
                f"{slot.key}: recommended option is not one of the options"
    return index


OPTION_INDEX = _build_option_index()


# --------------------------------------------------------------------------- #
#  Reading a workflow somebody else wrote
# --------------------------------------------------------------------------- #
# Synonyms, not a schema. These are the spellings seen in real protocol files
# and spreadsheets; anything not here is reported unread rather than guessed.
KEY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "profile": ("profile", "use_case", "usecase", "case", "pipeline"),
    "objective": ("objective", "aim", "goal", "purpose", "title", "question"),
    "material_origin": ("material", "material_origin", "source_material",
                        "sample_source", "origin"),
    "access_permit": ("permit", "abs_permit", "nagoya", "access_permit"),
    "library_size": ("library_size", "panel_size", "n_constructs", "n_candidates",
                     "constructs", "candidates", "n"),
    "build_route": ("build_route", "synthesis", "provider", "vendor", "supplier"),
    "replicates": ("replicates", "n_replicates", "repeats",
                   "technical_replicates"),
    "partial_policy": ("partial_policy", "partials", "truncated"),
    "order_format": ("order_format", "format", "sequence_format"),
    "vocabulary_scope": ("vocabulary", "vocabulary_scope", "ontology"),
    "identifier_style": ("identifier_style", "id_prefix", "design_item_id",
                         "naming"),
    "container": ("container", "container_id", "plate", "plate_id"),
}

# Keys worth keeping verbatim. They are not decisions the Architect can make,
# but throwing away the researcher's own protocol text would be rude and would
# lose the only description of the science that exists.
KEEP_KEYS: tuple[str, ...] = ("steps", "protocol", "procedure", "workflow",
                              "instruments", "equipment", "lab", "site",
                              "notes", "references", "doi")


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    m = re.search(r"-?\d+", str(value))
    return int(m.group()) if m else None


def _match_option_value(slot_key: str, value: Any) -> Any | None:
    """Turn a workflow value into one of a slot's values, or give up.

    Giving up is a real outcome: the key is then reported as recognised but
    uninterpreted, and the question for that slot is still asked.
    """
    slot = SLOTS_BY_KEY[slot_key]
    allowed = [v for _, v in slot.options]
    if value in allowed:
        return value
    text = str(value).strip().lower()
    for candidate in allowed:
        if isinstance(candidate, str) and candidate.lower() == text:
            return candidate
    if slot_key in ("library_size", "replicates"):
        # A number that is not one of the offered numbers is still a number the
        # researcher wrote down, and the limit is theirs to set.
        return _as_int(value)
    if slot_key == "container":
        # The options are examples, not the permitted set: any identifier
        # shaped like the profile's container pattern is the researcher's own
        # label and there is nothing to decide about it.
        m = re.fullmatch(r"\s*([A-Za-z]+)[ _-]?(\d+)\s*", str(value))
        if m:
            return f"{m.group(1).upper()}-{m.group(2)}"
    # A few spellings that are common enough to be worth reading.
    aliases = {
        "profile": {"bioprospect": "bioprospecting", "metagenomic": "bioprospecting",
                    "biomanufacture": "biomanufacturing", "pathway": "biomanufacturing"},
        "order_format": {"fa": "fasta", "fas": "fasta", "gb": "genbank",
                         "gbk": "genbank", "xml": "sbol"},
        "build_route": {"external": "external_provider", "outsourced": "external_provider",
                        "twist": "external_provider", "idt": "external_provider",
                        "in-house": "in_house", "inhouse": "in_house"},
        "identifier_style": {"cand": "CAND", "con": "CON", "enr": "ENR",
                             "cand-": "CAND", "con-": "CON", "enr-": "ENR"},
        "material_origin": {"freezer": "held_collection", "soil": "held_collection",
                            "public": "public_accessions",
                            "database": "public_accessions"},
    }.get(slot_key, {})
    for needle, mapped in aliases.items():
        if needle in text:
            return mapped
    return None


# --------------------------------------------------------------------------- #
#  The specification this module produces
# --------------------------------------------------------------------------- #
class AgreedSpecification:
    """A concrete `Specification` (contract.py, part 2).

    It keeps two kinds of statement apart, which is the whole point of that
    protocol. `agreed` is what the researcher decided and can change.
    `requirements_for` is what the profile and the handover contract require of
    anybody, which nobody here decided and nobody here can waive. Mixing them
    is how a requirement gets negotiated away by accident.

    Ingredient 2 of the Architect may replace this class; `Consultation`
    depends on the protocol, not on this implementation, and the class to build
    is a seam (`spec_class`) on the consultation object.
    """

    def __init__(self, profile: str | None = None, objective: str | None = None):
        self.agreed: dict[str, Any] = {}
        self.limits: list[dict] = []
        self.provenance: dict[str, Provenance] = {}
        self.objective: str = objective or ""
        self.spec_id: str = "spec:" + now().replace(":", "").replace("-", "")
        self.reading: WorkflowReading | None = None
        self.uninterpreted_answers: list[str] = []
        self.transcript: list[str] = []          # what was asked, in order
        self._profile_cache: dict | None = None
        if profile:
            self.set("profile", profile,
                     Provenance(Source.CONTRACT, "architect",
                                locator="given when the consultation opened"))

    # ---- values and their provenance ------------------------------------- #
    def set(self, key: str, value: Any, prov: Provenance) -> None:
        """Write one value and the record of where it came from.

        An overwrite is allowed - a researcher may change their mind - but the
        old value and its source are carried into the new provenance, so the
        specification can always say what it used to say.
        """
        if key in self.agreed and self.agreed[key] != value:
            old = self.provenance.get(key)
            prov.supersedes = (f"{self.agreed[key]!r} "
                               f"({old.source.value if old else 'unknown'})")
        self.agreed[key] = value
        self.provenance[key] = prov
        if key == "profile":
            self._profile_cache = None
        if key == "library_size":
            self._set_limit("library_size", value, "dimensionless", prov)
        if key == "replicates":
            self._set_limit("replicates", value, "dimensionless", prov)

    def _set_limit(self, quantity: str, value: Any, unit: str,
                   prov: Provenance) -> None:
        """Mirror an agreed number into the handover's `limits` list.

        The handover schema wants limits lifted out of the crates a package
        read, with `from` naming that crate. Before round 1 there is no crate
        yet: the limit comes from the consultation, so `from` names the
        specification and `stated_by` names whoever set it. `applies_to` is
        internal and is stripped before the list is handed to a phase.
        """
        number = _as_int(value)
        if number is None:
            return
        slot = SLOTS_BY_KEY.get(quantity)
        row = {"quantity": quantity, "value": number, "unit": unit,
               "from": self.spec_id, "stated_by": prov.decided_by,
               "applies_to": list(slot.affects) if slot else list(PHASES)}
        self.limits = [limit for limit in self.limits
                       if limit["quantity"] != quantity] + [row]

    # ---- the profile ------------------------------------------------------ #
    @property
    def profile_name(self) -> str | None:
        return self.agreed.get("profile")

    def profile(self) -> dict:
        """The profile document, or {} while no profile has been agreed."""
        if self._profile_cache is None:
            name = self.profile_name
            path = PROFILE_DIR / f"{name}.json" if name else None
            if path and path.is_file():
                self._profile_cache = json.loads(path.read_text())
            else:
                self._profile_cache = {}
        return self._profile_cache

    @staticmethod
    def _schema(handover: str) -> dict:
        path = CONTRACT_DIR / f"{handover}.schema.json"
        return json.loads(path.read_text()) if path.is_file() else {}

    # ---- the Specification protocol -------------------------------------- #
    def requirements_for(self, phase: str) -> dict:
        """What the process requires of this phase, whoever runs it.

        Everything here is read from the profile and the handover schema. None
        of it is up for discussion, so none of it is ever asked as a question -
        it is stated.
        """
        handover = HANDOVERS.get(phase)
        prof = self.profile()
        if not prof:
            return {"phase": phase, "handover": handover,
                    "note": ("no profile agreed yet, so the requirements cannot "
                             "be stated. This is the first question.")}
        provenance = prof.get("required_provenance", {}).get(handover, {})
        schema = self._schema(handover) if handover else {}
        not_waivable = [
            "every ordered item must bind to an entity the crate contains",
            "alignment.unaligned must be empty: an unmapped key cannot be queried",
            "crate_ref.checksum must match the crate it attests",
        ] if handover == "design_to_build" else []
        return {
            "phase": phase,
            "handover": handover,
            "profile": prof.get("name"),
            "measurements_required": prof.get("required_quantities", {})
                                         .get(handover, []),
            "provenance_root": provenance.get("root_type", []),
            "provenance_required": [
                {"type": e.get("type") or e.get("one_of"),
                 "requires": e.get("requires", []),
                 "why": e.get("why", "")}
                for e in provenance.get("entities", [])],
            "accepted_values": prof.get("accepted_values", {}).get(handover, []),
            "patterns": prof.get("patterns", {}),
            "instruments": prof.get("instruments", []),
            "contract_required_keys": schema.get("required", []),
            "not_waivable": not_waivable,
        }

    def limits_for(self, phase: str) -> list[dict]:
        return [limit for limit in self.limits
                if phase in limit.get("applies_to", PHASES)]

    def unresolved(self) -> list[str]:
        """What still has no answer. A run may start anyway; it may not finish."""
        out: list[str] = []
        for slot in sorted(SLOTS, key=lambda s: s.rank):
            if slot.key in self.agreed:
                continue
            if slot.needed_when and not slot.needed_when(self.agreed):
                continue
            out.append(f"{slot.key}: {slot.headline} "
                       f"(affects {', '.join(slot.affects)})")
        for line in self.uninterpreted_answers:
            out.append(f"answer not understood: {line}")
        if self.reading:
            for slot_key, entry in self.reading.uninterpreted.items():
                if slot_key not in self.agreed:
                    out.append("workflow key read but value not understood: "
                               f"{entry}")
        return out

    # ---- handing the specification on ------------------------------------ #
    def design_task_inputs(self, run_id: str = "adhoc") -> dict:
        """`Task.inputs` for a Design phase agent, built only from agreed values.

        The Design phase agent reads `n`, `container`, `limits` and `reads` off
        its task and takes the profile and the lab on its constructor. This is
        the join between a conversation and a run: if something here is missing
        it is because nobody agreed it, and the specification says so.
        """
        limits = [{k: v for k, v in limit.items() if k != "applies_to"}
                  for limit in self.limits_for("design")]
        inputs: dict[str, Any] = {"run_id": run_id, "limits": limits, "reads": []}
        if "library_size" in self.agreed:
            inputs["n"] = self.agreed["library_size"]
        if "container" in self.agreed:
            inputs["container"] = self.agreed["container"]
        return inputs

    def as_dict(self) -> dict:
        return {
            "spec_id": self.spec_id,
            "objective": self.objective,
            "agreed": dict(self.agreed),
            "provenance": {k: p.as_dict() for k, p in self.provenance.items()},
            "limits": self.limits,
            "unresolved": self.unresolved(),
            "workflow_unread": list(self.reading.unread) if self.reading else [],
        }

    # ---- saying it back -------------------------------------------------- #
    def say_back(self) -> list[str]:
        """What the Architect understood, where each piece came from, what it
        could not read, and what is still open. This is the text case (b) turns
        on: a researcher who uploaded a protocol needs to see it read back
        before being asked to change anything."""
        lines: list[str] = []
        if self.objective:
            lines.append(f"Objective as stated: {self.objective}")
        lines.append("Understood so far:")
        if not self.agreed:
            lines.append("  (nothing yet)")
        for key in sorted(self.agreed, key=lambda k: SLOTS_BY_KEY[k].rank
                          if k in SLOTS_BY_KEY else 99):
            prov = self.provenance.get(key)
            lines.append(f"  {key} = {self.agreed[key]!r}")
            if prov:
                lines.append(f"      <- {prov.line()}")
        if self.reading:
            if self.reading.kept:
                lines.append("Carried from your workflow as description, not as "
                             "a decision:")
                for key, value in self.reading.kept.items():
                    lines.append(f"  {key}: {_short(value)}")
            if self.reading.uninterpreted:
                lines.append("Recognised the key but could not read the value:")
                for slot_key, entry in self.reading.uninterpreted.items():
                    settled = (f" -> settled by your answer: "
                               f"{slot_key} = {self.agreed[slot_key]!r}"
                               if slot_key in self.agreed
                               else "  (so it is still a question)")
                    lines.append(f"  {entry}{settled}")
            if self.reading.unread:
                lines.append("Could NOT interpret these keys at all - tell me "
                             "what they mean and I will carry them:")
                for key in self.reading.unread:
                    lines.append(f"  {key}")
            for note in self.reading.notes:
                lines.append(f"Note: {note}")
        return lines

    def stated_requirements(self) -> list[str]:
        """The things that would be questions if they were not already settled.

        Rule 3 in one method: the profile names the measurement each handover
        is incomplete without, so it is said rather than asked.
        """
        prof = self.profile()
        if not prof:
            return ["No profile agreed yet, so nothing can be stated as required."]
        lines = [f"Profile {prof.get('name')}: {prof.get('description', '')}"]
        for phase in PHASES:
            req = self.requirements_for(phase)
            for quantity in req.get("measurements_required", []):
                lines.append(
                    f"{phase} -> {req['handover']}: {quantity['quantity']} must be "
                    f"reported in {quantity['unit']} "
                    f"({quantity.get('method_hint', 'no method stated')}). "
                    f"Not asked: the profile requires it.")
            for entity in req.get("provenance_required", []):
                if entity["requires"]:
                    lines.append(
                        f"{phase} -> {req['handover']}: {entity['type']} must "
                        f"carry {', '.join(entity['requires'])}. Not asked: the "
                        f"profile requires it.")
        return lines


def _short(value: Any, width: int = 70) -> str:
    text = json.dumps(value) if not isinstance(value, str) else value
    return text if len(text) <= width else text[: width - 3] + "..."


# --------------------------------------------------------------------------- #
#  The consultation itself
# --------------------------------------------------------------------------- #
class ArchitectConsultation:
    """`Consultation` from contract.py, part 1.

    Deterministic and offline. Every judgement it makes - which profile an
    objective suggests, what an unfamiliar workflow key means - is either a
    recommendation attached to a question or an admission that it does not
    know. The four `# SEAM` methods below are where a model would earn its
    place later; each has a defensible default so that nothing depends on one.
    """

    spec_class = AgreedSpecification     # SEAM: ingredient 2 can substitute here

    def __init__(self, researcher: str = "researcher") -> None:
        self.researcher = researcher

    # ---- (a) and (b): the two ways in ------------------------------------ #
    def open(self, *, objective: str | None = None,
             workflow: dict | str | None = None) -> Specification:
        """Start a consultation from an objective, a workflow, or both.

        Neither is required. With neither, the result is an empty specification
        whose `unresolved()` is the full list of questions - which is a usable
        starting point and more honest than refusing to begin.
        """
        spec = self.spec_class(objective=objective)
        if objective:
            spec.transcript.append(f"opened from an objective: {objective}")
        if workflow is not None:
            reading = self.read_workflow(workflow)
            spec.reading = reading
            source_name = reading.notes[0] if reading.notes else "uploaded workflow"
            for slot_key, value in reading.understood.items():
                spec.set(slot_key, value, Provenance(
                    Source.WORKFLOW, source_name,
                    locator=f"key {reading.from_key.get(slot_key, slot_key)!r}",
                    note="read from the workflow, not chosen by you - say so if "
                         "it is wrong"))
            if "objective" in reading.kept and not spec.objective:
                spec.objective = str(reading.kept["objective"])
            spec.transcript.append(
                f"read a workflow: understood {len(reading.understood)} "
                f"decision(s), kept {len(reading.kept)} description key(s), "
                f"could not interpret {len(reading.unread)} key(s)")
        self._seed_profile_defaults(spec)
        return spec

    def read_workflow(self, workflow: dict | str) -> WorkflowReading:
        """Read a workflow dict, a JSON file, or a loosely formatted text file.

        Nothing is inferred beyond a synonym table and a few spellings. A key
        with no meaning here goes on `unread` verbatim; a known key whose value
        cannot be read goes on `uninterpreted` and its question still gets
        asked. That asymmetry is deliberate: an unread key costs a sentence of
        explanation, a misread one costs a round of synthesis.
        """
        reading = WorkflowReading()
        raw: dict[str, Any]
        if isinstance(workflow, dict):
            raw = dict(workflow)
            reading.notes.append("workflow supplied as a dict")
        else:
            raw, notes = self._read_text_workflow(workflow)
            reading.notes.extend(notes)

        flat = _flatten(raw)
        for key, value in flat.items():
            norm = _norm_key(key.split(".")[-1])
            slot_key = next((s for s, names in KEY_SYNONYMS.items()
                             if norm in names), None)
            if slot_key is None:
                slot_key = self.map_unknown_key(key, value)   # SEAM
            if slot_key == "objective":
                reading.kept["objective"] = value
                continue
            if slot_key and slot_key in SLOTS_BY_KEY:
                matched = _match_option_value(slot_key, value)
                if matched is None:
                    matched = self.interpret_free_text(str(value), slot_key)  # SEAM
                if matched is None:
                    reading.uninterpreted[slot_key] = f"{key} = {_short(value)}"
                    continue
                reading.understood[slot_key] = matched
                reading.from_key[slot_key] = key
                continue
            if norm in KEEP_KEYS or key.split(".")[0] in KEEP_KEYS:
                reading.kept[key] = value
                continue
            reading.unread.append(f"{key} = {_short(value)}")
        return reading

    @staticmethod
    def _read_text_workflow(workflow: str) -> tuple[dict, list[str]]:
        """JSON if it parses, otherwise tolerant `key: value` lines.

        No YAML parser, because a new dependency is not allowed and a
        half-written one would read some files wrongly rather than refusing
        them. Lines that do not look like `key: value` are reported.
        """
        notes: list[str] = []
        text = workflow
        path = Path(workflow)
        try:
            if len(workflow) < 4096 and path.is_file():
                text = path.read_text()
                notes.append(f"workflow read from {path}")
        except OSError:
            pass
        if not notes:
            notes.append("workflow supplied as text")
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                notes.append("parsed as JSON")
                return (parsed if isinstance(parsed, dict)
                        else {"steps": parsed}), notes
            except json.JSONDecodeError as exc:
                notes.append(f"looked like JSON but did not parse: {exc.msg}")
        out: dict[str, Any] = {}
        unparsed = 0
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("-"):
                out.setdefault("steps", []).append(line.lstrip("- ").strip())
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                out[key.strip()] = value.strip()
            else:
                unparsed += 1
        if unparsed:
            notes.append(f"{unparsed} line(s) were neither 'key: value' nor a "
                         f"'-' step and were not read")
        return out, notes

    def _seed_profile_defaults(self, spec: AgreedSpecification) -> None:
        """Defaults are not written into `agreed`. On purpose.

        A profile default that lands in `agreed` is indistinguishable from a
        decision an hour later. Defaults appear only as the `recommended`
        option of a question, so that agreeing to one is an act somebody
        performed at a known time. This method therefore records what the
        profile offers and nothing more.
        """
        prof = spec.profile()
        if prof:
            spec.transcript.append(
                f"profile {prof.get('name')} loaded: its required measurements "
                f"and provenance are stated, not asked")

    # ---- the questions --------------------------------------------------- #
    def propose_changes(self, spec: Specification) -> list[Question]:
        """What the Architect would change, as questions rather than edits.

        Ordered by consequence, not by convenience: an answer that changes what
        every later phase must do comes before one that changes a label. A slot
        already answered is not asked again; a slot the profile has settled is
        never a slot. Every option is something the Architect can carry out -
        there is no 'decide later', because 'decide later' is what the
        unresolved list is for.
        """
        agreed = getattr(spec, "agreed", {})
        questions: list[Question] = []
        for slot in sorted(SLOTS, key=lambda s: s.rank):
            if slot.key in agreed:
                continue
            if slot.needed_when and not slot.needed_when(agreed):
                continue
            recommended = slot.recommended
            if slot.key == "profile":
                guessed = self.guess_profile(getattr(spec, "objective", ""))
                if guessed:
                    recommended = next((t for t, v in slot.options
                                        if v == guessed), None)
            questions.append(Question(
                asked_by=ASKED_BY,
                headline=slot.headline,
                detail=f"[{slot.key}] {slot.detail}",
                options=[text for text, _ in slot.options],
                recommended=recommended,
                because=slot.because,
            ))
        # Conflicts with the workflow come last in rank order but first in
        # importance when they exist, so they are appended as their own
        # questions rather than folded into a slot.
        questions.extend(self._conflict_questions(spec))
        questions = self.rank_questions(questions)               # SEAM
        if hasattr(spec, "transcript"):
            spec.transcript.extend(f"asked: {q.headline}" for q in questions)
        return questions

    def _conflict_questions(self, spec: Specification) -> list[Question]:
        """Where an agreed value and the profile disagree, ask rather than fix.

        Example worth having: a workflow that orders more constructs than the
        round's own limit. Silently clamping it would be the Architect making a
        scientific choice about which candidates to lose.
        """
        agreed = getattr(spec, "agreed", {})
        out: list[Question] = []
        size = agreed.get("library_size")
        if isinstance(size, int) and size > 384:
            out.append(Question(
                asked_by=ASKED_BY,
                headline=f"Your workflow orders {size} constructs in one round.",
                detail=("[library_size] Nothing forbids it, but the limit is "
                        "carried onto the handover and the receiving phase is "
                        "checked against it. If Build cannot take that many, "
                        "the refusal happens after the panel exists."),
                options=["Keep " + str(size) + " and record it as the limit",
                         "Up to 384 constructs, four plates",
                         "Up to 96 constructs, one plate"],
                recommended="Up to 384 constructs, four plates",
                because=("Dropping candidates to fit is a choice about which "
                         "ones to lose, so it is yours and not mine."),
            ))
        if (agreed.get("material_origin") == "public_accessions"
                and "access_permit" not in agreed):
            out.append(Question(
                asked_by=ASKED_BY,
                headline="No physical sample is held. The first handover will "
                         "be refused as it stands.",
                detail=("[material_origin] The Design -> Build check requires a "
                        "path of derivation from every ordered sequence back to "
                        "a physical sample. Public accessions end that path "
                        "outside this lab."),
                options=["Name a collaborator's sample collection as the origin "
                         "and record it in the crate",
                         "Order a physical sample and record its arrival before "
                         "the handover",
                         "Run this round as in-silico-only and accept that the "
                         "Design -> Build handover is refused"],
                recommended="Order a physical sample and record its arrival "
                            "before the handover",
                because=("Better to decide this now than to design a panel that "
                         "cannot be handed over."),
            ))
        return out

    # ---- the answers ----------------------------------------------------- #
    def apply(self, spec: Specification, answers: list[Answer]) -> Specification:
        """Record the answers, with provenance, and return a new specification.

        A copy rather than a mutation, so the version the researcher saw before
        answering still exists and can be compared. An answer that cannot be
        attributed to a slot is NOT guessed at: it is recorded on
        `uninterpreted_answers` and shows up in `unresolved()`, because an
        answer credited to the wrong question is worse than no answer.
        """
        new: AgreedSpecification = copy.deepcopy(spec)        # type: ignore[assignment]
        stamp = now()
        for answer in answers:
            slot_key, value = self._attribute(answer, new)
            if slot_key is None:
                new.uninterpreted_answers.append(
                    f"{answer.chosen!r}"
                    + (f" (note: {answer.note})" if answer.note else ""))
                new.transcript.append(
                    f"could not attribute an answer: {answer.chosen!r}")
                continue
            new.set(slot_key, value, Provenance(
                Source.RESEARCHER, self.researcher, at=stamp,
                locator=f"chose {answer.chosen!r}", note=answer.note))
            new.transcript.append(f"{slot_key} = {value!r} (you chose it)")
        return new

    def _attribute(self, answer: Answer,
                   spec: AgreedSpecification) -> tuple[str | None, Any]:
        """Which slot an answer belongs to, and what value it sets."""
        chosen = answer.chosen.strip()
        if chosen in OPTION_INDEX:
            return OPTION_INDEX[chosen]
        # `key = value` and `key: value`, which is how another agent or a test
        # will want to answer.
        m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(.+?)\s*$", chosen)
        if m and m.group(1) in SLOTS_BY_KEY:
            slot_key = m.group(1)
            value = _match_option_value(slot_key, m.group(2))
            if value is not None:
                return slot_key, value
        # The conflict questions offer "Keep <n> and record it as the limit".
        keep = re.match(r"^Keep (\d+) and record it as the limit$", chosen)
        if keep:
            return "library_size", int(keep.group(1))
        for slot in SLOTS:
            for text, value in slot.options:
                if chosen.lower() == text.lower():
                    return slot.key, value
        guessed = self.interpret_free_text(chosen, slot_key="")      # SEAM
        if isinstance(guessed, tuple):
            return guessed
        return None, None

    # ---- seams ----------------------------------------------------------- #
    # Four places where a language model would help and where this module
    # deliberately does not use one. Each default is defensible on its own, so
    # a subclass that overrides none of them still works; a subclass that
    # overrides all four changes no interface. Anything model-backed should
    # keep the same contract: return a value, or return None to mean "I do not
    # know", never a confident guess.
    def guess_profile(self, objective: str) -> str | None:
        """Suggest a profile from the objective text. Only ever used to set the
        `recommended` option of the profile question, never to set the value."""
        text = (objective or "").lower()
        bio = ("metagenom", "bioprospect", "enzyme", "esterase", "soil",
               "hot spring", "sediment", "screen")
        man = ("titre", "titer", "pathway", "strain", "host", "flavonoid",
               "pinocembrin", "yield", "fermentation")
        if any(word in text for word in bio):
            return "bioprospecting"
        if any(word in text for word in man):
            return "biomanufacturing"
        return None

    def interpret_free_text(self, text: str, slot_key: str) -> Any | None:
        """Read a value a rule could not read. Returns None here, on purpose:
        an unread value becomes a question, and a question is cheap."""
        return None

    def map_unknown_key(self, key: str, value: Any) -> str | None:
        """Map a workflow key the synonym table does not know. None here, so
        the key is reported unread rather than mapped on a hunch."""
        return None

    def rank_questions(self, questions: list[Question]) -> list[Question]:
        """Reorder questions. Identity here: the catalogue's rank is the order
        of consequence, and a model reordering it should have to say why."""
        return questions


def _flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """One level of nesting is flattened to `parent.child`, lists are kept
    whole. Deeper nesting is kept whole too and reported as unread, because a
    structure this module does not understand should be shown, not walked."""
    out: dict[str, Any] = {}
    if not isinstance(obj, dict):
        return {prefix or "value": obj}
    for key, value in obj.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict) and not prefix:
            out.update(_flatten(value, name))
        else:
            out[name] = value
    return out


# --------------------------------------------------------------------------- #
#  A scripted demonstration. No input() anywhere: this has to run unattended.
# --------------------------------------------------------------------------- #
EXAMPLE_WORKFLOW: dict[str, Any] = {
    # The kind of thing a group actually has: half decisions, half description,
    # a couple of keys only they understand, and one value in their own words.
    "title": "Esterase hunt in hot-spring sediment, round 3",
    "use_case": "bioprospecting",
    "panel_size": 120,
    "provider": "Twist",
    "format": "fasta",
    "material": "sediment cores, freezer -80",
    "replicates": "as many as fit",
    "plate_id": "PLATE-7",
    "instruments": ["Opentrons OT-2", "BMG CLARIOstar Plus"],
    "steps": ["call genes on the assembly", "cluster at 90%",
              "pick the top hits by HMM score", "order", "express", "screen"],
    "qc_gate": {"tapestation": "pass", "min_ng_ul": 20},
    "incubation": "o/n at 37",
    "elisa_ref": "SOP-114",
}


def _show_questions(questions: list[Question]) -> None:
    for i, question in enumerate(questions, 1):
        print(f"\n  Q{i}. {question.headline}")
        print(f"      {question.detail}")
        for option in question.options:
            mark = " *" if option == question.recommended else "  "
            print(f"     {mark} - {option}")
        if question.because:
            print(f"      why it is asked: {question.because}")


def _show_conclusion(spec: AgreedSpecification, run_id: str) -> None:
    print("\n  What was concluded:")
    for line in spec.say_back():
        print(f"    {line}")
    print("\n  Stated, not asked (the profile already requires it):")
    for line in spec.stated_requirements():
        print(f"    - {line}")
    print("\n  Limits carried onto the handover:")
    for limit in spec.limits:
        print(f"    - {limit}")
    print("\n  Still unresolved (a run may start; it may not finish):")
    for line in spec.unresolved() or ["(nothing)"]:
        print(f"    - {line}")
    print("\n  What a Design phase agent would be handed:")
    print(f"    profile={spec.profile_name!r}  "
          f"Task.inputs={spec.design_task_inputs(run_id)}")


def _demo_from_objective() -> None:
    print("=" * 74)
    print("(a) The researcher has nothing but an objective")
    print("=" * 74)
    consultation = ArchitectConsultation(researcher="A. Researcher")
    spec = consultation.open(
        objective="Find thermostable esterases in hot-spring metagenomes "
                  "and screen a plate of them")
    print("\n  Opened. Nothing is agreed yet, so everything is unresolved:")
    for line in spec.unresolved():
        print(f"    - {line}")

    print("\n  What the Architect asks, in order of consequence:")
    questions = consultation.propose_changes(spec)
    _show_questions(questions)

    # Answer them. The profile and the material origin are answered as a
    # person would; the replicate count is answered against the recommendation
    # to show that an override is recorded as an override.
    answers = [
        Answer(chosen=questions[0].recommended or questions[0].options[0],
               note="metagenomic screen, as the objective says"),
        Answer(chosen="Field-collected material already in a freezer here, "
                      "with its collection records"),
        Answer(chosen="Up to 96 constructs, one plate", note="one plate of budget"),
        Answer(chosen="Two replicates per candidate",
               note="three would not fit the plate alongside the controls"),
        Answer(chosen="library_size = 96"),          # the key = value form
        Answer(chosen="whatever you think best"),    # deliberately unattributable
    ]
    spec = consultation.apply(spec, answers)

    # The permit question only exists now, because the material turned out to
    # have been collected. Relevance is part of asking in order.
    follow_up = consultation.propose_changes(spec)
    print("\n  After those answers, the questions that remain "
          "(note the permit question, which did not exist before):")
    _show_questions(follow_up)

    spec = consultation.apply(spec, [
        Answer(chosen="Record a permit identifier on each collection site in "
                      "the crate", note="ABS-2026-114"),
        Answer(chosen="An external synthesis provider: sequences leave the "
                      "building, named in the order"),
        Answer(chosen="Order only complete coding sequences; keep the partials "
                      "in the crate, unordered"),
        Answer(chosen="FASTA: sequence and identifier only"),
        Answer(chosen="This site's vocabulary file as well as the core one"),
        Answer(chosen="CAND-001: a candidate selected for the panel"),
        Answer(chosen="PLATE-1"),
    ])
    _show_conclusion(spec, run_id="demo-objective")


def _demo_from_workflow() -> None:
    print("\n" + "=" * 74)
    print("(b) The researcher already has a workflow")
    print("=" * 74)
    consultation = ArchitectConsultation(researcher="A. Researcher")
    spec = consultation.open(workflow=EXAMPLE_WORKFLOW)

    print("\n  Read back before anything is proposed:")
    for line in spec.say_back():
        print(f"    {line}")

    questions = consultation.propose_changes(spec)
    print(f"\n  {len(questions)} question(s) left, because the workflow "
          f"answered the rest:")
    _show_questions(questions)

    spec = consultation.apply(spec, [
        Answer(chosen="Field-collected material already in a freezer here, "
                      "with its collection records",
               note="the 'sediment cores, freezer -80' line, confirmed"),
        Answer(chosen="Three replicates per candidate",
               note="'as many as fit' was not something I could act on"),
        Answer(chosen="Keep 120 and record it as the limit"),
        Answer(chosen="Order only complete coding sequences; keep the partials "
                      "in the crate, unordered"),
        Answer(chosen="This site's vocabulary file as well as the core one"),
        Answer(chosen="CAND-001: a candidate selected for the panel"),
    ])
    remaining = consultation.propose_changes(spec)
    if remaining:
        print("\n  One round more (the permit question became relevant):")
        _show_questions(remaining)
        spec = consultation.apply(spec, [
            Answer(chosen="Record a permit identifier on each collection site "
                          "in the crate", note="ABS-2024-07, hot-spring site"),
        ])
    _show_conclusion(spec, run_id="demo-workflow")


def _demo_text_workflow() -> None:
    """Same path, but the workflow arrives as a text file's contents rather
    than a dict - which is how it usually arrives."""
    print("\n" + "=" * 74)
    print("(b') The same workflow as loose text, to show what is NOT read")
    print("=" * 74)
    text = ("# round 4\n"
            "use case: biomanufacturing\n"
            "panel size: 48\n"
            "order format: xlsx\n"
            "replicates: 3\n"
            "- build the plasmids\n"
            "- grow in deep-well\n"
            "this line is not a key value pair\n"
            "mystery_knob: 0.7\n")
    consultation = ArchitectConsultation(researcher="A. Researcher")
    spec = consultation.open(workflow=text)
    for line in spec.say_back():
        print(f"    {line}")
    print("\n  The order format it gave is not one the handover schema accepts, "
          "so it stays a question:")
    for question in consultation.propose_changes(spec):
        if "order_format" in question.detail:
            _show_questions([question])


if __name__ == "__main__":
    _demo_from_objective()
    _demo_from_workflow()
    _demo_text_workflow()
    print("\nDone. Nothing above called a model, a network or input().")
