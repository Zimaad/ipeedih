"""Core data model: provenance-labelled items, agents and work steps."""
from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum


class State(IntEnum):
    NORMAL = 0
    GUARDED = 1
    RESTRICTED = 2
    ISOLATED = 3


ROLE_TOOLS = {
    "research": {"web_fetch"},
    "data": {"db_agg", "db_record"},
    "analysis": {"analyze", "write_file", "write_public"},
    "comms": {"send_email"},
}
AGENTS = tuple(ROLE_TOOLS)
TOOLS = ("web_fetch", "db_agg", "db_record", "analyze", "write_file",
         "write_public", "send_email", "send_msg")
# Powers lost in RESTRICTED: database, outbound email, outside calls, publishing.
RISKY_TOOLS = {"web_fetch", "db_agg", "db_record", "write_public", "send_email"}
# Sensitivity a tool's output carries: 0 public, 1 internal aggregate, 2 personal data.
TOOL_SENS = {"db_agg": 1, "db_record": 2}
TRUSTED_DOMAINS = {"company.com", "partner.com", "client.com"}
ATTACKER_DOMAIN = "evil.io"


def domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1]


def is_untrusted_source(src: str) -> bool:
    return src.startswith("web:")


def det_rand(*key) -> float:
    """Deterministic uniform [0,1) from a key, so paired setups see the same coin flips."""
    h = hashlib.blake2b(repr(key).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2**64


@dataclass(eq=False)
class Item:
    """A unit of state: page, query result, message, memory note, file, email.

    `sources` is the taint label the defense sees. `gt_attack` and `payload` are
    ground truth used only for scoring; the defense never reads them.
    """
    id: int
    kind: str
    owner: str
    tick: int
    parents: tuple
    sources: frozenset
    sens: int
    gt_attack: bool
    payload: str | None = None
    meta: dict = field(default_factory=dict)

    @property
    def trusted(self) -> bool:
        return not any(is_untrusted_source(s) for s in self.sources)


class Store:
    """Append-only provenance DAG. Labels propagate from parents to children."""

    def __init__(self):
        self.items: dict[int, Item] = {}

    def new(self, kind, owner, tick, parents=(), *, source=None, sens=0,
            gt_attack=False, payload=None, meta=None) -> Item:
        ps = [self.items[p] for p in parents]
        sources = {source} if source else set()
        for p in ps:
            sources |= p.sources
        item = Item(len(self.items), kind, owner, tick, tuple(parents), frozenset(sources),
                    max([sens] + [p.sens for p in ps]),
                    gt_attack or any(p.gt_attack for p in ps), payload, meta or {})
        self.items[item.id] = item
        return item

    def __getitem__(self, i) -> Item:
        return self.items[i]


@dataclass
class Step:
    """One tool call an agent has been asked to perform, plus the rest of its chain."""
    agent: str
    tool: str
    args: dict
    task: int | None            # user task id; None = agent-initiated
    origin: str                 # "user" or the agent that requested this work
    malicious: bool = False     # ground truth: attacker-driven
    input_item: int | None = None
    then: tuple = ()            # remaining chain: ((agent, tool, args), ...)
    ctx: dict = field(default_factory=dict)


@dataclass
class Agent:
    name: str
    context: list = field(default_factory=list)
    memory: list = field(default_factory=list)
    inbox: deque = field(default_factory=deque)
    state: State = State.NORMAL
    clean_streak: int = 0
    last_untrusted: int = -99
    infected_by: int | None = None   # ground truth
    payload: str | None = None       # ground truth
