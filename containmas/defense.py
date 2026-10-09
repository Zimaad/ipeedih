"""The ContainMAS checkpoint: rule check -> ML detector -> risk controller -> allow/restrict/block."""
from __future__ import annotations

from dataclasses import dataclass

from . import healing, policy
from .core import RISKY_TOOLS, TOOL_SENS, TRUSTED_DOMAINS, State, domain
from .ml import featurize


@dataclass(frozen=True)
class Setup:
    name: str
    rules: bool = False
    ml: bool = False
    mode: str = "none"        # none | block | binary | graduated
    msg_checks: bool = False  # gate agent-to-agent messages too
    heal: str = "none"        # none | taint | restart
    probation: bool = True
    m: int = 4                # probation length: clean actions per de-escalation step


SETUPS = {s.name: s for s in [
    Setup("A"),
    Setup("D", rules=True, mode="block"),
    Setup("E", rules=True, ml=True, mode="block"),
    Setup("F_bin", rules=True, ml=True, mode="binary"),
    Setup("F", rules=True, ml=True, mode="graduated"),
    Setup("G_noheal", rules=True, ml=True, mode="graduated", msg_checks=True),
    Setup("G", rules=True, ml=True, mode="graduated", msg_checks=True, heal="taint"),
    Setup("G_restart", rules=True, ml=True, mode="graduated", msg_checks=True, heal="restart"),
    Setup("G_noprob", rules=True, ml=True, mode="graduated", msg_checks=True, heal="taint", probation=False),
]}


class Checkpoint:
    def __init__(self, setup: Setup, models=None):
        self.s, self.models = setup, models

    def gate(self, sim, agent, step, tool, parents, args) -> tuple[bool, str]:
        items = [sim.store[p] for p in parents]
        untrusted = any(not it.trusted for it in items)
        sens = max([it.sens for it in items] + [TOOL_SENS.get(tool, 0)])
        to = args.get("to") if tool == "send_email" else None
        external = to is not None and domain(to) not in TRUSTED_DOMAINS
        viol = policy.check(agent.name, tool, untrusted, sens, to)
        x = featurize(sim, agent, step, tool, untrusted, sens, external, args)
        origin = step.origin if step.origin in sim.agents else agent.name
        sim.remember(origin, tool)

        p = 1.0 if viol else 0.0
        a = c = 0.0
        if self.s.ml and self.models:
            a, c = self.models.detector.score(x)
            R = self.models.risk((p, a, c, sens / 2, float(untrusted)))
        else:
            R = p
        allowed, reason = self._decide(sim, agent, step, tool, viol, R, parents)
        sim.log_action(step, tool, x, p, a, c, R, allowed, reason)
        return allowed, reason

    def _decide(self, sim, agent, step, tool, viol, R, parents):
        s = self.s
        if s.mode == "none" or (tool == "send_msg" and not s.msg_checks):
            return True, ""
        th = self.models.th if self.models else None
        target = sim.agents.get(step.origin, agent)  # who is held responsible

        if s.mode == "block":
            if viol:
                return False, f"rule {viol}"
            if s.ml and R >= th.restrict:
                return False, "ml risk"
            return True, ""

        if s.mode == "binary":
            if State.ISOLATED in (agent.state, target.state):
                return False, "isolated"
            if viol or R >= th.restrict:
                sim.set_state(target, State.ISOLATED)
                return False, f"rule {viol}" if viol else "ml risk"
            return True, ""

        # graduated
        reason = ""
        if agent.state == State.ISOLATED:
            reason = "isolated"
        elif agent.state >= State.RESTRICTED and tool in RISKY_TOOLS:
            reason = "restricted"
        elif target is not agent and target.state >= State.RESTRICTED:
            reason = "requester restricted"
        elif viol:
            reason = f"rule {viol}"
        elif R >= (th.restrict if target.state == State.NORMAL else th.guard):
            reason = "ml risk"
        self._update_state(sim, target, R, parents)
        return not reason, reason

    def _update_state(self, sim, target, R, parents):
        th, s = self.models.th, self.s
        levels = {State.GUARDED: th.guard, State.RESTRICTED: th.restrict, State.ISOLATED: th.isolate}
        if target.state < State.ISOLATED and R >= levels[State(target.state + 1)]:
            sim.set_state(target, State(target.state + 1))
            target.clean_streak = 0
            if target.state >= State.RESTRICTED and s.heal != "none":
                healing.heal(sim, target, parents, s.heal, s.probation)
        elif R < th.release:
            target.clean_streak += 1
            if target.clean_streak >= s.m and State.NORMAL < target.state < State.ISOLATED:
                sim.set_state(target, State(target.state - 1))
                target.clean_streak = 0
        else:
            target.clean_streak = 0
