#!/usr/bin/env python3
"""Draw every diagram in the system manual.

    /usr/local/bin/python3 make_diagrams.py

Use that interpreter and not plain `python3`: on this machine it is the only
installation with matplotlib available.

These were Mermaid, which is text and renders only in viewers that know about
it. The manuals are PDFs and a PDF cannot render Mermaid at all, so they are
drawn instead. A drawn image also works in every viewer, which Mermaid does
not, so this is not only a concession to the PDF.

The class diagram, 04-the-components.png, is drawn by 04_the_components.py
rather than here, because it began as a slide and is still used as one.
"""

from __future__ import annotations

from draw import Sheet, GREY, INK, RED, GREEN, BLUE, AMBER, PURPLE


# ------------------------------------------------------------------ 02a

def three_separate_things():
    s = Sheet(width=104, height=44)

    s.group(1, 20, 49, 22, "sentinel-oo: the generic product", "blue")
    s.box(3.5, 33.5, 44, 6, "The service\nno use case anywhere in it", "blue", size=9.5)
    s.box(3.5, 27.5, 44, 5, "Its own worked example: a coating laboratory",
          "blue", size=9)
    s.box(3.5, 21.5, 44, 5, "deploy.py, the deployment program", "blue", size=9)

    s.group(54, 25, 49, 17, "deployments/bioprospecting: one tailored instance",
            "green", size=9)
    s.box(56.5, 33.5, 44, 6, "Contract files\nthe whole of the tailoring", "green",
          size=9.5)
    s.box(56.5, 26.5, 44, 5.5, "Example crates", "green", size=9)

    s.group(54, 3, 49, 15, "demonstration: scaffolding", "grey")
    s.box(56.5, 5.5, 44, 9, "A simulation of the first\nprocess downstream",
          "grey", size=9.5)

    s.arrow((56.5, 36.5), (47.5, 36.5), "mounted at /contracts", dashed=True,
            colour=GREY, label_offset=(0, 2.1))
    s.arrow((56.5, 10), (34, 20.4), "reads a checked crate", dashed=True,
            colour=GREY, label_offset=(7, -2.6), bend=-0.18)

    s.plain(52, 1.0, "The product never reads anything from either of the other two.  "
                     "Two tests fail if that changes.",
            size=9, colour=INK, ha="center", style="italic")
    s.save("02-three-separate-things.png")


# ------------------------------------------------------------------ 02b

def fixed_boundaries():
    s = Sheet(width=108, height=30)

    s.box(1, 15, 22, 9, "The real\nupstream tool", "grey", size=9.5)
    s.plain(12, 12.6, "fixed, not ours", size=8.6, ha="center", style="italic")

    s.box(29, 15, 24, 9, "sentinel-oo", "blue", size=11, bold=True)
    s.plain(41, 12.6, "generic, tailored by a contract", size=8.6, ha="center",
            style="italic", colour=BLUE)

    s.box(59, 15, 22, 9, "An adapter\nif the shapes differ", "amber", size=9.5)
    s.plain(70, 12.6, "tailored, optional", size=8.6, ha="center", style="italic",
            colour=AMBER)

    s.box(87, 15, 20, 9, "The real\ndownstream tool", "grey", size=9.5)
    s.plain(97, 12.6, "fixed, not ours", size=8.6, ha="center", style="italic")

    s.arrow((23, 19.5), (29, 19.5))
    s.arrow((53, 19.5), (59, 19.5))
    s.arrow((81, 19.5), (87, 19.5))
    s.plain(26, 25.5, "a handover,\nas a crate", size=8.4, ha="center")
    s.plain(56, 25.5, "an accepted\nhandover", size=8.4, ha="center")

    s.arrow((41, 15), (97, 6.5), dashed=True, colour=GREY, bend=-0.12)
    s.plain(69, 4.0, "or straight through, if the downstream tool reads a crate",
            size=8.6, ha="center", style="italic")

    s.plain(54, 28.5, "The service is inserted into a workflow that already exists. "
                      "Changing either end is not its job.",
            size=9.2, colour=INK, ha="center", bold=True)
    s.save("02-fixed-boundaries.png")


# ------------------------------------------------------------------ 03

def how_one_check_flows():
    s = Sheet(width=112, height=76)

    actors = [
        ("Caller", 9, "grey"),
        ("Sentinel", 30, "blue"),
        ("ContractChecks", 56, "red"),
        ("Engine", 80, "amber"),
        ("ProvenanceWriter", 101, "green"),
    ]
    top, bottom = 70.0, 4.0
    for name, x, colour in actors:
        s.box(x - 9.5, top, 19, 5, name, colour, size=9)
        s.lifeline(x, top, bottom, GREY)

    s.message(9, 30, 66.5, "check(crate, contract, repair_budget)")
    s.note(14, 60.5, 32, 4.6,
           "checksum the crate AS IT ARRIVED,\nbefore anything can alter it", "blue")
    s.message(30, 56, 57.0, "validate(crate, contract)")
    s.message(56, 30, 52.5, "Report, with the verdict already settled", dashed=True)

    s.plain(4, 47.0, "if the repair budget is 0, which is the default:", size=8.8,
            colour=INK, bold=True)
    s.note(30, 41.5, 50, 4.4, "the model is never asked anything at all", "grey")

    s.plain(4, 36.0, "if a budget was given:", size=8.8, colour=INK, bold=True)
    s.message(30, 80, 32.0, "propose a value for one repairable violation")
    s.message(80, 30, 27.5, "a value, or nothing", dashed=True)
    s.message(30, 56, 23.0, "validate(the repaired copy, contract)")
    s.message(56, 30, 18.5, "a new Report", dashed=True)
    s.note(33, 12.5, 48, 5.0,
           "the change is kept only if that value now passes every\n"
           "rule about it, and nothing new broke anywhere", "amber")

    s.message(30, 101, 8.5, "write(crate, blessing)")
    s.message(101, 30, 5.6, "the crate, with the record inside it", dashed=True)
    s.save("03-how-one-check-flows.png")


# ------------------------------------------------------------------ 05

def where_a_decision_may_be_made():
    s = Sheet(width=104, height=40)

    s.group(1, 20, 44, 18, "May decide", "green")
    s.box(4, 29.5, 38, 6, "ContractChecks\napplies the requirements", "green", size=9.5)
    s.box(4, 22, 38, 6, "Report\ndraws the verdict from the findings", "green", size=9.5)
    s.arrow((23, 29.5), (23, 28.2), colour=GREEN)

    s.group(50, 2, 53, 36, "May never decide", "red")
    pairs = [
        ("Sentinel", "orchestrates"),
        ("Engine", "a model: proposes only"),
        ("Repairer", "writes, then asks the rules"),
        ("ProvenanceWriter", "records"),
        ("Api", "the web interface"),
        ("AgentInterface", "for a coordinating agent"),
    ]
    for i, (name, what) in enumerate(pairs):
        y = 30.0 - i * 4.9
        s.box(53, y, 47, 4.1, f"{name}   ({what})", "red", size=9)

    s.plain(52, 16.0,
            "A test proves it: a rule engine that refuses everything, and another that\n"
            "accepts everything. The verdict must follow the engine, whatever the crate.",
            size=9, colour=INK, ha="center", style="italic")
    s.save("05-where-a-decision-may-be-made.png")


# ------------------------------------------------------------------ 06

def a_contract_is_data():
    s = Sheet(width=112, height=26)

    s.box(1, 11, 24, 9, "a_handover.yaml\nin the mounted folder", "green", size=9.5)
    s.box(31, 11, 24, 9, "parse()\nrefuses anything it\ndoes not understand", "teal",
          size=9.5)
    s.box(61, 11, 20, 9, "Contract\nwith Requirements", "purple", size=9.5)
    s.box(87, 11, 24, 9, "ContractChecks\none branch per verb", "red", size=9.5)

    for a, b in ((25, 31), (55, 61), (81, 87)):
        s.arrow((a, 15.5), (b, 15.5))

    s.plain(56, 7.0,
            "No class for any handover. No registration call. No table mapping a name to code.",
            size=9.4, colour=INK, ha="center", bold=True)
    s.plain(56, 3.4,
            "A test greps the service source for every handover name it knows, "
            "and fails the day one appears.",
            size=9, colour=GREY, ha="center", style="italic")
    s.save("06-a-contract-is-data.png")


# ------------------------------------------------------------------ 07

def the_repair_path():
    s = Sheet(width=96, height=78)

    s.box(30, 71, 30, 5.5, "A violation", "red", size=10)
    s.diamond(45, 64, 40, 8.5, "Does the contract mark this\nrequirement repairable?")
    s.box(1, 58, 21, 5.5, "The model never sees it", "grey", size=9.2)
    s.box(30, 51, 30, 5.5, "The model is asked", "amber", size=10)
    s.box(26, 41, 38, 7, "The value is written at the one\nentity the rules named, on a copy",
          "amber", size=9.3)
    s.box(26, 32, 38, 5.5, "The whole contract runs again", "red", size=9.5)
    s.diamond(45, 22, 50, 11,
              "Does every requirement reading that value\n"
              "now pass, and did nothing new break?")
    s.box(54, 5, 40, 8, "Kept. The crate records that the value\n"
                        "was recovered from text, not stated", "green", size=9)
    s.box(2, 5, 40, 8, "Discarded. The original crate\nis returned untouched", "red",
          size=9)

    s.arrow((45, 71), (45, 68.3))
    s.arrow((25, 64), (22, 61.5), "no", colour=GREY, label_offset=(-1.0, 1.6))
    s.arrow((45, 59.7), (45, 56.5), "yes", label_offset=(2.6, 0))
    s.arrow((45, 51), (45, 48))
    s.arrow((45, 41), (45, 37.6))
    s.arrow((45, 32), (45, 27.6))
    s.arrow((60, 22), (74, 13.2), "yes", colour=GREEN, label_offset=(4.0, 1.6))
    s.arrow((30, 22), (22, 13.2), "no", colour=RED, label_offset=(-3.6, 1.6))

    s.plain(48, 1.2,
            "The default repair budget is 0, so by default no model is contacted at all.",
            size=9.2, colour=INK, ha="center", bold=True)
    s.save("07-the-repair-path.png")


# ------------------------------------------------------------------ 09

def the_two_ways_in():
    s = Sheet(width=100, height=46)

    s.box(4, 37, 36, 6.5, "A pipeline, or a person", "grey", size=10)
    s.box(60, 37, 36, 6.5, "A coordinating agent", "grey", size=10)

    s.box(4, 23, 36, 8, "Api\nHTTP, standard library only", "blue", size=9.5)
    s.box(60, 23, 36, 8, "AgentInterface\nModel Context Protocol,\n"
                         "over standard in and out", "purple", size=9)

    s.box(30, 9, 40, 7, "Sentinel", "blue", size=12, bold=True)

    s.arrow((22, 37), (22, 31.3), "POST /check/{name}", colour=BLUE,
            label_offset=(0, 0.4))
    s.arrow((78, 37), (78, 31.3), "tools/call check_handover", colour=PURPLE,
            label_offset=(0, 0.4))
    s.arrow((22, 23), (40, 16.2), colour=BLUE, bend=0.1)
    s.arrow((78, 23), (60, 16.2), colour=PURPLE, bend=-0.1)

    s.plain(25, 19.5, "returns the crate", size=8.8, colour=BLUE, ha="center")
    s.plain(76, 19.5, "never returns the crate", size=8.8, colour=PURPLE,
            ha="center", bold=True)

    s.plain(50, 5.0,
            "A test fails if the two ever give different verdicts.",
            size=9.6, colour=INK, ha="center", bold=True)
    s.plain(50, 1.8,
            "A crate is thousands of lines of JSON. In an agent's context it costs money "
            "on every call,\nand invites the agent to start editing laboratory records.",
            size=8.8, colour=GREY, ha="center", style="italic")
    s.save("09-the-two-ways-in.png")


# ------------------------------------------------------------------ 10

def the_container():
    s = Sheet(width=100, height=64)

    s.group(1, 40, 44, 21, "base", "blue")
    s.box(3.5, 52.5, 39, 4.6, "dependencies", "blue", size=9.3)
    s.box(3.5, 47, 39, 4.6, "src/ installed", "blue", size=9.3)
    s.box(3.5, 41.5, 39, 4.6, "vocabulary/", "blue", size=9.3)

    s.group(1, 9, 44, 26, "test: everything here is thrown away", "grey")
    s.box(3.5, 26.5, 39, 4.6, "tests/", "grey", size=9.3)
    s.box(3.5, 21, 39, 4.6, "examples/", "grey", size=9.3)
    s.box(3.5, 12, 39, 8, "pytest runs, and on success\ntouches a marker file",
          "grey", size=9.3)

    s.group(55, 9, 44, 52, "runtime: the final image", "green")
    s.box(57.5, 50, 39, 7, "the marker, copied from\nthe test stage", "green", size=9.3)
    s.box(57.5, 41.5, 39, 6, "/contracts, created empty", "green", size=9.3)
    s.box(57.5, 33.5, 39, 5.5, "runs as a non-root user", "green", size=9.3)
    s.box(57.5, 23, 39, 8, "no tests, no example,\nno contracts", "green", size=9.3)

    s.arrow((23, 40), (23, 35.4), colour=GREY)
    s.arrow((45, 53), (55, 53), colour=GREEN)
    s.arrow((45, 16), (57.5, 51), "the marker only", colour=RED, bend=0.3,
            label_offset=(-7.5, -11))

    s.plain(50, 5.0,
            "The marker cannot exist unless the suite passed, and the final image cannot be\n"
            "built without it. So an image whose tests fail is never produced.",
            size=9.2, colour=INK, ha="center", bold=True)
    s.plain(50, 1.2,
            "The build context is the product folder. Nothing outside it is read, which is "
            "what lets the\nproduct be copied out of its repository on its own and still "
            "build, test and run.",
            size=8.8, colour=GREY, ha="center", style="italic")
    s.save("10-the-container.png")


# ------------------------------------------------------------------ 11

def a_deployment():
    s = Sheet(width=96, height=74)

    s.box(30, 67, 36, 5.5, "Your folder of contract files", "green", size=10)
    s.diamond(48, 59, 40, 9, "1. Is every contract readable?")
    s.box(1, 52.5, 24, 11, "Refused.\nNothing built, nothing\nstarted. Exit code 1.\n"
                           "It names the file and\nthe requirement", "red", size=8.4)
    s.box(28, 40, 40, 8.5, "2. Build the generic image.\nThe product's 200 tests run\n"
                           "inside the build and gate it", "blue", size=9)
    s.box(28, 29, 40, 7, "3. Run it, with your folder mounted\n"
                         "read only at /contracts", "blue", size=9)
    s.diamond(48, 19, 40, 10, "4. Is the instance serving\nexactly what was validated?")
    s.box(1, 14, 24, 9, "Refused.\nIt names what it expected\nand what it found", "red",
          size=8.4)
    s.box(50, 4, 44, 7, "Deployed, and serving on a port", "green", size=10)

    s.arrow((48, 67), (48, 63.6))
    s.arrow((28, 59), (25, 58.5), "no", colour=RED, label_offset=(0.4, 1.8))
    s.arrow((48, 54.5), (48, 48.7), "yes", colour=GREEN, label_offset=(3.0, 0))
    s.arrow((48, 40), (48, 36.2))
    s.arrow((48, 29), (48, 24.1))
    s.arrow((28, 19), (25, 19.5), "no", colour=RED, label_offset=(0.4, 1.8))
    s.arrow((68, 19), (72, 11.3), "yes", colour=GREEN, label_offset=(3.6, 1.2))

    s.plain(48, 1.0,
            "A program, not a page of instructions. No person follows steps and nothing "
            "is tailored by hand.",
            size=9.4, colour=INK, ha="center", bold=True)
    s.save("11-a-deployment.png")


if __name__ == "__main__":
    print("drawing the system manual's diagrams")
    three_separate_things()
    fixed_boundaries()
    how_one_check_flows()
    where_a_decision_may_be_made()
    a_contract_is_data()
    the_repair_path()
    the_two_ways_in()
    the_container()
    a_deployment()
    print("\n04-the-components.png is drawn by 04_the_components.py")
