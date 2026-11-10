# Design to Build: crates that must be refused

Generated from `design-to-build-simple/` by:

```bash
python3 scripts/check_crate.py --write-broken sentinel/examples/design-to-build
```

One fault each, and the data files are copied unchanged so the only
difference is the one named below.

| folder | the fault |
|---|---|
| `dangling-reference` | the crate names a file that is not there |
| `missing-conformsto` | the root no longer declares the profile it follows |
| `missing-gene-calling-mode` | valid RO-Crate, valid profile, and Build still cannot tell whether the sequences are truncated |

Check any of them:

```bash
python3 scripts/check_crate.py sentinel/examples/design-to-build/<folder>
```

Two of the three pass every RO-Crate validator there is. That is the point
of including them.
