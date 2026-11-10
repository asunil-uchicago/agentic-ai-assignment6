"""The worker's return: designed before the roles (Lecture 6, slide 13).

The coordinator acts only on what a worker sends back, and whatever a worker leaves out
is lost for good. Prose loses what the worker did not do and code cannot check it, so a
return here is fixed fields, validated against split/contract.schema.json on every return,
and recorded in the trace as a worker_return line before the coordinator acts on it.

Two of the six fields are not the model's to report. `searched` and `calls_used` are facts
about the run, so the return tool does not even offer them: the model cannot state them,
and the coordinator fills them in from the worker's own tool calls. A model that is never
asked for a fact about itself cannot be wrong about it.

A return that breaks the schema is rejected, never repaired. Converting a string the
contract wanted as a list hides the error from the check and hands the next agent whatever
the conversion made (Python's list() of a string is a list of its characters). The
coordinator quotes the errors back and asks again; a second bad return becomes a contract
the coordinator writes itself, with status out_of_budget and the errors listed under
could_not_determine, so the writer is told plainly that nothing was established.
"""

from __future__ import annotations

import json
from pathlib import Path

from harness import ROOT
from harness.formats import CONTRACT_FIELDS, CONTRACT_STATUSES, normalize_path
from harness.roles import arg, role_of
from harness.schema import errors as schema_errors

RETURN_TOOL = "report_finding"
SCHEMA_PATH = Path("split") / "contract.schema.json"
# The fields the model is asked for. The other two are recomputed from the trace.
MODEL_FIELDS = ("result", "status", "not_searched", "could_not_determine")
FACT_FIELDS = ("searched", "calls_used")
UNKNOWN_LABEL = "unknown"


def schema(root: Path | None = None) -> dict:
    """split/contract.schema.json, the one the checker validates every return against."""
    return json.loads((Path(root or ROOT) / SCHEMA_PATH).read_text(encoding="utf-8"))


def return_tool(contract_schema: dict | None = None) -> dict:
    """The investigator's own return tool: the contract, less the two fields that are facts
    about the run. Marked strict, so a vendor with a strict mode holds the model to the
    shape instead of leaving the repair to us (Lecture 3, slide 20)."""
    full = contract_schema or schema()
    props = full.get("properties") or {}
    offered = {name: props[name] for name in MODEL_FIELDS if name in props}
    return {
        "name": RETURN_TOOL,
        "strict": True,
        "description": (
            "Send your finding back to the coordinator and stop. Call this exactly once, as your last "
            "action, whatever you found. The coordinator sees only this: it never reads your messages, "
            "so anything you leave out of these fields is lost. Say could_not_determine when you could "
            "not settle something, and set status to candidate when you are naming a file you did not "
            "read, or to out_of_budget when you stopped before you could settle the question. Do not "
            "report what you searched or how many calls you made: the coordinator takes those from your "
            "actual tool calls."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": list(offered),
            "properties": offered,
        },
    }


class CallFacts:
    """What a worker actually called, kept as the calls happen.

    Counted the way the checker counts it: every call the worker's loop asked for whose
    name plays one of RepoMind's roles, whether the role's tool surface allowed it or
    refused it, because the trace records a refused call too. The worker's own return tool
    plays no role, so it is not among them.
    """

    def __init__(self):
        self.calls = 0
        self.searched: list[str] = []

    def record(self, name: str, tool_input: dict) -> None:
        role = role_of(name)
        if role is None:
            return
        self.calls += 1
        key = arg("search", "query") if role == "search" else arg("read_file", "path") if role == "read_file" else None
        if key is None or not isinstance(tool_input, dict):
            return
        value = tool_input.get(key)
        if value is not None and str(value) not in self.searched:
            self.searched.append(str(value))


def build(returned: dict | None, facts: CallFacts) -> dict:
    """The contract as the coordinator receives it: the model's fields as they came, with
    the two facts filled in from the worker's tool calls. Nothing is coerced or defaulted:
    a field the model got wrong stays wrong, so that validation can see it."""
    contract = dict(returned) if isinstance(returned, dict) else {}
    contract["searched"] = list(facts.searched)
    contract["calls_used"] = int(facts.calls)
    return contract


def validate(contract, contract_schema: dict) -> list[str]:
    """Every way the return breaks the contract, one line each; [] when it fits.

    The schema first, then the two things the schema cannot say on its own: that all six
    of the course's fields are present, and that the status is one of slide 13's three.
    These are the checks checks/check_06.py makes of the same return, so a return this
    marks valid is one the checker also finds valid.
    """
    problems = list(schema_errors(contract, contract_schema))
    if not isinstance(contract, dict):
        return problems or [f"the return is {type(contract).__name__}, not an object"]
    for field in CONTRACT_FIELDS:
        if field not in contract:
            problems.append(f"{field}: required, and missing")
    status = contract.get("status")
    if status not in CONTRACT_STATUSES:
        problems.append(f"status: {status!r} is not one of {list(CONTRACT_STATUSES)}")
    return list(dict.fromkeys(problems))      # the same fault said once, in the order found


def unanswered(issue: int, facts: CallFacts, why: str, *, errors: list[str] | None = None) -> dict:
    """A contract the coordinator writes for a worker that sent none it could use: the
    honest return, which says that nothing was established rather than guessing."""
    return {
        "result": {"issue": int(issue), "label": UNKNOWN_LABEL, "file": "none",
                   "evidence": f"No usable return from the investigator: {why}"},
        "status": "out_of_budget",
        "searched": list(facts.searched),
        "not_searched": [],
        "calls_used": int(facts.calls),
        "could_not_determine": [f"which file is responsible for issue {issue}: {why}", *(errors or [])],
    }


def finding(contract: dict) -> tuple[str | None, str, str]:
    """The label, the file and the evidence a valid contract carries, in the form the
    writer's brief needs: the path normalised, and an unknown label as None."""
    result = contract.get("result") or {}
    label = str(result.get("label") or "").strip().lower()
    file = normalize_path(str(result.get("file") or "none")) or "none"
    return (None if label in ("", UNKNOWN_LABEL) else label), file, str(result.get("evidence") or "").strip()


def errors_for_model(problems: list[str], limit: int = 6) -> str:
    """The rejection, as the worker is told it: the fields and what was wrong, nothing else."""
    listed = "; ".join(problems[:limit])
    more = f" (and {len(problems) - limit} more)" if len(problems) > limit else ""
    return (f"Your return did not fit the contract and was rejected, so the coordinator has nothing from you "
            f"yet: {listed}{more}. Call {RETURN_TOOL} once more with the fields in the right shape.")


__all__ = ["RETURN_TOOL", "MODEL_FIELDS", "FACT_FIELDS", "UNKNOWN_LABEL", "CallFacts",
           "schema", "return_tool", "build", "validate", "unanswered", "finding", "errors_for_model"]
