# Assignment 6 predictions

Written and committed before any run of the split. Model: `gpt-4o-mini`, held fixed.
Budget: `B = 250000` tokens per issue, so a batch run carries 1,250,000.

The reasoning is written out so that a wrong prediction is still informative about what
I believed and why.

## 1. How many times the single agent's tokens the split will spend per task

| Kind of task | Predicted multiplier, arm M over arm S |
|---|---|
| Single issue | **about 1.4x** (range 1.1 to 1.8) |
| Batch of five | **about 0.5x** (range 0.3 to 0.9), that is, the split spends *less* |

Why they point in opposite directions.

On one issue the split pays twice for the same work: two system prompts instead of one,
two tool schema lists sent on every call instead of one, and a handoff that makes the
writer re-state what the investigator already established. There is nothing for the
second context to save, because one issue never grows a context large enough to hurt.
So the split should cost somewhat more, but not several times more: the extra is two
fixed overheads, not a second search.

On a batch of five the direction reverses. Arm S triages all five issues in one window,
one after another, so by the fifth issue every model call resends the whole transcript of
the first four: the issue texts, every search result, every file it read. Prompt tokens
grow roughly with the square of the number of issues. The split gives each issue its own
investigator with an empty context, so prompt tokens grow linearly. Context isolation is
the one benefit the lecture says is most likely to hold up (slide 12), and on this task
set it should show up as fewer tokens, not more.

This is a prediction *against* the lecture's headline figure. Anthropic's roughly 15x
(slide 15) is a research workload where each worker reads material the lead never sees,
measured against a chat. Mine is a partition of work one agent was already doing, where
the second context mostly deletes duplication rather than adding reading. I expect my
numbers to look nothing like 15x, and I expect the batch number to be below 1.

## 2. Which arm passes more tasks, and by roughly how much

Six single tasks and two batch tasks, three sweeps each: 18 single runs and 6 batch runs
per arm.

| Kind | Arm S | Arm M | Prediction |
|---|---|---|---|
| Single | 10 of 18 | 11 of 18 | **about equal**, M ahead by at most 1 or 2 runs |
| Batch | 1 of 6 | 3 of 6 | **M ahead**, by roughly 2 runs |

On one issue the two arms do the same work in the same order, so they should score the
same within noise. The split's small edge, if it has one, comes from the writer being
unable to search: it cannot talk itself out of the file the investigator named. Its small
penalty, if it has one, comes from the contract: the writer sees one `evidence` string,
not the search results, so when the investigator is half right the writer cannot recover.
I expect these to roughly cancel.

On a batch I expect arm S to fail most runs and for a reason that has nothing to do with
being right about the code: a batch task passes only when all five of its issues pass, so
one dropped comment fails the run. `gpt-4o-mini` holding five triages in one context is
likely to conflate issues, post a comment against the wrong number, or run out of steps
before the fifth. Five separate contexts should drop fewer. I still expect both arms to
fail most batch runs outright, because five-for-five on a weak model is demanding.

## 3. Whether one agent given the split's spend does as well (arm S-plus)

| Kind | Prediction |
|---|---|
| Single | **Yes.** S-plus should match or beat arm M. |
| Batch | **No**, and for an uninteresting reason: its budget will be too small. |

On one issue S-plus gets about 1.4 times arm S's natural spend, which buys one full
attempt and most of a second. A plurality over two attempts is a real, if weak, use of
the extra tokens, and I expect it to land within a run or two of arm M. If it does, the
honest reading is that the split's spend and the split's design cannot be told apart on
single issues, and the design gets no credit.

On a batch the matching rule works against S-plus. If arm M really spends about half of
arm S, then S-plus is handed about half the tokens arm S needed, in one context, and gets
cut off partway through. It will score below arm S, not above it. That is not evidence
that the split's design wins; it is evidence that the budget, matched in fact, is the
thing doing the work. I expect to have to say so explicitly in Part C, because slide 18's
third question assumes the team spent more, and on batches I predict it did not.

The checker's own tolerance makes the same point: it only requires S-plus to come within
25% *under* arm M where arm M spent more than arm S. It anticipates exactly this case.

## 4. What would make me wrong

- If `gpt-4o-mini` keeps five issues straight better than I think, arm S's batch runs pass
  and the multiplier below 1 buys nothing.
- If my investigators each re-read large files, the split's batch spend could exceed arm
  S's after all, and the multiplier goes above 1 in both rows.
- If the handoff loses more than I expect, arm M loses on single issues as well, and the
  decision is one agent for both kinds of task.
