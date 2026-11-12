# The Architect, in a container.
#
#   docker build -f architect/deploy/Dockerfile -t dbtl-architect:dev .
#
# **The build context is the repository root**, because the Architect is not a
# standalone product: it drives the four phase agents and the four sentinels in
# framework/, and a container that cannot reach them would demonstrate nothing.
# Every COPY below names exactly what goes in. Nothing else from the working
# tree reaches the image - not data/, not cache/, not runs/, not the slides and
# PDFs in the root - and because BuildKit only transfers the files the COPY
# lines ask for, a 2 GB working tree still builds in seconds.
#
# NOTHING IS INSTALLED. There is no pip install step anywhere in this file,
# which is not a saving but a claim being honoured: requirements.txt says every
# demo and every script here runs on the Python standard library alone, and an
# image that quietly installed something would make that untestable. So there
# is no compiler in any layer, no headers, no wheel cache to clean up, and the
# final image is the slim base plus about 1.5 MB of Python. PyYAML is still
# optional and still absent; load_contract() reads the *.schema.json form of
# each contract, which is what the YAML is generated from.
#
# NO KEY IS BUILT IN. The image contains no key, no key file and no default
# key, and it cannot: see architect/deploy/README.md. The default engine is
# RulesEngine - deterministic, offline - and a run with no key is the normal
# case, not a degraded one.
#
# ONE THING LISTENS, and only when it is asked to: `architect/web/server.py`,
# which the `web` service in compose.yaml runs. Everything else here is a
# run-to-completion job. The EXPOSE below is documentation - it publishes
# nothing by itself - and the compose file is where the address is decided.
EXPOSE 8765

# What follows was written when nothing in this framework bound a socket:
# no port and no bind address. If one is ever added, the operator says where it
# binds; see the commented block in compose.yaml.
#
# Three stages:
#
#   code      the base and the source, which is all there is
#   test      runs the suite and the engine's key checks, then leaves a marker
#   runtime   the final image: code, the tests, and proof the checks passed
#
# The runtime stage copies one marker file out of the test stage, so the checks
# are a gate and not an optional extra: the marker cannot exist unless they
# passed, and the image cannot be built without the marker.


# ----------------------------------------------------------------- code
# Pinned by digest, not by tag. `python:3.13-slim` is a different program on a
# different day, and an image that silently changes under a framework whose
# whole argument is reproducibility is the wrong default. This digest is the
# multi-architecture index, so it builds on arm64 and amd64 alike. To move it
# on: docker buildx imagetools inspect python:3.13-slim
FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS code

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# The framework: the contracts, the profiles, the vocabulary, the four phase
# agents, the four sentinels, the validator, the crate store, the engines.
COPY framework/ ./framework/

# The centre, and its five parts.
COPY architect/ ./architect/

# The use case. The Architect must not understand the science, but it has to
# have some to orchestrate, and this is the one that is written.
COPY usecases/ ./usecases/

# The demonstrations. tests/test_framework.py runs demo.py and demo_cycle.py as
# subprocesses and reads their output, so these are part of the test suite
# whether or not anybody runs them by hand.
COPY demo.py demo_cycle.py demo_d2b.py demo_l2d.py ./

# Six of the scripts, not all of them. These six import nothing but the
# standard library and this framework. The rest of scripts/ belongs to the
# literature survey and needs matplotlib, pandas and network access; shipping
# them would mean either a broken script in the image or a toolchain that
# exists only for them.
COPY scripts/ask.py scripts/trace.py scripts/check_crate.py \
     scripts/new_handover.py scripts/show_agents.py scripts/prove_engine.py \
     ./scripts/

# The promise itself, so it can be read inside the image and checked against it.
COPY requirements.txt ./

# Byte-code compiled on somebody's laptop, for another Python, in a directory
# that was copied in because it sits inside the source tree.
RUN find /app -name __pycache__ -type d -prune -exec rm -rf {} + \
 && find /app -name '*.pyc' -delete


# ----------------------------------------------------------------- test
# Everything in this stage is thrown away except the marker.
FROM code AS test

COPY tests/ ./tests/

# Two gates, and they check different things.
#
# The suite proves the framework works: it runs the demos as subprocesses,
# asserts the verdicts they report, checks that the profiles' units are
# coherent, that a graph query reaches a physical sample on disk, and that a
# patch outside the paths the validator reported is refused. It runs with no
# network and no key, which is the point - if it needed either, the default
# deployment below would be a fiction.
#
# The engine's own checks prove the key discipline: no key is a normal state,
# the ledger learns the model and not the key, the key travels in a header and
# not in the body or the URL, and an API error that quotes the key back is
# redacted before it is raised.
RUN python3 tests/test_framework.py && python3 framework/engines_api.py \
 && touch /app/.checks-passed


# ----------------------------------------------------------------- runtime
FROM code AS runtime

# The tests ship, unlike in sentinel-oo where they deliberately do not. The
# reason is the health check below: a check that proves only that Python starts
# is worth nothing, so the check is the suite, and the suite has to be here to
# be run. They are about 50 KB.
COPY tests/ ./tests/

# The gate. This file exists only if both checks passed in the stage above, so
# an image whose tests fail is never produced.
COPY --from=test /app/.checks-passed /app/.checks-passed

# Build identity, recorded in the environment so a run can say which image it
# came from. No key is ever a build argument: a --build-arg is visible in
# `docker history` for the life of the image.
ARG IMAGE_TAG=dev
ARG GIT_COMMIT=unset
ENV ARCHITECT_IMAGE_TAG=${IMAGE_TAG} \
    ARCHITECT_GIT_COMMIT=${GIT_COMMIT}

# Where every run is written: ledgers, crates, graphs, handover packages. It is
# created and owned here so that a volume mounted over it inherits the right
# ownership. It is deliberately NOT declared as a VOLUME: a declared volume
# makes `docker run` create an anonymous one that nobody ever cleans up and
# that hides whether the operator mounted anything at all. Mount it explicitly
# - compose.yaml does - or accept that the run dies with the container.
RUN mkdir -p /app/runs \
 && useradd --create-home --uid 10001 architect \
 && chown -R architect /app

# Not root. This process reads crates other people wrote and runs whatever
# callable is handed to a phase; neither has any business being root.
USER architect

# The health check is the test suite. It takes a few seconds, runs four
# demonstrations end to end and asserts their verdicts, so a container that
# answers it is a container in which the framework demonstrably works.
#
# It writes its own run directories into /app/runs - that is the price of a
# check that is a real run. A long interval, because nothing here is a service
# that degrades; one retry, because this suite is deterministic and a second
# identical failure would tell you nothing a first did not.
HEALTHCHECK --interval=10m --timeout=180s --start-period=5s --retries=1 \
    CMD ["python3", "/app/tests/test_framework.py"]

# Any file in the image is runnable, which is the whole interface:
#
#   docker run --rm IMAGE                            the suite (the default)
#   docker run --rm IMAGE architect/wiring.py        the real agents, wired
#   docker run --rm IMAGE architect/architect.py     the loop, verdicts scripted
#   docker run --rm IMAGE framework/engines_api.py   what happens to a key
#   docker run --rm IMAGE scripts/show_agents.py     what is in here
ENTRYPOINT ["python3"]
CMD ["tests/test_framework.py"]
