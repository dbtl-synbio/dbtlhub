#!/usr/bin/env python3
"""Keep every YAML file's JSON twin in step with it.

    python3 scripts/make_twins.py            # write the twins
    python3 scripts/make_twins.py --check    # say what is stale, write nothing

WHY THIS EXISTS
This framework claims to run on the Python standard library alone: clone it,
run it, no pip, no virtualenv, no network. YAML is not in the standard library,
so every YAML file this code reads exists twice - as the YAML a person edits,
because it can carry the reason for a rule beside the rule, and as a JSON twin
with the comments stripped, which is what gets read when PyYAML is not
installed.

The promise held for the contracts and the workflows, whose twins were written,
and quietly failed for the forms, whose twins were not: on a machine without
PyYAML the Architect fell back to the generic form and said so in small text
near the top of the page. The use case the person chose was simply not
available to them. Twins are mechanical, so they should be made mechanically
rather than remembered.

This needs PyYAML itself - it is the tool that makes the no-PyYAML path work,
run by whoever edits a YAML file, not by whoever clones the repository.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Each pair is a folder of YAML and the suffix its twins carry. The contracts
# are `*.schema.json` for historical reasons and the rest are plain `.json`;
# `load_contract()` and both loaders already look for exactly these names.
PLACES = (
    (ROOT / "framework" / "contracts", ".schema.json"),
    (ROOT / "architect" / "forms", ".json"),
    (ROOT / "architect" / "workflows", ".json"),
    # The worked example from `template/MAKE_A_SENTINEL.md`: a handover that is
    # a file and nothing else. It needs the twin for the same reason - someone
    # copying the recipe onto a machine without PyYAML has to be able to read
    # what they dropped in.
    (ROOT / "template" / "example", ".schema.json"),
)


def twin_of(path: Path, suffix: str) -> Path:
    return path.with_name(path.stem + suffix)


def main() -> int:
    check = "--check" in sys.argv[1:]
    try:
        import yaml                                        # noqa: PLC0415
    except ImportError:
        print("\n  This one script needs PyYAML, because it reads the YAML:\n"
              "\n      pip install 'PyYAML>=5.1'\n"
              "\n  Everything else here runs without it, which is what the "
              "twins are for.\n")
        return 2

    stale: list[Path] = []
    for folder, suffix in PLACES:
        for source in sorted(folder.glob("*.yaml")):
            twin = twin_of(source, suffix)
            wanted = json.dumps(yaml.safe_load(source.read_text(
                encoding="utf-8")), indent=1, ensure_ascii=False) + "\n"
            have = twin.read_text(encoding="utf-8") if twin.is_file() else None
            same = have is not None and json.loads(have) == json.loads(wanted)
            where = twin.relative_to(ROOT)
            if same:
                print(f"  ok       {where}")
                continue
            stale.append(twin)
            if check:
                print(f"  STALE    {where}"
                      f"{' (does not exist)' if have is None else ''}")
            else:
                twin.write_text(wanted, encoding="utf-8")
                print(f"  written  {where}"
                      f"{' (new)' if have is None else ' (was out of date)'}")

    if check and stale:
        print(f"\n  {len(stale)} twin(s) out of date. "
              f"Run `python3 scripts/make_twins.py`.\n")
        return 1
    print(f"\n  {len(stale)} changed, "
          f"{sum(len(list(f.glob('*.yaml'))) for f, _ in PLACES)} YAML "
          f"file(s) have a twin.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
