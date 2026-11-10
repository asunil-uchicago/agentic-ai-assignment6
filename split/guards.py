"""Three of the five checks Lecture 6 calls cheap and usually absent (slide 47).

None of them coordinates anything. Each is here so that the code running the agents can
see or check what the agents cannot see about themselves:

    WaitGraph        who waits on whom, and the cycle a wait closes (slides 35 and 38).
                     No agent can see its own deadlock; the code running them can, if it
                     logs who waits on whom.
    SharedState      compare-and-set on a shared write (slides 34 and 37). Agents that
                     share state behave like concurrent transactions, so the remedy is
                     the one databases found decades ago: a write names the version it
                     read and is refused if the state moved since.
    check_combined   the combined result against rules set before the run, read from the
                     end state and never from what a worker reported (slides 36 and 45).
                     It is the only one of the five that catches silent divergence, where
                     every agent succeeds and the result is wrong.

checks/FORMATS.md, section 14.6, fixes the interface each replay calls; it is not mine to
change. The other two of the five checks are the return contract (split/contract.py) and
one trace for all agents (ways/split.py gives every loop its own ctx.agent).
"""

from __future__ import annotations

import threading
from pathlib import PurePosixPath

from harness.formats import parse_triage_comment

COORDINATOR = "coordinator"
ABSENT = 0          # the version of a path the shared state does not hold yet


# -- 1. Deadlock: who waits on whom (slides 35 and 38) --------------------------------------

class WaitGraph:
    """The waits-for graph of one run, and the cycle each new wait closes.

    A wait is an edge from the waiter to the agent it waits on. `wait` returns the cycle
    that wait just closed, or None. Waits accumulate until `satisfied` releases them, so a
    worker that is still blocked on two things is recorded as blocked on both.

    The lecture's case (slide 38): the patch worker waits for the test worker's failing
    case and the test worker waits for the patch. No file is locked, each is right by its
    own brief, and without this graph the run ends forty turns later on the turn limit.
    """

    def __init__(self, coordinator: str | None = COORDINATOR):
        self.coordinator = coordinator
        self._waits_on: dict[str, set[str]] = {}
        self._edges: list[tuple[str, str, str]] = []     # every wait recorded, in order
        self._lock = threading.RLock()

    # -- recording -------------------------------------------------------------------
    def wait(self, waiter: str, on: str, what: str = "") -> list[str] | None:
        """Record that `waiter` now waits on `on`. Return the cycle this wait closes, as
        the agents in it beginning with `waiter`, or None when it closes none."""
        waiter, on = str(waiter), str(on)
        with self._lock:
            if waiter == on:                      # an agent waiting on itself is a cycle of one
                self._edges.append((waiter, on, str(what)))
                self._waits_on.setdefault(waiter, set()).add(on)
                return [waiter]
            self._waits_on.setdefault(waiter, set()).add(on)
            self._edges.append((waiter, on, str(what)))
            back = self._path(on, waiter)
            return [waiter, *back] if back is not None else None

    def satisfied(self, waiter: str, on: str | None = None) -> None:
        """The wait is over: the waiter got what it waited for. With `on` None, every wait
        of that waiter is released. A real run calls this; the replays never do."""
        with self._lock:
            if on is None:
                self._waits_on.pop(str(waiter), None)
            else:
                self._waits_on.get(str(waiter), set()).discard(str(on))

    # -- reading ---------------------------------------------------------------------
    def _path(self, start: str, goal: str) -> list[str] | None:
        """The agents from `start` to `goal` along waits-for edges, inclusive, or None."""
        seen: set[str] = set()
        stack: list[tuple[str, list[str]]] = [(start, [start])]
        while stack:
            node, trail = stack.pop()
            if node == goal:
                return trail[:-1] if len(trail) > 1 else trail
            if node in seen:
                continue
            seen.add(node)
            for nxt in sorted(self._waits_on.get(node, ())):
                stack.append((nxt, [*trail, nxt]))
        return None

    def victim(self, cycle: list[str]) -> str:
        """The worker to stop to break the cycle: one of its agents, never the coordinator.

        The agent whose own wait closed the cycle, because stopping it is the smallest
        break that frees the others, and because it is the one the run can name.
        """
        members = [str(a) for a in cycle]
        if not members:
            raise ValueError("a cycle to break has at least one agent in it")
        workers = [a for a in members if a != self.coordinator] or members
        with self._lock:
            for waiter, _, _ in reversed(self._edges):
                if waiter in workers:
                    return waiter
        return workers[-1]

    @property
    def edges(self) -> list[tuple[str, str, str]]:
        with self._lock:
            return list(self._edges)


# -- 2. Lost update: compare-and-set on a shared write (slides 34 and 37) ---------------------

class SharedState:
    """State two agents share, written only by compare-and-set.

    `read` hands back the content and the version it was at; `write` names the version the
    agent read and is refused when the path has moved since. Writes to the world have
    carried harness-derived idempotency keys since Assignment 3, so a retry lands once;
    this is the other half, so that a retry does not land on top of somebody else's work.

    The lecture's case (Activity 4, Alternate A): Worker A reads exportUtils.ts at
    14:02:04, Worker B reads it at 14:02:06, A writes its timeout fix at 14:02:29, and B
    writes its lint fix at 14:02:41 from its older read, erasing A's. Here B's write is
    refused, and B must read again before it can write.
    """

    def __init__(self, initial: dict[str, str]):
        self._content: dict[str, str] = {str(k): str(v) for k, v in (initial or {}).items()}
        self._version: dict[str, int] = {k: 1 for k in self._content}
        self._reads: dict[tuple[str, str], int] = {}
        self._refused: list[dict] = []
        self._lock = threading.RLock()

    def read(self, agent: str, path: str) -> tuple[str, int]:
        """The content and its version. A path the state does not hold reads as empty at
        version 0, which a first write may then claim."""
        with self._lock:
            path = str(path)
            version = self._version.get(path, ABSENT)
            self._reads[(str(agent), path)] = version
            return self._content.get(path, ""), version

    def write(self, agent: str, path: str, content: str, version: int) -> bool:
        """Compare-and-set: write only if `path` is still at `version`, the version the
        agent read. True when written; False when refused, leaving the content as it was."""
        with self._lock:
            path = str(path)
            current = self._version.get(path, ABSENT)
            if int(version) != current:
                self._refused.append({"agent": str(agent), "path": path,
                                      "wrote_version": int(version), "current_version": current})
                return False
            self._content[path] = str(content)
            self._version[path] = current + 1
            return True

    def content(self, path: str) -> str:
        with self._lock:
            return self._content.get(str(path), "")

    def version(self, path: str) -> int:
        with self._lock:
            return self._version.get(str(path), ABSENT)

    def update(self, agent: str, path: str, change, attempts: int = 5) -> bool:
        """Read, apply `change` to the content, and write it back under the version read;
        on a refusal, read again and try once more. What a real agent does with a stale
        read, and what Worker B should have done."""
        for _ in range(max(1, attempts)):
            text, seen = self.read(agent, path)
            if self.write(agent, path, change(text), seen):
                return True
        return False

    @property
    def refused(self) -> list[dict]:
        with self._lock:
            return list(self._refused)


# -- 3. The combined result (slides 36 and 45) ------------------------------------------------

def _names(text: str, file: str) -> bool:
    """A pull request names a file when its title or body holds the path or the file's name."""
    text = (text or "").lower()
    file = (file or "").lower()
    return bool(file) and (file in text or PurePosixPath(file).name in text)


def check_combined(task, state: dict) -> list[str]:
    """The combined result's violations of the task's rules; [] when it passes.

    `state` is harness.tasks.end_state(tracker, run_id, task): what the run actually left
    on the remote, read from the tracker, never what a worker reported. The rules are set
    before the run and need no answer key, so the same check runs on a live run and on
    fixtures/planted6. For each of the task's issues:

        one comment from the run, carrying a label line and a file line;
        exactly that label still on the issue, and no other;
        one open pull request naming the comment's file when that file is not none, and
        no pull request at all when it is.

    Per-part checks do not replace this one: in fixtures/planted6/wrong.json every issue
    was triaged, every worker reported success, and one pull request names a file its own
    comment does not. That is silent divergence, and nothing else in the system reports it.
    """
    violations: list[str] = []
    for number in task.issues:
        part = _part(state, number)
        comments = list(part.get("comments") or [])
        labels = sorted({str(label).strip().lower() for label in (part.get("labels") or []) if str(label).strip()})
        prs = list(part.get("prs") or [])

        if len(comments) != 1:
            violations.append(f"issue {number}: {len(comments)} comments from this run, not one")
            said_label, said_file = None, None
        else:
            said_label, said_file = parse_triage_comment(comments[0])
            if not said_label:
                violations.append(f"issue {number}: the comment has no 'label:' line")
            if not said_file:
                violations.append(f"issue {number}: the comment has no 'file:' line")

        if said_label:
            if labels != [said_label]:
                violations.append(f"issue {number}: the labels on the issue are {labels or 'none'}, "
                                  f"and its comment says {said_label!r}")
        elif len(labels) != 1:
            violations.append(f"issue {number}: {len(labels)} labels on the issue, not one")

        if said_file is None:
            if len(prs) > 1:
                violations.append(f"issue {number}: {len(prs)} open pull requests, and no comment to judge them by")
        elif said_file == "none":
            if prs:
                violations.append(f"issue {number}: {len(prs)} open pull requests, where its comment says "
                                  f"the file is none")
        elif len(prs) != 1:
            violations.append(f"issue {number}: {len(prs)} open pull requests, not one, where its comment "
                              f"names {said_file}")
        elif not _names(f"{prs[0].get('title', '')}\n{prs[0].get('body', '')}", said_file):
            violations.append(f"issue {number}: the open pull request names neither {said_file} nor its file name, "
                              f"and its own comment says that is the responsible file")
    return violations


def _part(state: dict, number) -> dict:
    """One issue's end state, however the caller keyed it (the tracker gives integers;
    a recorded end state read from JSON gives strings)."""
    for key in (int(number), str(number)):
        if key in (state or {}):
            return state[key] or {}
    return {}


__all__ = ["WaitGraph", "SharedState", "check_combined", "COORDINATOR", "ABSENT"]
