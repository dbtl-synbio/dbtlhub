# sentinel-oo, read and compared

A briefing on Anil Wipat's `sentinel-oo`, at `dbtlhub/sentinel-oo`, written
against our `framework/`. Everything quoted is quoted from his files; nothing
in his repository was changed.

Read for this: `README.md`, `docs/WRITING_A_CONTRACT.md`,
`docs/SYSTEM_MANUAL.md`, `src/sentinel_oo/contract.py`,
`src/sentinel_oo/rules.py`, `src/sentinel_oo/sentinel.py`,
`src/sentinel_oo/provenance.py`, `src/sentinel_oo/blessing.py`, and both files
in `examples/contracts/`.

**What it is in one line.** A deployable service that stands at one handover,
reads an RO-Crate, checks it against a YAML contract, and returns the same
crate with the record of the check written inside it. "A crate goes in and a
crate comes out... plus a record of what was checked, against which rules, by
which build of the service, with which model if any, and what was found."

**The same ideas, a different object.** Ours is a library plus demos: four
JSON-Schema contracts, a validator, four sentinel agents, a ledger. His is one
generic container with no contract in it — "The service holds no contracts and
knows no handover by name" — plus an HTTP API, an MCP agent interface, and a
`deploy.py` that validates the contracts before it builds anything.

---

## 1. The contract format, key by key

A contract is one YAML file. The reader is `parse()` in `contract.py`. It has
exactly five top-level keys and refuses any sixth:

```python
CONTRACT_KEYS = {"contract", "version", "description", "expects", "requires"}
```

"Five top level keys and nothing else... The name in `contract` is how callers
ask for it, as in `POST /check/mixing_to_coating`. The file name does not
matter; this name does."

| Key | Required | Type | What it is |
|---|---|---|---|
| `contract` | yes | string | The handover's name, the registry key, the URL path segment |
| `version` | yes | string | "A version is what somebody cites in an argument about why a batch was refused." |
| `description` | no | string (folded) | Prose for the plain-words summary. Free text, read by people |
| `expects` | no in code, "write this block" in the docs | list of type names | What kinds of entity the crate must contain, or the handover is refused before any requirement runs |
| `requires` | no in code (empty = no requirements) | list of requirements | The rules |

### A whole minimal contract

This is `examples/contracts/coating_to_inspection.yaml`, complete:

```yaml
contract: coating_to_inspection
version: 0.2.0

description: >
  A second handover in the same worked example, present to demonstrate one
  thing: adding a handover means writing a file like this and nothing else.
  ...

# What this contract is for. A crate containing none of these is refused
# rather than accepted in silence.
expects:
  - CoatedPanel
  - CoatingStep

requires:

  - name: coated_panel_names_its_slot
    applies_to: CoatedPanel
    property: isPartOf
    must: point at something in the crate
    severity: refuse
    message: >-
      This coated panel does not say which rack slot it came off, so the
      recipe that produced it cannot be identified.

  - name: coating_run_is_dated
    applies_to: CoatingStep
    property: endTime
    must: be recorded
    severity: refuse
    message: >-
      The coating step does not say when it finished, so nothing downstream
      can be put in order against the other runs of the day.
```

### Every field of a requirement

```python
REQUIREMENT_KEYS = {
    "name", "applies_to", "property", "named_value", "must",
    "one_of", "of_type", "between", "severity", "message", "repairable",
}
```

| Field | Required | What it does | Validation in `_parse_requirement` |
|---|---|---|---|
| `name` | yes | How the finding names itself. "Use words, not numbers" | non-empty string; must be unique within the file ("two requirements are called ...") |
| `applies_to` | yes | Which entities it reads: `root`, `descriptor`, or a type name (`type:` prefix optional) | non-empty string, not otherwise constrained |
| `property` | one of the two | A property written directly on the entity | `bool(prop) != bool(named)` — "It says both or neither" |
| `named_value` | one of the two | A value hanging off the entity as a separate `PropertyValue` entity | same test |
| `must` | yes (defaults to `be recorded`) | One of exactly four verbs | must be in `MUSTS`, else the whole contract is refused |
| `severity` | yes | `refuse` or `flag` | must be in `SEVERITIES` — no default |
| `message` | yes | The sentence a person reads | non-empty after strip: "A violation nobody can read is not worth raising." |
| `one_of` | no | The only permitted values; hangs off `be recorded` | non-empty list, coerced to `tuple(str(v))` |
| `of_type` | no | Narrows `point at something in the crate` to one kind | non-empty string |
| `between` | only with `be a number between` | `[low, high]` inclusive | list of exactly 2 numbers, `between[0] <= between[1]` |
| `repairable` | no, default `false` | Whether a model may be asked to recover the value from free text | `bool(...)` |

A `NEEDS` table ties a verb to its extra field — currently only
`{"be a number between": "between"}` — and a missing one is an error:
"says 'be a number between' but does not say `between`".

### `applies_to`, precisely

From `rules.py::_targets`: `root` is the crate's root entity, `descriptor` the
metadata-file entity, "Anything else is read as a type". A type means either
`@type` **or** `additionalType` (`types_of`), which is what makes a
domain-specific contract possible at all: "Schema.org has no word for an
coating recipe, and without this a rule could not say 'every recipe' at all:
recipes and racks are both CreativeWork."

Stated limitation: "Types are compared as plain text. Nothing in the service
knows that schema.org considers a `Hotel` to be a kind of `LodgingBusiness`...
the requirement will match nothing and pass silently."

### `named_value`, and why it exists

"Crates following the Process Run Crate profile record most numbers and
strings the second way: the film thickness is not written on the recipe. It is
a separate entity carrying the name `film thickness` and the value `42`, which
the recipe points at."

And — this is the part worth copying — no property name is needed: "Every
reference the entity makes is followed, and only entities of type
`PropertyValue` are read as values. So a step that points at a file, a tool
and a setting will give up only the setting."

### `expects`, and the fault that produced it

```yaml
expects:
  - CoatingRecipe
  - RackSlot
  - IntendedRackLayout
  - ThicknessReading
  - DryingStep
```

This is the single most important thing in his design that is not in ours. It
was added on 11 November 2026 after "deploying two instances and sending a
crate to the wrong one":

| Of the 18 requirements | Count |
|---|---|
| Looked at something in that crate | 6 |
| Matched no entity at all, and passed | 12 |

"So the service said ACCEPTED on a crate it had not meaningfully read. **That
is the worst thing this service can do.** Refusing something good is visible
and sends somebody to look. Blessing something unchecked is silent and looks
like success."

`_expected_types` emits one synthetic `refuse` violation per absent type,
before any requirement is applied. With no `expects` block, `summary()` prints
a warning instead: "⚠ This contract does not say what it is for, so it accepts
any crate whose packaging is sound, including one from another phase."

### What is deliberately absent

"It is not a set of instructions to a model: there is no field for that,
deliberately, and the reader refuses a file that invents one." The reason is
stated in the module docstring: "this service accepts contracts from the
sender, so prompt text in a contract means the sender writes the model's
instructions."

---

## 2. The four verbs, against our ten check kinds

His vocabulary, from `contract.py`:

```python
MUSTS = {
    "be recorded",
    "be unique",
    "point at something in the crate",
    "be a number between",
}
```

"You cannot add a verb by writing a contract... you are blocked until a fifth
is added to the product. That means editing `MUSTS` in
`src/sentinel_oo/contract.py`, adding a branch to `_apply` in
`src/sentinel_oo/rules.py`, and writing tests for both."

Ours, from `framework/validator.py`:

```python
CHECKS = {"unique": _check_unique, "cross_ref": _check_cross_ref,
          "derived": _check_derived,
          "required_quantities": _check_required_quantities,
          "provenance_chain": _check_provenance_chain,
          "required_provenance": _check_required_provenance,
          "entity_value": _check_entity_value,
          "within_limits": _check_within_limits,
          "accounted_for": _check_accounted_for,
          "empty": _check_empty}
```

The two lists are not the same kind of list. His four are **verbs** — one
value, one judgement, applied to a set of entities picked by type. Our ten are
**check kinds** — several of them whole algorithms with their own parameter
sets, three of which read the profile rather than the contract. The honest
mapping:

| His verb | Our nearest | How they differ |
|---|---|---|
| `be recorded` | JSON Schema `required` + `_check_node`'s missing-field branch | His fires per matching entity in a graph and carries an author's sentence; ours fires per document path and reports `sub.get("description", "required field is absent")`. Ours cannot express "every entity of type X must record Y" at all without SHACL. |
| `be recorded` + `one_of` | JSON Schema `enum` / `const` | Same intent. His pairs it with presence in one requirement and admits the cost: "`one_of` hangs off `be recorded`, so when the value is absent both the presence requirement and this one fire, and the report says two things rather than one." Ours separates them — `_check_node` returns early on an `enum` miss — so we do not double-report. |
| `be unique` | `unique` | Closest match of all. Both refuse duplicates. Differences: ours takes `fields: [...]`, a **composite** key (`["location.container_id", "location.position"]`), his takes one `property` only. Ours skips a row when any key part is `None` ("a missing field is the schema's business"); his does the same by not firing on absence. His reports **every** holder of a shared value: "a person fixing it needs to see both ends of the clash" — ours reports only the second occurrence, with both indices in the path (`samples[0],[3].sample_id`). |
| `point at something in the crate` (+ `of_type`) | `cross_ref` | Both check that a reference resolves. His resolves inside the crate graph by `@id` and can additionally demand the target's type (`of_type: CoatingRecipe`) — we have no type constraint on a reference. Ours resolves against an arbitrary dotted path in the package (`against: "design_ref.items[].design_item_id"`), so it can join an order to a binding table, which his cannot: his target set is always "the crate". His counts an external URL as a failure: "A reference that points outside the crate... counts as not resolving." |
| `be a number between` | JSON Schema `minimum`/`maximum` in `_check_node`, and `within_limits` | His is one requirement with `between: [5, 500]`, inclusive, and a non-number is the same fault as an out-of-range number. Our `minimum`/`maximum` only fire when the value is already numeric. Our `within_limits` is different in kind: the bound is not in the contract, it is read out of the package's `limits` array, "this run's equipment, this round's budget". He has no equivalent and could not express one, because a contract value cannot come from the data. |
| — | `derived` | No equivalent. Ours recomputes a claimed checksum: "Requiring the field to be *present* is not enough... an engine that is wrong, or hostile, can supply a plausible string that satisfies 'present' while the crate's integrity claim becomes a lie." He takes a checksum of the crate as it arrived and writes it into the record, but never checks a checksum the sender claimed. |
| — | `required_quantities` | No equivalent, and not expressible. It asks the **profile**, not the contract, which measurements are mandatory, and checks the unit too (`wrong_unit`). His language has no units field at all — "The contract has no field for units, and a number with no unit in a finding is an invitation to compare a thickness against a temperature" — his answer is to put the unit in the message prose. |
| — | `required_provenance` | No equivalent. Per entity type: a list of required properties, with `within`/`where` narrowing, `one_of` alternatives across dialects, `if_present` for dialect-specific entries, and nested `measurements`. His `expects` is the thin end of this: it checks presence of a type, never properties on it in a single requirement. |
| — | `provenance_chain` | No equivalent, and explicitly out of reach for him. We walk backwards across the graph, following PROV properties, `CreateAction.object`, and a reverse `result` index, until a root type is reached. His docs: "No rule here walks the chain from a reading back to the recipe it came from, because a requirement follows one reference and the chain is a search backwards across the graph." His substitute is two requirements that every step's `object` and `result` resolve — "If every step's inputs and outputs are present, the chain holds, whether or not anybody walks it." That is weaker: a complete set of links that forms a cycle, or that bottoms out in the wrong kind of entity, passes. |
| — | `entity_value` | Partial overlap with `be recorded` + `one_of`, but ours reaches **through** a reference: for each row in `bindings`, resolve `crate_entity` into the graph and judge a property on the entity found there, with per-rule `severity`. His requirements apply to entities selected by type, never to entities reached from a row of a table. |
| — | `accounted_for` | No equivalent, and this is the one we should be proudest of. "`cross_ref` catches the easy direction: something arrived that was never asked for. This is the other one... a well that was asked for and simply is not in the record. Nothing is wrong with any row; a row is just absent, and absence has no field to check." Nothing in his four verbs can see an absence that has no entity. |
| — | `empty` | No equivalent. A list that must be empty (`alignment.unaligned`, `crate_ref_missing_files`). Expressible for him only as the inverse of a presence rule, which is not the same statement. |

Three further asymmetries that are not about verbs:

- **Document versus graph.** Ours validates a JSON package with an inlined
  crate, so most of the work is JSON Schema over `order.items`, `samples`,
  `recommendations` — tables. His validates only a crate, as a graph. Our
  `x-dbtl-checks` are the part that leaves the document shape; his language
  never had one.
- **Profiles.** We have a second file. `x-pattern` placeholders are bound at
  load time by `_bind()`, and three check kinds read `from_profile`. He has
  one file per handover and no notion of a use-case profile, so his contracts
  carry concrete values and are copied rather than parameterised.
- **Severity per finding.** His severity is fixed in the requirement. Ours is
  mostly fixed in the check, but `entity_value` and `required_provenance`
  can set severity **per rule inside the profile**, which is how "a right
  partial coding sequence" becomes a flag for one use case and nothing for
  another.

---

## 3. The three verdicts

His, from `blessing.py`:

```python
class Verdict(str, Enum):
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_FLAGS = "ACCEPTED_WITH_FLAGS"
    REFUSED = "REFUSED"
```

Decided once, in `Report.__post_init__`, and nowhere else:

```python
if any(v.severity is Severity.REFUSE for v in self.violations):
    decided = Verdict.REFUSED
elif self.violations:
    decided = Verdict.ACCEPTED_WITH_FLAGS
else:
    decided = Verdict.ACCEPTED
```

"The verdict is settled when the report is made and there is no way to set it
afterwards." A fourth state exists but is not a verdict: `verdict=None`, which
`verdict_text()` renders as "NOT CHECKED: no contract was applied to this
crate" — "which is not the same as saying the crate was accepted."

Ours, from `validator.py`:

```python
@property
def ok(self) -> bool:
    """A flag does not make a package invalid. It makes it conditional."""
    return not self.blocking
```

The mapping is exact in meaning and different in form:

| sentinel-oo | ours, as computed | ours, as named |
|---|---|---|
| `ACCEPTED` | `report.ok and not report.flags` | `Result(status="ok")` with empty `errors` |
| `ACCEPTED_WITH_FLAGS` | `report.ok and report.flags` | `Result(status="ok")`, flags in `errors`, trace line "accepted with N flag(s)" |
| `REFUSED` | `not report.ok`, i.e. any `severity == "error"` | `Result(status="escalated")` |
| `verdict=None` (not checked) | no equivalent — we cannot distinguish "checked and clean" from "not checked" | — |

Our severities are `"error"` and `"flag"`; his are `refuse` and `flag`. Same
two, same reasoning, almost the same words. Ours:

```python
# "error" stops the handover. "flag" does not: it is something the crate
# states honestly and the receiving phase has to be told about...
```

His: "There is no middle value on purpose. A severity nobody can act on is a
severity nobody reads."

The real difference is that **his verdict is a named value that travels**, on
the `Blessing`, into the crate, out of the HTTP API and out of the MCP tool.
Ours is a boolean recomputed from a list of `Error`s by whoever asks, and the
three-way distinction exists only as a sentence in a trace. Our
`architect/contract.py` has already converged on his enum, lower-cased:

```python
class Verdict(str, Enum):
    """What a sentinel decided. The three the group has converged on."""
    ACCEPTED = "accepted"
    ACCEPTED_WITH_FLAGS = "accepted_with_flags"
    REFUSED = "refused"
```

So the Architect side of ours already speaks his vocabulary; the validator
does not yet.

---

## 4. How it writes its findings back into the crate

`provenance.py`. "Everything the service did is written into the returned
crate as RO-Crate entities, so the crate carries its own history and needs no
database beside it."

The shape, per run:

1. **One `SoftwareApplication`**, `@id: "#sentinel-oo"`, with `url`,
   `softwareVersion` **and** `version` — "which is a real validator finding
   and not a guess."
2. **One `PropertyValue` per fact**, at `#sentinel-oo/run/<id>/about/<slug>`,
   from `Blessing.facts()` in a fixed order "so that two runs that did the
   same thing produce records that can be compared line by line": run
   identifier, contract name, contract version, contract checksum, **contract
   source**, service image tag, service commit, rules checksum, model engine,
   and the checksum of the crate as received.
3. **One `PropertyValue` for the verdict**, at `.../found/verdict`. Placed in
   `result`, not `object`: "A verdict is a result of the check, not an input
   to it... Putting a result in `object` was another of the six faults found
   on 10 November 2026."
4. **One `PropertyValue` per violation**, at
   `.../found/NN-<slug of requirement name>`, with
   `name: "<severity>: <requirement name>"`, `value: <the contract's
   message>`, `description: "at <node>"`, and — only when the node really
   exists — `about: {"@id": node}`. The reason for the guard: "a record must
   not add a dangling reference while complaining about the crate."
5. **One `PropertyValue` per surviving model repair**, at
   `.../changed/NN-<slug>`, name `"recovered: <what>"`. "A value somebody
   wrote down and a value something read out of prose are not equally
   trustworthy, so the crate says which this was."
6. **One `CreateAction`** tying it together: `instrument` the service,
   `object` the root plus the facts, `result` the verdict plus the findings
   plus the changes, `startTime`/`endTime`, and
   `actionStatus: FailedActionStatus` when refused, `CompletedActionStatus`
   otherwise — "so a reader who looks only at the action status still gets the
   right answer."
7. **The one mutation**: the root entity's `mentions` gains the action.
   "Without it the action sits in the crate unreachable from the root, which
   was one of the six faults found in the published example crate on
   10 November 2026, and no validator catches it."

Everything else "comes out byte for byte as it went in" — the crate is frozen
internally, dicts to read-only views and lists to tuples, recursively, and
every write returns a new crate. The reason is not style: "If it could edit
what it was given in place, then the thing it checksummed and the thing it
returned would not provably be related."

And the checksum is taken **before** anything else: "Taken after any repair it
would describe something the sender never sent."

**What we do instead.** Nothing of ours writes a finding into the crate. Our
findings land in `runs/<id>/ledger.jsonl` via `framework/ledger.py`, and in
`Result.notes` / `Result.errors`, which are in-process. `framework/crate_store.py`
writes the *phase's own* entities and a `CreateAction` per phase into one
growing crate per run — so we already have the machinery and the
`CreateAction` habit — but no sentinel ever adds its verdict to it. A refused
handover of ours leaves the crate indistinguishable from one never checked.
That is the gap his section 3 names: "A refusal that exists only as a message
in somebody's terminal is not a record."

---

## 5. What it does that we do not

- **`expects`.** Refuses a crate from the wrong phase instead of accepting it
  vacuously. We have the identical hole and no equivalent: a
  `required_provenance` entry for an absent type does report "no entity of
  type X anywhere in the crate", but only for entries the profile lists, and
  our `unique`/`cross_ref`/`entity_value` checks all pass silently on an empty
  `of` path.
- **The verdict written into the artefact.** Section 4 above.
- **A deployable service.** Container, `compose.yaml`, `deploy.py` that
  "validates every contract and refuses before building anything, builds the
  image with the test suite running inside the build as a gate... then checks
  the running instance is serving exactly what it validated". Contracts
  mounted read-only: "a service that checks handovers has no business editing
  the contract it checks against."
- **Two ways in, proven equivalent.** An HTTP API and an MCP interface, with
  "A test fails if the two interfaces ever give different verdicts." The MCP
  tool deliberately does **not** return the crate: "A crate is thousands of
  lines of JSON. Putting it in an agent's context costs money on every call
  and invites the agent to start editing laboratory records." Its findings
  field is named `message_from_contract` so an agent can tell the wording came
  from a file somebody wrote.
- **A contract that refuses to be misunderstood.** Unknown key, unknown verb,
  bad severity, missing message, duplicate requirement name, reversed
  `between` — each refuses the whole file, by name, at load. "It does not
  ignore what it does not understand, because a silently ignored requirement
  is a requirement you believe is protecting you." Our `load_contract` does
  `json.loads` and nothing else: a typo in `"kind"` makes a check vanish, and
  only `test_every_check_kind_is_implemented` catches it, in our test suite,
  not in his users' hands.
- **Build identity in the record.** Image tag, git commit, a checksum over
  every contract held (`ContractRegistry.checksum()`), so an instance can say
  exactly what it is carrying. We record `produced_by.{agent,tool,engine}` and
  `contract_version`, but not a checksum of the contract that judged us.
- **`contract_source`.** `registry` versus `supplied by requester` versus
  `none`. "'Checked against the published rules' and 'checked against rules
  the sender supplied' are different claims about a crate and must not look
  alike." We have no concept of a caller-supplied contract at all, so we have
  nothing to distinguish — but the day we accept one, this is the field.
- **A plain-words rendering of a contract.** `--show-contract` prints every
  requirement as a sentence, "which is what you send to the team that produces
  the handover". We have `scripts/show_agents.py`, which describes agents, not
  contracts.
- **Measurement of the model, written down.** Section 7 of the system manual
  reports two 14b models failing the real job, named, dated, with the
  conclusion that "a model being wrong, slow, absent or confidently mistaken
  changes no verdict". We assert the constraint in a test
  (`test_a_patch_outside_the_reported_paths_is_refused`); he also measured it
  against real models.
- **200 tests, run inside the image at build time**, with the network disabled
  by a fixture, and three that call `rocrate-validator` on the crate we
  returned. We have 16 tests and no third-party check that our crate is still
  a valid RO-Crate.

## 6. What we do that it does not

- **Four handovers, actually written.** `design_to_build`, `build_to_test`,
  `test_to_learn`, `learn_to_design`, with handover numbers tied to the use
  case (`x-handover.number`, and the note "two teams arguing about 'the Design
  handover' are provably arguing about the same one"). His worked example is
  "deliberately not a DBTL cycle" — a coating laboratory — so no DBTL contract
  exists on his side at all.
- **Profiles.** One contract, two use cases, bound at load by `_bind()`.
  `x-pattern: design_item_id` becomes bioprospecting's regex or
  biomanufacturing's. His language has no parameterisation, so the same
  handover under two use cases is two files that drift.
- **Measurements as first-class objects.** `quantity + value + unit + method`
  travelling together, with `uncertainty`, `normalised_to` and
  `in_training_range`, and a `wrong_unit` finding when the unit disagrees with
  the profile. This is "peak area is not flux" made checkable. He has no unit
  anywhere and says so.
- **The provenance chain walk.** `_check_provenance_chain` reaches a root
  entity or reports how far it got: "(walked N entities, deepest X)". Out of
  reach in his language, by his own account.
- **`accounted_for`** — the absence that has no field. His four verbs cannot
  express it.
- **`derived`** — checking a claimed checksum against the data, which is
  defence against a repair engine, not against a careless author.
- **`within_limits`** — a bound that comes from the data (`limits`, with
  `from` naming the crate it was read out of), not from the contract. His
  `between` is a constant in a file.
- **Both directions of information flow.** Our `reads` and `limits` arrays
  record that a sending phase looked at what the receiving phase said it could
  do. He has no notion of a handover reading anything.
- **`not_delivered`** and the whole treatment of a legitimate failure as a
  thing that must be stated rather than omitted.
- **A repair path driven by the contract's own prose.** Our `fix_hint`
  starting with `"not auto-fixable"` blocks a patch, and
  `test_every_check_is_blocking_or_says_why_not` fails if any check is
  silently patchable. "The decision lives in the contract, in prose a reviewer
  reads, rather than in a Python set only the author knows about." His
  `repairable: true` is the inverse default — opt in, boolean, no reason
  recorded beside it. We carry a *reason*, he carries a *flag*.
- **A growing crate and a graph written in the same call.** `crate_store.py`
  is append-only in intent, reports `extended`/`conflicts`/`collisions`/
  `dangling`, and writes `graph/run.nt` alongside, so "the graph and the crate
  never drift". He receives a crate, judges it, and returns it; he never
  accumulates one across four handovers.
- **A vocabulary layer.** `framework/vocab.py` plus `vocabulary/core.json` and
  `vocabulary/labs/*.json`, and the rule that a site may rename an agreed term
  but may not coin one. His `vocabulary/` is empty, and his README says so:
  "Taken from the `sentinel` framework at a later step."
- **An Architect.** `architect/contract.py` fixes the seams for consultation,
  specification, conversation, route and memory, with a `Move` enum
  (`go_on` / `go_back` / `ask`). He decides a verdict; nothing on his side
  decides what to *do* about one.

---

## 7. Worth adopting

1. **`expects`, or our own version of it.** Reason: we have the identical
   hole, and it is the failure mode that looks like success. Every one of our
   `x-dbtl-checks` whose `of` path is empty passes. A contract should state
   the types or paths whose absence means "this is not the handover I am
   for", and refuse before any check runs.
2. **A named three-value verdict on `Report`.** Reason: we already compute all
   three (`ok`, `flags`), `architect/contract.py` already names all three, and
   the HTML/pptx walkthroughs already talk in all three. Only `validator.py`
   is behind. Make it a property, decided once, not recomputed by callers.
3. **Writing the verdict and the findings into the crate as entities.**
   Reason: his argument is unanswerable — "A refusal that exists only as an
   error message in somebody's terminal is not a record." We already write
   `CreateAction`s per phase in `crate_store.py`; a sentinel action with
   `actionStatus: FailedActionStatus` is a small addition with a large payoff,
   and it makes a refused handover auditable a year later.
4. **A contract reader that refuses what it does not understand.** Reason: our
   `load_contract` is `json.loads`. A misspelt `kind` silently removes a
   check. Validating the `x-dbtl-checks` entries against `CHECKS` and against
   a per-kind required-field table, at load, moves that from our test suite to
   the author's own machine.
5. **`of_type` on a reference check.** Reason: cheap, and `cross_ref` already
   resolves references. "This binding points at *something*" is weaker than
   "this binding points at a `Protein`", and we currently only get the weaker
   one.
6. **The contract checksum in the record.** Reason: one line, and it turns
   "refused under v0.1.0" into a claim somebody can verify against the exact
   file. Ours records `contract_version`, which a contract author can edit
   without changing the version.
7. **The plain-words rendering of a contract.** Reason: it is the artefact you
   send to the team that produces the handover, and it is the cheapest way to
   find out that a requirement means something different to them. Also the
   fastest way to review our own four contracts for preferences masquerading
   as requirements.
8. **His YAML conventions for the shared surface** — `contract`, `version`,
   `description`, `severity: refuse|flag`, a `message` that is a sentence
   about consequence. Reason: convergence is the point of this exercise, and
   these cost nothing to match.

## 8. Worth not adopting

1. **Four verbs only.** Reason: our checks that matter most —
   `provenance_chain`, `accounted_for`, `required_quantities`,
   `required_provenance` — are not expressible as "one value, one judgement",
   and his documentation agrees they are out of reach. Narrowing to his
   vocabulary would delete the part of our work that catches the handover bugs
   we actually found.
2. **One concrete contract per handover, with no profile layer.** Reason: the
   whole claim of our framework is that bioprospecting and biomanufacturing
   validate against the *same* structure, which is "what makes a handover
   comparable across teams". Two copied files drift, and then the comparison
   is gone.
3. **Dropping JSON Schema for the document shape.** Reason: our handover is a
   package with an order, bindings, samples and recommendations — tables, not
   just a graph. JSON Schema states their shape in a form other tools already
   read. Re-expressing `minItems`, `pattern` and nested `required` as per-entity
   requirements would be longer and less checkable.
4. **A model on by default.** Reason: his own measurement is that two 14b
   models recovered nothing on the real job and "both stated a wrong meaning
   without hedging". Our `RulesEngine` default — no key, no network, no model
   — is what makes `python3 demo.py` a thing anybody can run, and the thing we
   demonstrate is the constraint, not the model. Keep the model opt-in.
5. **`repairable: true` as a bare boolean.** Reason: ours is better. A
   `fix_hint` that begins "not auto-fixable" and then says *why* — "inventing
   the missing step would fabricate the origin of a sequence" — is reviewable
   prose that a test already enforces. A boolean records the decision and
   loses the argument for it.
6. **Returning no crate from the agent interface.** Reason: his argument
   ("thousands of lines of JSON" in an agent's context) is right about MCP and
   wrong as a general rule. Our Architect is in-process and needs the package
   to route on. Adopt the reasoning for a network interface, not for the
   library.
7. **Severity fixed in the requirement.** Reason: `entity_value` and
   `required_provenance` set severity per rule *in the profile*, which is how
   a right-partial coding sequence flags for bioprospecting and is silent
   elsewhere. Moving severity into the contract would force one answer for
   both use cases.
8. **The container and `deploy.py`, for now.** Reason: not a disagreement, a
   sequencing judgement. He has built it; duplicating it is work we would
   rather spend on the contracts. If we need a deployable sentinel, the right
   move is to put our contracts behind his service — which is exactly what the
   YAML conversion in the second half of this task is for.

---

## 9. One defect noted, not fixed

`ContractRegistry.from_dir` globs `*.yaml` then `*.yml` and refuses two files
that define the same `contract` name. It does **not** refuse a folder
containing a file that is not a contract: any `.yaml` in the mounted folder is
parsed and must be a valid contract, so a stray `notes.yaml` fails the whole
deployment rather than being skipped. That is arguably correct — "nothing is
silently ignored" — but it is not documented in `DEPLOYING.md`, and
`deploy.py` validates the same folder, so the failure happens before the build
rather than at run time. Reported, not changed: his repository is read-only
here.
