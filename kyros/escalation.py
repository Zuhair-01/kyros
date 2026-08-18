"""Escalation ladder: what happens after a dispatched task fails.

Local 7-8B models fail on ambiguity, not difficulty. Re-prompting the same
model with "that was wrong, try again" regenerates the same mistake and
burns tokens. This tracks attempts per task and forces escalation after
two failures, instead of looping forever on a model that can't do the job.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Attempt:
    model: str
    passed: bool
    note: str = ""


@dataclass(frozen=True, slots=True)
class LadderState:
    task_id: str
    attempts: tuple[Attempt, ...] = ()

    @property
    def failures(self) -> int:
        return sum(1 for a in self.attempts if not a.passed)

    @property
    def exhausted(self) -> bool:
        """Two failures on one task -> stop dispatching it, retain at master tier."""
        return self.failures >= 2

    def record(self, attempt: Attempt) -> "LadderState":
        return LadderState(self.task_id, self.attempts + (attempt,))


class EscalationLadder:
    """Mutable convenience wrapper over immutable LadderState, keyed by task id."""

    def __init__(self) -> None:
        self._states: dict[str, LadderState] = {}

    def state(self, task_id: str) -> LadderState:
        return self._states.get(task_id, LadderState(task_id))

    def record(self, task_id: str, model: str, passed: bool, note: str = "") -> LadderState:
        new_state = self.state(task_id).record(Attempt(model, passed, note))
        self._states[task_id] = new_state
        return new_state

    def should_retain(self, task_id: str) -> bool:
        """True once a task has failed twice and should no longer be re-dispatched."""
        return self.state(task_id).exhausted
