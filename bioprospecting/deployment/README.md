# A tailored instance: the bioprospecting DBTL cycle

This folder is one deployment of `sentinel-oo`. DBTL stands for Design, Build,
Test, Learn, which is the engineering cycle used in synthetic biology.

**There is no code in this folder and none was written to deploy it.** The
image is the generic product, unmodified. Everything that makes this instance
specific to bioprospecting is the contract files below, mounted into that
image at the path `/contracts`.

## What is in here

| File or folder | What it is |
|---|---|
| `contracts/design_to_build.yaml` | The Design to Build handover, 18 requirements, version 0.10.0 |
| `contracts/build_to_test.yaml` | The Build to Test handover, 2 requirements, version 0.2.0, a stub. ⚠ It has no `expects` block, so it accepts any crate whose packaging is sound. Read the warning at the top of the file before relying on it |
| `crates/design-to-build-simple/` | One RO-Crate that satisfies the contract |
| `crates/design-to-build/` | The same crate, plus 4 copies each broken in one way |
| `compose.yaml` | Starts the generic image with these contracts mounted, by hand |

An RO-Crate is a folder of data files with a JSON file alongside them
describing what each file is and how the things in it relate to each other.

## Running it

One command, run from the product folder:

```
cd ../../../sentinel-oo
python deploy.py ../bioprospecting/contracts \
    --crates ../bioprospecting/exampleROcrates
```

That validates both contracts, refuses the deployment if either is
malformed, builds the generic image with the product's 200 tests running
inside the build, starts the instance with this folder's contracts mounted
read only, and then confirms the running instance is serving exactly what it
validated. See `../../sentinel-oo/docs/DEPLOYING.md`.

`compose.yaml` in this folder does the same thing by hand, without the
validation before and after, so a broken contract would not be caught until
first use.

The service then answers on port 8080 of the local machine. From another
terminal, in this folder:

```
curl -s http://127.0.0.1:8080/contracts

curl -s -X POST --data-binary \
  @crates/design-to-build-simple/ro-crate-metadata.json \
  http://127.0.0.1:8080/check/design_to_build
```

## What it does with the five crates

Measured on 11 November 2026 through the running container over HTTP. The
third party tool `rocrate-validator` calls all 5 of these crates valid.

| Crate | Verdict | Which requirement caught it |
|---|---|---|
| `design-to-build-simple` | ACCEPTED, 0 findings | |
| `invalid/missing-conformsto` | REFUSED | `declares_a_profile` |
| `invalid/dangling-reference` | REFUSED | `everything_the_crate_lists_is_present` |
| `invalid/missing-gene-calling-mode` | REFUSED | `edge_handling_is_recorded`, `edge_handling_is_closed` |
| `invalid/mode-in-prose` | REFUSED | `edge_handling_is_recorded`, `edge_handling_is_closed` |

The last one is the interesting case. Nothing is missing from that crate: the
gene calling setting is present, inside the text of a command line, where no
rule can read it. A valid crate can therefore be refused for being
unreadable rather than for being incomplete, which is the whole argument for
a contract on top of a validator.

## Deploying a different DBTL cycle

Copy `compose.yaml`, point its contracts mount at your own folder of contract
files, and start it. The image does not change and nothing is rebuilt.

What the product's documentation covers, and what you will need, is the
contract language: what a requirement looks like, and the verbs it has. There
are currently 4 verbs, and if your requirement needs a fifth you will get a
message naming the four that exist rather than a working contract. Adding a
verb is a change to the product, and it is the one case where tailoring is not
enough.
