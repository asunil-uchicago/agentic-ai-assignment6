# Assignment 6 · Split it, measure it, decide

Model: OpenAI `gpt-4o-mini`, the same for every run.

## Part A · The gates, before you build

**The roles you considered, and what each would need from the others mid-task.**

| Two roles | What one needs from the other while the task runs | How it would get it | What that costs |
|---|---|---|---|
| Investigator (reads the issue and the repository) and writer (labels, opens the pull request, comments) | The writer needs the label, the file and one sentence of evidence. Nothing else, and only once, at the end of the investigator's work. | One return contract, validated in code, handed over through a findings board the coordinator owns. | Two system prompts and two tool schema lists instead of one, plus a handoff in which the writer sees one `evidence` string and none of the search results. |
| Searcher (searches only) and reader (opens files only) | Each needs the other's partial results continuously: a search hit is useless until a file is read, and a file is chosen from a hit. | A shared scratchpad written and re-read on almost every turn. | Constant chatter, and no useful check on either half. Rejected at gate 1. |
| Triager (decides the label) and reviewer (a second opinion on the same issue) | Nothing mid-task, but the reviewer needs the triager's whole reasoning to add anything. | A second contract carrying the evidence. | Two agents of the same model on the same evidence agree for reasons unrelated to being right (slide 41). Rejected: agreement here is weak evidence, not a check. |

- For one issue: one handoff, at the end. The investigator finishes, the writer starts. There is nothing to exchange in between.
- For a batch of five: still one handoff per issue, and nothing at all between the five issues. Each issue is independent of the other four, in the fixtures and in the tracker.

**The sketch** (text, or an image in `reports/`):

```
coordinator  (parent None, runs no model loop of its own)
  |   budget: holds back 8%, divides the rest over the issues,
  |           splits each issue's share investigator 0.70 / writer 0.30
  |
  +-- issue 4410 --- investigator-4410 --[contract]--> findings.md --> writer-4410 --> tracker
  +-- issue 4412 --- investigator-4412 --[contract]--> findings.md --> writer-4412 --> tracker
  +-- issue 4414 --- investigator-4414 --[contract]--> findings.md --> writer-4414 --> tracker
  +-- issue 4420 --- investigator-4420 --[contract]--> findings.md --> writer-4420 --> tracker
  +-- issue 4423 --- investigator-4423 --[contract]--> findings.md --> writer-4423 --> tracker
            (one thread per issue; each writer starts when its own
             investigator returns, not when all five have)
  |
  +-- after the last write: check_combined(task, end_state) --> combined_check line

A single-issue task is this same code with one pipeline. A batch is five at once.
That is the only place parallelism can appear, and it is why the two columns below differ.
```

**The four gates** (slide 46), in order, stopping at the first no.

The unit of decomposition is not the same in the two columns. On a batch the natural parts
are the five issues. On a single task there is only one issue, so the only split available
is by role, and the gates are asked of the two roles.

| Gate | One issue | Why | A batch of five | Why |
|---|---|---|---|---|
| 1. The parts work mostly without talking | pass | One handoff, at the end of the investigator's work. No exchange mid-task. | pass | The five issues never need to talk at all, and inside each issue there is still only the one handoff. |
| 2. Each part's result can be checked on its own | **fail** | The writer's half can be checked without an answer key: did the comment carry the label and file it was given. The investigator's half cannot. "`src/export/xlsx.ts` is the responsible file" is exactly what the task is asking, so a check for it is the answer key. With one issue there is also only one part, so there is nothing for a failure to be localised to. | pass | A part here is one issue. Its result is a comment, a label and at most one pull request in the tracker, and all of that is checkable per issue with no key: exactly one comment, its `label:` and `file:` lines present, the labels on the issue equal to the comment's label, one pull request naming the comment's file when that file is not `none` and no pull request when it is. A failure localises to one issue of five. |
| 3. A team buys what one agent cannot get more cheaply | not reached | Gate 2 said no. Recorded for the comparison: there is nothing to buy. One issue never grows a context large enough to hurt, and there is nothing to run at once. | pass | Five empty contexts instead of one context holding five issue texts and every search result, plus five pipelines running at once. Neither is available to one agent in one window at any price. |
| 4. The result is worth the multiplier | not reached | Gate 2 said no. | pass, as judged here | Judged on the prediction committed before building: the split spends about 0.5x of one agent on a batch, so the multiplier is below 1 and anything the split wins is free. Part C shows this gate was decided on a false premise. |

- The benefit you are trying to buy, and the condition it needs: **context isolation**, the one of the three benefits the lecture says is most likely to hold up (slide 12). Its condition is that the context has to be the binding constraint. It buys something only where one agent's window is filling with work it no longer needs, and that is the batch, not the single issue.
- Your prediction, as committed in `reports/PREDICTIONS_06.md`, and its commit: commit `30ff4e1`, "Assignment 6 Part A: prediction, before any split run", pushed before the first measured run of any arm. It predicted 1.4x on a single issue, 0.5x on a batch, the two arms level on single issues, arm M about two runs ahead on batches, and arm S-plus matching arm M on single issues.

## Part B · The split

- The coordinator and the roles, and the tools each holds:

| Agent | Parent | Tools its loop is offered | Can it write to the world |
|---|---|---|---|
| `coordinator` | none | No model loop at all. It runs `issues_list` and the findings board itself through `agent.call_tool`, hands out budget, and runs the combined check. | the board only |
| `investigator-<n>` | `coordinator` | `issues_read`, `code_search`, `code_read_file`, and one local `report_finding` that reaches no registry | no |
| `writer-<n>` | `coordinator` | `issues_label`, `pulls_open`, `issues_comment` | yes, and nothing else |

- Why they split by tool surface: slide 11. A role defined by its prompt alone is the same
  weights with different instructions, and it can still do everything the other roles can,
  so the split buys no new guarantee. A role defined by what it is allowed to call changes
  what it can do wrong. `split/roles.py: RoleTools` offers `run_loop` only the names that
  role holds and refuses every other name without touching the registry, naming the tools
  the role does hold. The investigator cannot label, comment or open a pull request even if
  it decides to, and the writer cannot search, so it cannot talk itself out of the file it
  was handed. Every call that is allowed still goes through the run's registry, so the
  boundary, the idempotency keys and `policy/hook.py` hold for every agent in every arm.

- The return contract, field by field, and which fields come from the worker's tool calls
  (`split/contract.schema.json`, `split/contract.py`):

| Field | Type | Source |
|---|---|---|
| `result.issue` | integer | the model |
| `result.label` | `bug` \| `feature` \| `question` \| `docs` \| `unknown` | the model |
| `result.file` | string: a repository path, or `none` | the model |
| `result.evidence` | string | the model. This is the only thing the writer sees of the investigator's work. |
| `status` | `found` \| `candidate` \| `out_of_budget` | the model |
| `searched` | array of strings | **code**, from the worker's own `tool_call` lines: each search query and each read path, once each |
| `not_searched` | array of strings | the model. The one field in the contract that nothing can check. |
| `calls_used` | integer | **code**, the count of the worker's registry calls before the return |
| `could_not_determine` | array of strings | the model |

  `MODEL_FIELDS` in `split/contract.py` deliberately excludes `searched` and `calls_used`,
  so the return tool does not offer them to the model at all. The coordinator injects both
  from the trace before validating. The return tool carries `"strict": true`, which
  `harness/backends.py` passes through as `function.strict`, so the API holds the model to
  the shape in the first place.

  Rejection, never repair: `validate(contract, schema)` returns the schema errors, the
  coordinator writes a `worker_return` line for every return whether valid or not, and an
  invalid return is asked once more with its errors quoted back. A second invalid return
  becomes a contract of the coordinator's own making with `status: out_of_budget` and the
  errors listed in `could_not_determine`. Nothing anywhere turns a string into a list.

  What the contract cannot say, which turned out to be the finding of the whole assignment:
  `status` is the only way it can tell "nothing is responsible" from "I did not get far
  enough to find out", and `status` is the model's own word. In all 17 failed arm M runs the
  investigator reported `status: found` while naming the wrong file, and 13 of the 17 left
  `could_not_determine` empty. The two fields recomputed in code were right every time, by
  construction. The fields that could have carried a warning carried none.

- Each worker's share of the budget, and what is held back: `ways/split.py: shares(ctx)`.
  The coordinator holds back `RESERVE = 8%` of `ctx.budget` unspent, so a loop that
  overshoots its last call cannot push the run past `ctx.ceiling`. It divides the rest
  evenly over the task's issues, then divides each issue's share `INVESTIGATOR_SHARE = 0.70`
  to the investigator and the remaining `0.30` to its writer. Each share is handed to
  `run_loop` as that agent's `Bounds.max_tokens`, and `AgentClient` totals are per agent, so
  the bound binds that agent alone while every call still counts against the one run
  ceiling. Steps come from `agent/bounds.yaml`: the investigator gets the full `max_steps`
  of 12 and the writer `max(4, 12 // 2)`. The investigator also gets a reading deadline of
  `READS_UNTIL = 9` registry calls, enforced in `RoleTools.call` before the call is made and
  never asked of the model, because a worker that reads until its turn limit returns
  nothing, and nothing is the one answer the coordinator cannot use.

- The five checks, where each is in your code:

| Check | Where | When it runs |
|---|---|---|
| 1. A return contract the code checks | `split/contract.schema.json` and `split/contract.py: validate` | every return in every arm M run |
| 2. A waits-for graph with cycle detection | `split/guards.py: WaitGraph` | the coordinator feeds it every wait before it blocks. My topology is a directed acyclic graph, so across 24 measured arm M runs it recorded 15 waits per batch run and 3 per single run and never found a cycle. It fires only on the course's replay, where it scored 8 of 8. Stated plainly rather than claimed as a live defence. |
| 3. A combined check on the end state | `split/guards.py: check_combined`, called from `ways/split.py: run` | once, after the last write, writing a `combined_check` line. It reads `harness.tasks.end_state`, that is the tracker, never a worker's report. |
| 4. Compare-and-set on shared state | `split/guards.py: SharedState`, used for the per-run `findings.md` board | every board write. `write(agent, path, content, version)` refuses a stale version and `update` re-reads and retries up to five times. |
| 5. One trace | `ways/split.py`, `split/investigator.py`, `split/writer.py` | every loop gets its own `ctx.agent(id, parent=...)`. `ctx.trace` and `ctx.call_tool` are never used, so no model or tool line is written without an agent and a parent. |

  Check 3 deserves one more line, because the measurement turned it into a result.
  `combined_check` passed on all 30 failed issue-parts of arm M. That is not a bug in the
  check. It catches divergence between what the agents wrote, and here the agents never
  diverged: the writer wrote faithfully what the investigator found, and what the
  investigator found was wrong. A check with no answer key can catch two agents disagreeing.
  It cannot catch two agents agreeing on the same wrong thing.

## Part C · Measured

**The five constants** (slide 59): model, tools, budget, evaluator, task set.

Recorded in every run's `run_start.constants`, identical across all 72 measured runs, and
compared against `reports/LAB_06.json` by the checker.

| Constant | Value |
|---|---|
| model | `gpt-4o-mini`, provider `openai-compatible`, the same for every run |
| tools | the registry unchanged, `schemas_sha` `703c0002892f27ec` |
| budget | `B = 250000` tokens from `agent/bounds.yaml`; a batch of five carries `5B = 1250000`. `--jobs 4` for every arm. |
| evaluator | `checks_sha` `55abcd67e6a3b208`, reviewer `scripted:approve-all` |
| task set | all eight of `fixtures/tasks6`: `batch-a`, `batch-b`, `one-4402`, `one-4403`, `one-4405`, `one-4406`, `one-4409`, `one-4413` |

**The results.**

72 finished runs: three arms by eight tasks by three sweeps, with no errored or
quota-stopped run. Every pass below is recomputed from the tracker by `eval/check_task.py`,
never read from a trace.

| Arm | Kind | Passes / runs | Lowest and highest sweep | Tasks all three passed | Mean tokens | Mean wall-clock (s) |
|---|---|---|---|---|---|---|
| S | single | 2 / 18 | 0 and 1 | 0 | 40,277 | 15.6 |
| S | batch | 0 / 6 | 0 and 0 | 0 | 89,794 | 47.2 |
| M | single | 7 / 18 | 2 and 3 | 1 | 34,023 | 14.8 |
| M | batch | 0 / 6 | 0 and 0 | 0 | 209,842 | 23.1 |
| S-plus | single | 3 / 18 | 1 and 1 | 1 | 34,497 | 14.8 |
| S-plus | batch | 0 / 6 | 0 and 0 | 0 | 212,194 | 82.9 |

Per task, passes out of three sweeps:

| Task | S | M | S-plus |
|---|---|---|---|
| one-4402 | 0 | 1 | 0 |
| one-4403 | 0 | 2 | 3 |
| one-4405 | 0 | 0 | 0 |
| one-4406 | 0 | 1 | 0 |
| one-4409 | 2 | 0 | 0 |
| one-4413 | 0 | 3 | 0 |
| batch-a | 0 | 0 | 0 |
| batch-b | 0 | 0 | 0 |

A batch run passes only when all five of its issues pass, and no arm managed that once. The
per-issue parts underneath the batch rows are worth stating, because they move the other way
from the single-issue rows: of 30 batch issue-parts, arm S passed 17, arm S-plus 12 and arm
M 11.

- Your multiplier (M over S), single and batch, beside the lecture's 15x:

| Kind | Predicted | Measured |
|---|---|---|
| Single issue | about 1.4x | **0.84x** |
| Batch of five | about 0.5x | **2.34x** |

  Both predictions were wrong, and each was wrong in the direction opposite to the one
  predicted. Neither resembles slide 15's roughly 15x, which is the one thing the prediction
  got right, though not for the reason it gave: that figure is a research workload where
  each worker reads material the lead never sees, measured against a chat, and this is a
  partition of work one agent was already doing.

  The mechanism behind 2.34x is not the one the prediction reasoned about, and it is not
  context growth either. Handed five issues in one window, arm S does not work through them
  in sequence. It asks for **2.42 tool calls per model call** on a batch, against arm M's
  0.93, with single responses requesting five or eight calls at once. That lets it finish a
  batch in **11.5 model calls** against arm M's **61.0**, and it is the resending of the
  growing transcript on each call that costs tokens, not the transcript itself. The split
  cannot batch calls that way: each investigator holds one issue and has nothing to batch.
  Its five empty contexts do save prompt tokens per call, and it still loses, because it
  pays for more than five times as many calls. Context isolation was bought as designed, and
  the thing it was supposed to save was never the binding cost.

  Arm M does halve the wall-clock on batches, 23.1 s against 47.2 s, which is parallelism
  appearing exactly where gate 3 said it would. The benefit is real and it is in the wrong
  currency: nothing in the task set pays for seconds.

- Whether S-plus's spend matched M's in fact, task by task:

| Task | Arm S mean | Arm M mean | Arm S-plus mean | S-plus as a share of M |
|---|---|---|---|---|
| batch-a | 127,739 | 208,901 | 212,605 | 101.8% |
| batch-b | 51,849 | 210,783 | 211,784 | 100.5% |
| one-4402 | 28,431 | 41,857 | 43,564 | 104.1% |
| one-4403 | 38,312 | 21,601 | 22,220 | 102.9% |
| one-4405 | 55,805 | 37,779 | 39,335 | 104.1% |
| one-4406 | 58,667 | 42,836 | 42,609 | 99.5% |
| one-4409 | 30,133 | 24,752 | 25,532 | 103.2% |
| one-4413 | 30,311 | 35,313 | 33,720 | 95.5% |

  Yes, in fact and not only on paper. Every S-plus run carried `matched_to: split` and a
  `budget` equal to arm M's mean spend on that same task over the runs that finished before
  it, and the spend it actually reached is within 4.5% of arm M's on every one of the eight
  tasks, and within 1.4% overall. The match is not an artefact of a shared ceiling: on five
  of the eight tasks arm M spent *less* than arm S, so S-plus was handed less than arm S's
  natural spend and still had to be held to it.

  The prediction said the batch match would starve S-plus, handing it about half of arm S's
  tokens. The opposite happened. Arm M spent 2.34x of arm S on batches, so S-plus was handed
  more than four times arm S's natural batch spend, spent it on 12.5 reads per issue against
  arm S's 2.8, and passed nothing.

**Slide 18's three questions**, for each kind of task.

| Question | One issue | A batch of five |
|---|---|---|
| Did the split spend more? | **No.** 34,023 against 40,277, a multiplier of 0.84. | **Yes.** 209,842 against 89,794, a multiplier of 2.34. |
| Does spending more raise the score? | **No.** One agent given arm M's budget spent 34,497 and scored 3 of 18, against arm S's 40,277 for 2 of 18 and arm M's 34,023 for 7 of 18. Score does not track spend in either direction. | **No.** 89,794, 209,842 and 212,194 tokens all bought 0 of 6. Per issue-part the arm that spent least scored highest: arm S 17 of 30 at 89,794, arm S-plus 12 of 30 at 212,194, arm M 11 of 30 at 209,842. |
| Given the same budget, did one agent do as well? | **No.** 3 of 18 against arm M's 7 of 18, on a spend 1.4% higher. | **Yes.** 0 of 6 against 0 of 6, and 12 issue-parts of 30 against arm M's 11, on a spend within 1.1%. |

  On single issues all three answers are no, which is the only combination in which the
  design, and not the spend, is credited: the split was cheaper, extra spend did not help
  any arm, and one agent handed the split's budget could not match it. On batches the answers
  are yes, no, yes, which is the combination in which the design earns nothing at all.

- What you would have claimed from arms S and M alone, and what you claim now:

  From arms S and M alone the claim would have been that splitting the work wins on single
  issues and is close to free: 7 of 18 against 2 of 18, three and a half times the passes at
  0.84 of the tokens. That is a reasonable reading of two arms and it is not a safe one,
  because it rests on no evidence at all about what one agent would do with 34,023 tokens
  instead of its own 40,277. Arm S-plus is what rules that out, and it is the reason the
  answer survives at all: one agent handed exactly arm M's budget, spending it on more
  reading in fresh contexts, reached 3 of 18.

  What is claimed now is narrower in two ways. First, the batch half of the earlier claim is
  gone. Arm M spends 2.34x there for 11 issue-parts of 30 against arm S's 17 at less than
  half the price, so on batches the split is both worse and more expensive, and the one
  benefit it delivers is wall-clock, which nothing is paying for. Second, the single-issue
  win is a point estimate that does not clear any reasonable bar. 7 of 18 against 2 of 18 is
  p = 0.121 by Fisher's exact test, two-sided (p = 0.061 one-sided), and the independent unit
  is the task, not the run: by task arm M is ahead on four of six and behind on one, a sign
  test at p = 0.375. Against arm S-plus, the comparison that actually isolates the design, it
  is 7 of 18 against 3 of 18, p = 0.264.

  There is also a mechanism underneath the single-issue result that the pass counts hide and
  that weakens the architectural reading. Arm S hit its 12-step turn limit on 7 of its 18
  single runs, and on 5 of those it never applied a label or wrote a comment at all: it spent
  all twelve steps reading. Arm M never did, because its writer holds its own steps and its
  own 30% of the budget, and arm M applied a label and wrote exactly one comment on every one
  of its 18 single issues. Part of the win is therefore not better triage. It is that
  reserving steps for the writing guarantees the writing happens. That is a genuine benefit
  of separating the roles, and it is also the kind of benefit one agent could have had from a
  step budget rather than from a second agent.

**Every arm M run that failed.**

17 of 24 arm M runs failed, covering 30 failed issue-parts. All 30 have the same shape: the
investigator named the wrong file, and the writer faithfully wrote down what it was given.
In 30 of 30 the comment carried exactly the label and file in the contract, in 30 of 30
`combined_check` passed, and in 0 of 30 did two agents disagree about anything. The anomaly
column is therefore `none` throughout, in its documented sense of one agent getting its own
part wrong. The first failing issue of each run is the one described. Where a run failed more
than one issue, the others are named.

| Run | What each agent read, wrote and waited on | The first thing that went wrong | Anomaly | MAST category |
|---|---|---|---|---|
| `split-batch-a-s01-fef7a5` | 10 agents, 15 waits. `investigator-4412` made 5 reads and returned `bug` / `src/api/health.ts`, `status: found`, `could_not_determine` empty. `writer-4412` waited on that finding alone, then wrote the label, a pull request and one comment. Investigators 4410, 4414 and 4420 used all nine reads. Also failed: 4414, 4420, 4423. | Issue 4412 is a `question` whose answer is `none`. The investigator read five times, found a plausible health endpoint and reported it as found. Nothing downstream could see that the issue asked for no change. | none | task_verification |
| `split-batch-a-s02-2c5ef7` | `investigator-4410` spent all 9 reads, was refused a tenth by the deadline in `RoleTools`, and returned `bug` / `src/api/auth.ts` with one entry in `could_not_determine`. `writer-4410` wrote all three calls from it. Investigators 4420 and 4423 were also capped. All five issues failed. | The reading deadline ended the search before `src/config.ts` was reached, and the investigator reported its best unverified candidate as `found` rather than as a candidate. | none | system_design |
| `split-batch-a-s03-94fd62` | `investigator-4412` made 6 reads and returned `bug` / `src/api/health.ts` as found. Its writer wrote label, pull request and comment. `investigator-4420` was capped at 9. Also failed: 4420, 4423. | The same wrong reading of issue 4412 as sweep 1, reached from a different number of reads. | none | task_verification |
| `split-batch-b-s01-aff21d` | `investigator-4431` made 8 reads and returned `feature` / `src/export/scheduler.ts` as found, nothing under `could_not_determine`. Its writer wrote all three. Investigators 4424, 4429 and 4434 used all nine reads. Also failed: 4434. | The answer is `src/util/strings.ts`. The investigator stopped at the export scheduler, which mentions the feature but does not contain it. | none | task_verification |
| `split-batch-b-s02-83d889` | No investigator was capped. `investigator-4424` made 6 reads and returned `bug` / `src/export/scheduler.ts` as found. Its writer wrote all three. Also failed: 4431. | The answer is `src/exportUtils.ts`. The investigator had three reads left, stopped anyway, and reported found. | none | task_verification |
| `split-batch-b-s03-7a8635` | `investigator-4424` used all 9 reads, was refused a tenth, and returned `bug` / `src/export/scheduler.ts` with one entry in `could_not_determine`. `investigator-4434` was also capped. Also failed: 4431, 4434. | The reading deadline ended the search with `src/exportUtils.ts` still unread. | none | system_design |
| `split-one-4402-s01-621b77` | 2 agents, 3 waits. `investigator-4402` made 8 reads and returned `bug` / `src/ingest/schema.ts` as found. `writer-4402` waited on the finding, then wrote the label, a pull request naming that file and one comment. | The answer is `src/util/money.ts`. The investigator traced the symptom to the ingest schema and never reached the rounding helper. | none | task_verification |
| `split-one-4402-s03-a4476f` | `investigator-4402` made 6 reads, returned the same finding. Its writer wrote all three faithfully. | The same wrong file as sweep 1, from two fewer reads. | none | task_verification |
| `split-one-4403-s02-64fb62` | `investigator-4403` made 5 reads and returned `feature` / `src/export/csv.ts` as found. Its writer wrote all three, including a pull request. | Issue 4403 is a `question` whose answer is `none`, so the label, the file and the pull request are all wrong. The contract has a way to say "nothing needs to change" and the model declined to use it. | none | task_verification |
| `split-one-4405-s01-a52b28` | `investigator-4405` used all 9 reads, was refused a tenth, and returned `feature` / `src/export/xlsx.ts` with one entry in `could_not_determine`. Its writer wrote all three. | The reading deadline ended the search while the answer, `src/components/ExportButton.tsx`, was still unread, and the investigator reported `found`. | none | system_design |
| `split-one-4405-s02-ee4a7d` | `investigator-4405` made 7 reads and returned `feature` / `src/export/scheduler.ts` as found. Its writer wrote all three. | A third wrong file for the same issue, with two reads still unspent. | none | task_verification |
| `split-one-4405-s03-29ce6d` | `investigator-4405` made 5 reads and returned `feature` / `src/export/xlsx.ts` as found. Its writer wrote all three. | Sweep 1's wrong answer, reached in four fewer reads and without the deadline firing, which shows the deadline was not the cause of that answer. | none | task_verification |
| `split-one-4406-s01-a260a8` | `investigator-4406` made 6 reads and returned `bug` / `src/export/csv.ts` as found. Its writer wrote all three. | The answer is `src/ingest/parser.ts`. The investigator worked from where the bad value was displayed rather than from where it was produced. | none | task_verification |
| `split-one-4406-s03-d76e08` | `investigator-4406` used all 9 reads, was refused a tenth, and returned `bug` / `src/db/repos/transactionRepo.ts` with one entry in `could_not_determine`. Its writer wrote all three. | The reading deadline ended the search in the repository layer, two hops from `src/ingest/parser.ts`. | none | system_design |
| `split-one-4409-s01-544878` | `investigator-4409` made 4 reads and returned `docs` / `docs/CONFIG.md` as found. Its writer wrote all three. | The label is right and the file is not: the answer is `README.md`. Four reads, five left unspent, and still reported as found. | none | task_verification |
| `split-one-4409-s02-d6b0d6` | `investigator-4409` made 5 reads and returned `docs` / `none` as found. Its writer wrote the label and a comment, and correctly opened no pull request. | `docs` with file `none` is internally contradictory and the contract permits it: the label says a document is wrong and the file says no document needs changing. The writer behaved correctly on a finding that could not be correct. | none | task_verification |
| `split-one-4409-s03-c70aed` | `investigator-4409` made 4 reads and returned `docs` / `docs/CONFIG.md` as found. Its writer wrote all three. | The same wrong document as sweep 1. | none | task_verification |

Reading the column totals: 13 of the 17 are `task_verification`, because nothing in the
system verified the investigator's claim about the file, and the one check that could have
objected, `check_combined`, is not allowed an answer key. The other 4 are `system_design`,
and they are mine. The nine-read deadline is a design decision I made to stop investigators
burning their whole budget without returning, and in those four runs it ended the search
before the answer was reached. The deadline was still worth keeping: without it, development
runs spent twice the tokens and returned nothing at all, and nothing is the one answer the
coordinator cannot use. What the four runs show is that the deadline only works if
`status: candidate` means something, and `status` is the model's word, and the model said
`found` in all 17.

None of the four concurrency anomalies appeared anywhere in 24 arm M runs. No lost update:
`SharedState` refused no board write in any measured run. No write skew: the per-issue
pipelines touch disjoint issues, and the combined check found no divergence in 30 of 30. No
deadlock: `WaitGraph` saw 15 waits per batch run and 3 per single run and found no cycle,
which is what a directed acyclic topology should produce. No misalignment: the writer agreed
with its investigator in 30 of 30. The failures here were not coordination failures. They
were one agent being wrong about its own part, which is the dominant individual failure mode
in the MAST taxonomy (slide 31) and the one a second agent does nothing about.

## Part D · The decision

- One issue: **single**. The split is ahead on the measurement that matters, 7 of 18 against
  arm S's 2 and arm S-plus's 3, and the compute confound is ruled out rather than argued
  away: it spends 0.84x, no arm's score tracks its spend, and one agent handed exactly its
  budget reached 3 of 18. If any result in this assignment justified a second agent, this is
  the one. It is still not enough. The second agent has to make the case, and 7 against 2 at
  p = 0.121 two-sided, or four tasks to one at p = 0.375 by sign test, does not make it. Part
  of the margin is also attributable to something cheaper than a second agent: arm S hit its
  turn limit on 7 of 18 single runs and wrote nothing at all on 5 of them, while arm M's
  writer, holding its own steps, wrote on all 18. A step budget reserved for the writing
  would buy most of that inside one agent. The topology stays single, and the honest
  statement is that the split showed a real but unproven advantage, not that it showed
  nothing.
- A batch of five: **single**, and this one is not close. The split spends 2.34x, passes 0 of
  6 exactly as the single agent does, and loses on the finer measure, 11 issue-parts of 30
  against arm S's 17 at 43% of the price. One agent handed the split's budget did as well or
  slightly better, 12 parts of 30. The one benefit delivered is halved wall-clock, 23.1 s
  against 47.2 s, and nothing in this system pays for seconds. Gate 4 passed in Part A on a
  predicted multiplier of 0.5x; the measured 2.34x fails it outright.
- The condition that would reopen it: three things together, not any one of them alone.
  First, the single-issue comparison re-run at twelve sweeps per task instead of three,
  holding all five constants, with arm M ahead of **arm S-plus** at p < 0.05 by a sign test
  over tasks. Arm S is not the comparison that decides this; arm S-plus is. Second, a check
  on the investigator's finding that needs no answer key, since the measured ceiling on the
  split is not coordination but an unverifiable claim about which file is responsible:
  something like requiring the evidence string to quote a line the trace shows was actually
  read, and forcing `status: candidate` in code when it does not. Third, for batches, a task
  set in which wall-clock is scored, because halved latency is the one thing the split
  demonstrably delivers and the only thing that would make its multiplier worth paying.
- The record: `decisions/0006-topology.md`

## AI assistance

I used Gemini Web App and Claude Code to better understand the repository, I also used Claude Code to help draft the prompts and report. I used GitHub Copilot autocompletion while coding and Claude to debug any errors I had. I also made sure to manually verify any work done by AI.