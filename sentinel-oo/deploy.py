#!/usr/bin/env python3
"""Deploy a tailored instance of sentinel-oo from a folder of contracts.

This is the deployment step, and it is a program rather than a page of
instructions. You run it, it runs, and at the end an instance is serving. No
person follows steps and nothing is tailored by hand.

    python deploy.py <a folder of contract files>

What it does, in order, stopping at the first thing that fails:

  1. Reads every contract in the folder and refuses the deployment if any of
     them is malformed, naming the file and the fault. This happens before
     anything is built or started, because finding out at first use means
     finding out in front of whoever sent the handover.

  2. Builds the generic image from this folder. The product's own test suite
     runs inside that build and the image cannot be produced if it fails.

  3. Starts an instance with the contracts folder mounted read only at
     /contracts. The image is not modified and holds no contracts of its own.

  4. Waits for the instance to answer, then checks that it is serving exactly
     the contracts that were validated in step 1, comparing names, versions
     and a checksum over the files.

     That check catches two things: the wrong folder being mounted, and a
     contract edited between step 1 and step 3, which is a real window
     because the build in step 2 takes a minute. It was tested by pointing
     it at an instance serving a different folder, and it reported which
     contracts it expected and which it found.

Nothing here is specific to any DBTL cycle. The contracts folder is the whole
of the tailoring.

    python deploy.py <contracts> --check-only   validate and stop
    python deploy.py <contracts> --stop         stop a running instance
    python deploy.py <contracts> --no-build     use the existing image
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

# The product's own contract reader, used to validate before deploying. The
# deployment program and the running service therefore agree about what a
# valid contract is, because they are the same code.
sys.path.insert(0, str(HERE / "src"))

from sentinel_oo.contract import ContractError, ContractRegistry  # noqa: E402

DEFAULT_IMAGE = "sentinel-oo:dev"
DEFAULT_PORT = 8080

# The model container. Started by this program unless the deployment points
# somewhere else, because the model is on by default and a deployment that
# cannot reach one is a deployment doing none of what it was deployed to do.
#
# Found by a deployment trial on 11 November 2026: the deployment guide
# labelled `python deploy.py <contracts>` as giving "a model beside it", and
# it started only the sentinel container. Its own stage 4 then reported
# "configured but not answering", which was correct and unhelpful.
MODEL_IMAGE = "ollama/ollama:0.5.7"
MODEL_PORT = 11434
DEFAULT_MODEL = "qwen2.5:14b"

# The model server image, before any model is downloaded into it. Announced
# and timed separately, because `docker run` pulls it first and a 300 second
# limit is not enough for a gigabyte and a half on conference wifi. Found on
# 11 November 2026 by running this with nothing cached.
MODEL_IMAGE_GB = 2

# Roughly, for the models likely to be asked for, so somebody on hackathon
# wifi is told before several gigabytes start moving rather than after.
# Only used when the model is not already downloaded.
MODEL_SIZES_GB = {
    "qwen2.5:14b": 9,
    "qwen2.5-coder:14b": 9,
    "qwen2.5:7b": 5,
    "llama3.1:8b": 5,
    "llama3.3:70b": 43,
}


class Failed(Exception):
    """Something went wrong and the deployment stopped. Carries the reason."""


def say(step: str, text: str = "") -> None:
    if step:
        print(f"\n{step}")
    if text:
        print(text)


def run(command: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, check=False
    )


# ------------------------------------------------------------------ step 1


def read_contracts(folder: Path):
    """Load every contract, or stop with the reason.

    A deployment that starts with a broken contract discovers the problem at
    first use, which means discovering it in front of whoever sent the
    handover. Finding out here costs nobody anything.
    """
    if not folder.is_dir():
        raise Failed(f"there is no folder at {folder}")

    files = sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml"))
    if not files:
        raise Failed(
            f"{folder} holds no contract files. A deployment is a folder of "
            "them, and an instance with none would refuse every handover it "
            "was given."
        )

    try:
        registry = ContractRegistry.from_dir(folder)
    except ContractError as exc:
        raise Failed(
            f"a contract in {folder} cannot be read, so nothing was "
            f"deployed:\n\n    {exc}\n\n"
            "See docs/WRITING_A_CONTRACT.md for what a requirement may say."
        ) from exc

    held = sorted(registry.list(), key=lambda c: c.name)
    for contract in held:
        print(f"   {contract.name:28} {contract.version:8} "
              f"{len(contract.requirements):3} requirements")
    print(f"   checksum over all of them: {registry.checksum()}")
    return registry


# ------------------------------------------------------------------ step 2


def build_image(image: str) -> None:
    commit = "unset"
    found = run(["git", "-C", str(HERE), "rev-parse", "--short", "HEAD"], timeout=30)
    if found.returncode == 0:
        commit = found.stdout.strip()

    built = run([
        "docker", "build",
        "-t", image,
        "--build-arg", f"GIT_COMMIT={commit}",
        "--target", "runtime",
        str(HERE),
    ])
    if built.returncode != 0:
        tail = "\n".join((built.stdout + built.stderr).splitlines()[-25:])
        raise Failed(
            "the image did not build, so nothing was deployed. The product's "
            "test suite runs inside this build, so a test failure stops it "
            f"here by design:\n\n{tail}"
        )
    print(f"   {image} built from {HERE}")
    print("   the product's test suite ran inside the build and passed")


def image_exists(image: str) -> bool:
    found = run(["docker", "image", "inspect", image], timeout=60)
    return found.returncode == 0


# ------------------------------------------------------------------ step 3


def stop_instance(name: str, quiet: bool = False) -> None:
    """Remove the sentinel, the model beside it, and the network they share.

    All three, because this program created all three. Leaving a model
    container running after a stop is a 9 gigabyte surprise on somebody's
    laptop.
    """
    for container in (name, model_name(name)):
        run(["docker", "rm", "-f", container], timeout=120)
    run(["docker", "network", "rm", network_name(name)], timeout=60)
    if not quiet:
        print(f"   stopped and removed {name}, {model_name(name)} "
              f"and the network between them")


def model_name(name: str) -> str:
    return f"{name}-model"


def network_name(name: str) -> str:
    return f"{name}-net"


def model_already_there(container: str, model: str) -> bool:
    """Is the model already downloaded into this container's volume?"""
    found = run(["docker", "exec", container, "ollama", "list"], timeout=60)
    return found.returncode == 0 and model.split(":")[0] in found.stdout


def agree_to_download(wanted, yes: bool) -> bool:
    """Say what is about to be downloaded and how big it is, then ask.

    Nobody should find out after the event that several gigabytes have
    started moving, least of all on conference wifi. Without a terminal to
    ask in, this stops rather than guessing, and says how to proceed.
    """
    total = sum(size or 0 for _, size in wanted)
    print()
    print("   This deployment needs to download:")
    for what, size in wanted:
        amount = f"about {size} GB" if size else "size unknown"
        print(f"       {what:46} {amount}")
    known = all(size for _, size in wanted)
    print(f"   {'Total: about ' + str(total) + ' GB' if known else 'Total: at least ' + str(total) + ' GB'}, "
          "which on a hotel or conference connection takes a long time.")
    print()

    if yes:
        print("   Proceeding, because --yes was given.")
        return True
    if not sys.stdin.isatty():
        raise Failed(
            "this deployment needs to download "
            f"{'about ' + str(total) if known else 'at least ' + str(total)} "
            "GB and there is nobody to ask.\n"
            "Run again with --yes to agree to it, or with --model-url '' to "
            "deploy without a model."
        )
    return input("   Download now? [y/N] ").strip().lower() in ("y", "yes")


def start_model(name: str, model: str, yes: bool) -> str:
    """Start a model container beside the sentinel and return its address.

    Returns the address the sentinel should use, which is the container
    name on their shared network rather than a port on this machine.
    """
    container = model_name(name)
    network = network_name(name)

    # Everything that may have to be downloaded, totalled before anything
    # starts, so one question covers the whole wait rather than two.
    need_image = not image_exists(MODEL_IMAGE)
    wanted = []
    if need_image:
        wanted.append((f"the model server, {MODEL_IMAGE}", MODEL_IMAGE_GB))

    size = MODEL_SIZES_GB.get(model)
    # Whether the model itself is already there cannot be known until the
    # container runs, so it is assumed to be needed when the image is not
    # there either: a fresh image has an empty store.
    if need_image:
        wanted.append((model, size))

    if wanted and not agree_to_download(wanted, yes):
        raise Failed(
            "the download was declined, so nothing was started.\n"
            "Deploy without a model with --model-url '', or point at one you "
            "already have with --model-url <address>."
        )

    if need_image:
        print(f"   downloading {MODEL_IMAGE}")
        pulled = run(["docker", "pull", MODEL_IMAGE], timeout=3600)
        if pulled.returncode != 0:
            raise Failed(
                f"{MODEL_IMAGE} could not be downloaded:\n\n"
                + (pulled.stdout + pulled.stderr).strip()[-800:]
            )

    run(["docker", "network", "create", network], timeout=60)

    started = run([
        "docker", "run", "-d",
        "--name", container,
        "--network", network,
        # Named after the deployment, so two deployments do not fight over
        # one download and removing one does not take the other's model.
        "-v", f"{container}-store:/root/.ollama",
        MODEL_IMAGE,
    ], timeout=300)
    if started.returncode != 0:
        raise Failed(
            "the model container did not start:\n\n"
            + (started.stdout + started.stderr).strip()
            + "\n\nTo deploy without a model, pass --model-url ''"
        )
    print(f"   {container} started from {MODEL_IMAGE}")

    # Wait for it to answer before asking it for anything.
    for _ in range(60):
        if run(["docker", "exec", container, "ollama", "list"],
               timeout=30).returncode == 0:
            break
        time.sleep(1)

    if model_already_there(container, model):
        print(f"   {model} is already downloaded")
    else:
        if not need_image and not agree_to_download([(model, size)], yes):
            raise Failed(
                "the download was declined, so nothing was started.\n"
                "Deploy without a model with --model-url '', or point at one "
                "you already have with --model-url <address>."
            )
        print(f"   downloading {model}. This is the slow part.")
        pulled = run(["docker", "exec", container, "ollama", "pull", model],
                     timeout=7200)
        if pulled.returncode != 0:
            raise Failed(
                f"{model} could not be downloaded:\n\n"
                + (pulled.stdout + pulled.stderr).strip()[-800:]
            )
        print(f"   {model} downloaded")

    return f"http://{container}:{MODEL_PORT}"


def start_instance(name: str, image: str, contracts: Path, crates: Path | None,
                   port: int, model_url: str | None, model: str | None,
                   network: str | None = None,
                   reachable_from_network: bool = False) -> None:
    stop_instance(name, quiet=True)

    command = [
        "docker", "run", "-d",
        "--name", name,
        # The loopback interface only, unless asked otherwise.
        #
        # Before 11 November 2026 this published on every interface, so on
        # shared wifi anyone on the same network could send the instance
        # requests. There is no password of any kind. The API manual warned
        # against exactly that and this program did it by default, which is
        # the wrong way round. Found by a deployment trial on 11 November
        # 2026 at a hackathon.
        "-p", f"{'' if reachable_from_network else '127.0.0.1:'}{port}:{port}",
    ]
    if network:
        # The same network as the model beside it, so the sentinel reaches
        # it by container name rather than by a port on this machine.
        command += ["--network", network]
    command += [
        # The whole of the tailoring, and read only: a service that checks
        # handovers has no business editing the contract it checks against.
        "-v", f"{contracts.resolve()}:/contracts:ro",
    ]
    if crates is not None:
        command += ["-v", f"{crates.resolve()}:/crates:ro"]

    # Where the model is, and which one. The model runs in its own
    # container, and that container does not have to be on this machine: a
    # model worth using wants a GPU, and the machine with the GPU is
    # usually not the machine running the service.
    #
    # An empty address is how a deployment says it wants no model, which is
    # a deliberate state rather than a failure.
    if model_url is not None:
        command += ["-e", f"SENTINEL_MODEL_URL={model_url}"]
    if model:
        command += ["-e", f"SENTINEL_MODEL={model}"]

    command += [image, "--serve", "--port", str(port)]

    started = run(command, timeout=120)
    if started.returncode != 0:
        raise Failed(
            "the instance did not start:\n\n"
            + (started.stdout + started.stderr).strip()
        )
    print(f"   container {name} started from {image}")
    if reachable_from_network:
        print("   WARNING: reachable from your whole network, and the "
              "service has no password.")
        print("            On shared wifi anyone on it can send this "
              "instance requests.")
    else:
        print("   reachable from this machine only. Pass "
              "--reachable-from-network to change that")
    print(f"   contracts mounted read only from {contracts}")


# ------------------------------------------------------------------ step 4


def ask(port: int, path: str, timeout: float = 2.0):
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}{path}", timeout=timeout
    ) as answer:
        return json.loads(answer.read().decode())


def wait_until_answering(name: str, port: int, seconds: int = 30):
    deadline = time.time() + seconds
    last = None
    while time.time() < deadline:
        try:
            return ask(port, "/health")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = exc
            time.sleep(0.5)

    logs = run(["docker", "logs", "--tail", "25", name], timeout=60)
    raise Failed(
        f"the instance did not answer on port {port} within {seconds} "
        f"seconds. The last attempt said: {last}\n\n"
        + (logs.stdout + logs.stderr).strip()
    )


def confirm_it_serves_what_was_validated(registry, port: int) -> None:
    """The instance must hold exactly the contracts that were validated.

    Without this a wrong path, a stale mount or a contract edited after
    validation would deploy silently, and the first anybody would know is a
    handover being judged against something nobody checked.
    """
    served = ask(port, "/contracts")

    wanted = {c.name: c.version for c in registry.list()}
    got = {c["name"]: c["version"] for c in served.get("contracts", [])}

    if got != wanted:
        raise Failed(
            "the running instance is not serving the contracts that were "
            f"validated.\n    validated: {wanted}\n    serving:   {got}\n"
            "The usual cause is the wrong folder being mounted."
        )

    if served.get("checksum") != registry.checksum():
        raise Failed(
            "the running instance serves contracts with the same names and "
            "versions but a different checksum, so a file has been edited "
            "since it was validated.\n"
            f"    validated: {registry.checksum()}\n"
            f"    serving:   {served.get('checksum')}"
        )

    print(f"   {len(got)} contract(s) served, checksum matches what was "
          "validated")


# ------------------------------------------------------------------ the whole


def deploy(args) -> int:
    contracts = Path(args.contracts)
    crates = Path(args.crates) if args.crates else None
    name = args.name or f"sentinel-{contracts.resolve().parent.name}"

    if args.stop:
        say("Stopping", "")
        stop_instance(name)
        return 0

    print("sentinel-oo: deploying a tailored instance")
    print(f"the generic product is at {HERE}")

    say(f"1. Reading contracts from {contracts}")
    registry = read_contracts(contracts)

    if args.check_only:
        say("", "The contracts are readable. Nothing was built or started, "
                "because --check-only was given.")
        return 0

    say("2. Building the generic image")
    if args.no_build:
        if not image_exists(args.image):
            raise Failed(
                f"--no-build was given but there is no image called "
                f"{args.image}. Run again without --no-build."
            )
        print(f"   using the existing {args.image}, because --no-build was given")
    else:
        build_image(args.image)

    model = args.model or DEFAULT_MODEL
    network = None
    model_url = args.model_url

    if model_url is None:
        # Nothing was said, so this program provides the model, which is
        # what "the model is on by default" has to mean for the one command
        # the documents tell people to use.
        say("3. Starting the model beside it")
        model_url = start_model(name, model, args.yes)
        network = network_name(name)
    elif model_url == "":
        say("3. The model", "   none: --model-url was empty, so this "
                            "deployment runs without one")
    else:
        say("3. The model",
            f"   not started here: {model_url} was given, so the model is "
            "somebody else's to run")

    say("4. Starting the instance")
    start_instance(name, args.image, contracts, crates, args.port,
                   model_url, model, network, args.reachable_from_network)

    say("5. Checking the instance serves what was validated")
    health = wait_until_answering(name, args.port)
    print(f"   answering on http://127.0.0.1:{args.port}")
    print(f"   image {health.get('image_tag')}, commit {health.get('git_commit')}")
    model_state = (health.get("model") or {})
    print(f"   model: {model_state.get('state', 'unknown')}"
          f"  ({model_state.get('engine', 'none')})")
    if model_state.get("state") == "configured but not answering":
        print(f"   WARNING: {model_state.get('detail', '')}")
        print(f"            {model_state.get('effect', '')}")
    confirm_it_serves_what_was_validated(registry, args.port)

    # The one with the most requirements, because a folder often holds a
    # substantial contract and a stub, and suggesting the stub teaches the
    # reader nothing.
    first = max(registry.list(), key=lambda c: len(c.requirements)).name
    say("Deployed.", f"""
To see what it holds:

    curl -s http://127.0.0.1:{args.port}/contracts

To check a handover:

    curl -s -X POST --data-binary @<a crate>/ro-crate-metadata.json \\
      http://127.0.0.1:{args.port}/check/{first}

To stop it:

    python {Path(__file__).name} {args.contracts} --stop
""".rstrip())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="deploy",
        description=(
            "Deploy a tailored instance of sentinel-oo from a folder of "
            "contract files. The contracts are the whole of the tailoring: "
            "the image is generic and is not modified."
        ),
    )
    parser.add_argument(
        "contracts",
        help="a folder of contract files, which is what tailors the instance",
    )
    parser.add_argument(
        "--crates",
        help="a folder of crates to mount read only at /crates, for trying it",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"the port to serve on, default {DEFAULT_PORT}")
    parser.add_argument(
        "--model-url", default=os.environ.get("SENTINEL_MODEL_URL"),
        help=("where the model is, such as http://gpu-box.lan:11434. Leave "
              "it out and a model container is started beside the service. "
              "Give an address and that model is used instead, and nothing "
              "is started here. Give an empty value for no model at all"),
    )
    parser.add_argument(
        "--model", default=os.environ.get("SENTINEL_MODEL"),
        help="which model to use, pinned by name so a run repeats",
    )
    parser.add_argument("--image", default=DEFAULT_IMAGE,
                        help=f"the image to build and run, default {DEFAULT_IMAGE}")
    parser.add_argument("--name",
                        help="the container name, default sentinel-<folder>")
    parser.add_argument(
        "--yes", action="store_true",
        help=("agree in advance to downloading the model, which is several "
              "gigabytes. Without it you are asked, and without a terminal "
              "to ask in the deployment stops"),
    )
    parser.add_argument(
        "--reachable-from-network", action="store_true",
        help=("let other machines on your network reach this instance. Off "
              "by default, because the service asks for no password of any "
              "kind, so on shared wifi this means anyone on it can send it "
              "requests"),
    )
    parser.add_argument("--no-build", action="store_true",
                        help="use the existing image instead of building")
    parser.add_argument("--check-only", action="store_true",
                        help="validate the contracts and stop")
    parser.add_argument("--stop", action="store_true",
                        help="stop and remove the instance")
    args = parser.parse_args(argv)

    try:
        return deploy(args)
    except Failed as exc:
        print(f"\nDEPLOYMENT STOPPED\n\n{exc}\n", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        print(f"\nDEPLOYMENT STOPPED\n\na command took too long: {exc}\n",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
