"""The read-only role: one issue, three reading tools, and one return.

It holds issues_read, code_search and code_read_file, and its own return tool. It has no
write, so the worst it can do is be wrong: it cannot label, comment or open a pull request,
and a call it does not hold never reaches the registry.

Its loop is Assignment 1's, unchanged (agent/loop.py), given this agent's own client and
trace, so the agent's token share bounds that agent alone.
"""

from __future__ import annotations

import json
from dataclasses import replace

from agent.loop import load_bounds, run_loop
from split.contract import RETURN_TOOL, CallFacts, return_tool
from split.roles import READ_ROLES, RoleTools, tools_for

# At most this many of the registry's calls before only the return tool is left. Arm S has
# twelve steps per issue for its reads and its three writes together; an investigator here
# gets nine for reading, and its writer gets its own steps for the writing, so neither arm
# is given more of the model's attention per issue than the other.
READS_UNTIL = 9

RECEIVED = json.dumps({"received": True,
                       "note": "The coordinator has your finding. Stop now: say nothing further and call nothing else."})


def brief(issue: int, note: str = "") -> str:
    text = (f"Investigate issue #{issue}, and only that issue. Find the one file most responsible, then call "
            f"{RETURN_TOOL} once with what you found and stop. You cannot write to the issue; another agent "
            f"does that from your report alone, so everything that matters has to be in the report.")
    return f"{text}\n\n{note.strip()}" if note.strip() else text


def investigate(ctx, agent, issue: int, *, max_tokens: int, contract_schema: dict,
                note: str = "") -> tuple[dict | None, CallFacts]:
    """Run one investigator to its end. Returns what it put in its return tool, as it sent
    it and unrepaired, with the facts of what it actually called; (None, facts) when it
    returned nothing at all."""
    facts = CallFacts()
    returned: list[dict] = []

    def receive(tool_input):
        returned.append(tool_input if isinstance(tool_input, dict) else {"not_an_object": tool_input})
        return RECEIVED

    tools = RoleTools(ctx.tools, tools_for(READ_ROLES), facts=facts, role="investigator",
                      reads_until=READS_UNTIL,
                      local={RETURN_TOOL: (return_tool(contract_schema), receive)})
    bounds = replace(load_bounds(), max_tokens=int(max_tokens))
    run_loop(agent.client, tools, ctx.prompt("investigator.md"), brief(issue, note), bounds, agent.trace)
    return (returned[-1] if returned else None), facts


__all__ = ["investigate", "brief", "RECEIVED", "READS_UNTIL"]
