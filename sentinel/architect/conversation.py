"""Ingredient 3 of the Architect: what to say when a check fails.

The sentinel already did the detection. By the time anything here runs, the
problem is known, located and named. What is missing is the only part a person
can use: what happened in their words, what it costs to do nothing, and two or
three things that can actually be done about it.

Three rules shape everything below.

    Group.        Six wells missing a unit is one question with the number six
                  in it, not six questions. A researcher who is asked the same
                  thing six times stops reading at the second.

    Separate.     A flag is not an error. It does not stop the handover. If
                  that is not said in the first line of the flag section,
                  somebody will start repairing data that is correct.

    Invent nothing. Where the only way to pass a check would be to supply a
                  measurement nobody took, this module says so and offers the
                  three honest moves instead: find the record, drop the item,
                  or accept the gap and state it. "Fill it in" is never an
                  option, and neither is "think about it" - every option here
                  is something the Architect can carry out.

`fix_hint` in the contracts is the seed of the phrasing, not the phrasing. A
hint is written for a developer with the schema open; it says "not auto-fixable:
re-read the liquid handler worklist". A researcher deciding whether to re-read a
plate needs to know what it costs them if they do not. The table in this file is
the translation, one entry per code that actually exists in the four contracts
(framework/contracts/*.schema.json) plus the validator's own structural codes
(framework/validator.py). Nothing is invented: every entry is traceable to a
check in one of those files.

Seams for a model, both clearly named and both off by default:

    ArchitectConversation.phrasing_hook   every line a researcher reads passes
        through `_say`. Set the hook to a callable and a model re-words the
        text for this lab's vocabulary. Default None: the text is unchanged.

    _UNKNOWN / `_phrasing_for`             when a new code appears that the
        table does not cover, the fallback hands over the validator's own words
        verbatim and says it has no translation. That is the right place for a
        model to generate a Phrasing. It is deliberately not the place where
        one is required: a new code must still produce a usable question with
        no model present.

Standard library only. No network, no LLM, no new dependency.
"""
from __future__ import annotations

import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from architect.contract import (  # noqa: E402
    Checked, Conversation, Finding, Move, Question, Specification, Step,
    Verdict,
)

WIDTH = 78
MAX_ADVICE = 3          # a system that always has an opinion stops being read
MAX_PATHS_SHOWN = 3


# --------------------------------------------------------------------------- #
#  How to put a finding to a person
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Phrasing:
    """One row of the code -> plain English table.

    `what` and `cost` may use {n} (the count) and {items} ("6 samples").
    `options` are imperative: each one names an action the Architect can carry
    out, and what it leaves behind. `recommended` is an index into options, or
    None where the choice is a scientific one the Architect must not make.
    """
    subject: str
    what: str
    cost: str
    options: tuple[str, ...]
    recommended: int | None = None
    because: str = ""
    fabrication: bool = False       # the only "fix" would invent a record
    note: str = ""                  # one extra line, where one is warranted


_FABRICATION_LINE = (
    "Nothing here can be filled in by this system. A value supplied to make "
    "the check pass would be a fabricated record, and it would pass."
)


# --- codes from framework/contracts/*.schema.json -------------------------- #
_TABLE: dict[str, Phrasing] = {

    # build_to_test
    "double_booked_location": Phrasing(
        subject="position clash",
        what="{items} on the plate. In each case two rows claim the same "
             "container and well, so at least one of them is about a well "
             "that held something else.",
        cost="Test reads the well once and attaches the result to whichever "
             "row it finds first. The number will look perfectly ordinary and "
             "belong to the wrong construct. Nothing downstream can detect "
             "it; it surfaces months later as a result that will not "
             "reproduce.",
        options=(
            "Send the {n} clash{es} back to Build and have it re-export the "
            "plate map from the liquid-handler worklist, then re-run the "
            "check. Costs one re-export; changes no data.",
            "Drop the {n} affected sample{s} from this handover and record "
            "them in not_delivered as 'position unresolved'. Test proceeds "
            "with the rest and the gap is on the record.",
        ),
        recommended=0,
        because="the worklist is the record of where things actually sat, and "
                "it still exists",
        fabrication=True,
        note="Deciding which sample sat where, without the worklist, would be "
             "writing a lab record from a guess.",
    ),
    "duplicate_sample_id": Phrasing(
        subject="repeated sample id",
        what="{items}. In each case one name is on more than one well, so two "
             "different wells are travelling under a single identifier.",
        cost="Every measurement keyed on that name afterwards is ambiguous. "
             "Learn will pool or overwrite the two without reporting that it "
             "did, and the model will be fitted to an average of two things "
             "nobody meant to average.",
        options=(
            "Go back to the phase that wrote the ids and have it re-export "
            "them from the instrument or LIMS record, then re-run the check.",
            "Drop every row carrying a duplicated id from this handover and "
            "report those wells as unidentified. The data is kept out of the "
            "model rather than silently merged into it.",
        ),
        recommended=0,
        because="the ids exist in the source record; renaming one here would "
                "be choosing which well is which",
        fabrication=True,
    ),
    "unknown_design_item": Phrasing(
        subject="sample",
        what="{items} carrying a design item id that Design never committed "
             "to. Either Build labelled the sample wrong, or something was "
             "built that was never designed.",
        cost="A result that belongs to nothing. It cannot be compared with the "
             "panel, and next round's model has a point it cannot explain.",
        options=(
            "Have Build check the {n} label{s} against the order sheet and "
            "correct them there. Cheapest, and the most likely cause.",
            "Have Design add the item{s} to what it committed to, if {they} "
            "{are} genuinely intended and the design record is the thing "
            "that is incomplete.",
            "Drop the {n} sample{s} from this handover and record them as "
            "unattributed.",
        ),
        recommended=0,
        because="a mislabelled sample is the common case and it is fixed at "
                "the source, not here",
    ),
    "missing_quantity": Phrasing(
        subject="sample",
        what="{items} with no value for a measurement the use case requires "
             "before the next phase may use the data.",
        cost="The phase can start, but those samples cannot be compared with "
             "the rest - the measurement is required precisely because the "
             "comparison depends on it. Unrecorded, the gap looks like a bad "
             "result instead of a missing one.",
        options=(
            "Go back to Build with the {n} named sample{s} and attach the "
            "instrument output, if the file exists.",
            "Re-measure the {n} sample{s}. This only works while the plate or "
            "the culture still exists, so it is a decision with a clock on it.",
            "Report the {n} sample{s} as incomplete, hand over the rest, and "
            "record in the ledger that those have no value for this quantity. "
            "Honest, and the gap stays visible next round.",
        ),
        recommended=0,
        because="a file that was written and not collected is the most common "
                "cause, and it costs nothing to look",
        fabrication=True,
    ),
    "unaccounted_item": Phrasing(
        subject="design item",
        what="Design committed to {items} that the Build record neither "
             "contains nor reports as failed. Nothing is wrong with any row; a "
             "row is simply absent.",
        cost="Silent loss. Next round nobody can tell a synthesis that failed "
             "from a measurement nobody looked for, so the candidate is either "
             "written off for the wrong reason or quietly tried again.",
        options=(
            "Have Build state the {n} item{s} in not_delivered with what "
            "happened. A failure is a legitimate outcome; it only has to be "
            "said.",
            "Have Build search for the {n} sample{s} and add {them}, if "
            "{they} exist and were missed in the export.",
        ),
        recommended=0,
        because="a stated failure is a usable result and an omission is not",
        fabrication=True,
    ),

    # design_to_build
    "double_booked_position": Phrasing(
        subject="position clash",
        what="{items} on the order plate. In each case two ordered sequences "
             "are assigned to the same well.",
        cost="The provider synthesises one of them and drops the other without "
             "saying so. You pay for the panel and receive the panel minus "
             "one, and the missing one looks like a synthesis failure.",
        options=(
            "Have Design re-lay the order plate and re-issue positions, then "
            "re-run the check. Nothing physical exists yet, so this costs "
            "nothing but a re-export.",
            "Drop one of each clashing pair from the order. Which one is a "
            "choice about the panel, so name them and the Architect will carry "
            "it out and record it.",
        ),
        recommended=0,
        because="the order has not gone out; a layout is a plan, and a plan can "
                "be redrawn without touching a record",
    ),
    "duplicate_order_item": Phrasing(
        subject="design item",
        what="{items} ordered twice in the same order.",
        cost="You pay twice for one sequence, and Build receives two wells "
             "that look like replicates but were never planned as replicates. "
             "Learn will treat them as independent points.",
        options=(
            "Remove the duplicate order line{s} and re-run the check. The "
            "panel is unchanged.",
            "Keep both and declare them as intended replicates in the order, "
            "so the duplication is a stated design choice rather than an "
            "accident.",
        ),
        recommended=0,
        because="unless the replication was intended, the second line is cost "
                "with no information in it",
    ),
    "unbound_order_item": Phrasing(
        subject="order line",
        what="{items} being ordered with nothing saying which crate entity "
             "{they} came from. A sequence with no stated origin.",
        cost="When the construct works, you cannot say what it was derived "
             "from. Under the Nagoya Protocol you cannot show the material was "
             "collected legally, and no partner can re-obtain it.",
        options=(
            "Search the crate for the entity each line came from and add the "
            "binding. If the search finds nothing, that is the answer: there "
            "is no origin to record.",
            "Drop the {n} unbound line{s} from the order. The panel shrinks by "
            "{n} and every remaining line has a traceable origin.",
        ),
        recommended=0,
        because="the binding either exists in the crate or does not; looking "
                "settles it",
        fabrication=True,
        note="Writing a binding that the crate does not support would "
             "fabricate the origin of a sequence.",
    ),
    "missing_crate_entity": Phrasing(
        subject="binding",
        what="{items}, each pointing at a crate entity this crate does not "
             "contain. The chain of custody refers to something that is not "
             "here.",
        cost="The handover claims a provenance it cannot show. Anyone checking "
             "it later - a reviewer, a partner, an audit - finds a dangling "
             "reference and has to treat the whole chain as unverified.",
        options=(
            "Find the entity in the source crate and add it, with its own "
            "provenance, then re-run the check.",
            "Remove the {n} binding{s} and the order line{s} that depend on "
            "them.",
        ),
        recommended=0,
        because="the entity usually exists in the crate the package was built "
                "from and was lost in the export",
    ),
    "broken_provenance_chain": Phrasing(
        subject="candidate",
        what="{items} cannot be traced, link by link, back to a physical "
             "sample. Somewhere in the derivation a step was never recorded.",
        cost="The sequence has no origin that can be shown. It cannot be "
             "re-collected, the result cannot be reproduced by anybody else, "
             "and for field material the legal basis for using it cannot be "
             "demonstrated. This is the failure the whole chain exists to stop.",
        options=(
            "Have the person who did that step record it, then re-run the "
            "check. Usually one derivation link, known to one person.",
            "Drop the {n} candidate{s} from the order and record why. The "
            "panel is smaller and entirely traceable.",
        ),
        recommended=0,
        because="the missing step is usually known and merely unwritten, and "
                "once written it holds for every future round",
        fabrication=True,
        note="Supplying the missing step would invent where a sequence came "
             "from. That is the one thing this system must never do.",
    ),
    "missing_provenance": Phrasing(
        subject="entity",
        what="{items} missing a property the use case requires on that kind "
             "of entity - a collection site, a storage condition, a registry "
             "accession.",
        cost="Without it the material cannot be re-obtained and the result "
             "cannot be reproduced. For located material it is also what "
             "shows the collection was lawful.",
        options=(
            "Pull the value from the field or freezer record and add it to the "
            "crate. It is a fact somebody wrote down, not a new measurement.",
            "Drop the candidates derived from the {n} entit{ies} from this "
            "order.",
            "Accept the gap: hand over as it is and record in the ledger that "
            "these entities are incompletely described and why.",
        ),
        recommended=0,
        because="these are usually recorded somewhere outside the crate and "
                "only need to be brought in",
        fabrication=True,
    ),
    "unaligned_key": Phrasing(
        subject="key",
        what="{items} in this package with no agreed term behind {them}. The "
             "data is there; nothing can query it, here or at any partner.",
        cost="The column is invisible. It will not appear in the knowledge "
             "graph, no cross-site query will return it, and the next team to "
             "need it will record the same thing again under a third name.",
        options=(
            "Draft the one-line mapping in vocabulary/labs/<lab>.json, with a "
            "proposed existing term for each of the {n} key{s}, and put it up "
            "for review. A person decides, once, and every partner gets it.",
            "Open the {n} key{s} as new terms against vocabulary/core.json, if "
            "nothing existing means the same thing.",
            "Hand over as it is: the {n} key{s} travel with the package and "
            "stay unqueryable until somebody decides.",
        ),
        recommended=0,
        because="a mapping is cheap, reviewable, and it only has to be done "
                "once per spelling",
        note="This system may propose the mapping. It may not adopt it: "
             "agreeing a term is a decision for the people who share it.",
    ),
    "checksum_mismatch": Phrasing(
        subject="checksum",
        what="The checksum travelling with this package does not match the "
             "crate it is supposed to attest.",
        cost="Either the crate changed after the checksum was taken, or the "
             "checksum was written by hand. Until you know which, nothing "
             "downstream can claim to have validated this crate - and a "
             "checksum nobody trusts is worse than none, because it looks like "
             "an assurance.",
        options=(
            "Recompute the checksum from the crate as it stands and record "
            "both values and the fact it was recomputed. The crate is then "
            "attested as it is now, and the discrepancy is on the record.",
            "Find out what changed: compare this crate against the version the "
            "checksum was taken from before anything is recomputed.",
        ),
        recommended=1,
        because="recomputing makes the mismatch disappear without answering "
                "it, so it is worth one look first",
    ),
    "missing_file": Phrasing(
        subject="file",
        what="The crate names {items} it does not contain. It promises data "
             "it does not carry.",
        cost="Whatever cites the file cannot be checked by anybody. A reviewer "
             "reading the crate sees a reference; following it, they find "
             "nothing.",
        options=(
            "Find the {n} file{s} and add {them} to the crate.",
            "Remove the entity that names each missing file, and record that "
            "the data was not available.",
        ),
        recommended=0,
        because="the file usually exists outside the crate and was not packed",
        fabrication=True,
        note="An agent cannot create the data the file was supposed to hold.",
    ),
    "flagged_entity": Phrasing(
        subject="ordered entity",
        what="The crate states something about {items} that the receiving "
             "phase has to act on - a sequence recorded as partial, a value "
             "outside what the use case accepts. The crate is not wrong. It is "
             "telling the truth about the material.",
        cost="If this is passed on without being said, Build synthesises a "
             "truncated gene and nobody told it. The result then looks like an "
             "enzyme that does not work, rather than a gene that was never "
             "whole.",
        options=(
            "Hand over and record explicitly that Build was told about the {n} "
            "entit{ies} and accepted them knowingly. Nothing is dropped and "
            "nothing is hidden.",
            "Drop the {n} candidate{s} from the order, if building a partial "
            "construct is not worth a well.",
        ),
        recommended=0,
        because="the information is accurate and useful; it only has to travel "
                "with the material",
    ),
    "exceeds_stated_limit": Phrasing(
        subject="construct",
        what="The order contains more constructs than the receiving phase "
             "said it can build. Both numbers are in the sentinel's line "
             "below, and they came from Build's own crate, not from here.",
        cost="Build builds what it can and the remainder quietly does not "
             "exist, or the round goes over budget. Either way the panel that "
             "gets measured is not the panel that was designed, and nobody "
             "recorded the difference.",
        options=(
            "Have Build raise the limit in its own crate, with the reason and "
            "the source, if the capacity is actually there.",
            "Have Design select a smaller panel and state which candidates "
            "were dropped and why. The Architect will carry out the drop once "
            "the list is named.",
            "Split the panel across two rounds and order the first part now, "
            "if the limit is per round rather than absolute.",
        ),
        recommended=None,
        because="which candidates to lose is a scientific choice about the "
                "experiment, and this system does not make it",
    ),

    # learn_to_design
    "duplicate_recommendation_id": Phrasing(
        subject="repeated recommendation id",
        what="{items}. Two recommendations are travelling under one name, and "
             "they may not be the same recommendation.",
        cost="Next round's design cannot refer to either of them "
             "unambiguously, and the ledger will read as though one of them "
             "never happened.",
        options=(
            "Have Learn re-issue the ids from its own record and resubmit.",
            "Drop the colliding recommendations from this handover and carry "
            "the rest forward.",
        ),
        recommended=0,
        because="renaming one here would hide the collision rather than "
                "resolve it, and the two may be different things",
        fabrication=True,
    ),
    "duplicate_rank": Phrasing(
        subject="tied rank",
        what="{items} in Learn's ordering, each claimed by more than one "
             "recommendation. The ordering is Learn's judgement, and here it "
             "did not express one.",
        cost="If the tie is broken by position in the file, next round is "
             "prioritised by an accident of export order, and it will look "
             "like a decision somebody made.",
        options=(
            "Have Learn break the tie and resubmit the ranking.",
            "Record the tie explicitly and let Design take the {n} "
            "recommendation{s} at equal priority. Honest, and it survives into "
            "the ledger.",
        ),
        recommended=0,
        because="the ranking is the point of the handover; a tie resolved by "
                "file order is not a ranking",
    ),
    "unsupported_recommendation": Phrasing(
        subject="recommendation",
        what="{items} citing evidence that is not in the results {they} "
             "claim to have learned from.",
        cost="A recommendation with no measurement behind it. Next round would "
             "be built on something nobody can trace back to an experiment, "
             "which is precisely what this chain exists to prevent.",
        options=(
            "Add the missing result{s} to what Learn was given, if the "
            "measurement exists and was left out of the handover.",
            "Withdraw the {n} recommendation{s}. The round proceeds on the "
            "ones that are supported.",
        ),
        recommended=0,
        because="the measurement often exists and was simply not passed in; "
                "if it does not, the recommendation has nothing behind it",
        fabrication=True,
    ),

    # test_to_learn
    "unusable_reading": Phrasing(
        subject="reading",
        what="{items} that do not state the conditions a model needs before "
             "it is fitted to {them}: whether the blank was subtracted, how "
             "many replicates there were, whether the value sat inside the "
             "instrument's range.",
        cost="A value below the limit of quantification is not a small value, "
             "and one colony is not a measurement of a strain. A model fitted "
             "on these learns the instrument instead of the biology, and it "
             "will do it convincingly.",
        options=(
            "Attach the run record or instrument export for the {n} "
            "reading{s}. These are facts about the run and they were written "
            "down somewhere.",
            "Exclude the {n} reading{s} from this handover and state why. "
            "Learn fits fewer points and knows which are missing.",
            "Accept them and record that the model was fitted on readings whose "
            "conditions are unknown. Only worth doing if you intend to say so "
            "in the write-up.",
        ),
        recommended=0,
        because="the conditions of a run are recorded by the instrument, not "
                "decided afterwards",
        fabrication=True,
    ),
}


# --- the same code means different things in different handovers ----------- #
_OVERRIDES: dict[tuple[str, str], Phrasing] = {
    ("learn_to_design", "unknown_design_item"): Phrasing(
        subject="recommendation",
        what="{items} proposing a variant of something that was not built "
             "and measured this round.",
        cost="It will be read as an improvement on a measured result when it "
             "is not. If it is actually a new candidate, saying so is what "
             "lets next round judge it on the right basis.",
        options=(
            "Have Learn point the {n} recommendation{s} at the item they were "
            "derived from, if it is in the results and was missed.",
            "Have Learn re-declare them as new candidates rather than "
            "variants, which is what they are.",
            "Withdraw the {n} recommendation{s} from this round.",
        ),
        recommended=1,
        because="a new candidate is a legitimate recommendation; it only has "
                "to be labelled as one",
    ),
    ("learn_to_design", "missing_quantity"): Phrasing(
        subject="recommendation",
        what="{items} missing a prediction the use case requires.",
        cost="Design cannot size or rank the next round against a prediction "
             "that does not exist, so it will rank on something else and not "
             "record that it did.",
        options=(
            "Ask the model for the missing prediction{s} and resubmit. The "
            "model exists and the input is there.",
            "Report the {n} recommendation{s} as incomplete and let Design "
            "rank them last, explicitly, rather than by accident.",
            "Withdraw the {n} recommendation{s}.",
        ),
        recommended=0,
        because="the prediction is a model run, not a measurement, so it can "
                "be obtained",
        fabrication=True,
    ),
    ("test_to_learn", "missing_quantity"): Phrasing(
        subject="result",
        what="{items} missing a measurement the use case requires before "
             "Learn may use the data.",
        cost="Learn fits on fewer points than the design assumed, and unless "
             "the gap is written down now, nothing downstream will say which "
             "points are absent or why the model is weaker than expected.",
        options=(
            "Find the instrument output for the {n} sample{s} and attach it.",
            "Re-measure, while the material still exists.",
            "Report the {n} sample{s} as incomplete and record the gap. Learn "
            "then knows what it is missing instead of inferring it.",
        ),
        recommended=0,
        because="an unread file is the usual cause and looking costs nothing",
        fabrication=True,
    ),
}


# --- the validator's own structural codes (framework/validator.py) --------- #
_STRUCTURAL_COST = (
    "This is the shape of the record, not the experiment. Left alone the "
    "package cannot be read by the next phase at all, so nothing downstream "
    "happens - but no measurement is in question."
)
_STRUCTURAL_OPTIONS = (
    "Send the {n} field{s} back to the phase agent that wrote them and have it "
    "re-emit the package. Mechanical, and it is where the shape is decided.",
    "Correct the {n} field{s} in place where the intended value is "
    "unambiguous from the record, and record that the package was reshaped.",
)
_STRUCTURAL: dict[str, str] = {
    "missing_field": "{items} required by the contract {are} absent from "
                     "the package.",
    "wrong_type": "{items} holding a value of the wrong kind - a number "
                  "where text was required, or the reverse.",
    "bad_format": "{items} that do not match the identifier format this use "
                  "case uses, so nothing will match {them} up across phases.",
    "not_in_enum": "{items} holding a value outside the list the contract "
                   "allows.",
    "wrong_const": "{items} holding a value the contract fixes to one "
                   "thing.",
    "out_of_range": "{items} holding a number outside the range the "
                    "contract allows.",
    "too_few_items": "{items} shorter than the contract requires - a list "
                     "that has to carry something is empty or nearly so.",
}
for _code, _what in _STRUCTURAL.items():
    _TABLE.setdefault(_code, Phrasing(
        subject="field",
        what=_what,
        cost=_STRUCTURAL_COST,
        options=_STRUCTURAL_OPTIONS,
        recommended=0,
        because="the agent that wrote the field is the one that knows what it "
                "meant",
    ))

_UNKNOWN = Phrasing(
    subject="finding",
    what="The sentinel reported {items} under a code this module has no plain "
         "translation for. Its own words are below, unedited, because a "
         "paraphrase of something not understood is worse than a quotation.",
    cost="Unknown. Until somebody reads the finding, the honest position is "
         "that the cost is not established.",
    options=(
        "Put the {n} finding{s} to the person who wrote the contract check, "
        "verbatim, and hold the handover until there is an answer.",
        "Send the handover back to the phase that produced it with the "
        "findings attached.",
    ),
    recommended=0,
    because="an unrecognised check is a gap in this module, not a licence to "
            "guess what it meant",
)


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _plural(n: int, noun: str) -> str:
    if n == 1:
        return f"1 {noun}"
    if noun.endswith(("s", "x", "ch", "sh")):
        return f"{n} {noun}es"
    if noun.endswith("y") and not noun.endswith(("ay", "ey", "oy", "uy")):
        return f"{n} {noun[:-1]}ies"
    return f"{n} {noun}s"


def _phases(handover: str) -> tuple[str, str]:
    """('build_to_test') -> ('build', 'test'). Tolerant of an odd name."""
    if "_to_" in handover:
        left, right = handover.split("_to_", 1)
        return left, right
    return handover, ""


def _pretty(handover: str) -> str:
    sender, receiver = _phases(handover)
    if not receiver:
        return handover
    return f"{sender.capitalize()} -> {receiver.capitalize()}"


def _wrap(text: str, indent: str = "") -> str:
    return textwrap.fill(" ".join(text.split()), width=WIDTH,
                         initial_indent=indent, subsequent_indent=indent)


def _label(group_index: int, option_index: int) -> str:
    return f"{group_index}{chr(ord('a') + option_index)}"


@dataclass
class _Group:
    """Findings that are one question: same code, same severity."""
    handover: str
    code: str
    blocking: bool
    findings: list[Finding]
    phrasing: Phrasing

    @property
    def n(self) -> int:
        return len(self.findings)

    @property
    def items(self) -> str:
        return _plural(self.n, self.phrasing.subject)

    def fill(self, text: str) -> str:
        """Put the count into the phrasing, and keep the grammar honest.

        One finding and six findings are the same sentence with a different
        number in it, and a sentence that says "1 samples are" reads as a bug
        in the system rather than a problem with the plate.
        """
        n = self.n
        return text.format(
            n=n, items=self.items,
            s="" if n == 1 else "s",
            es="" if n == 1 else "es",
            ies="y" if n == 1 else "ies",
            are="is" if n == 1 else "are",
            they="it" if n == 1 else "they",
            them="it" if n == 1 else "them",
            this="this" if n == 1 else "these",
        )

    def paths(self) -> str:
        shown = [f.path for f in self.findings[:MAX_PATHS_SHOWN] if f.path]
        if not shown:
            return ""
        extra = self.n - len(shown)
        return ", ".join(shown) + (f" and {extra} more" if extra > 0 else "")


# --------------------------------------------------------------------------- #
#  The Conversation
# --------------------------------------------------------------------------- #
class ArchitectConversation:
    """Implements the `Conversation` protocol from architect/contract.py.

    Deterministic and offline. `phrasing_hook`, if set, is the one seam where
    a model may re-word what the researcher reads; nothing in the logic depends
    on it being present.
    """

    asked_by = "architect"

    def __init__(self, phrasing_hook: Callable[[str, dict], str] | None = None):
        # SEAM: (text, context) -> text. A model could translate the table's
        # English into this lab's own words, or shorten it for a chat window.
        # It must not be allowed to add options: the options are the commitments
        # the Architect can keep, and a model does not know what those are.
        self.phrasing_hook = phrasing_hook

    # -- the seam ----------------------------------------------------------- #
    def _say(self, text: str, **context: object) -> str:
        if self.phrasing_hook is None:
            return text
        try:
            out = self.phrasing_hook(text, dict(context))
            return out if isinstance(out, str) and out.strip() else text
        except Exception:
            return text          # a failed rewording never costs the message

    # -- grouping ----------------------------------------------------------- #
    def _phrasing_for(self, handover: str, code: str) -> Phrasing:
        # SEAM: a model belongs here, generating a Phrasing for a code the
        # table does not know. Until then the fallback is honest rather than
        # fluent, which is the right way round.
        override = _OVERRIDES.get((handover, code))
        if override is not None:
            return override
        return _TABLE.get(code, _UNKNOWN)

    def group(self, checked: Checked) -> list[_Group]:
        """Six wells missing a unit is one group with six findings in it.

        Blocking first, then flags; within each, the biggest group first, so
        the thing that affects most of the plate is read first.
        """
        buckets: dict[tuple[str, bool], list[Finding]] = {}
        for finding in checked.findings:
            buckets.setdefault((finding.code, finding.blocking), []).append(finding)

        groups = [
            _Group(checked.handover, code, blocking, findings,
                   self._phrasing_for(checked.handover, code))
            for (code, blocking), findings in buckets.items()
        ]
        groups.sort(key=lambda g: (not g.blocking, -g.n, g.code))
        return groups

    # -- explain ------------------------------------------------------------ #
    def explain(self, checked: Checked, spec: Specification) -> Question:
        """One question for the whole handover. Never six for six wells."""
        groups = self.group(checked)
        blocking = [g for g in groups if g.blocking]
        flags = [g for g in groups if not g.blocking]

        if checked.verdict is Verdict.REFUSED or blocking:
            return self._refusal(checked, spec, blocking, flags)
        if checked.verdict is Verdict.ACCEPTED_WITH_FLAGS or flags:
            return self._accepted_with_flags(checked, spec, flags)
        return self._clean(checked, spec)

    def explain_each(self, checked: Checked, spec: Specification) -> list[Question]:
        """One question per group, for callers that want to ask serially.

        `explain` is the protocol and the default; this exists because a chat
        interface sometimes wants to put one thing at a time, and the grouping
        must be the same either way.
        """
        out: list[Question] = []
        for index, group in enumerate(self.group(checked), start=1):
            out.append(self._question_for_group(checked, spec, group, index))
        return out

    # -- the three shapes of answer ----------------------------------------- #
    def _refusal(self, checked: Checked, spec: Specification,
                 blocking: list[_Group], flags: list[_Group]) -> Question:
        sender, receiver = _phases(checked.handover)
        decisions = len(blocking)
        headline = (
            f"{_pretty(checked.handover)} refused: "
            f"{_plural(decisions, 'thing')} to decide"
            f" ({_plural(len(checked.blocking), 'finding')}"
            + (f", plus {_plural(len(checked.flags), 'flag')} that do not "
               f"block)"
               if checked.flags else ")")
        )

        lines: list[str] = [_wrap(
            f"{receiver.capitalize() or 'The next phase'} does not start "
            f"until one of the options below is chosen. The package itself is "
            f"unchanged and nothing has been dropped, here or anywhere else."
        )]
        if ctx := self._context_line(spec, receiver):
            lines += ["", _wrap(ctx)]

        options: list[str] = []
        recommended: str | None = None
        because = ""

        for index, group in enumerate(blocking, start=1):
            lines += [""] + self._group_block(group, index, spec)
            for opt_index, option in enumerate(group.phrasing.options):
                options.append(f"[{_label(index, opt_index)}] "
                               + self._say(group.fill(option), code=group.code))
            if recommended is None and group.phrasing.recommended is not None:
                recommended = f"[{_label(index, group.phrasing.recommended)}]"
                because = group.phrasing.because

        if flags:
            lines += [""] + self._flag_block(flags, len(blocking), spec)

        options.append("[stop] Stop the run here. Nothing goes on, the package "
                       "and the ledger stay exactly as they are.")

        if recommended is None:
            because = (blocking[0].phrasing.because if blocking else
                       "there is no default here")
            because = (f"no option is recommended: {because}")

        return Question(asked_by=self.asked_by, headline=headline,
                        detail="\n".join(lines), options=options,
                        recommended=recommended, because=because)

    def _accepted_with_flags(self, checked: Checked, spec: Specification,
                             flags: list[_Group]) -> Question:
        sender, receiver = _phases(checked.handover)
        next_phase = receiver.capitalize() or "The next phase"
        headline = (f"{_pretty(checked.handover)} accepted with "
                    f"{_plural(len(checked.flags), 'flag')} - "
                    f"nothing is blocked")

        lines = [_wrap(
            f"This handover is valid. {next_phase} can start now, and will "
            f"unless you say otherwise. What follows is not a list of errors: "
            f"the crate is stating something true about the material that "
            f"{next_phase.lower() if receiver else 'the next phase'} has to "
            f"be told. Nothing here needs repairing."
        )]
        if ctx := self._context_line(spec, receiver):
            lines += ["", _wrap(ctx)]

        options = [f"[1a] Go on to {next_phase} and record "
                   f"the {_plural(len(checked.flags), 'flag')} in the "
                   f"ledger as "
                   f"knowingly accepted."]
        for index, group in enumerate(flags, start=2):
            lines += [""] + self._group_block(group, index, spec, flag=True)
            for opt_index, option in enumerate(group.phrasing.options):
                options.append(f"[{_label(index, opt_index)}] "
                               + self._say(group.fill(option), code=group.code))

        return Question(
            asked_by=self.asked_by, headline=headline,
            detail="\n".join(lines), options=options, recommended="[1a]",
            because="the package is valid and the flags are information, not "
                    "defects; recording them is what makes them travel",
        )

    def _clean(self, checked: Checked, spec: Specification) -> Question:
        sender, receiver = _phases(checked.handover)
        return Question(
            asked_by=self.asked_by,
            headline=f"{_pretty(checked.handover)} accepted - nothing to decide",
            detail=_wrap(f"The package satisfies its contract with no "
                         f"findings. "
                         f"{receiver.capitalize() or 'The next phase'} can "
                         f"start. This is here so the ledger has a line for "
                         f"it, not because anything is being asked of you."),
            options=[f"[1a] Go on to "
                     f"{receiver.capitalize() or 'the next phase'}."],
            recommended="[1a]",
            because="there is nothing in the way",
        )

    # -- blocks ------------------------------------------------------------- #
    def _question_for_group(self, checked: Checked, spec: Specification,
                            group: _Group, index: int) -> Question:
        phrasing = group.phrasing
        headline = (f"{_pretty(checked.handover)}: "
                    + self._say(group.fill(phrasing.what).split(".")[0] + ".",
                                code=group.code)
                    + ("" if group.blocking else " (flag, not blocking)"))
        options = [f"[{_label(index, i)}] " + self._say(group.fill(o),
                                                        code=group.code)
                   for i, o in enumerate(phrasing.options)]
        if group.blocking:
            options.append("[stop] Stop the run here.")
        recommended = (f"[{_label(index, phrasing.recommended)}]"
                       if phrasing.recommended is not None else None)
        return Question(asked_by=self.asked_by, headline=headline,
                        detail="\n".join(self._group_block(
                            group, index, spec, flag=not group.blocking)),
                        options=options, recommended=recommended,
                        because=phrasing.because)

    def _group_block(self, group: _Group, index: int, spec: Specification,
                     flag: bool = False) -> list[str]:
        phrasing = group.phrasing
        mark = "flag, does not block" if flag else "blocking"
        lines = [f"{index}. [{group.code}] {_plural(group.n, 'finding')}, "
                 f"{mark}",
                 _wrap(self._say(group.fill(phrasing.what), code=group.code),
                       "   ")]

        if paths := group.paths():
            lines.append(_wrap(f"Where: {paths}", "   "))

        if requirement := self._requirement_line(group, spec):
            lines.append(_wrap(requirement, "   "))

        lines.append(_wrap("If nothing is done: "
                           + self._say(group.fill(phrasing.cost),
                                       code=group.code), "   "))
        if phrasing.note:
            lines.append(_wrap(group.fill(phrasing.note), "   "))
        if phrasing.fabrication:
            lines.append(_wrap(_FABRICATION_LINE, "   "))

        # The sentinel's own words, once per group, quoted rather than
        # paraphrased. For an unknown code this is the whole of what we know.
        first = group.findings[0]
        lines.append(_wrap(f"Sentinel, verbatim: {first.message}", "   "))
        if group.phrasing is _UNKNOWN and first.fix_hint:
            lines.append(_wrap(f"Contract hint, verbatim: {first.fix_hint}",
                               "   "))

        lines.append("   What can be done:")
        for opt_index, option in enumerate(phrasing.options):
            lines.append(_wrap(
                f"[{_label(index, opt_index)}] "
                + self._say(group.fill(option), code=group.code), "     "))
        if phrasing.recommended is None:
            lines.append(_wrap("No recommendation: " + phrasing.because,
                               "     "))
        else:
            lines.append(_wrap(
                f"Recommended: [{_label(index, phrasing.recommended)}], "
                f"because {phrasing.because}.", "     "))
        return lines

    def _flag_block(self, flags: list[_Group], offset: int,
                    spec: Specification) -> list[str]:
        total = sum(g.n for g in flags)
        lines = [_wrap(
            f"Flags ({total}). These are not part of the decision above and "
            f"they are not errors. A flag does not stop a handover: it is "
            f"something the crate states honestly and the receiving phase has "
            f"to be told about. Do not repair these - they are correct."
        )]
        for index, group in enumerate(flags, start=offset + 1):
            lines += [""] + self._group_block(group, index, spec, flag=True)
        return lines

    # -- what the specification can add ------------------------------------- #
    def _context_line(self, spec: Specification, receiver: str) -> str:
        """One line of context from the specification, or nothing."""
        agreed = _safe(lambda: dict(getattr(spec, "agreed", {}) or {}), {})
        bits = [str(agreed[key]) for key in ("use_case", "profile", "objective")
                if agreed.get(key)]
        if not bits:
            return ""
        return "This run: " + "; ".join(bits[:2]) + "."

    def _requirement_line(self, group: _Group, spec: Specification) -> str:
        """For a missing requirement, name what the use case asks for.

        The validator says "the profile requires this measurement". A person
        wants to know which measurement, and the specification is where that
        lives - so it is read here rather than guessed at.
        """
        if group.code not in ("missing_quantity", "missing_provenance"):
            return ""
        sender, _ = _phases(group.handover)
        requirements = _safe(lambda: spec.requirements_for(sender), {})
        quantities = []
        if isinstance(requirements, dict):
            for item in (requirements.get("required_quantities") or []):
                if isinstance(item, dict) and item.get("quantity"):
                    unit = item.get("unit")
                    quantities.append(f"{item['quantity']}"
                                      + (f" ({unit})" if unit else ""))
        if not quantities:
            return ""
        return "The use case requires: " + ", ".join(quantities[:4]) + "."

    # -- advise ------------------------------------------------------------- #
    def advise(self, spec: Specification, history: list[Step]) -> list[str]:
        """Unprompted observations. Empty is the usual and correct answer.

        Each line here has to be worth interrupting somebody for, and has to
        say what to do. Everything else is noise that teaches people to skip
        this field.
        """
        out: list[str] = []

        # 1. An unanswered question outranks everything: nothing is moving.
        last = history[-1] if history else None
        if last is not None and _safe(
                lambda: last.decision is not None
                and last.decision.move is Move.ASK, False):
            asked = _safe(lambda: last.decision.question.headline, "") or ""
            out.append(f"Nothing is moving until you answer the open question"
                       + (f": {asked}" if asked else "") + ".")

        # 2. The same handover refused more than once. Re-running will not
        #    change the data; at that point the decision is which gap to take.
        refusals: dict[str, int] = {}
        for step in history:
            if step.verdict is Verdict.REFUSED:
                refusals[step.phase] = refusals.get(step.phase, 0) + 1
        for phase, count in sorted(refusals.items()):
            if count >= 2:
                out.append(
                    f"{phase} has been refused {count} times. Another re-run "
                    f"will not produce data that does not exist - the open "
                    f"choice is which gap to accept and state.")

        # 3. Going back to the same phase repeatedly is a loop, and a loop
        #    costs plate time that nobody budgeted.
        rewinds: dict[str, int] = {}
        for step in history:
            target = _safe(lambda s=step: (
                s.decision.target_phase
                if s.decision is not None and s.decision.move is Move.GO_BACK
                else None), None)
            if target:
                rewinds[target] = rewinds.get(target, 0) + 1
        for phase, count in sorted(rewinds.items()):
            if count >= 2 and refusals.get(phase, 0) < 2:
                out.append(
                    f"The route has gone back to {phase} {count} times. Worth "
                    f"deciding whether the specification is asking for "
                    f"something that phase cannot deliver.")

        # 4. Things the specification never settled. A run may start without
        #    them; it cannot be written up.
        unresolved = _safe(lambda: list(spec.unresolved() or []), [])
        if unresolved and history:
            named = ", ".join(str(item) for item in unresolved[:3])
            more = f" and {len(unresolved) - 3} more" if len(unresolved) > 3 else ""
            out.append(f"{_plural(len(unresolved), 'thing')} in the "
                       f"specification still "
                       f"have no answer ({named}{more}). The run can continue; "
                       f"it cannot be written up as it stands.")

        # 5. No stated limits, once the run is under way. Limits are what turn
        #    "too many constructs" into a check instead of an argument later.
        limits = _safe(lambda: list(getattr(spec, "limits", []) or []), [])
        if history and not limits:
            out.append("The specification states no limits, so nothing can "
                       "check that a panel is buildable before it is ordered. "
                       "One line per constraint - plate count, budget, reactor "
                       "slots - is enough.")

        return out[:MAX_ADVICE]


def _safe(call: Callable[[], object], default: object):
    """Read from a protocol somebody else implements, without trusting it.

    `Specification` and `Step` are written by other parts of the Architect. A
    conversation that crashes because a field is missing has failed at the one
    moment it exists for, so every read of them goes through here.
    """
    try:
        value = call()
    except Exception:
        return default
    return default if value is None else value


# --------------------------------------------------------------------------- #
#  Seen as a researcher sees it
# --------------------------------------------------------------------------- #
def _render(question: Question) -> str:
    rule = "=" * WIDTH
    out = [rule, _wrap(question.headline), rule, question.detail, "",
           "Options:"]
    for option in question.options:
        out.append(_wrap(option, "  "))
    if question.recommended:
        out.append("")
        out.append(_wrap(f"Recommended: {question.recommended} - "
                         f"{question.because}"))
    elif question.because:
        out.append("")
        out.append(_wrap(question.because.capitalize() + "."))
    return "\n".join(out)


if __name__ == "__main__":
    from architect.contract import Decision

    class _DemoSpec:
        """A specification stub. The real one is ingredient 2."""

        def __init__(self, use_case: str, quantities: list[dict],
                     limits: list[dict], open_items: list[str]):
            self.agreed = {"use_case": use_case,
                           "objective": "raise titre in the named chassis"}
            self.limits = limits
            self._quantities = quantities
            self._open = open_items

        def requirements_for(self, phase: str) -> dict:
            return {"required_quantities": self._quantities}

        def limits_for(self, phase: str) -> list[dict]:
            return self.limits

        def unresolved(self) -> list[str]:
            return list(self._open)

    talk = ArchitectConversation()
    _conforms: Conversation = talk      # the protocol, checked by reading it

    spec = _DemoSpec(
        use_case="bioprospecting",
        quantities=[{"quantity": "dna_concentration", "unit": "ng/uL"},
                    {"quantity": "purity_260_280", "unit": "ratio"}],
        limits=[{"quantity": "library_size", "value": 48, "unit": "constructs",
                 "from": "build crate"}],
        open_items=["which substrate panel Test will use",
                    "who signs off the Nagoya declaration"],
    )

    # 1. A refusal where one code accounts for most of it: six wells, one
    #    question, the number six in the first line.
    refused_b2t = Checked(
        handover="build_to_test",
        verdict=Verdict.REFUSED,
        findings=[
            Finding("missing_quantity", f"samples[{i}].qc.measurements",
                    "the profile requires this measurement: dna_concentration",
                    True,
                    "not auto-fixable: a measurement that was never taken "
                    "cannot be supplied. Either the instrument output is "
                    "found, or the sample is reported as incomplete")
            for i in (3, 4, 5, 11, 12, 27)
        ] + [
            Finding("unaccounted_item", "design_ref.items[9].design_item_id",
                    "'CAND-010': Design committed to this item and the Build "
                    "record neither contains it nor reports it as not "
                    "delivered", True,
                    "not auto-fixable: an absent well has no field to correct."),
        ],
        trace=["validate against build_to_test -> FAIL, 7 error(s)"],
    )

    # 2. Blocking and flags in the same answer. The flags must not read as
    #    errors or somebody repairs a correct crate.
    mixed_d2b = Checked(
        handover="design_to_build",
        verdict=Verdict.REFUSED,
        findings=[
            Finding("broken_provenance_chain", "bindings[2].crate_entity",
                    "no path of derivation from this sequence back to a "
                    "physical sample", True,
                    "not auto-fixable: inventing the missing step would "
                    "fabricate the origin of a sequence"),
            Finding("broken_provenance_chain", "bindings[7].crate_entity",
                    "no path of derivation from this sequence back to a "
                    "physical sample", True,
                    "not auto-fixable: inventing the missing step would "
                    "fabricate the origin of a sequence"),
            Finding("exceeds_stated_limit", "order.items",
                    "61 constructs against a stated limit of 48 constructs "
                    "(from build crate)", True,
                    "not auto-fixable: dropping candidates to fit is a "
                    "scientific choice about which ones to lose"),
            Finding("flagged_entity", "bindings[4].dbtl:completeness",
                    "MGYP000123456: completeness is 'right_partial', not "
                    "'complete'", False,
                    "not auto-fixable, and not a defect in the crate: the "
                    "crate is telling the truth"),
            Finding("flagged_entity", "bindings[18].dbtl:completeness",
                    "MGYP000998877: completeness is 'right_partial', not "
                    "'complete'", False, ""),
            Finding("unaligned_key", "alignment.unaligned",
                    "'od_600_corrected': no term has been agreed for this "
                    "key, so nothing can query it", False,
                    "one reviewed line in vocabulary/labs/<lab>.json ..."),
        ],
        trace=["validate against design_to_build -> FAIL, 3 error(s) + 3 flag(s)"],
    )

    # 3. Accepted, with flags. Valid, going on, and the researcher is told
    #    plainly that there is nothing to fix.
    flagged_d2b = Checked(
        handover="design_to_build",
        verdict=Verdict.ACCEPTED_WITH_FLAGS,
        findings=[
            Finding("flagged_entity", "bindings[4].dbtl:completeness",
                    "MGYP000123456: completeness is 'right_partial', not "
                    "'complete'", False,
                    "not auto-fixable, and not a defect in the crate"),
            Finding("flagged_entity", "bindings[6].dbtl:completeness",
                    "MGYP000445566: completeness is 'left_partial', not "
                    "'complete'", False, ""),
        ],
        trace=["accepted with 2 flag(s)"],
    )

    for checked in (refused_b2t, mixed_d2b, flagged_d2b):
        print(_render(talk.explain(checked, spec)))
        print()

    # advise: once with something worth saying, once with nothing.
    history = [
        Step(phase="design", actor="phase_design", verdict=Verdict.ACCEPTED),
        Step(phase="build_to_test", actor="sentinel_b2t",
             verdict=Verdict.REFUSED,
             decision=Decision(Move.GO_BACK, target_phase="build")),
        Step(phase="build_to_test", actor="sentinel_b2t",
             verdict=Verdict.REFUSED,
             decision=Decision(Move.ASK, because="the gap needs a decision",
                               question=talk.explain(refused_b2t, spec))),
    ]
    print("=" * WIDTH)
    print("advise(), run in trouble:")
    for line in talk.advise(spec, history):
        print(_wrap(f"- {line}", "  "))

    print()
    print("=" * WIDTH)
    print("advise(), clean run with nothing worth saying:")
    quiet_spec = _DemoSpec("bioprospecting", [], [{"quantity": "library_size",
                                                   "value": 48}], [])
    quiet = talk.advise(quiet_spec, [Step(phase="design", actor="phase_design",
                                          verdict=Verdict.ACCEPTED)])
    print(_wrap(f"  {quiet!r}  <- silence is an answer"))
