"""The seam for a structured specification: fields, not a prompt.

Nothing here does any work. It fixes the shape of the thing the interface
renders, the thing the researcher fills in, and the thing the DBTL cycle then
starts from, so those three can be built separately and still fit.

WHY A FORM AND NOT A PROMPT
An open prompt asks the researcher to guess what the system needs. They will
guess differently each time, and two runs of the same project will start from
incomparable statements. A field has a name, a type, a unit, a reason it is
being asked, and a phase it affects - so a half-filled specification can say
precisely what is still missing, and a filled one can be compared with the
next project's.

The questions are also not free. Every field here exists because some contract
or profile will later refuse a handover without it. A field nobody checks is a
field nobody should be asked for, and `why_it_is_asked` has to name what would
go wrong.

TWO LAYERS, AND THEY ARE DIFFERENT THINGS
    a TEMPLATE   the generic form: the fields any DBTL project has to answer
    an INSTANCE  one use case's version, with its own steps, units and vendors

A use case fills in the template. It may add fields, and it may narrow a
field's options. It may not remove a field the template marks `required`,
because that is what makes two projects comparable.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from typing import Any


class Kind(str, Enum):
    """What the interface should render, and what the loader should accept."""
    TEXT = "text"
    LONGTEXT = "longtext"
    NUMBER = "number"
    QUANTITY = "quantity"        # a number that must carry a unit
    CHOICE = "choice"            # one of `options`
    MULTI = "multi"              # several of `options`
    BOOL = "bool"
    LIST = "list"                # free list of short strings
    STEPS = "steps"              # an ordered list of named steps


@dataclass
class Field:
    """One thing the researcher is asked, and why."""
    key: str
    label: str
    kind: Kind
    phase: str | None = None            # design | build | test | learn | None
    required: bool = False
    unit: str | None = None             # for QUANTITY, the unit it must be in
    options: list[str] = dataclass_field(default_factory=list)
    default: Any = None                 # shown, never applied silently
    placeholder: str = ""
    why_it_is_asked: str = ""           # what refuses a handover without it
    feeds: list[str] = dataclass_field(default_factory=list)
    # `feeds` names what this field becomes downstream: a profile key, a
    # `limits` entry, a contract field. A field that feeds nothing is a field
    # that will quietly stop being filled in.

    def unanswered(self, value: Any) -> bool:
        return value is None or value == "" or value == [] or value == {}


@dataclass
class Section:
    """Fields grouped by the decision they serve, in the order they are asked."""
    key: str
    title: str
    intent: str                          # one line: what this section settles
    fields: list[Field] = dataclass_field(default_factory=list)


@dataclass
class Form:
    """A whole specification form: the template, or one use case's instance."""
    name: str
    title: str
    based_on: str | None = None          # the template this instance fills in
    description: str = ""
    sections: list[Section] = dataclass_field(default_factory=list)
    steps: list[dict] = dataclass_field(default_factory=list)
    # `steps` is the use case's own numbered workflow - Anil's 14 for
    # bioprospecting - with which handover follows which step. The Architect
    # needs it to say where in the cycle a run has got to, in the
    # researcher's own vocabulary rather than in phase names.

    def all_fields(self) -> list[Field]:
        return [f for section in self.sections for f in section.fields]

    def field(self, key: str) -> Field | None:
        return next((f for f in self.all_fields() if f.key == key), None)

    def required_keys(self) -> list[str]:
        return [f.key for f in self.all_fields() if f.required]


@dataclass
class Filled:
    """A form with answers. Knows what is still missing and why it matters."""
    form: Form
    values: dict[str, Any] = dataclass_field(default_factory=dict)
    provenance: dict[str, dict] = dataclass_field(default_factory=dict)

    def missing(self) -> list[Field]:
        return [f for f in self.form.all_fields()
                if f.required and f.unanswered(self.values.get(f.key))]

    def ready(self) -> bool:
        return not self.missing()


# What an instance may and may not do to a template. Stated here because it is
# the rule that keeps two use cases comparable, and a rule stated in prose in
# one README is a rule nobody enforces.
INSTANCE_MAY = (
    "add a field",
    "narrow a CHOICE's options to a subset",
    "fix a QUANTITY's unit",
    "supply its own steps and its own labels",
    "make an optional field required",
)
INSTANCE_MAY_NOT = (
    "remove a field the template marks required",
    "widen a CHOICE beyond the template's options",
    "change a field's kind",
    "change what a field feeds",
)
