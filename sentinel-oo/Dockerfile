# sentinel-oo: the generic product.
#
# The image built here contains the service and nothing else. It holds no
# deployable contracts, no use case and no example data. A deployment
# supplies its own contracts by mounting a folder at /contracts, and the same
# image serves any DBTL cycle.
#
# **The build context is this folder.** Nothing outside sentinel-oo/ is read,
# which is the point: the product can be copied out of this repository on its
# own and still build, test and run.
#
#   docker build -t sentinel-oo:dev \
#       --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) sentinel-oo/
#
# Three stages:
#
#   base      dependencies and the service, which is all the product is
#   test      adds the test suite and the worked example, and runs the suite
#   runtime   the final image: base, plus proof the suite passed
#
# The runtime stage copies one marker file out of the test stage. That is what
# makes the test run a gate rather than an optional extra: the marker cannot
# exist unless the suite passed, and the final image cannot be built without
# the marker. Nothing else from the test stage reaches the final image, so
# neither the tests nor the example ship.


# ---------------------------------------------------------------- base
FROM python:3.13-slim AS base

WORKDIR /app/sentinel-oo

# Dependencies first, because they change rarely and this layer is almost
# always cached. roc-validator is a third party tool, present so that the
# test asserting the returned crate is still a valid RO-Crate is answered by
# something that knows nothing about this service.
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir 'PyYAML>=6' pytest 'roc-validator>=0.13'

# The service. This is the whole of the product.
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# The agreed core vocabulary, which is generic. A site's own mapping of local
# names onto those terms is tailored, so it belongs to a deployment and is
# mounted rather than built in.
COPY vocabulary/ ./vocabulary/


# ---------------------------------------------------------------- test
# Everything in this stage is thrown away. Nothing it copies reaches the
# final image.
FROM base AS test

COPY tests/ ./tests/

# The product's own worked example: a coating laboratory, deliberately not a
# DBTL cycle. The test fixtures read it, and it lives inside the product, so
# this stage reads nothing from outside sentinel-oo/.
COPY examples/ ./examples/

RUN python -m pytest -q && touch /app/tests-passed


# ---------------------------------------------------------------- runtime
FROM base AS runtime

# The gate. This file exists only if the suite passed, and the build fails
# here if it did not, so an image whose tests fail is never produced.
COPY --from=test /app/tests-passed /app/tests-passed

# The build identity: the image tag, the commit it was built from, and a
# checksum over the contracts a deployment supplies. The three are tied
# together and any one of them should recover the other two.
ARG IMAGE_TAG=dev
ARG GIT_COMMIT=unset
ARG RULES_CHECKSUM=none
ENV SENTINEL_IMAGE_TAG=${IMAGE_TAG} \
    SENTINEL_GIT_COMMIT=${GIT_COMMIT} \
    SENTINEL_RULES_CHECKSUM=${RULES_CHECKSUM} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Where a deployment mounts its contracts. The folder is created empty so the
# service starting with nothing mounted fails by saying it has no contracts,
# rather than by saying a path does not exist.
ENV SENTINEL_CONTRACTS=/contracts
RUN mkdir -p /contracts

# Runs as somebody other than root. A service that reads files other people
# send it has no business running as root.
RUN useradd --create-home --uid 10001 sentinel && chown -R sentinel /app /contracts
USER sentinel

ENTRYPOINT ["python", "-m", "sentinel_oo"]
CMD ["--help"]
