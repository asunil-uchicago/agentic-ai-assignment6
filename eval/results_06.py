"""Assignment 6, Part C: one line per measured run, read from the environment.

    python eval/results_06.py                  # writes results/runs_06.jsonl and prints the summary
    python eval/results_06.py --quiet          # the file only

Every value here comes from the environment, never from an agent's words: `passed` and
`parts` from eval/check_task.py, which reads the tracker; `tokens` from the run's run_end
totals; `wall_s` from its elapsed_s. A run is counted when it is one of Assignment 6's, on
a task in fixtures/tasks6, on a real backend, and finished (it has a run_end line and
neither the daily quota nor a rate limit stopped it). Scripted runs test the code and score
nothing, so they are left out, exactly as checks/check_06.py leaves them out.

The printed summary is what reports/LAB_06.json's `arms`, `multiplier` and the results
table need, computed the same way the checker computes them, so the report recomputes
rather than being asserted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.check_task import check_task                      # noqa: E402
from harness import LAB                                      # noqa: E402
from harness.formats import ARMS, UNFINISHED                 # noqa: E402
from harness.runner import is_free, is_trace                 # noqa: E402
from harness.tasks import load_tasks                         # noqa: E402
from harness.trace import read_trace                         # noqa: E402

TASK_DIR = "fixtures/tasks6"
OUT = Path("results") / "runs_06.jsonl"
SWEEPS = 3
KINDS = ("single", "batch")


def measured_runs(root: Path = ROOT) -> list[tuple[dict, list[dict]]]:
    """Every finished Assignment 6 run on the task set, on a real backend: (run_start, records)."""
    tasks = {t.id: t for t in load_tasks(root / TASK_DIR)}
    out = []
    for path in sorted((root / "runs").glob("*.jsonl")):
        if not is_trace(path):
            continue
        try:
            records = read_trace(path)
        except (json.JSONDecodeError, OSError):
            continue
        start = records[0] if records and records[0].get("type") == "run_start" else None
        if not start or start.get("lab") != LAB or start.get("task") not in tasks:
            continue
        if is_free(start.get("backend") or "") or start.get("way") not in ARMS:
            continue
        if not records or records[-1].get("type") != "run_end":
            continue
        ends = {r.get("terminal_reason") for r in records if r.get("type") == "end"}
        if ends & set(UNFINISHED):
            continue
        out.append((start, records))
    return out


def row_for(start: dict, records: list[dict], tasks: dict) -> dict:
    """One run's line. The pass is recomputed from the tracker, never read from the trace."""
    run_id = start.get("run_id")
    checked = check_task(run_id, tasks[start["task"]])
    end = records[-1]
    return {
        "run_id": run_id,
        "arm": ARMS[start["way"]],
        "way": start["way"],
        "task": start["task"],
        "kind": start.get("kind"),
        "sweep": start.get("sweep"),
        "passed": bool(checked["passed"]),
        "parts": {str(k): bool(v) for k, v in checked["parts"].items()},
        "tokens": int((end.get("totals") or {}).get("total_tokens") or 0),
        "wall_s": round(float(end.get("elapsed_s") or 0.0), 1),
    }


def write_rows(root: Path = ROOT) -> list[dict]:
    tasks = {t.id: t for t in load_tasks(root / TASK_DIR)}
    rows = [row_for(start, records, tasks) for start, records in measured_runs(root)]
    rows.sort(key=lambda r: (r["arm"], r["task"], r["sweep"] or 0))
    path = root / OUT
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return rows


def mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def summarize(rows: list[dict]) -> dict:
    """Per arm and kind, the fields reports/LAB_06.json's `arms` names (section 14.8),
    computed as checks/check_06.py computes them."""
    out: dict = {}
    for arm in ("S", "M", "S_plus"):
        out[arm] = {}
        for kind in KINDS:
            mine = [r for r in rows if r["arm"] == arm and r["kind"] == kind]
            per_task: dict[str, int] = {}
            sweeps: dict = {}
            for r in mine:
                per_task[r["task"]] = per_task.get(r["task"], 0) + int(r["passed"])
                sweeps[r["sweep"]] = sweeps.get(r["sweep"], 0) + int(r["passed"])
            tasks = sorted({r["task"] for r in mine})
            out[arm][kind] = {
                "runs": len(mine),
                "passes": sum(int(r["passed"]) for r in mine),
                "per_task": per_task,
                "sweep_min": min(sweeps.values()) if sweeps else 0,
                "sweep_max": max(sweeps.values()) if sweeps else 0,
                "all_three": sum(1 for t in tasks if per_task.get(t, 0) >= SWEEPS),
                "mean_tokens": round(mean(r["tokens"] for r in mine)),
                "mean_wall_s": round(mean(r["wall_s"] for r in mine), 1),
            }
    return out


def multiplier(summary: dict) -> dict:
    """Arm M's mean tokens over arm S's, per kind: slide 18's first question as a number."""
    out = {}
    for kind in KINDS:
        s, m = summary["S"][kind]["mean_tokens"], summary["M"][kind]["mean_tokens"]
        out[kind] = round(m / s, 2) if s else None
    return out


def report(rows: list[dict]) -> str:
    summary, lines = summarize(rows), []
    lines.append(f"{len(rows)} finished measured runs in results/runs_06.jsonl\n")
    head = f"{'arm':<7}{'kind':<8}{'passes':>9}{'sweeps':>10}{'all 3':>7}{'mean tok':>11}{'mean s':>9}"
    lines.append(head)
    lines.append("-" * len(head))
    for arm in ("S", "M", "S_plus"):
        for kind in KINDS:
            c = summary[arm][kind]
            if not c["runs"]:
                continue
            lines.append(f"{arm:<7}{kind:<8}{str(c['passes']) + '/' + str(c['runs']):>9}"
                         f"{str(c['sweep_min']) + '-' + str(c['sweep_max']):>10}{c['all_three']:>7}"
                         f"{c['mean_tokens']:>11,}{c['mean_wall_s']:>9}")
    lines.append("")
    for kind in KINDS:
        got = multiplier(summary)[kind]
        if got is not None:
            lines.append(f"multiplier (M over S), {kind}: {got}x")
    lines.append("")
    for arm in ("S", "M", "S_plus"):
        for kind in KINDS:
            c = summary[arm][kind]
            if c["runs"]:
                lines.append(f"{arm} {kind} per task: " + ", ".join(f"{t} {n}/{SWEEPS}"
                                                                    for t, n in sorted(c["per_task"].items())))
    lines.append("\nfailed runs, for Part C task 8:")
    for r in rows:
        if not r["passed"]:
            failed = [k for k, v in r["parts"].items() if not v]
            lines.append(f"  {r['arm']:<7}{r['run_id']:<36} issues failed: {', '.join(failed) or 'none'}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    rows = write_rows()
    if "--quiet" not in argv:
        print(report(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
