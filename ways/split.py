"""Arm M: the split. A coordinator and two roles, on the lab-06-split branch only.

The decomposition is by issue first and by role second. Each of the task's issues gets its
own pipeline, an investigator followed by a writer, and the pipelines run at once: a writer
starts the moment its own investigator returns, not when all five have. A single task is
the same code with one pipeline, which is why the batch task and the single task get
different verdicts at the four gates (reports/LAB_06.md, section A).

    coordinator (parent None, no loop of its own)
      |
      +-- issue 4410 : investigator-4410  --(contract)-->  writer-4410
      +-- issue 4412 : investigator-4412  --(contract)-->  writer-4412
      +-- ...

The coordinator runs no model loop. It divides the budget, starts the workers, records
every wait, validates every return against split/contract.schema.json, carries findings on
a shared board written only by compare-and-set, and checks the combined result from the
tracker at the end. It never reads a result from a worker's prose, and it never decides
that the run succeeded: eval/check_task.py does that, from the tracker.

The five checks of slide 47 are all here or under split/:
  1. the return contract, checked on every return          split/contract.py, below
  2. deadlock detection over the waits                     split/guards.py: WaitGraph
  3. a check of the combined result from the end state     split/guards.py: check_combined
  4. compare-and-set on the shared board                   split/guards.py: SharedState
  5. one trace, every line naming its agent and parent     ctx.agent(...) everywhere here
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

from agent.loop import load_bounds
from harness.tasks import end_state
from split import contract as C
from split.guards import COORDINATOR, SharedState, WaitGraph, check_combined
from split.investigator import investigate
from split.writer import write_up

BOARD = "findings.md"          # the one shared document every pipeline appends its finding to
RESERVE = 0.08                 # of the run's budget, held back unspent so the run stays under its ceiling
INVESTIGATOR_SHARE = 0.70      # of an issue's share; the writer gets the rest
RETRY_FLOOR = 2000             # below this many tokens left, a rejected return is not asked for again
BOARD_ATTEMPTS = 12            # compare-and-set retries on the shared board, one per contending pipeline and spare
FALLBACK_LABEL = "question"    # the rule, set before the run, for an issue whose file was never established
FALLBACK_FILE = "none"


# -- the budget ------------------------------------------------------------------------------

def shares(ctx) -> tuple[int, int]:
    """One issue's token share, split investigator and writer. The coordinator spends none:
    it makes no model calls. A reserve is held back so that the last call of the last worker
    cannot push the run past the ceiling every agent shares."""
    issues = max(1, len(ctx.issues))
    total = int(ctx.budget) if ctx.budget else load_bounds().max_tokens * issues
    per_issue = int(total * (1.0 - RESERVE)) // issues
    investigator = int(per_issue * INVESTIGATOR_SHARE)
    return investigator, per_issue - investigator


# -- the shared board ------------------------------------------------------------------------

def _line(issue: int, label: str, file: str, status: str, evidence: str) -> str:
    return json.dumps({"issue": int(issue), "label": label, "file": file, "status": status,
                       "evidence": evidence}, ensure_ascii=False)


def post_finding(board: SharedState, agent: str, issue: int, label, file: str, status: str,
                 evidence: str) -> tuple[bool, int]:
    """Append one finding to the shared board by compare-and-set. Returns whether it landed
    and how many of this agent's writes were refused because another pipeline got there
    first: with every pipeline appending to one document, stale writes are ordinary here,
    and each one is a lost update that did not happen."""
    before = len(board.refused)
    written = board.update(agent, BOARD,
                           lambda text: text + _line(issue, label or C.UNKNOWN_LABEL, file, status,
                                                     evidence) + "\n",
                           attempts=BOARD_ATTEMPTS)
    return written, len(board.refused) - before


def read_finding(board: SharedState, agent: str, issue: int) -> dict | None:
    """This issue's finding, read back from the board the writer writes from. The writer's
    brief is built from this read, so the board is on the path and not beside it."""
    text, _ = board.read(agent, BOARD)
    for row in reversed([r for r in text.splitlines() if r.strip()]):
        try:
            found = json.loads(row)
        except ValueError:
            continue
        if int(found.get("issue", -1)) == int(issue):
            return found
    return None


# -- one issue's pipeline --------------------------------------------------------------------

def pipeline(ctx, lead, graph: WaitGraph, board: SharedState, schema: dict, issue: int,
             inv_tokens: int, writer_tokens: int, lock: threading.Lock) -> None:
    """Investigate one issue, then write it up. Runs in its own thread, one per issue."""
    inv_id, writer_id = f"investigator-{issue}", f"writer-{issue}"
    investigator = ctx.agent(inv_id, parent=COORDINATOR)
    writer = ctx.agent(writer_id, parent=COORDINATOR)

    # Both the coordinator and this issue's writer are blocked on this investigator, and both
    # waits are true at once. Every wait goes to the graph as it is recorded.
    if _blocked(graph, lead, lead, COORDINATOR, inv_id, "a finding", 0, lock):
        return
    if _blocked(graph, lead, writer, writer_id, inv_id, "the finding it writes from", 0, lock):
        return

    returned, facts = investigate(ctx, investigator, issue, max_tokens=inv_tokens, contract_schema=schema)
    contract = C.build(returned, facts)
    errors = C.validate(contract, schema)
    lead.trace.event("worker_return", worker=inv_id, contract=contract, valid=not errors, errors=errors)

    if errors:
        # Rejected, never repaired. Ask once more, with the errors quoted back, on an agent of
        # its own: one loop ends one agent's trace, so a second attempt is a second agent.
        left = max(0, inv_tokens - investigator.client.total_tokens)
        if left >= RETRY_FLOOR:
            again = ctx.agent(f"{inv_id}-again", parent=COORDINATOR)
            retried, facts = investigate(ctx, again, issue, max_tokens=left, contract_schema=schema,
                                         note=C.errors_for_model(errors))
            contract = C.build(retried, facts)
            errors = C.validate(contract, schema)
            lead.trace.event("worker_return", worker=f"{inv_id}-again", contract=contract,
                             valid=not errors, errors=errors)
        if errors:
            contract = C.unanswered(issue, facts, "its return did not fit the contract", errors=errors)

    graph.satisfied(COORDINATOR, inv_id)
    graph.satisfied(writer_id, inv_id)

    label, file, evidence = C.finding(contract)
    status = str(contract.get("status") or "out_of_budget")
    written, refused = post_finding(board, inv_id, issue, label, file, status, evidence)
    if refused or not written:
        lead.trace.event("shared_write", path=BOARD, writer=inv_id, refused=refused, written=written,
                         note="a stale write was refused and retried from a fresh read")

    found = read_finding(board, writer_id, issue) or {"label": label, "file": file, "evidence": evidence}
    label, file = found.get("label") or C.UNKNOWN_LABEL, found.get("file") or FALLBACK_FILE
    if label == C.UNKNOWN_LABEL:
        # The rule, set before the run: nothing established means nothing to change. It is
        # recorded as the coordinator's decision, not as something a worker found.
        lead.trace.event("fallback", issue=issue, label=FALLBACK_LABEL, file=FALLBACK_FILE,
                         reason=f"status {status}: " + "; ".join(contract.get("could_not_determine") or [])[:200])
        label, file = FALLBACK_LABEL, FALLBACK_FILE

    if _blocked(graph, lead, lead, COORDINATOR, writer_id, "the comment", 1, lock):
        return
    write_up(ctx, writer, issue, label, file, found.get("evidence") or evidence,
             max_tokens=writer_tokens, status=status)
    graph.satisfied(COORDINATOR, writer_id)


def _blocked(graph: WaitGraph, lead, by, waiter: str, on: str, what: str, turn: int,
             lock: threading.Lock) -> bool:
    """Record one wait, on the waiter's own lines, and feed it to the graph. True when the
    wait closed a cycle and a worker was stopped, so the caller goes no further."""
    with lock:
        cycle = graph.wait(waiter, on, what)
        by.trace.event("wait", waiter=waiter, on=on, what=what, turn=turn)
        if not cycle:
            return False
        victim = graph.victim(cycle)
        lead.trace.event("worker_stopped", worker=victim,
                         reason=f"a cycle of waits: {' waits on '.join([*cycle, cycle[0]])}")
        graph.satisfied(victim)
        return True


# -- the way ------------------------------------------------------------------------------------

def run(ctx) -> None:
    lead = ctx.agent(COORDINATOR)                       # parent None
    schema = C.schema(ctx.root)
    graph = WaitGraph(coordinator=COORDINATOR)
    board = SharedState({BOARD: ""})
    inv_tokens, writer_tokens = shares(ctx)
    lock = threading.Lock()
    issues = list(ctx.issues)

    with ThreadPoolExecutor(max_workers=max(1, len(issues))) as pool:
        futures = [pool.submit(pipeline, ctx, lead, graph, board, schema, issue, inv_tokens,
                               writer_tokens, lock) for issue in issues]
        raised = [f.exception() for f in futures]
    first = next((exc for exc in raised if exc is not None), None)

    # The combined result, from the tracker and from rules set before the run: the only one of
    # the five checks that catches every part passing while the whole is wrong.
    state = end_state(ctx.tracker, ctx.run_id, ctx.task)
    violations = check_combined(ctx.task, state)
    lead.trace.event("combined_check", passed=not violations, violations=violations)
    if first is not None:
        raise first
    ctx.trace.end("completed", detail=("the combined result passed its rules" if not violations
                                       else f"{len(violations)} violations of the combined result's rules"))


__all__ = ["run", "pipeline", "shares", "post_finding", "read_finding", "BOARD"]
