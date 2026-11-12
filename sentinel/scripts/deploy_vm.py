#!/usr/bin/env python3
"""Put the Architect on a cloud machine, the way sentinel-oo is already put there.

    python3 scripts/deploy_vm.py up                 # prints what it would do
    python3 scripts/deploy_vm.py up --yes           # actually does it
    python3 scripts/deploy_vm.py tunnel --yes       # reach the interface
    python3 scripts/deploy_vm.py down --yes         # stop paying for it

IT PRINTS BY DEFAULT AND DOES NOTHING
Every subcommand is a dry run unless `--yes` is given. This script creates
billable infrastructure on somebody's Google Cloud account, and a tool that
did that on being run by accident would be a badly designed tool. Read what it
prints, then run it again with `--yes`.

WHY IT LOOKS LIKE ANIL WIPAT'S NOTEBOOK
Because it is the same recipe, on purpose:
`dbtlhub/bioprospecting/demonstration/demo_part1.ipynb` deploys `sentinel-oo`
on a Google Cloud VM, and the point of this file is that our side can stand
beside his on the same kind of machine - or, with `--on`, on the very same one.
Same zone, same machine type, same Ubuntu, same Ollama-in-a-named-volume so a
nine-gigabyte model is downloaded once. What differs is the last step: he runs
`deploy.py` to start sentinel-oo on port 8080, and this runs
`docker compose up web` to start the Architect's interface on port 8765.

NOTHING IS PUBLISHED TO THE INTERNET
No firewall rule is created and no port is opened. The interface binds
0.0.0.0 inside its container and is published to 127.0.0.1 on the VM, which
nothing outside that machine can reach; `tunnel` forwards a local port to it
over SSH. The interface has no authentication and its Run button starts real
agents, so a public address would be an open door - and the server refuses a
POST whose Host is not a loopback name anyway, which is the second lock.

WHAT IT WILL NOT DO
It will not delete anything you have not named. `down` deletes the whole
project, which is what actually stops the billing, and it asks you to type the
project's name first even with `--yes`.
"""
from __future__ import annotations

import argparse
import datetime
import shutil
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Anil Wipat's choices, kept rather than second-guessed. Madrid is the nearest
# region to Barcelona; e2-standard-4 is 4 processors and 16 GB, which is what a
# 14-billion-parameter model needs to answer in a reasonable time.
ZONE = "europe-southwest1-a"
MACHINE = "e2-standard-4"
IMAGE_FAMILY = "ubuntu-2404-lts-amd64"
IMAGE_PROJECT = "ubuntu-os-cloud"
DISK = "100GB"
MODEL = "qwen2.5:14b"
OLLAMA_IMAGE = "ollama/ollama:0.5.7"
REPO = "https://github.com/dbtl-synbio/dbtlhub.git"
PORT = 8765

STARTUP = """#!/bin/bash
apt-get update -y
apt-get install -y docker.io docker-compose-v2 git python3 python3-yaml
systemctl enable --now docker
usermod -aG docker $(ls /home | head -1)
touch /var/tmp/ready
"""


def say(step: str, text: str = "") -> None:
    print(f"\n  {step}")
    if text:
        print(textwrap.indent(text.rstrip(), "      "))


class Plan:
    """Collects commands, prints them, and runs them only when told to.

    One object so that a dry run and a real run take exactly the same path
    through this file. A dry run that skipped the code it is supposed to be
    previewing would preview something else.
    """

    def __init__(self, do_it: bool):
        self.do_it = do_it
        self.steps = 0

    def run(self, what: str, *argv: str, allow_fail: bool = False,
            quiet: bool = False) -> subprocess.CompletedProcess | None:
        self.steps += 1
        shown = " ".join(argv)
        print(f"\n  {self.steps:>2}. {what}")
        print(f"      $ {shown}")
        if not self.do_it:
            return None
        done = subprocess.run(argv, capture_output=True, text=True)
        if done.stdout.strip() and not quiet:
            print(textwrap.indent(done.stdout.strip()[-1200:], "      "))
        if done.returncode != 0:
            print(textwrap.indent((done.stderr or done.stdout).strip()[-1200:],
                                  "      ! "))
            if not allow_fail:
                raise SystemExit(
                    f"\n  Stopped at: {what}\n  Nothing after this ran. The "
                    f"resources already made are still there - "
                    f"`deploy_vm.py down` removes them.\n")
        return done


def ssh(plan: Plan, project: str, vm: str, zone: str, command: str,
        what: str, allow_fail: bool = False):
    return plan.run(what, "gcloud", "compute", "ssh", vm, "--zone", zone,
                    "--project", project, "--quiet", "--command", command,
                    allow_fail=allow_fail)


# --------------------------------------------------------------------------- #
#  up
# --------------------------------------------------------------------------- #
def up(args) -> int:
    plan = Plan(args.yes)
    project, vm, zone = args.project, args.vm, args.zone

    print(f"\n{'=' * 78}\nTHE ARCHITECT ON A CLOUD MACHINE\n{'=' * 78}")
    say("project", project)
    say("machine", f"{vm}, {args.machine}, {zone}, {DISK} disk, {IMAGE_FAMILY}")
    say("model", f"{args.model} in a named Docker volume, downloaded once")
    say("reached by", f"an SSH tunnel to 127.0.0.1:{PORT} on the machine. "
                      f"No firewall rule, no public port.")
    if not args.yes:
        say("THIS IS A DRY RUN",
            "Nothing below is executed. Read it, then add --yes.\n"
            "It creates a billable Google Cloud project; `down` deletes it.")

    if not args.on:
        plan.run("make the project",
                 "gcloud", "projects", "create", project,
                 "--name=DBTL Architect", "--quiet")
        if args.billing:
            plan.run("attach billing",
                     "gcloud", "billing", "projects", "link", project,
                     f"--billing-account={args.billing}", "--quiet")
        else:
            say("billing", "no --billing given. Attach an account in the "
                           "console, or the machine cannot be created.")
        plan.run("switch on Compute Engine",
                 "gcloud", "services", "enable", "compute.googleapis.com",
                 f"--project={project}", "--quiet")

        startup = ROOT / "runs" / "deploy-startup.sh"
        startup.parent.mkdir(parents=True, exist_ok=True)
        startup.write_text(STARTUP)
        say("startup script", f"written to {startup}\n{STARTUP}")

        plan.run("make the machine",
                 "gcloud", "compute", "instances", "create", vm,
                 f"--project={project}", f"--zone={zone}",
                 f"--machine-type={args.machine}",
                 f"--image-family={IMAGE_FAMILY}",
                 f"--image-project={IMAGE_PROJECT}",
                 f"--boot-disk-size={DISK}",
                 f"--metadata-from-file=startup-script={startup}",
                 "--quiet")

        # The machine answers SSH before the startup script has finished, so
        # the file it touches at the end is what "ready" means. Until then SSH
        # failing is the expected condition, not a fault.
        say("waiting", "for Docker to finish installing (up to ~7 minutes). "
                       "SSH failing during this is expected.")
        if args.yes:
            import time                                    # noqa: PLC0415
            for _ in range(40):
                got = ssh(plan, project, vm, zone,
                          "test -f /var/tmp/ready && echo yes",
                          "is it ready?", allow_fail=True)
                if got is not None and got.stdout.strip() == "yes":
                    say("ready", "the machine has Docker")
                    break
                time.sleep(10)
            else:
                raise SystemExit(
                    "\n  The machine did not finish installing within about "
                    "seven minutes. Run `up` again, or look at it in the "
                    "console.\n")
    else:
        say("using an existing machine",
            f"{vm} in {project}. Nothing is created; our side is deployed "
            f"beside whatever is already running there.")

    ssh(plan, project, vm, zone,
        f"rm -rf dbtlhub && git clone --depth 1 {REPO} && ls dbtlhub",
        "clone the repository")

    # The model lives in a named volume so that deploying again, or deploying
    # sentinel-oo beside this, does not download nine gigabytes twice.
    volume = f"{args.name}-model-store"
    ssh(plan, project, vm, zone,
        f"set -o pipefail; "
        f"sudo docker volume create {volume} >/dev/null && "
        f"sudo docker rm -f warming >/dev/null 2>&1; "
        f"sudo docker run -d --name warming -v {volume}:/root/.ollama "
        f"{OLLAMA_IMAGE} >/dev/null && "
        f"until sudo docker exec warming ollama list >/dev/null 2>&1; "
        f"do sleep 2; done && "
        f"sudo docker exec warming ollama pull {args.model} 2>&1 | tail -2 && "
        f"sudo docker exec warming ollama list && "
        f"sudo docker rm -f warming >/dev/null",
        f"download {args.model} into the volume {volume}")

    # Our last step, where his runs deploy.py: the interface, published to the
    # machine's own loopback and nowhere else.
    ssh(plan, project, vm, zone,
        f"set -o pipefail; cd dbtlhub/sentinel/architect/deploy && "
        f"sudo ARCHITECT_BIND=127.0.0.1 ARCHITECT_PORT={PORT} "
        f"docker compose up -d --build web 2>&1 | tail -20 && "
        f"sudo docker compose ps",
        "start the Architect's interface")

    ssh(plan, project, vm, zone,
        f"curl -sS -o /dev/null -w 'the interface answers: %{{http_code}}\\n' "
        f"http://127.0.0.1:{PORT}/",
        "check it answers, on the machine itself")

    print(f"\n{'=' * 78}")
    if args.yes:
        print(f"  Up. Reach it with:\n\n"
              f"    python3 scripts/deploy_vm.py tunnel --yes "
              f"--project {project} --vm {vm}\n\n"
              f"  And when you are finished, so it stops costing money:\n\n"
              f"    python3 scripts/deploy_vm.py down --yes --project {project}\n")
    else:
        print(f"  That was a dry run: {plan.steps} step(s), none executed.\n"
              f"  Add --yes to carry them out.\n")
    return 0


# --------------------------------------------------------------------------- #
#  tunnel
# --------------------------------------------------------------------------- #
def tunnel(args) -> int:
    """Forward a local port to the interface on the machine, over SSH.

    Nothing travels over the open internet and no port is opened on the VM.
    The local port is asked of the operating system rather than chosen here,
    because something is usually already on the obvious ones.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        local = probe.getsockname()[1]

    argv = ["gcloud", "compute", "ssh", args.vm, "--zone", args.zone,
            "--project", args.project, "--quiet", "--",
            "-N", "-L", f"{local}:127.0.0.1:{PORT}"]
    print(f"\n  forwarding http://127.0.0.1:{local}/ here "
          f"to 127.0.0.1:{PORT} on {args.vm}")
    print(f"      $ {' '.join(argv)}")
    if not args.yes:
        print("\n  Dry run. Add --yes to open the tunnel.\n")
        return 0
    print(f"\n  Open http://127.0.0.1:{local}/ in a browser. "
          f"Ctrl-C closes the tunnel.\n")
    try:
        subprocess.run(argv)
    except KeyboardInterrupt:
        print("\n  tunnel closed\n")
    return 0


# --------------------------------------------------------------------------- #
#  status / down
# --------------------------------------------------------------------------- #
def status(args) -> int:
    plan = Plan(args.yes)
    plan.run("the machine",
             "gcloud", "compute", "instances", "describe", args.vm,
             "--zone", args.zone, "--project", args.project,
             "--format=value(name,status,machineType)", allow_fail=True)
    ssh(plan, args.project, args.vm, args.zone,
        "sudo docker ps --format '{{.Names}}  {{.Status}}'",
        "what is running on it", allow_fail=True)
    return 0


def down(args) -> int:
    """Delete the project, which is what actually stops the billing.

    Deleting a machine leaves the disk, the address and the project behind,
    and a project left attached to a billing account is how a demonstration
    becomes an invoice. So this removes the whole project - and because that
    cannot be undone, it asks for the name to be typed even with --yes.
    """
    print(f"\n{'=' * 78}\nDELETE THE PROJECT {args.project}\n{'=' * 78}\n")
    print("  This removes the machine, its disk and everything in the "
          "project.\n  It cannot be undone, and it is the only thing that "
          "stops the billing.\n")
    if not args.yes:
        print(f"      $ gcloud projects delete {args.project} --quiet\n")
        print("  Dry run. Add --yes to be asked to confirm it.\n")
        return 0
    typed = input(f"  Type the project name to confirm ({args.project}): ")
    if typed.strip() != args.project:
        print("\n  That did not match. Nothing was deleted.\n")
        return 1
    Plan(True).run("delete the project",
                   "gcloud", "projects", "delete", args.project, "--quiet")
    print("\n  Deleted. Billing for it stops.\n")
    return 0


# --------------------------------------------------------------------------- #
def main() -> int:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    parser = argparse.ArgumentParser(
        description="Put the Architect on a cloud machine. Prints by default; "
                    "--yes carries it out.")
    parser.add_argument("what", choices=("up", "tunnel", "status", "down"))
    parser.add_argument("--yes", action="store_true",
                        help="actually do it. Without this, nothing runs.")
    parser.add_argument("--project", default=f"dbtl-architect-{stamp}",
                        help="the Google Cloud project (default: a new one "
                             "named for this minute)")
    parser.add_argument("--billing", default="",
                        help="the billing account to attach, for `up`")
    parser.add_argument("--vm", default="architect-demo")
    parser.add_argument("--zone", default=ZONE)
    parser.add_argument("--machine", default=MACHINE)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--name", default="architect-demo",
                        help="names the model volume, so two deployments on "
                             "one machine can share it")
    parser.add_argument("--on", action="store_true",
                        help="the machine already exists - deploy beside what "
                             "is on it, create nothing. This is how our side "
                             "goes onto the VM sentinel-oo is already on.")
    args = parser.parse_args()

    if args.yes and shutil.which("gcloud") is None:
        print("\n  `gcloud` is not on PATH. Install the Google Cloud CLI and "
              "sign in with `gcloud auth login`.\n")
        return 2

    return {"up": up, "tunnel": tunnel, "status": status, "down": down}[
        args.what](args)


if __name__ == "__main__":
    sys.exit(main())
