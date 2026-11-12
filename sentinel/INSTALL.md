# Running the Architect on your own machine

Clone, run, open a browser. There is no install step: no pip, no virtualenv,
no account, no key, and no network once the clone is down.

```bash
git clone https://github.com/dbtl-synbio/dbtlhub.git
cd dbtlhub/sentinel
python3 architect/web/server.py
```

Then open **<http://127.0.0.1:8765/>**.

You need `git` and `python3` and nothing else. Tested on Python 3.9.6 and
3.12.9, from a clone with an empty environment. If `python3 --version` prints
3.9 or newer you have everything.

## The first three clicks

The interface asks before it does anything, in this order:

1. **What should do the thinking?** Pick **no model — deterministic rules**.
   It is offline, needs no key, and is enough to check every handover. The
   other four options (Claude Code CLI, Codex CLI, Ollama, Anthropic API) are
   detected on your machine and marked ready or not ready; none is needed to
   see the cycle run.
2. **Which use case?** Bioprospecting, biomanufacturing or directed evolution.
   The card says what each one actually has — directed evolution has no
   profile of its own and says so.
3. **Load the worked example**, then **Run**.

From a clean clone that gives four accepted handovers — design → build →
test → learn — with no model involved. That is the verification, not a
promise: this page was written by cloning the repository into an empty
directory and doing exactly the above.

After the run, the views across the top are the whole system: **the cycle**
(the ring from the architecture figure — click a phase or a verdict to see
what the sentinel did), **specification**, **workflow**, **the crate**,
**knowledge graph**, and **send it back**.

## Where your run ends up

Everything a run produces is a folder, not a database:

| | |
|---|---|
| `runs/<run id>/crate/ro-crate-metadata.json` | the one crate, append-only. The knowledge graph is this file |
| `runs/<run id>/graph/*.nt` | the same thing as triples |
| `runs/<run id>/architect.jsonl` | every move the Architect made, and why |

`runs/` is not in git, so a clone starts empty and your runs stay yours. A
restart of the server loses the form and the log and keeps the crate and the
ledger: the disk is the record, the session is not.

## Checking it rather than trusting it

```bash
python3 tests/test_framework.py        # 46 tests, no dependencies
python3 scripts/show_agents.py         # every agent, read from the live code
python3 demo_cycle.py                  # the four handovers, in the terminal
python3 scripts/check_crate.py --break-all   # a real crate, then broken three ways
python3 scripts/compare_sentinels.py   # this sentinel and sentinel-oo, same crates
```

`compare_sentinels.py` runs **Anil's engine**, not our reading of it, over the
six example crates in `bioprospecting/exampleROcrates/`, and prints whether
the two independent contracts agree. It finds `sentinel-oo` and the use-case
folders by looking one level up, which is where they are in a clone of
dbtlhub. If you keep them somewhere else:

```bash
DBTLHUB=/path/to/dbtlhub python3 scripts/compare_sentinels.py
```

## Making it yours

| You want to | Read |
|---|---|
| add a handover of your own | [`template/MAKE_A_SENTINEL.md`](template/MAKE_A_SENTINEL.md) — a sentinel is a YAML file dropped in `framework/contracts/`, and no Python |
| change what the run asks the researcher | `architect/forms/` — `template.yaml` is the question set, `bioprospecting.yaml` an instance of it |
| change the steps a phase has | `architect/workflows/*.yaml`, or edit the workflow in the interface |
| see what a contract checks, in words | `python3 scripts/show_agents.py --handover 1` |

**If you edit any YAML file here, run `python3 scripts/make_twins.py`.** Every
YAML file has a JSON twin, because YAML is not in the Python standard library
and the twin is what gets read on a machine without PyYAML. That script is the
only thing in this repository that needs `pip install PyYAML`, and only the
person editing needs it — never the person cloning.

## Options, and one warning

```bash
python3 architect/web/server.py --port 9000     # another port
python3 architect/web/server.py --host 0.0.0.0  # reachable from elsewhere
```

**There is no authentication, and pressing Run executes real agents.** The
default host is loopback for that reason, and posts are refused for any host
name that was not asked for. Widening it with `--host` is a decision; the
server says so out loud when you do.

## When it does not work

| What you see | What it is |
|---|---|
| `Address already in use` | something else has 8765. `--port 9000` |
| `form from fallback form (… PyYAML is not installed …)` | a JSON twin is missing. `python3 scripts/make_twins.py` on a machine that has PyYAML, and commit it |
| a `SyntaxError`, or a `TypeError` about an unsupported operand, before the server prints anything | a Python this has not been tried on. 3.9 and 3.12 both work; 3.8 and older have never been run. Nothing here needs a new Python, so please say which version it was rather than upgrading quietly — it is a bug on our side |
| Design → Build refused with `missing_provenance` on a sample | the run was not told **whose words the crate is written in**. Answer that question in the specification; a laboratory writes `freezer_id` and `rack`, the profile wants `dbtl:storageContainer` and `dbtl:storagePosition`, and the line that joins them is the reviewed file in `framework/vocabulary/labs/` |
| a view is empty | nothing has run yet in this session. The cycle view is drawn from the crate, and an empty crate is an honest empty picture |

## Updating

```bash
git pull
python3 tests/test_framework.py
```

Your `runs/` are untracked, so a pull never touches them.
