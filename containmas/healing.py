"""Self-healing: trace the poisoned source through taint labels, purge only what it touched."""
from __future__ import annotations

from .core import State, is_untrusted_source


def live_items(sim) -> set[int]:
    live = set(sim.files)
    for a in sim.agents.values():
        live.update(a.context, a.memory)
        live.update(st.input_item for st in a.inbox if st.input_item is not None)
    return live


def _fidelity(sim, live, purged) -> dict:
    tainted = {i for i in live if sim.store[i].gt_attack}
    good = live - tainted
    total = len(live) or 1
    return {"fidelity": (len(good - purged) + len(tainted & purged)) / total,
            "good_lost": len(good & purged), "tainted_left": len(tainted - purged),
            "live": len(live)}


def heal(sim, target, parents, mode: str, probation: bool) -> None:
    live = live_items(sim)
    if mode == "restart":
        purged = set(live)
        for a in sim.agents.values():
            _drop_inbox(sim, a, lambda st: True)
            a.context.clear(); a.memory.clear()
            a.infected_by = a.payload = None
            sim.set_state(a, State.NORMAL)
        sim.files.clear()
        roots = set()
    else:
        # 1. Trace: untrusted sources in the provenance of the flagged action.
        roots = {s for p in parents for s in sim.store[p].sources if is_untrusted_source(s)}
        if not roots:  # fall back to what the agent read recently
            roots = {s for i in target.context[-8:] for s in sim.store[i].sources
                     if is_untrusted_source(s)}
        # 2. Infection set: every live item whose label includes a root.
        purged = {i for i in live if sim.store[i].sources & roots}
        # 3. Clean: purge contexts, memories, files and queued work built on it.
        for a in sim.agents.values():
            a.context = [i for i in a.context if i not in purged]
            a.memory = [i for i in a.memory if i not in purged]
            _drop_inbox(sim, a, lambda st, a=a: st.input_item in purged
                        or (st.task is None and st.origin == target.name))
            if a.infected_by is not None and sim.store[a.infected_by].sources & roots:
                a.infected_by = a.payload = None
        sim.files[:] = [f for f in sim.files if f not in purged]
        sim.quarantine |= {r[4:] for r in roots}
        # 4. Restore on probation: privileges come back in stages.
        sim.set_state(target, State.RESTRICTED if probation else State.NORMAL)
        target.clean_streak = 0
    sim.record_heal(target, roots, len(purged), _fidelity(sim, live, purged))


def _drop_inbox(sim, agent, pred) -> None:
    keep = []
    for st in agent.inbox:
        if pred(st):
            sim.fail(st, "purged")
        else:
            keep.append(st)
    agent.inbox.clear()
    agent.inbox.extend(keep)
