"""A role's tool surface: the registry, narrowed to the tools that role may call.

Lecture 6, slide 11: split by tool surface, not by persona. A role defined by its prompt
alone is the same weights with different instructions, and it can still do everything the
others can; a role defined by what it is allowed to call changes what it can do wrong. The
investigator here cannot write to the world at all, and the writer cannot read the
repository, so each can only be wrong in its own way.

`run_loop` accepts anything with `.schemas` and `.call(name, input)`, so a tool surface is
just an object: the tools the role holds, plus any local tool of its own (the
investigator's return), refusing every other name without touching the registry. Every
call it does forward goes through the run's registry, so the boundary, the idempotency
keys and policy/hook.py hold for every agent.
"""

from __future__ import annotations

import time

from harness.roles import role_of
from split.contract import CallFacts
from tools import ToolResult

# The two surfaces, by role (tools/roles.yaml names which tool plays each role).
READ_ROLES = ("read_issue", "search", "read_file")
WRITE_ROLES = ("apply_label", "open_pr", "comment")


def tools_for(roles) -> tuple[str, ...]:
    """The tool names that play these roles, whatever they have been renamed to."""
    from harness.roles import tool_for
    return tuple(tool_for(role) for role in roles)


class RoleTools:
    """One role's tools. `.schemas` offers only them; `.call` refuses every other name.

    `local` maps a name to (definition, handler): a tool this role answers itself, such as
    the investigator's return, which never reaches the registry and plays none of
    RepoMind's roles.
    """

    def __init__(self, tools, allowed, *, local: dict | None = None, facts: CallFacts | None = None,
                 role: str = "worker", reads_until: int | None = None):
        self.tools = tools
        self.allowed = tuple(allowed)
        self.local = dict(local or {})
        self.facts = facts or CallFacts()
        self.role = role
        self.reads_until = reads_until      # at most this many of the registry's calls, then only the local tools
        self.refused: list[str] = []

    @property
    def schemas(self) -> list[dict]:
        want = set(self.allowed)
        offered = [s for s in self.tools.schemas if s.get("name") in want]
        return offered + [definition for definition, _ in self.local.values()]

    def names(self) -> list[str]:
        return [*self.allowed, *self.local]

    def call(self, name: str, tool_input: dict, **kwargs) -> ToolResult:
        started = time.monotonic()
        if name in self.local:
            _, handler = self.local[name]
            return ToolResult(handler(tool_input), False, time.monotonic() - started)
        if name not in self.allowed:
            self.refused.append(name)
            result = ToolResult(self._refusal(name), True, time.monotonic() - started)
        elif self.reads_until is not None and self.facts.calls >= self.reads_until:
            # The deadline, checked here in code before the call, never asked of the model: a
            # worker that reads until its turn limit returns nothing, and nothing is the one
            # answer the coordinator cannot use.
            self.refused.append(name)
            result = ToolResult(self._spent(), True, time.monotonic() - started)
        else:
            result = self.tools.call(name, tool_input, **kwargs)
        # Counted the way the checker counts it: a call the loop made and the trace records,
        # whether this surface allowed it or refused it. A name that plays no role is not one.
        self.facts.record(name, tool_input)
        return result

    def _spent(self) -> str:
        local = ", ".join(self.local) or "nothing"
        return (f"This call was not made: you have used your {self.reads_until} reading calls for this issue, "
                f"and reading is now closed. Call {local} with the best answer you have from what you have "
                f"already read, and say what you could not settle. Nothing else will run.")

    def _refusal(self, name: str) -> str:
        played = role_of(name)
        held = ", ".join(self.names())
        mine = (f" {name} belongs to another agent in this run, not to you."
                if played else f" There is no tool called {name}.")
        return (f"This call was not made: as the {self.role} you hold only {held}.{mine} "
                f"Use one of your own tools, or finish.")

    def __getattr__(self, attr):          # everything else is the registry's
        return getattr(self.tools, attr)


__all__ = ["RoleTools", "READ_ROLES", "WRITE_ROLES", "tools_for"]
