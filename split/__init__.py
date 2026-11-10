"""Assignment 6's split: the coordinator's parts, on the lab-06-split branch only.

Nothing here is merged into main. RepoMind's state after Assignment 6 is a decision,
not a feature (the handout, Part D).

    split.contract   the worker's return: its schema, its validation, and the facts
                     the coordinator recomputes from the trace rather than believing
    split.guards     the three guards the checker's replays call: WaitGraph,
                     SharedState and check_combined (checks/FORMATS.md, section 14.6)
    split.roles      a role's tool surface: the registry, narrowed to the tools that
                     role may call, and refusing every other name
    split.investigator  the read-only role
    split.writer        the write-only role
"""
