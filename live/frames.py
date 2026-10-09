"""Turn an event list into per-step UI frames (agent states + counters + log), for the dashboard."""
from __future__ import annotations

AGENTS = ["research", "data", "analysis", "comms"]
STATE_COLOR = {"NORMAL": "#1baf7a", "GUARDED": "#eda100", "RESTRICTED": "#eb6834", "ISOLATED": "#e34948"}


def build_frames(events: list[dict]) -> list[dict]:
    """Each frame is the full visible state just after one event."""
    states = {a: "NORMAL" for a in AGENTS}
    last = {a: "" for a in AGENTS}
    c = {"exfil": 0, "leaked": 0, "blocks": 0, "heals": 0, "messages": 0, "reads": 0, "purged": 0}
    frames = []
    for e in events:
        k, ag = e["kind"], e.get("agent")
        headline = ""
        if k == "allow":
            last[ag] = f"✓ {e.get('tool')}"
        elif k == "block":
            last[ag] = f"✗ {e.get('tool')} — {e.get('reason', '')}"
            c["blocks"] += 1
            headline = f"BLOCKED {ag}.{e.get('tool')}: {e.get('reason','')}"
        elif k == "message":
            c["messages"] += 1
            last[ag] = f"→ msg to {e.get('to')}" + (" (untrusted)" if e.get("untrusted") else "")
        elif k == "state":
            states[ag] = e["to"]
            headline = f"{ag}: {e['frm']} → {e['to']}"
        elif k == "read_poison":
            c["reads"] += 1
            headline = f"{ag} read a POISONED page ({e.get('source','')})"
        elif k == "exfil_export":
            c["exfil"] += e.get("units", 0)
            headline = f"BREACH: {ag} exported {e.get('units',0)} sensitive records under untrusted instruction"
        elif k == "leak":
            c["leaked"] = e.get("units", c["leaked"])
            headline = f"LEAK: {ag} emailed records to {e.get('to')}"
        elif k == "heal":
            c["heals"] += 1
            c["purged"] += e.get("removed", 0)
            headline = (f"HEAL {ag}: traced to {', '.join(e.get('roots', []))[:60]} — "
                        f"purged {e.get('removed',0)} items ({e.get('mode','')})")
        frames.append({"i": len(frames), "t": e.get("t", 0), "kind": k, "headline": headline,
                       "states": dict(states), "last": dict(last), "counters": dict(c)})
    return frames


def empty_frame():
    return {"i": -1, "t": 0, "kind": "", "headline": "", "states": {a: "NORMAL" for a in AGENTS},
            "last": {a: "" for a in AGENTS},
            "counters": {k: 0 for k in ["exfil", "leaked", "blocks", "heals", "messages", "reads", "purged"]}}
