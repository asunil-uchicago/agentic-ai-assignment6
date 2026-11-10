"""The write-only role: one finding, three writing tools, no way to check it.

It holds issues_label, pulls_open and issues_comment, and nothing else. It cannot read the
issue or search the code, so it cannot talk itself out of the file the investigator named,
and it cannot quietly substitute another one: the comment it posts and the label it applies
come from the same finding, which is what the check of the combined result then tests.

Every comment passes ways.agent.with_disclosure before the registry, inside Disclosing, so
the disclosure line is added in code for every agent in the run and the model is never
asked to remember it.
"""

from __future__ import annotations

from dataclasses import replace

from agent.loop import load_bounds, run_loop
from split.contract import CallFacts
from split.roles import WRITE_ROLES, RoleTools, tools_for
from ways.agent import Disclosing, disclosure_line

WRITER_STEPS = 6            # the label, the pull request, the comment, and room for one refused call
WRITER_WALL_S = 120.0


def brief(issue: int, label: str, file: str, evidence: str, status: str = "found") -> str:
    """What the writer is given. The two lines are the finding, in the form the comment
    needs; `evidence` is the whole of the investigator's reasoning that survives the seam."""
    pr = (f"Open one draft pull request from repomind/issue-{issue} whose body names {file} on its first line."
          if file != "none" else "Open no pull request: this issue's file is none.")
    return (f"Issue #{issue} has been investigated. Write up this finding, exactly as it stands.\n\n"
            f"label: {label}\n"
            f"file: {file}\n\n"
            f"Why that file, from the investigator: {evidence or 'no reason was recorded.'}\n"
            f"The investigator's status for this finding: {status}.\n\n"
            f"Apply the label to issue-{issue}. {pr} Post exactly one comment on issue-{issue} last, "
            f"whose first two lines are the label line and the file line above.")


def write_up(ctx, agent, issue: int, label: str, file: str, evidence: str, *, max_tokens: int,
             status: str = "found") -> CallFacts:
    """Run one writer to its end, against a tool surface that holds only the three writes."""
    facts = CallFacts()
    tools = RoleTools(Disclosing(ctx.tools, disclosure_line()), tools_for(WRITE_ROLES),
                      facts=facts, role="writer")
    base = load_bounds()
    bounds = replace(base, max_tokens=int(max_tokens), max_steps=WRITER_STEPS, wall_clock_s=WRITER_WALL_S)
    run_loop(agent.client, tools, ctx.prompt("writer.md"),
             brief(issue, label, file, evidence, status), bounds, agent.trace)
    return facts


__all__ = ["write_up", "brief", "WRITER_STEPS", "WRITER_WALL_S"]
