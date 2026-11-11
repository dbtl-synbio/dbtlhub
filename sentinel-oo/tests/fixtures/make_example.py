#!/usr/bin/env python3
"""Build the product's own worked example, and four broken copies of it.

This example belongs to `sentinel-oo` itself, not to any deployment. Its
purpose is to exercise every shape the rule engine knows how to read, and to
be short enough that somebody learning the contract language can hold the
whole of it in their head.

It is deliberately not a DBTL cycle. The domain is a coating laboratory:
recipes are blended, applied to metal panels held in numbered slots on a
rack, dried, and their film thickness measured. Nothing here is biology, so
nobody reading the product can mistake its example for somebody's use case.

The handover it describes is from Mixing to Coating. Mixing finishes with a
set of recipes and an intended rack layout saying which recipe goes on which
panel position. Coating applies them and spends materials, so anything
Coating cannot judge from the crate is a panel that may be wasted.

    python make_example.py

Writes five crates into this folder:

    coating-test/valid/                        satisfies the contract
    coating-test/invalid/missing-conformsto/   root does not declare a profile
    coating-test/invalid/dangling-reference/   lists a file it does not describe
    coating-test/invalid/missing-atmosphere/   a required setting is absent
    coating-test/invalid/atmosphere-in-prose/  the setting is present, in prose

All four broken copies are valid RO-Crate 1.3 and all four are refused by
`tests/fixtures/contracts/mixing_to_coating.yaml`, which is the argument for a
contract on top of a validator, in four examples.

ALL DATA HERE IS INVENTED. The thicknesses, the recipe codes and the
identifiers under example.org are made up and resolve to nothing.
"""

from __future__ import annotations

import copy
import json
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))

RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.3/context"
WFRUN_CONTEXT = "https://w3id.org/ro/terms/workflow-run/context"
RO_CRATE_SPEC = "https://w3id.org/ro/crate/1.3"
PROCESS_RUN_CRATE = "https://w3id.org/ro/wfrun/process/0.6"

EX = "https://example.org/coating-test"
# The library catalogue is not part of the coating laboratory and should not
# borrow its addresses. It is the one crate here that a reader of the
# product's worked example sees.
LIBRARY = "https://example.org/library-catalogue"

# Three recipes, each on one slot of the rack, each with one thickness
# reading. Three rather than one so that "must be unique" has something to
# be unique across, and small enough to read.
RECIPES = [
    # code, slot, thickness in micrometres, coverage
    ("REC-001", "P1", 42, "full"),
    ("REC-002", "P2", 65, "full"),
    ("REC-003", "P3", 38, "full"),
]

# What the drying step actually ran. The value lives in two places in the
# valid crate: as a recorded value, and inside this command line. The
# `atmosphere-in-prose` copy keeps only the command line, which is the one
# case a model may be asked to recover.
DRYER_COMMAND = "dryer --panels rack-A1 --atmosphere dry --hold 20 -q"


def build_graph(record_atmosphere=True, atmosphere_in_prose=False,
                declare_profile=True, dangling_reference=False):
    """The whole crate as a list of entities.

    Each argument removes or damages exactly one thing, so each broken copy
    differs from the valid one in one way only and a refusal can be read
    back to a single cause.
    """
    graph = []

    # ---------------------------------------------------------------
    # The packaging
    # ---------------------------------------------------------------
    graph.append({
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "conformsTo": {"@id": RO_CRATE_SPEC},
        "about": {"@id": "./"},
    })

    graph.append({
        "@id": PROCESS_RUN_CRATE,
        "@type": ["CreativeWork", "Profile"],
        "name": "Process Run Crate",
        "version": "0.6",
    })

    parts = [{"@id": "recipes.csv"}, {"@id": "rack-layout.csv"}]
    if dangling_reference:
        # A file the crate claims as part of itself and then never
        # describes. Whoever receives this will look for it and not find it.
        parts.append({"@id": "coverage-photographs.zip"})

    root = {
        "@id": "./",
        "@type": "Dataset",
        "name": "Mixing to Coating handover, rack A1",
        "description": (
            "The output of one Mixing run: three coating recipes, the "
            "intended rack layout saying which recipe goes on which panel "
            "position, and a record of every step that produced them. ALL "
            "DATA IN THIS CRATE IS INVENTED. The thicknesses and recipe "
            "codes are made up and the identifiers under example.org "
            "resolve to nothing. It exists to exercise the rule engine and "
            "to be read by somebody learning the contract language."
        ),
        "datePublished": "2026-11-11",
        "license": {"@id": "https://spdx.org/licenses/CC0-1.0"},
        "hasPart": parts,
        "mentions": [
            {"@id": "#act-blending"},
            {"@id": "#act-drying"},
        ],
    }
    if declare_profile:
        root["conformsTo"] = {"@id": PROCESS_RUN_CRATE}
    graph.append(root)

    # ---------------------------------------------------------------
    # The files the crate carries
    # ---------------------------------------------------------------
    graph.append({
        "@id": "recipes.csv",
        "@type": "File",
        "name": "The three recipes, one per row",
        "encodingFormat": "text/csv",
    })
    graph.append({
        "@id": "rack-layout.csv",
        "@type": "File",
        "name": "Which recipe is intended for which slot",
        "encodingFormat": "text/csv",
    })

    # ---------------------------------------------------------------
    # Who and what did the work
    # ---------------------------------------------------------------
    graph.append({
        "@id": "#operator",
        "@type": "Person",
        "name": "A. Operator",
    })

    graph.append({
        "@id": f"{EX}/equipment/blender",
        "@type": "SoftwareApplication",
        "name": "Bench blender, model B2",
        "url": f"{EX}/equipment/blender",
        "softwareVersion": "2",
        "version": "2",
        "description": (
            "A bench blender. It is not software and it has no version. The "
            "value 2 is its model number, present because RO-Crate requires "
            "a version. Saying plainly what it is beats borrowing another "
            "step's instrument."
        ),
    })

    graph.append({
        "@id": f"{EX}/equipment/dryer",
        "@type": "SoftwareApplication",
        "name": "Cabinet dryer control software",
        "url": f"{EX}/equipment/dryer",
        "softwareVersion": "4.2.0",
        "version": "4.2.0",
    })

    graph.append({
        "@id": f"{EX}/equipment/gauge",
        "@type": "SoftwareApplication",
        "name": "Film thickness gauge",
        "url": f"{EX}/equipment/gauge",
        "softwareVersion": "1.9",
        "version": "1.9",
    })

    # ---------------------------------------------------------------
    # The two process steps
    # ---------------------------------------------------------------
    graph.append({
        "@id": "#act-blending",
        "@type": "CreateAction",
        "additionalType": "BlendingStep",
        "name": "Blend the three recipes",
        "instrument": {"@id": f"{EX}/equipment/blender"},
        "object": [{"@id": "recipes.csv"}],
        "result": [{"@id": f"#recipe-{code}"} for code, _, _, _ in RECIPES],
        "agent": {"@id": "#operator"},
        "endTime": "2026-10-02T10:15:00Z",
        "actionStatus": "http://schema.org/CompletedActionStatus",
    })

    # The drying step. Its setting hangs off `object`, because that is what
    # Process Run Crate says a parameter of a step is. A recipe hangs its
    # values off `additionalProperty` instead. Having both in one example is
    # deliberate: a reader of the crate that knew only one of the two would
    # see half of it, and the rule engine had to be generalised once for
    # exactly that reason.
    drying_objects = [{"@id": f"#recipe-{code}"} for code, _, _, _ in RECIPES]
    if record_atmosphere:
        drying_objects.append({"@id": "#pv-drying-atmosphere"})

    drying_description = (
        "Panels were dried in the cabinet before the thickness gauge was "
        "run over them."
    )
    if atmosphere_in_prose:
        # Nothing is missing from this crate. The value is here, inside a
        # sentence, where no rule can read it. That is the whole of what
        # makes this copy different from the one above.
        drying_description = (
            "Panels were dried in the cabinet before the thickness gauge "
            f"was run over them. The command was: {DRYER_COMMAND}"
        )

    graph.append({
        "@id": "#act-drying",
        "@type": "CreateAction",
        "additionalType": "DryingStep",
        "name": "Dry the coated panels",
        "description": drying_description,
        "instrument": {"@id": f"{EX}/equipment/dryer"},
        "object": drying_objects,
        "result": [{"@id": f"#reading-{code}"} for code, _, _, _ in RECIPES],
        "agent": {"@id": "#operator"},
        "endTime": "2026-10-02T14:40:00Z",
        "actionStatus": "http://schema.org/CompletedActionStatus",
    })

    if record_atmosphere:
        graph.append({
            "@id": "#pv-drying-atmosphere",
            "@type": "PropertyValue",
            "name": "drying atmosphere",
            "value": "dry",
            "description": (
                "The dryer was run with --atmosphere dry, meaning no "
                "humidity was added. A coating dried in a humid atmosphere "
                "cures differently and its thickness reading is not "
                "comparable, so a panel dried any other way needs a "
                "contract that says what to do about it."
            ),
        })

    # ---------------------------------------------------------------
    # The rack, and a slot for each recipe
    # ---------------------------------------------------------------
    graph.append({
        "@id": "#rack-A1",
        "@type": "CreativeWork",
        "additionalType": "IntendedRackLayout",
        "identifier": "RACK-A1",
        "name": "Intended rack layout A1",
        "description": (
            "What Mixing asked for. Not a record of what was actually "
            "coated, which is Coating's to write."
        ),
    })

    for code, slot, thickness, coverage in RECIPES:
        graph.append({
            "@id": f"#slot-{slot}",
            "@type": "CreativeWork",
            "additionalType": "RackSlot",
            "name": slot,
            "description": (
                "A panel position on the rack, P1 to P3. The slot belongs "
                "to the rack rather than to the recipe, because Coating "
                "needs somewhere to record what actually arrived in it."
            ),
            "isPartOf": {"@id": "#rack-A1"},
            "mainEntity": {"@id": f"#recipe-{code}"},
        })

        graph.append({
            "@id": f"#recipe-{code}",
            "@type": "CreativeWork",
            "additionalType": "CoatingRecipe",
            "identifier": code,
            "name": f"Coating recipe {code}",
            "isBasedOn": {"@id": f"#reading-{code}"},
            "additionalProperty": [{"@id": f"#pv-thickness-{code}"}],
        })

        graph.append({
            "@id": f"#pv-thickness-{code}",
            "@type": "PropertyValue",
            "name": "film thickness",
            "value": thickness,
            "unitText": "micrometres",
            "description": (
                "The thickness the recipe is specified to produce, in "
                "micrometres. The coating line will not run below 5 or "
                "above 500 micrometres."
            ),
        })

        graph.append({
            "@id": f"#reading-{code}",
            "@type": "CreativeWork",
            "additionalType": "ThicknessReading",
            "name": f"Thickness reading for {code}",
            "additionalProperty": [{"@id": f"#pv-coverage-{code}"}],
        })

        graph.append({
            "@id": f"#pv-coverage-{code}",
            "@type": "PropertyValue",
            "name": "coverage",
            "value": coverage,
            "description": (
                "Whether the gauge covered the whole panel. The gauge "
                "writes 'full' when it did and 'partial' when the panel was "
                "too small or badly seated, and a partial reading cannot be "
                "compared with a full one."
            ),
        })

    return graph


# ---------------------------------------------------------------------
# Writing the crates out
# ---------------------------------------------------------------------

PAYLOAD = {
    "recipes.csv": (
        "code,thickness_micrometres,coverage\n"
        + "".join(f"{c},{t},{v}\n" for c, _, t, v in RECIPES)
    ),
    "rack-layout.csv": (
        "slot,recipe\n" + "".join(f"{s},{c}\n" for c, s, _, _ in RECIPES)
    ),
}


def write_crate(folder, graph, payload=None, under="coating-test"):
    path = os.path.join(HERE, under, folder)
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path)

    for name, body in (PAYLOAD if payload is None else payload).items():
        with open(os.path.join(path, name), "w", encoding="utf-8") as fh:
            fh.write(body)

    document = {
        "@context": [RO_CRATE_CONTEXT, WFRUN_CONTEXT],
        "@graph": copy.deepcopy(graph),
    }
    with open(os.path.join(path, "ro-crate-metadata.json"), "w",
              encoding="utf-8") as fh:
        json.dump(document, fh, indent=2)
        fh.write("\n")

    print(f"  {folder:34} {len(graph):3} entities")
    return path


# A crate from somewhere else entirely, with none of the types above in it.
#
# It is here so that the tutorial's most important lesson can be run rather
# than described. A contract with no `expects` block accepts a crate from a
# completely different phase, because every requirement about a type the
# crate does not contain matches nothing and passes. That is the worst thing
# this service can do, and a reader should see it happen to them.
#
# A library catalogue, chosen because nobody could mistake it for a
# laboratory or for anybody's DBTL cycle.

def another_domain():
    return [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "conformsTo": {"@id": RO_CRATE_SPEC},
            "about": {"@id": "./"},
        },
        {
            "@id": PROCESS_RUN_CRATE,
            "@type": ["CreativeWork", "Profile"],
            "name": "Process Run Crate",
            "version": "0.6",
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": "A handover from somewhere else entirely",
            "description": (
                "A library catalogue. It contains no plate wells, no "
                "constructs and no gene calling step, and no recipes, rack "
                "slots or drying step either, so a contract written for any "
                "of those handovers has nothing here to check. It exists so "
                "that the tutorial can show what happens when a contract "
                "does not say what it is for. ALL DATA HERE IS INVENTED."
            ),
            "datePublished": "2026-11-11",
            "license": {"@id": "https://spdx.org/licenses/CC0-1.0"},
            "conformsTo": {"@id": PROCESS_RUN_CRATE},
            "hasPart": [{"@id": "catalogue.csv"}],
            "mentions": [{"@id": "#act-cataloguing"}],
        },
        {
            "@id": "catalogue.csv",
            "@type": "File",
            "name": "One row per book",
            "encodingFormat": "text/csv",
        },
        {
            "@id": "#librarian",
            "@type": "Person",
            "name": "A. Librarian",
        },
        {
            "@id": f"{LIBRARY}/equipment/scanner",
            "@type": "SoftwareApplication",
            "name": "Barcode scanner",
            "url": f"{LIBRARY}/equipment/scanner",
            "softwareVersion": "3",
            "version": "3",
        },
        {
            "@id": "#act-cataloguing",
            "@type": "CreateAction",
            "additionalType": "CataloguingStep",
            "name": "Catalogue the new arrivals",
            "instrument": {"@id": f"{LIBRARY}/equipment/scanner"},
            "object": [{"@id": "catalogue.csv"}],
            "result": [{"@id": "#book-0001"}],
            "agent": {"@id": "#librarian"},
            "endTime": "2026-10-02T09:00:00Z",
            "actionStatus": "http://schema.org/CompletedActionStatus",
        },
        {
            "@id": "#book-0001",
            "@type": "CreativeWork",
            "additionalType": "ShelvedBook",
            "identifier": "BOOK-0001",
            "name": "A book on a shelf",
            "isPartOf": {"@id": "#shelf-A"},
        },
        {
            "@id": "#shelf-A",
            "@type": "CreativeWork",
            "additionalType": "Shelf",
            "identifier": "SHELF-A",
            "name": "Shelf A",
        },
    ]


VARIANTS = [
    ("valid", {}),
    ("invalid/missing-conformsto", {"declare_profile": False}),
    ("invalid/dangling-reference", {"dangling_reference": True}),
    ("invalid/missing-atmosphere", {"record_atmosphere": False}),
    ("invalid/atmosphere-in-prose", {"record_atmosphere": False,
                                     "atmosphere_in_prose": True}),
]


def main():
    print("the test suite's fixtures: a coating laboratory, which is a "
          "domain\nnothing in the service knows anything about")
    for folder, changes in VARIANTS:
        write_crate(folder, build_graph(**changes))
    # This one is not a fixture. The tutorial uses it to show that a
    # contract with no `expects` block accepts a crate from any domain at
    # all, so it lives with the worked example rather than in here.
    write_crate("from-another-phase", another_domain(),
                under="../../examples",
                payload={"catalogue.csv": "barcode,title,shelf\n"
                                          "BOOK-0001,A book on a shelf,SHELF-A\n"})
    print("\nAll six are valid RO-Crate 1.3. Four of the coating five are")
    print("refused by tests/fixtures/contracts/mixing_to_coating.yaml, and")
    print("from-another-phase is refused because it contains nothing that")
    print("contract is written for.")


if __name__ == "__main__":
    main()
