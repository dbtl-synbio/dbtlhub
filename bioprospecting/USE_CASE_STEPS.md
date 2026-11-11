# The bioprospecting use case, step by step

The 14 practical steps of a bioprospecting Design, Build, Test, Learn cycle, and where the four handovers sit between them.

Drafted on 8 November 2026 from a worked bioprospecting cycle run in Anil Wipat's laboratory at Newcastle University, and confirmed as correct on 9 November 2026. The steps are written generically so they fit any bioprospecting project.

DBTL stands for Design, Build, Test, Learn. Bioprospecting here means searching genomes and metagenomes for enzymes that could be used industrially.

## The diagram

```
  DESIGN                 BUILD                  TEST                   LEARN
 ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
 │1 Search metagen- │   │5 Synthesise DNA  │   │9 Run enzyme      │   │12 Record results │
 │  ome for enzyme  │   │  (vendor)        │   │  reactions with  │   │  against each    │
 │  candidates      │   │                  │   │  substrates      │   │  candidate       │
 ├──────────────────┤   ├──────────────────┤   ├──────────────────┤   ├──────────────────┤
 │2 Filter on pre-  │   │6 Rehydrate and   │   │10 Measure on     │   │13 Compare hits   │
 │  dicted structure│   │  amplify DNA     │   │  plate reader    │   │  with sequence   │
 │  and solubility  │   │  (PCR)           │   │                  │   │  and structure   │
 ├──────────────────┤   ├──────────────────┤   ├──────────────────┤   ├──────────────────┤
 │3 Select a        │   │7 Check PCR       │   │11 Call hits      │   │14 Recommend what │
 │  diverse panel   │   │  products        │   │  (statistics)    │   │  to test next    │
 ├──────────────────┤   ├──────────────────┤   └──────────────────┘   └──────────────────┘
 │4 Prepare DNA     │   │8 Make protein    │
 │  designs for     │   │  (cell-free or   │
 │  synthesis       │   │  fermentation)   │
 └──────────────────┘   └──────────────────┘
        │ Handover 1           │ Handover 2           │ Handover 3           │
        ▼ Construct            ▼ Assembly outputs     ▼ Screening results    │
          specification          and QC results                              │
  ◄──────────────────── Handover 4: model predictions and recommendations ───┘
```

Step 14 and Handover 4 should be drawn with dashed outlines in any slide version, because Matt's cycle never carried them out. He wrote annotations back onto each candidate sequence but never ran a second design round.

## What each handover carries

The four handovers are the four transitions Project 25 promises schemas for. Each schema must specify minimum artefacts, metadata requirements, provenance tracking and quality signals.

| Handover | Between | What passes |
|---|---|---|
| 1. Design to Build | Step 4 and step 5 | Construct specifications: the identifier, the amino acid sequence, the codon-optimised DNA sequence, flanking promoter and terminator parts, restriction sites that must not appear, plate and well position. The vendor then replies with a difficulty flag per sequence and a yield. |
| 2. Build to Test | Step 8 and step 9 | Assembly outputs and quality control results: which constructs passed, the product size in base pairs against the accepted range, the concentration in nanograms per microlitre, and the build route used. |
| 3. Test to Learn | Step 11 and step 12 | Screening results: the enzyme and substrate pair, the conditions, the calibration curve, the limits of detection and quantification, the controls used, the hit-calling rule and the result class. |
| 4. Learn to Design | Step 14 and step 1 | Model predictions and recommendations: which candidates have been tested, their outcomes, and what the next selection round should exclude or prioritise. |

## Three things the diagram does not show

**Attrition.** Numbers fall at every step. In Matt's cycle, 96 enzymes were selected, 86 sequences were synthesised, and 75 constructs passed the PCR check. The handover packages have to carry that attrition, and the reason for each loss.

**Two build routes.** Step 8 is a fork, not a single step. Protein can be made by cell-free synthesis, taking under 1 day, or by fermentation in *E. coli*, taking about 4 months in total. The two routes fail on different enzymes and give different test results, so the route taken must travel with the sample.

**Manual steps.** Several steps are done by hand even when the rest is automated, including plate sealing, centrifugation and moving plates between instruments. Any handover contract has to represent a manual step as a first-class thing rather than as a gap between automated ones.
