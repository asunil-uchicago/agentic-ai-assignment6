# 0006 · Topology: RepoMind stays a single agent

Date: 2026-11-10
Status: accepted
Scope: the triage way RepoMind runs by default, for both kinds of task in `fixtures/tasks6`
Evidence: 72 measured runs at tag `lab-06` on `main`; the split itself at tag
`lab-06-split-final` on branch `lab-06-split`, which is not merged

## 1. The gate verdicts from Part A, and the prediction committed

Decided before any code was written, and recorded in `reports/LAB_06.md` Part A. The unit of
decomposition differs between the two columns: a batch's natural parts are its five issues,
while a single task has one issue and can only be split by role.

| Gate | One issue | A batch of five |
|---|---|---|
| 1. The parts work mostly without talking | pass | pass |
| 2. Each part's result can be checked on its own | **fail** | pass |
| 3. A team buys what one agent cannot get more cheaply | not reached | pass |
| 4. The result is worth the multiplier | not reached | pass, as judged then |

Gate 2 failed on a single issue because the investigator's half of the work cannot be
checked without the answer key: "this file is responsible" is the thing the task is asking.
The writer's half can be checked, and on a batch each issue's whole result can be checked
per issue without a key, which is why the batch column passed. Gate 4 passed on the batch
only because of the multiplier I predicted, and that prediction was wrong.

The prediction is `reports/PREDICTIONS_06.md`, commit `30ff4e1`, pushed before the first
measured run of any arm. It said: 1.4x on a single issue, 0.5x on a batch, the two arms
level on single issues, the split about two runs ahead on batches, and one agent given the
split's budget matching the split on single issues. Every one of those five was wrong, and
the two multipliers were wrong in the opposite direction from the one predicted.

## 2. The results, the five constants, the multiplier, and slide 18's three answers

The five constants, identical in all 72 runs' `run_start.constants`: model `gpt-4o-mini`;
the tool registry unchanged, `schemas_sha` `703c0002892f27ec`; budget `B = 250000` per issue,
`5B` for a batch, `--jobs 4` throughout; evaluator `checks_sha` `55abcd67e6a3b208` with
reviewer `scripted:approve-all`; task set all eight of `fixtures/tasks6`.

| Arm | Kind | Passes / runs | Issue-parts | Mean tokens | Mean wall-clock |
|---|---|---|---|---|---|
| S, one agent | single | 2 / 18 | 2 / 18 | 40,277 | 15.6 s |
| M, the split | single | **7 / 18** | 7 / 18 | 34,023 | 14.8 s |
| S-plus, one agent at the split's budget | single | 3 / 18 | 3 / 18 | 34,497 | 14.8 s |
| S, one agent | batch | 0 / 6 | **17 / 30** | 89,794 | 47.2 s |
| M, the split | batch | 0 / 6 | 11 / 30 | 209,842 | **23.1 s** |
| S-plus, one agent at the split's budget | batch | 0 / 6 | 12 / 30 | 212,194 | 82.9 s |

Multiplier, the split over one agent: **0.84x on a single issue, 2.34x on a batch**. Neither
is near slide 15's roughly 15x, and the batch figure is the reverse of the 0.5x predicted.
The reason is that one agent handed five issues does not work through them in sequence: it
asks for 2.42 tool calls per model call against the split's 0.93, finishing a batch in 11.5
model calls against the split's 61.0. The split's five empty contexts do cut prompt tokens
per call, and it still pays more, because it pays for more than five times as many calls.

Slide 18's three questions:

| Question | One issue | A batch of five |
|---|---|---|
| Did the split spend more? | no, 0.84x | yes, 2.34x |
| Does spending more raise the score? | no | no |
| Given the same budget, did one agent do as well? | no, 3 of 18 against 7 of 18 | yes, 12 issue-parts of 30 against 11 |

All three answers are no on a single issue, which is the only combination in which the
design rather than the spend is credited. On a batch they are yes, no, yes, which is the
combination in which the design earns nothing.

## 3. The decision, for each kind of task

**One issue: one agent.** The split won this comparison and the win is not large enough to
spend a second agent on. 7 of 18 against 2 of 18 is p = 0.121 by Fisher's exact test,
two-sided; against arm S-plus, the arm that actually isolates the design from the budget, it
is 7 of 18 against 3 of 18, p = 0.264; and by task, which is the independent unit, the split
leads on four of six and trails on one, a sign test at p = 0.375. The burden of proof is on
the second agent and it was not discharged. Part of the margin is also available more
cheaply: one agent hit its 12-step turn limit on 7 of 18 single runs and wrote nothing at all
on 5 of them, while the split's writer, holding its own steps and its own 30% of the budget,
wrote on all 18. A step budget reserved for the writing would recover most of that inside one
agent.

**A batch of five: one agent.** The split spends 2.34x, passes 0 of 6 exactly as one agent
does, and loses on the finer measure: 11 issue-parts of 30 against one agent's 17 at 43% of
the price. One agent handed the split's own budget scored 12 of 30. The only benefit the
split delivered is halved wall-clock, 23.1 s against 47.2 s, and nothing in this system pays
for seconds.

**No part of the work is split.** There is no named part of the work for which the data
supports a split. The strongest candidate, separating the writing so it cannot be crowded
out by reading, is a budget problem rather than a topology problem.

## 4. The condition that would reopen it, testable by someone else

All three together, each checkable by someone with this repository and no access to me:

1. **The single-issue comparison re-run at twelve sweeps per task instead of three**, holding
   the five constants above, with the split ahead of arm S-plus at p < 0.05 by a sign test
   over tasks. Arm S is not the comparison that decides this. Arm S-plus is, because it
   spends the split's tokens without the split's roles.
2. **A check on the investigator's finding that needs no answer key.** The measured ceiling
   on the split is not coordination, it is an unverifiable claim about which file is
   responsible: in 17 of 17 failed runs the investigator reported `status: found` while
   naming the wrong file, and 13 of the 17 left `could_not_determine` empty. A concrete test:
   require the `evidence` string to quote a line the trace shows was actually read, and force
   `status: candidate` in code when it does not. If that check exists and the split still
   wins, the split is buying something real.
3. **For batches, a task set in which wall-clock is scored.** Halved latency is the one thing
   the split demonstrably delivers, and it is the only thing that would make a 2.34x
   multiplier worth paying.

**Does the batch result speak to the condition in slide 49's sense, a batch of separate
issues each with its own test, run at once?** Yes, directly, and that is the clearest result
here. `batch-a` and `batch-b` are exactly that shape: five independent issues, each with its
own answer in the fixture, run concurrently, three sweeps each. It is the case where
parallelism and context isolation should both pay, where the gates said they would, and
where the prediction said the split would spend half as much. The split delivered the
parallelism (23.1 s against 47.2 s) and lost anyway, on both tokens and correctness, because
the benefit one agent gets from holding five issues in one window is not the one anybody
modelled: it batches its tool calls. So this condition has been tested on this task set and
the answer is no. Reopening it needs something the batch task does not have, namely a check
on each part that does not need the key, or a scoring function that pays for latency.

## 5. What would be lost by splitting, and what is lost by not splitting

**Lost by splitting, measured here:**

- Tokens on batch work: 2.34x, 209,842 against 89,794 per run, for a worse result.
- The reasoning behind the finding. The writer sees one `evidence` string and none of the
  search results, so when the investigator is half right the writer cannot recover. In 30 of
  30 failed issue-parts the writer wrote down faithfully what it was given, and what it was
  given was wrong.
- A whole class of failure that one agent cannot have: lost update, write skew, deadlock and
  silent divergence become possible the moment there are two writers and shared state. None
  of the four appeared in 24 runs, which is a property of a directed acyclic topology and
  five disjoint issues, not a guarantee. The guards that detect them (`split/guards.py`) are
  code that exists only because the split exists.
- The simplicity of one trace with one agent in it, and of a bounds check that binds the one
  thing doing the work.

**Lost by not splitting, measured here:**

- The single-issue result, 7 of 18 against 2 of 18 at 0.84x the tokens, with the compute
  confound ruled out by arm S-plus. This is a real effect that is being declined because it
  is unproven, not because it is absent. Declining it has a cost and this record is where
  that cost is written down.
- The guarantee that the writing happens. One agent spent all twelve steps reading on 7 of
  18 single runs and never wrote a comment on 5 of them. The split's writer wrote on all 18.
- Halved wall-clock on batch work.
- The one thing the role split gave for free: an agent that cannot write cannot write the
  wrong thing, and an agent that cannot search cannot talk itself out of the file it was
  handed.

## 6. ARCHITECTURE.md

`ARCHITECTURE.md` is unchanged by this assignment, and that is the result: RepoMind remains
one agent, the `lab-06-split` branch is tagged `lab-06-split-final` and is not merged, and
this record is the only thing the decision leaves behind.
