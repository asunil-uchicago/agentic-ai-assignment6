"""Arm S-plus: one agent, given what the split actually spent.

Slide 18's third question, and the rerun its footer asks for: given the same budget, did
one agent do as well? A shared ceiling matches the budget on paper; only this matches it
in fact. `run.py --match split` sets ctx.budget to arm M's mean spend on each task, so
this way's job is to spend about that much and answer once.

It spends the way slide 16's fair rival does: further attempts with read-only tools, each
attempt a fresh context, until it has spent about its budget, and then a choice of answer
by something it can compute without the known answers, a plurality over its own attempts.
That is a way of spending a budget, not a check. Two attempts by one model do not fail
independently (slide 41), so their agreement is weak evidence and is not treated as any
evidence at all: it only breaks ties among candidates the attempts themselves produced.

It is still one agent. Nothing runs at once and there are no roles: every attempt holds
the same read-only tools and reads the same brief, and the one chosen answer is written
once, by the harness, through the registry on this agent's own trace. A run passes only
with exactly one comment per issue, so nothing here writes twice.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from agent.loop import load_bounds, run_loop
from harness.formats import LABELS, format_triage_comment, normalize_path
from harness.roles import arg, tool_for
from split.roles import READ_ROLES, RoleTools, tools_for
from ways.agent import disclosure_line, with_disclosure

SOLO = "solo"
ANSWER_TOOL = "answer"
TARGET = 0.90          # of an issue's share: stop once about this much of the budget is spent
MIN_ATTEMPT = 6000     # tokens: below this, there is not enough left for another attempt to mean anything
MAX_ATTEMPTS = 8
FALLBACK = ("question", "none")   # the rule, set before the run, when no attempt answered at all


def answer_tool() -> dict:
    """The attempt's own tool for reporting its answer. It plays none of RepoMind's roles,
    so it is not one of the registry's calls and writes nothing anywhere."""
    return {
        "name": ANSWER_TOOL,
        "strict": True,
        "description": ("Report this attempt's answer and stop. Call it exactly once, as your last action. "
                        "It writes nothing: the harness writes the chosen answer after every attempt has run."),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["issue", "label", "file", "evidence"],
            "properties": {
                "issue": {"type": "integer", "description": "The issue, as a number."},
                "label": {"type": "string", "enum": list(LABELS),
                          "description": "The one label for this issue."},
                "file": {"type": "string",
                         "description": "The path of the file most responsible, as code_search printed it, or none."},
                "evidence": {"type": "string", "description": "In one sentence, why that file."},
            },
        },
    }


def brief(issue: int, attempt: int) -> str:
    return (f"Triage issue #{issue}. This is attempt {attempt} at this issue, made with no knowledge of any "
            f"other attempt. Read it, find the one file most responsible, and call {ANSWER_TOOL} once with "
            f"your best answer.")


def attempt(ctx, agent, issue: int, number: int, max_tokens: int) -> dict | None:
    """One attempt, in a context of its own. Returns what it answered, or None."""
    answers: list[dict] = []

    def receive(tool_input):
        if isinstance(tool_input, dict):
            answers.append(tool_input)
        return '{"received": true, "note": "Answer recorded. Stop now: say nothing further."}'

    tools = RoleTools(ctx.tools, tools_for(READ_ROLES), role=f"attempt {number}",
                      local={ANSWER_TOOL: (answer_tool(), receive)})
    bounds = replace(load_bounds(), max_tokens=int(max_tokens))
    run_loop(agent.client, tools, ctx.prompt("attempt.md"), brief(issue, number), bounds, agent.trace)
    return answers[-1] if answers else None


def choose(answers: list[dict]) -> tuple[str, str]:
    """The plurality answer over the attempts, ties broken by the earliest attempt that gave
    it. Computed from the attempts alone: nothing here can see the known answers."""
    pairs = [(str(a.get("label", "")).strip().lower(), normalize_path(str(a.get("file", "none"))) or "none")
             for a in answers if isinstance(a, dict)]
    pairs = [(label, file) for label, file in pairs if label in LABELS]
    if not pairs:
        return FALLBACK
    counts = Counter(pairs)
    best = max(counts.values())
    for pair in pairs:                       # the earliest attempt that gave a most-common answer
        if counts[pair] == best:
            return pair
    return FALLBACK


def note_for(answers: list[dict], chosen: tuple[str, str]) -> str:
    """The one or two sentences after the comment's two lines: the reason an attempt that
    gave the chosen answer recorded, so the comment says why that file."""
    for a in answers:
        if (str(a.get("label", "")).strip().lower(), normalize_path(str(a.get("file", "none"))) or "none") == chosen:
            said = str(a.get("evidence") or "").strip()
            if said:
                return said
    return "No single file could be established for this issue."


def write_once(ctx, agent, issue: int, label: str, file: str, note: str, step: int) -> None:
    """The chosen answer, written once: the label, then the draft pull request when the file
    is not none, then the comment, last. The disclosure line goes on in code, as it does for
    every agent in every arm."""
    number = f"issue-{issue}"
    agent.call_tool(step, tool_for("apply_label"),
                    {arg("apply_label", "number"): number, arg("apply_label", "label"): label})
    if file != "none":
        agent.call_tool(step, tool_for("open_pr"), {
            arg("open_pr", "number"): number,
            arg("open_pr", "branch"): f"repomind/issue-{issue}",
            arg("open_pr", "title"): f"Fix the cause of issue {issue} in {file}"[:120],
            arg("open_pr", "body"): f"File: {file}\n\n{note}"[:4000],
        })
    body = with_disclosure(format_triage_comment(label, file, note), disclosure_line())
    agent.call_tool(step, tool_for("comment"),
                    {arg("comment", "number"): number, arg("comment", "body"): body[:2000]})


def run(ctx) -> None:
    solo = ctx.agent(SOLO)                       # one agent: parent None
    issues = list(ctx.issues)
    total = int(ctx.budget) if ctx.budget else load_bounds().max_tokens * len(issues)
    share = total // max(1, len(issues))

    for step, issue in enumerate(issues, start=1):
        answers: list[dict] = []
        spent = 0
        for number in range(1, MAX_ATTEMPTS + 1):
            left = share - spent
            if number > 1 and left < MIN_ATTEMPT:
                break
            tries = ctx.agent(f"attempt-{number}-{issue}", parent=SOLO)
            said = attempt(ctx, tries, issue, number, max(MIN_ATTEMPT, left))
            spent += tries.client.total_tokens
            if said is not None:
                answers.append(said)
            if spent >= TARGET * share:
                break
        chosen = choose(answers)
        solo.trace.event("vote", issue=issue, attempts=[
            {"label": a.get("label"), "file": a.get("file")} for a in answers],
            chosen={"label": chosen[0], "file": chosen[1]}, tokens=spent, share=share)
        write_once(ctx, solo, issue, chosen[0], chosen[1], note_for(answers, chosen), step)

    ctx.trace.end("completed", detail=f"one agent, {len(issues)} issues, each answered once")


__all__ = ["run", "attempt", "choose", "write_once", "answer_tool", "SOLO", "ANSWER_TOOL"]
