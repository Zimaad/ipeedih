"""Turn an event list into per-step UI frames (agent states + counters + log), for the dashboard."""
from __future__ import annotations

AGENTS = ["research", "data", "analysis", "comms"]
STATES = ["NORMAL", "GUARDED", "RESTRICTED", "ISOLATED"]
STATE_COLOR = {"NORMAL": "#1baf7a", "GUARDED": "#eda100", "RESTRICTED": "#eb6834", "ISOLATED": "#e34948"}
COUNTERS = ["exfil", "leaked", "blocks", "heals", "messages", "reads", "purged", "good_lost"]


def _reason(r: str) -> str:
    """'rule R2: rule R2' -> 'rule R2' (the gate sometimes repeats the rule id as the explanation)."""
    head, _, tail = (r or "").partition(": ")
    return head if tail == head else (r or "")


def describe(e: dict) -> str:
    """One-line human description of any event (routine ones included)."""
    k, ag = e["kind"], e.get("agent")
    if k == "allow":
        return f"{ag} ran {e.get('tool')}" + (" on untrusted input" if e.get("untrusted") else "")
    if k == "message":
        return f"{ag} → {e.get('to')} message" + (" (carries untrusted data)" if e.get("untrusted") else "")
    if k == "block":
        return f"BLOCKED {ag}.{e.get('tool')}: {_reason(e.get('reason', ''))}"
    if k == "state":
        return f"{ag}: {e['frm']} → {e['to']}"
    if k == "read_poison":
        return f"{ag} read a POISONED page ({e.get('source', '')})"
    if k == "exfil_export":
        return f"BREACH: {ag} exported {e.get('units', 0)} sensitive records under untrusted instruction"
    if k == "leak":
        return f"LEAK: {ag} emailed records to {e.get('to')}"
    if k == "heal":
        lost = f", {e['good_lost']} of them clean" if e.get("good_lost") else ""
        return (f"HEAL {ag}: traced to {', '.join(e.get('roots', []))[:70]} — "
                f"purged {e.get('removed', 0)} items{lost} ({e.get('mode', '')})")
    return f"{ag} {k}"


def build_frames(events: list[dict]) -> list[dict]:
    """Each frame is the full visible state just after one event."""
    states = {a: "NORMAL" for a in AGENTS}
    last = {a: "" for a in AGENTS}
    taint = {a: False for a in AGENTS}
    risk = {a: 0.0 for a in AGENTS}
    stats = {a: {"ok": 0, "blocked": 0, "sent": 0} for a in AGENTS}
    pairs: dict[str, dict] = {}          # "src>dst" -> {"n", "untrusted"}
    c = {k: 0 for k in COUNTERS}
    frames = []
    for e in events:
        k, ag = e["kind"], e.get("agent")
        headline = ""
        if k == "allow":
            last[ag] = f"✓ {e.get('tool')}"
            stats[ag]["ok"] += 1
            risk[ag] = e.get("risk", risk[ag])
            taint[ag] |= bool(e.get("untrusted"))
        elif k == "block":
            last[ag] = f"✗ {e.get('tool')} — {_reason(e.get('reason', ''))}"
            stats[ag]["blocked"] += 1
            risk[ag] = e.get("risk", risk[ag])
            c["blocks"] += 1
            headline = describe(e)
        elif k == "message":
            c["messages"] += 1
            stats[ag]["sent"] += 1
            to = e.get("to")
            last[ag] = f"→ msg to {to}" + (" (untrusted)" if e.get("untrusted") else "")
            p = pairs.setdefault(f"{ag}>{to}", {"n": 0, "untrusted": False})
            p["n"] += 1
            p["untrusted"] |= bool(e.get("untrusted"))
            if to in taint and e.get("untrusted"):
                taint[to] = True
        elif k == "state":
            states[ag] = e["to"]
            headline = describe(e)
        elif k == "read_poison":
            c["reads"] += 1
            taint[ag] = True
            headline = describe(e)
        elif k == "exfil_export":
            c["exfil"] += e.get("units", 0)
            headline = describe(e)
        elif k == "leak":
            c["leaked"] = e.get("units", c["leaked"])
            headline = describe(e)
        elif k == "heal":
            c["heals"] += 1
            c["purged"] += e.get("removed", 0)
            c["good_lost"] += e.get("good_lost", 0)
            taint[ag] = False
            headline = describe(e)
        frames.append({"i": len(frames), "t": e.get("t", 0), "kind": k, "headline": headline,
                       "detail": describe(e), "event": e, "agent": ag,
                       "states": dict(states), "last": dict(last), "counters": dict(c),
                       "taint": dict(taint), "risk": dict(risk),
                       "stats": {a: dict(s) for a, s in stats.items()},
                       "pairs": {p: dict(v) for p, v in pairs.items()}})
    return frames


def empty_frame():
    return {"i": -1, "t": 0, "kind": "", "headline": "", "detail": "", "event": {}, "agent": None,
            "states": {a: "NORMAL" for a in AGENTS}, "last": {a: "" for a in AGENTS},
            "counters": {k: 0 for k in COUNTERS}, "taint": {a: False for a in AGENTS},
            "risk": {a: 0.0 for a in AGENTS},
            "stats": {a: {"ok": 0, "blocked": 0, "sent": 0} for a in AGENTS}, "pairs": {}}
