"""A simulation of the first process in the downstream workflow.

In reality this is a gene synthesis vendor's ordering system. It exists
already, we do not build it, and the boundary where it sits is fixed. This
program stands in for it so the demonstration has somewhere to hand a checked
crate off to, because there is no live vendor account in the room.

So this is neither part of the service nor part of a deployment. The service
decides; this acts on the decision. That separation is what lets another use
case act on the same verdict in a completely different way without the
service knowing anything about synthesis vendors, plates or wells.

It reads a crate the service has returned, refuses to do anything with one
that was refused, drops any well the service flagged, and writes two files:
the order, and a list of what was held back and why.

    python make_order.py blessed.json --out orders/

Exit codes: 0 when an order was written, 1 when the handover was refused and
nothing was written, 2 when the crate carries no record at all.

A SIMPLIFICATION, stated here rather than left for somebody to spot. This
simulator reads the RO-Crate directly. A real vendor ordering system would
not: it would accept a comma-separated file or a web form, and something
would have to convert the crate into that shape first. That something is an
adapter, it belongs to a deployment, and it is a slot this demonstration
leaves empty by collapsing the adapter and the downstream tool into one
program.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# The product, used as a library. Found relative to this file so the
# simulator runs as a program and not only under its own tests, where a test
# fixture used to be the only thing putting the product on the path. Running
# the demonstration end to end on 11 November 2026 is what exposed that: the
# command in this folder's README did not work.
#
# The simulator may import the service. The service may never import the
# simulator, and a test in the product's own suite fails if it ever does.
def _the_product(start: Path) -> Path | None:
    """Where sentinel-oo's source is, found by climbing rather than counting.

    This used to count folders upwards, which broke the day the use case
    moved from its own repository into dbtlhub and gained one level of
    depth. Climbing until the product is seen survives being moved again.
    """
    for folder in [start, *start.parents]:
        candidate = folder / "sentinel-oo" / "src"
        if candidate.is_dir():
            return candidate
    return None


_PRODUCT = _the_product(Path(__file__).resolve().parent)
if _PRODUCT is not None and str(_PRODUCT) not in sys.path:
    sys.path.insert(0, str(_PRODUCT))

from sentinel_oo import Crate, CrateMalformed  # noqa: E402
from sentinel_oo.provenance import SERVICE_ID
from sentinel_oo.rules import types_of, values_of

ORDER_COLUMNS = ["plate", "well", "name", "sequence"]
HELD_COLUMNS = ["plate", "well", "construct", "reason"]

SEQUENCE_VALUE = "codon optimised coding sequence"


class NoRecord(Exception):
    """The crate has never been through the service."""


class Refused(Exception):
    """The service refused this handover."""


def _named_value(crate: Crate, entity, wanted: str):
    """One value hanging off an entity, by name. None when absent."""
    for key in entity:
        if key.startswith("@"):
            continue
        for reference in values_of(entity, key):
            carrier = crate.get(reference)
            if carrier is None or "PropertyValue" not in types_of(carrier):
                continue
            if str(carrier.get("name", "")) == wanted:
                found = values_of(carrier, "value")
                return found[0] if found else None
    return None


def latest_record(crate: Crate):
    """The service's most recent action in this crate.

    A crate is checked at more than one handover over its life, so there may
    be several. The one that matters is the last, by end time.
    """
    records = [
        e for e in crate
        if str(e.get("@id", "")).startswith(f"{SERVICE_ID}/run/")
        and "CreateAction" in types_of(e)
    ]
    if not records:
        raise NoRecord(
            "this crate carries no record from the checking service, so "
            "nothing has confirmed it is fit to order from"
        )
    return sorted(records, key=lambda e: str(e.get("endTime", "")))[-1]


def verdict_of(crate: Crate, record) -> str:
    found = _named_value(crate, record, "verdict")
    return found or "unknown"


def findings_of(crate: Crate, record) -> list[tuple[str, str]]:
    """Every finding the service recorded, as (where, what)."""
    out = []
    for reference in values_of(record, "result"):
        carrier = crate.get(reference)
        if carrier is None or "PropertyValue" not in types_of(carrier):
            continue
        name = str(carrier.get("name", ""))
        if name == "verdict":
            continue
        where = values_of(carrier, "about")
        text = values_of(carrier, "value")
        out.append((where[0] if where else "", text[0] if text else name))
    return out


def wells_of(crate: Crate) -> list:
    return [e for e in crate if "PlateWell" in types_of(e)]


def build_order(crate: Crate):
    """Read the plate and return the rows to order and the rows held back."""
    record = latest_record(crate)
    verdict = verdict_of(crate, record)

    if verdict.startswith("REFUSED"):
        raise Refused(
            "the service refused this handover, so no order is written. "
            "Fix what it reported and check the crate again."
        )
    if verdict.startswith("NOT CHECKED"):
        raise NoRecord(
            "this crate was read by the service but never checked against a "
            "contract, so nothing has confirmed it is fit to order from"
        )

    flagged = {where for where, _ in findings_of(crate, record) if where}
    reasons = {where: what for where, what in findings_of(crate, record) if where}

    order, held = [], []
    for well in sorted(wells_of(crate), key=lambda w: str(w.get("name", ""))):
        position = str(well.get("name", ""))
        plate_ref = values_of(well, "isPartOf")
        plate = crate.get(plate_ref[0]) if plate_ref else None
        plate_name = str(plate.get("identifier", plate.get("name", ""))) if plate else ""

        construct_ref = values_of(well, "mainEntity")
        construct = crate.get(construct_ref[0]) if construct_ref else None
        if construct is None:
            held.append([plate_name, position, "", "no construct named for this well"])
            continue

        construct_name = str(construct.get("identifier", construct["@id"]))

        if well["@id"] in flagged or construct["@id"] in flagged:
            where = well["@id"] if well["@id"] in flagged else construct["@id"]
            held.append([plate_name, position, construct_name, reasons[where]])
            continue

        sequence = _named_value(crate, construct, SEQUENCE_VALUE)
        if not sequence:
            held.append([plate_name, position, construct_name,
                         "no coding sequence recorded, so there is nothing to make"])
            continue

        order.append([plate_name, position, construct_name, sequence])

    return order, held


def write_csv(path: Path, columns: list[str], rows: list[list]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        writer.writerows(rows)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="make-order",
        description=(
            "Turn a crate the checking service has accepted into a vendor "
            "upload file. Refuses to run on a crate that was refused."
        ),
    )
    parser.add_argument("crate", help="a crate the service has returned")
    parser.add_argument("--out", default="order",
                        help="the folder to write the two files into")
    args = parser.parse_args(argv)

    try:
        crate = Crate.from_path(args.crate)
    except CrateMalformed as exc:
        print(f"not a crate: {exc}", file=sys.stderr)
        return 2

    try:
        order, held = build_order(crate)
    except Refused as exc:
        print(f"no order written: {exc}", file=sys.stderr)
        return 1
    except NoRecord as exc:
        print(f"no order written: {exc}", file=sys.stderr)
        return 2

    out = Path(args.out)
    order_file = write_csv(out / "vendor_upload.csv", ORDER_COLUMNS, order)
    held_file = write_csv(out / "held_back.csv", HELD_COLUMNS, held)

    print(f"{len(order)} well(s) to order    -> {order_file}")
    print(f"{len(held)} well(s) held back   -> {held_file}")
    for row in held:
        print(f"    {row[1]:4} {row[2]:10} {row[3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
