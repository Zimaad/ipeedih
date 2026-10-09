"""Scripted-agent multi-agent simulator. Every tool call and agent message passes the checkpoint."""
from __future__ import annotations

import math
from collections import defaultdict, deque

from .core import (AGENTS, ATTACKER_DOMAIN, TOOL_SENS, Agent, State, Step, Store,
                   det_rand, domain)
from .defense import Checkpoint, Setup
from .scenario import CARRY, SPREAD, SUSCEPTIBILITY, Attacker, Scenario, task_chain

BENIGN_CONTACT = "partner@partner.com"


class Sim:
    def __init__(self, sc: Scenario, setup: Setup, models=None, log_rows=False, narrate=None):
        self.sc, self.setup, self.seed = sc, setup, sc.seed
        self.t = 0
        self.store = Store()
        self.agents = {n: Agent(n) for n in AGENTS}
        self.pages = {f"site{i}.org": {"payload": None, "contact": BENIGN_CONTACT, "gt": False}
                      for i in range(10)}
        self.quarantine: set[str] = set()
        self.files: list[int] = []
        self.attacker = Attacker(sc)
        self.checkpoint = Checkpoint(setup, models)
        self.tasks: dict[int, dict] = {}
        self.rows = [] if log_rows else None
        self.narrate = narrate or (lambda *a: None)
        self._hist = defaultdict(deque)
        self._tasks_at = defaultdict(list)
        for task in sc.tasks:
            self._tasks_at[task[0]].append(task)
        # outcome tracking (ground truth)
        self.leaked = 0
        self.ever: set[str] = set()
        self.first_comp = self.contained_at = None
        self.heals: list[dict] = []
        self.legit_attempts = self.legit_blocked = 0
        self.mal_attempts = self.mal_blocked = 0

    # ---------------------------------------------------------------- main loop
    def run(self) -> dict:
        for t in range(self.sc.T):
            self.t = t
            self.attacker.on_tick(self)
            for _, tid, ttype, params in self._tasks_at[t]:
                self._start_task(tid, ttype, params)
            for name in AGENTS:
                a = self.agents[name]
                self._attacker_actions(a)
                if a.inbox:
                    self._process(a, a.inbox.popleft())
            self._check_containment()
        return self.result()

    def _start_task(self, tid, ttype, params):
        chain = task_chain(ttype, params)
        agent, tool, args = chain[0]
        self.tasks[tid] = {"t": self.t, "status": "pending", "ttype": ttype}
        self.agents[agent].inbox.append(
            Step(agent, tool, dict(args), tid, "user", then=tuple(chain[1:]), ctx={"ttype": ttype}))

    # ---------------------------------------------------------------- one step
    def _process(self, a: Agent, step: Step):
        # Detector-aware attacker (T4): piggyback on a legitimate publication, slightly widened.
        if (a.payload == "mimic" and step.tool == "db_agg" and not step.malicious
                and step.ctx.get("ttype") == "public_stats"):
            step.args = {**step.args, "n": step.args["n"] + 2}
            step.malicious = True
            step.ctx = {**step.ctx, "extra": 2}
        args = dict(step.args)
        if step.tool == "send_email" and args.get("to") == "$contact":
            args["to"] = step.ctx.get("contact", BENIGN_CONTACT)
            if domain(args["to"]) == ATTACKER_DOMAIN:
                step.malicious = True  # data-only attack (T2) redirected the recipient
        if step.tool == "web_fetch":
            args["url"] = self._choose_url(step)
            if args["url"] is None:
                self.fail(step, "no source")
                return
        parents = ([step.input_item] if step.input_item is not None else []) + list(a.memory)
        ok, reason = self.checkpoint.gate(self, a, step, step.tool, parents, args)
        if not ok:
            self.fail(step, reason)
            return
        out = self._execute(a, step, parents, args)
        self._continue(a, step, out)

    def _execute(self, a, step, parents, args):
        S, t, tool = self.store, self.t, step.tool
        if tool == "web_fetch":
            pg = self.pages[args["url"]]
            payload = pg["payload"] if pg["payload"] != "data" else None
            it = S.new("page", "world", t, (), source=f"web:{args['url']}", gt_attack=pg["gt"],
                       payload=payload, meta={"url": args["url"]})
            step.ctx = {**step.ctx, "contact": pg["contact"]}
            self.ingest(a, it)
            if not step.malicious and det_rand(self.seed, "note", a.name, t) < .3:
                a.memory.append(S.new("memory", a.name, t, [it.id]).id)
            if step.task is not None and det_rand(self.seed, "fyi", t) < .15:
                self.request(a, [("analysis", "analyze", {})], it.id, None, False)
            return it
        if tool in TOOL_SENS:
            it = S.new("query", a.name, t, parents, source="db", sens=TOOL_SENS[tool],
                       meta={"n": args["n"]})
            a.context.append(it.id)
            return it
        if tool == "analyze":
            inp = S[step.input_item] if step.input_item is not None else None
            carried = (inp.payload if inp is not None and inp.payload in SUSCEPTIBILITY
                       and det_rand(self.seed, "carry", a.name, t) < CARRY else None)
            it = S.new("report", a.name, t, parents, payload=carried)
            a.context.append(it.id)
            if det_rand(self.seed, "rnote", a.name, t) < .5:
                a.memory.append(S.new("memory", a.name, t, [it.id]).id)
            if step.task is not None and not step.malicious and det_rand(self.seed, "follow", t) < .3:
                # legitimate dynamic teamwork: analysis asks data for one more aggregate
                self.request(a, [("data", "db_agg", {"n": 1}), ("analysis", "analyze", {})],
                             None, None, False)
            return it
        if tool == "write_file":
            it = S.new("file", a.name, t, parents)
            self.files.append(it.id)
            return it
        if tool == "write_public":
            it = S.new("public", a.name, t, parents)
            if step.malicious and it.sens >= 1:
                self._leak(step.ctx.get("extra", 1), "public dashboard")
            return it
        if tool == "send_email":
            it = S.new("email", a.name, t, parents, meta={"to": args["to"]})
            if domain(args["to"]) == ATTACKER_DOMAIN:
                self._leak(step.ctx.get("units", 1), f"email to {args['to']}")
            return it
        raise ValueError(tool)

    def _continue(self, a, step, out):
        if not step.then:
            if step.task is not None and step.origin == "user":
                self._complete(step)
            return
        (nxt, tool, args), rest = step.then[0], step.then[1:]
        inp = out.id
        if nxt != a.name:
            inp = self._send(a, nxt, out.id, step)
            if inp is None:
                self.fail(step, "message blocked")
                return
        self.agents[nxt].inbox.append(
            Step(nxt, tool, dict(args), step.task, step.origin, step.malicious, inp, rest, step.ctx))

    # ---------------------------------------------------------------- messaging
    def _send(self, sender, receiver, content, step, force_payload=None):
        """Agent-to-agent message. Gated only when the setup enables message checks."""
        parents = ([content] if content is not None else []) + list(sender.memory)
        msg_step = Step(sender.name, "send_msg", {}, step.task, step.origin, step.malicious,
                        ctx=step.ctx)
        ok, _ = self.checkpoint.gate(self, sender, msg_step, "send_msg", parents, {})
        if not ok:
            return None
        payload = force_payload
        src = self.store[content] if content is not None else None
        r = det_rand(self.seed, "msgcarry", sender.name, receiver, self.t)
        if payload is None and src is not None and src.payload in SUSCEPTIBILITY and r < CARRY:
            payload = src.payload
        if payload is None and sender.payload in SUSCEPTIBILITY and r < .5:
            payload = sender.payload
        msg = self.store.new("msg", sender.name, self.t, parents, payload=payload,
                             meta={"to": receiver})
        self.ingest(self.agents[receiver], msg)
        return msg.id

    def request(self, origin, chain, content, task, malicious, ctx=None):
        """An agent asks a teammate (or itself) to run a chain of work."""
        (first, tool, args), rest = chain[0], tuple(chain[1:])
        ctx = ctx or {}
        inp = content
        if first != origin.name:
            req = Step(origin.name, "send_msg", {}, task, origin.name, malicious, ctx=ctx)
            inp = self._send(origin, first, content, req)
            if inp is None:
                return
        self.agents[first].inbox.append(
            Step(first, tool, dict(args), task, origin.name, malicious, inp, rest, ctx))

    # ---------------------------------------------------------------- the attacker
    def add_page(self, payload, contact=None):
        url = f"blog{len(self.pages)}.net"
        self.pages[url] = {"payload": payload, "contact": contact or BENIGN_CONTACT, "gt": True}
        self.narrate(self.t, "attack", f"attacker publishes {url} ({payload} payload)")

    def _choose_url(self, step):
        live = [u for u in self.pages if u not in self.quarantine]
        if not live:
            return None
        w = [3 if self.pages[u]["gt"] else 1 for u in live]
        r = det_rand(self.seed, "url", step.task, self.t) * sum(w)
        for u, wi in zip(live, w):
            r -= wi
            if r < 0:
                return u
        return live[-1]

    def ingest(self, a: Agent, item):
        a.context.append(item.id)
        if not item.trusted:
            a.last_untrusted = self.t
        p = item.payload
        # a real payload can take over an agent that only a decoy has hijacked
        open_to = a.infected_by is None or (a.payload == "decoy" and p != "decoy")
        if (p in SUSCEPTIBILITY and open_to
                and det_rand(self.seed, "infect", a.name, self.t, p) < SUSCEPTIBILITY[p]):
            a.infected_by, a.payload = item.id, p
            a.memory.append(self.store.new("memory", a.name, self.t, [item.id], payload=p).id)
            if p != "decoy":
                self.ever.add(a.name)
                if self.first_comp is None:
                    self.first_comp = self.t
                for h in self.heals:
                    if not h["reinfected"] and self.t - h["t"] <= 15:
                        h["reinfected"] = True
            self.narrate(self.t, "infect", f"{a.name} is compromised by item #{item.id} ({p})")

    def _attacker_actions(self, a: Agent):
        if a.infected_by is None or a.state == State.ISOLATED:
            return
        k, t, r = a.payload, self.t, det_rand(self.seed, "act", a.name, self.t)
        if len(a.inbox) < 4:
            if k == "loud" and r < .5:
                if a.name == "research" and det_rand(self.seed, "abuse", t) < .3:
                    a.inbox.append(Step(a.name, "db_record", {"n": 50}, None, a.name, True,
                                        ctx={"units": 50}))  # tool abuse
                else:
                    self.request(a, [("data", "db_record", {"n": 50}),
                                     ("comms", "send_email", {"to": "drop@evil.io"})],
                                 None, None, True, {"units": 50})
            elif (k == "stealth" and r < .35) or (k == "mimic" and a.name != "data" and r < .06):
                self.request(a, [("data", "db_agg", {"n": 1}), ("analysis", "write_public", {})],
                             None, None, True)
            elif k == "decoy" and r < .6:
                self.request(a, [("data", "db_agg", {"n": 3}), ("analysis", "write_file", {})],
                             None, None, True)
        if det_rand(self.seed, "spread", a.name, t) < SPREAD[k]:
            others = [n for n in AGENTS if n != a.name]
            tgt = others[int(det_rand(self.seed, "tgt", a.name, t) * len(others))]
            self._send(a, tgt, None, Step(a.name, "send_msg", {}, None, a.name, True),
                       force_payload=k)

    # ---------------------------------------------------------------- bookkeeping
    def recent(self, origin):
        h = self._hist[origin]
        while h and self.t - h[0][0] >= 10:
            h.popleft()
        return h

    def remember(self, origin, tool):
        self._hist[origin].append((self.t, tool))

    def log_action(self, step, tool, x, p, a, c, R, allowed, reason):
        if step.malicious:
            self.mal_attempts += 1
            self.mal_blocked += not allowed
        else:
            self.legit_attempts += 1
            self.legit_blocked += not allowed
        if self.rows is not None:
            self.rows.append({"x": x, "p": p, "label": int(step.malicious),
                              "attacker": self.sc.attacker, "seed": self.seed})
        if not allowed:
            who = step.origin if step.origin != "user" else "user task"
            self.narrate(self.t, "block", f"BLOCK {step.agent}.{tool} (requested by {who}): "
                                          f"{reason}  [risk={R:.2f}]")

    def set_state(self, agent, state):
        if state != agent.state:
            self.narrate(self.t, "state", f"{agent.name}: {agent.state.name} -> {state.name}")
            agent.state = state
        if state == State.NORMAL:
            for h in self.heals:
                if h["agent"] == agent.name and h["restored_at"] is None:
                    h["restored_at"] = self.t

    def record_heal(self, target, roots, n_purged, fid):
        self.heals.append({"t": self.t, "agent": target.name, "roots": sorted(roots),
                           "purged": n_purged, **fid,
                           "restored_at": self.t if target.state == State.NORMAL else None,
                           "reinfected": False})
        self.narrate(self.t, "heal", f"HEAL {target.name}: traced to {sorted(roots) or 'n/a'}, "
                                     f"purged {n_purged} items, fidelity={fid['fidelity']:.2f}")
        self.attacker.on_heal(self)

    def fail(self, step, reason):
        if step.task is not None and step.origin == "user":
            task = self.tasks.get(step.task)
            if task and task["status"] == "pending":
                task["status"] = "failed"

    def _complete(self, step):
        task = self.tasks[step.task]
        if task["status"] == "pending":
            task["status"] = "failed" if step.malicious and step.tool == "send_email" else "done"

    def _leak(self, units, where):
        self.leaked += units
        self.narrate(self.t, "leak", f"LEAK {units} unit(s) via {where}")

    def _check_containment(self):
        if self.first_comp is None or self.contained_at is not None:
            return
        live = [a for a in self.agents.values() if a.infected_by is not None and a.payload != "decoy"]
        if all(a.state >= State.RESTRICTED for a in live):
            self.contained_at = self.t

    def result(self) -> dict:
        T = self.sc.T
        tasks = list(self.tasks.values())
        after = [x for x in tasks if x["t"] >= self.sc.attack_t0]
        nan = math.nan

        def mean(v):
            return sum(v) / len(v) if v else nan

        return {
            "attack_success": int(self.leaked > 0),
            "leaked": self.leaked,
            "spread": len(self.ever) / len(AGENTS),
            "compromised": int(self.first_comp is not None),
            "ttc": (nan if self.first_comp is None else
                    (self.contained_at if self.contained_at is not None else T) - self.first_comp),
            "contained": int(self.contained_at is not None),
            "task_success": mean([x["status"] == "done" for x in tasks]),
            "availability": mean([x["status"] == "done" for x in after]),
            "fpr": self.legit_blocked / max(1, self.legit_attempts),
            "mal_block_rate": self.mal_blocked / self.mal_attempts if self.mal_attempts else nan,
            "n_heals": len(self.heals),
            "fidelity": mean([h["fidelity"] for h in self.heals]),
            "good_lost": mean([h["good_lost"] for h in self.heals]),
            "reinfection": mean([h["reinfected"] for h in self.heals]),
            "recovery": mean([(h["restored_at"] if h["restored_at"] is not None else T) - h["t"]
                              for h in self.heals]),
        }
