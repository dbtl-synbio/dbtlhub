"""The uniform agent interface.

The coordinator must not care whether an agent is an LLM, a shell script or a
person reading a plate. Every agent answers two questions: what can you do
(`capabilities`) and here is a job (`handle`).

Keeping this interface boring is the whole point - it is what lets the two teams
build different agents in parallel and still plug them together on Friday.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Task:
    """A job handed to an agent."""
    goal: str
    inputs: dict[str, Any] = field(default_factory=dict)
    contract: str | None = None          # the contract the output must satisfy
    max_repairs: int = 2                 # bounded, or two agents ping-pong for hours


@dataclass
class Result:
    """What an agent hands back."""
    status: str                          # "ok" | "escalated" | "failed"
    outputs: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    engine: str = "none"                 # which model ran, or "none"
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class Agent(ABC):
    name: str = "agent"
    phase: str | None = None
    consumes: list[str] = []
    produces: list[str] = []

    def capabilities(self) -> dict:
        return {"name": self.name, "phase": self.phase,
                "consumes": self.consumes, "produces": self.produces}

    @abstractmethod
    def handle(self, task: Task) -> Result:
        ...
