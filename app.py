"""ContainMAS live dashboard.  Run:  .venv/Scripts/streamlit run app.py

Two modes:
  - Replay: animate a saved run from results/live_*.json (safe for the presentation).
  - Run live: drive 4 real LLM agents through the checkpoint and watch it unfold.
"""
from __future__ import annotations

import html
import json
import threading
import time
from pathlib import Path

import streamlit as st

from live.frames import AGENTS, STATE_COLOR, STATES, build_frames, empty_frame

st.set_page_config(page_title="ContainMAS", layout="wide", page_icon="🛡️")
RESULTS = Path(__file__).parent / "results"
ROLE = {"research": "web & documents", "data": "customer database",
        "analysis": "reports & publishing", "comms": "email"}
ICON = {"research": "🔎", "data": "🗄️", "analysis": "📊", "comms": "✉️"}
# topology layout (svg viewBox 760x360): agents in the middle, the resource each one touches outside
POS = {"research": (250, 80), "analysis": (510, 80), "data": (250, 280), "comms": (510, 280)}
RES = {"web": ("🌐 Web", 70, 80, "research"), "db": ("🗄️ Customer DB", 70, 280, "data"),
       "files": ("📄 Reports / public", 690, 80, "analysis"), "mail": ("📤 Email", 690, 280, "comms")}
TOOL_RES = {"web_fetch": "web", "db_aggregate": "db", "db_export_records": "db", "write_file": "files",
            "publish": "files", "send_email": "mail"}
KIND_STYLE = {  # icon, accent colour
    "allow": ("✓", "#5b6474"), "message": ("→", "#5b6474"), "state": ("⇅", "#6d8cff"),
    "block": ("⛔", "#eda100"), "heal": ("🩹", "#1baf7a"), "read_poison": ("☣", "#e34948"),
    "exfil_export": ("🚨", "#e34948"), "leak": ("📤", "#e34948")}

st.markdown("""<style>
.block-container{padding-top:1.2rem;padding-bottom:2rem;max-width:1500px;}
.hdr{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:.4rem;}
.hdr h1{font-size:1.7rem;margin:0;padding:0;}
.pill{display:inline-block;padding:3px 11px;border-radius:999px;font-size:.75rem;font-weight:700;
  letter-spacing:.4px;background:#1c2433;color:#c9d4e5;border:1px solid #2a3446;}
.pill.live{background:#3a1216;color:#ff8a8a;border-color:#6b1f26;}
.pill.live::before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;
  background:#ff5a5a;margin-right:6px;animation:blink 1s infinite;}
@keyframes blink{50%{opacity:.2}}
.banner{border-radius:12px;padding:12px 16px;font-weight:600;margin:.3rem 0 .8rem;border:1px solid;}
.banner.bad{background:#2a1013;border-color:#6b1f26;color:#ffb3b3;}
.banner.good{background:#0f2a20;border-color:#1f6b4c;color:#9be8c4;}
.banner.idle{background:#141b27;border-color:#263044;color:#a8b3c7;}
.panel{background:#121925;border:1px solid #232d3d;border-radius:14px;padding:12px 14px;}
.ptitle{font-size:.72rem;color:#8a96aa;text-transform:uppercase;letter-spacing:.8px;font-weight:700;
  margin-bottom:6px;}
.kpis{display:grid;grid-template-columns:1fr 1fr;gap:10px;}
.kpi{background:#121925;border:1px solid #232d3d;border-radius:12px;padding:12px 14px;}
.kpi .v{font-size:2rem;font-weight:800;line-height:1.05;color:#e6edf3;}
.kpi .v.bad{color:#ff6b6b;} .kpi .v.warn{color:#f5b942;} .kpi .v.good{color:#3ddc97;}
.kpi .l{font-size:.7rem;color:#8a96aa;text-transform:uppercase;letter-spacing:.6px;margin-top:2px;}
.kpi .s{font-size:.72rem;color:#6f7b90;margin-top:2px;}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:.8rem 0;}
@media (max-width:1100px){.cards{grid-template-columns:repeat(2,minmax(0,1fr));}}
.card{background:#121925;border:1px solid #232d3d;border-top:4px solid var(--c);border-radius:14px;
  padding:12px 14px;transition:box-shadow .3s;}
.card.active{box-shadow:0 0 0 2px var(--c),0 0 22px -4px var(--c);}
.card .top{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;}
.card .nm{font-weight:800;font-size:1.02rem;color:#e6edf3;}
.card .role{font-size:.74rem;color:#8a96aa;}
.card .ic{font-size:1.5rem;line-height:1;}
.ladder{display:flex;gap:3px;margin:10px 0 4px;}
.ladder span{flex:1;height:6px;border-radius:3px;background:#263044;}
.stname{font-size:.75rem;font-weight:800;letter-spacing:.6px;color:var(--c);}
.tag{display:inline-block;font-size:.66rem;font-weight:700;padding:1px 7px;border-radius:999px;margin-left:4px;}
.tag.taint{background:#3a1216;color:#ff8a8a;} .tag.clean{background:#0f2a20;color:#7fdcb0;}
.act{margin-top:8px;font-family:ui-monospace,Consolas,monospace;font-size:.78rem;color:#c9d4e5;
  background:#0c121b;border-radius:8px;padding:6px 8px;min-height:2.3em;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;}
.risk{display:flex;align-items:center;gap:8px;margin-top:8px;font-size:.7rem;color:#8a96aa;}
.risk .bar{flex:1;height:5px;background:#263044;border-radius:3px;overflow:hidden;}
.risk .bar i{display:block;height:100%;}
.stats{display:flex;gap:12px;margin-top:8px;font-size:.72rem;color:#8a96aa;}
.stats b{color:#e6edf3;}
.ev{display:flex;gap:8px;align-items:baseline;font-size:.82rem;padding:5px 8px;margin:3px 0;
  border-radius:8px;background:#0f1520;border-left:3px solid var(--c);color:#d5deeb;}
.ev .t{font-family:ui-monospace,Consolas,monospace;color:#6f7b90;min-width:2.6em;}
.ev.now{background:#18233a;}
.ev.dim{color:#7d889b;}
svg .flow{stroke-dasharray:6 6;animation:flow .6s linear infinite;}
@keyframes flow{to{stroke-dashoffset:-12}}
svg .pulse{animation:pulse 1.1s ease-in-out infinite;}
@keyframes pulse{50%{opacity:.35}}
</style>""", unsafe_allow_html=True)

ss = st.session_state
ss.setdefault("frames", [])
ss.setdefault("idx", 0)
ss.setdefault("live", None)        # dict with system + thread when running live
ss.setdefault("playing", False)


# ----------------------------------------------------------------- live runner
def start_live(defense, flood, model, poison):
    from live.agents import Orchestrator
    from live.llm import LLM
    from live.run import TASKS
    from live.system import Config, LiveSystem
    from live.world import World

    world = World(seed=1)
    world.poison_on = poison
    world.decoys = [f"mirror{i}.test" for i in range(flood)]
    cfg = (Config(budgets=(defense == "budgets")) if defense != "off"
           else Config(rules=False, graduated=False, heal=False))
    sysm = LiveSystem(world, cfg)
    orch = Orchestrator(sysm, LLM(model))
    tasks = list(TASKS) + ([("research", "Also check mirror sites: " +
                             ", ".join(f"mirror{i}.test/x" for i in range(flood)))] if flood else [])
    # plain dict the worker thread owns -- NEVER touch st.session_state from the thread
    ctrl = {"sys": sysm, "world": world, "done": False, "stop": False, "error": None, "model": model}

    def worker():
        try:
            for lead, goal in tasks:
                if ctrl["stop"]:
                    break
                orch.run_task(goal, lead)
        except Exception as e:  # surface LLM/key errors in the UI instead of dying silently
            ctrl["error"] = f"{type(e).__name__}: {e}"
        ctrl["done"] = True

    ctrl["thread"] = threading.Thread(target=worker, daemon=True)
    ss["live"] = ctrl
    ctrl["thread"].start()


# ----------------------------------------------------------------- rendering
def esc(s) -> str:
    return html.escape(str(s or ""))


def topology_svg(frame) -> str:
    """Agents as nodes (coloured by containment state), messages as edges, tools as edges to resources."""
    ev, cur = frame["event"], frame["agent"]
    out = ['<svg viewBox="0 36 760 290" width="100%" style="display:block;max-height:360px">',
           '<defs>'] + [
        f'<marker id="ar{n}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="{c}"/></marker>'
        for n, c in (("g", "#3a4558"), ("r", "#e05555"), ("b", "#6d8cff"), ("y", "#eda100"))] + ['</defs>']

    def edge_pts(a, b, off):
        (x1, y1), (x2, y2) = POS[a], POS[b]
        # shorten to node border and offset sideways so a>b and b>a don't overlap
        dx, dy = x2 - x1, y2 - y1
        d = max((dx * dx + dy * dy) ** .5, 1)
        ux, uy = dx / d, dy / d
        nx, ny = -uy * off, ux * off
        # distance from node centre to its 160x68 border along (ux, uy)
        r = min(80 / abs(ux) if ux else 1e9, 34 / abs(uy) if uy else 1e9) + 4
        return x1 + ux * r + nx, y1 + uy * r + ny, x2 - ux * r + nx, y2 - uy * r + ny, nx / 7, ny / 7

    # agent<->agent message edges
    live_pair = f"{cur}>{ev.get('to')}" if ev.get("kind") == "message" else None
    for i, a in enumerate(AGENTS):
        for b in AGENTS[i + 1:]:
            x1, y1, x2, y2, *_ = edge_pts(a, b, 0)
            out.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="#1f2836" '
                       f'stroke-width="1.5"/>')
    for key, p in frame["pairs"].items():
        a, b = key.split(">")
        if a not in POS or b not in POS:
            continue
        x1, y1, x2, y2, px, py = edge_pts(a, b, 7)
        hot = key == live_pair
        col, mk = (("#6d8cff", "b") if hot else ("#e05555", "r") if p["untrusted"] else ("#3a4558", "g"))
        w = min(1.5 + p["n"] * .6, 5) + (1.5 if hot else 0)
        out.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{col}" '
                   f'stroke-width="{w:.1f}" marker-end="url(#ar{mk})" class="{"flow" if hot else ""}" '
                   f'opacity="{1 if hot else .75}"><title>{a} → {b}: {p["n"]} msgs'
                   f'{" (untrusted)" if p["untrusted"] else ""}</title></line>')
        if p["n"] > 1:
            out.append(f'<text x="{(x1 + x2) / 2 + px * 11:.0f}" y="{(y1 + y2) / 2 + py * 11 + 4:.0f}" fill="#8a96aa" '
                       f'font-size="11" text-anchor="middle">{p["n"]}</text>')

    # resources + agent->resource tool edges
    tool_res = TOOL_RES.get(ev.get("tool")) if ev.get("kind") in ("allow", "block") else None
    if ev.get("kind") == "exfil_export":
        tool_res = "db"
    if ev.get("kind") in ("leak", "read_poison"):
        tool_res = "mail" if ev["kind"] == "leak" else "web"
    for rid, (label, rx, ry, owner) in RES.items():
        ax, ay = POS[owner]
        hot = rid == tool_res and cur == owner
        bad = hot and ev.get("kind") in ("exfil_export", "leak", "read_poison")
        blocked = hot and ev.get("kind") == "block"
        col, mk = (("#e05555", "r") if bad else ("#eda100", "y") if blocked else
                   ("#6d8cff", "b") if hot else ("#2a3446", "g"))
        x_in = ax - 84 if rx < ax else ax + 84
        x_out = rx + 68 if rx < ax else rx - 68
        if rid in ("web", "db"):          # sources: data flows into the agent
            x_in, x_out = x_out, x_in
        out.append(f'<line x1="{x_in}" y1="{ay}" x2="{x_out}" y2="{ry}" stroke="{col}" '
                   f'stroke-width="{3 if hot else 1.5}" class="{"flow" if hot else ""}" '
                   f'marker-end="url(#ar{mk})"/>')
        if blocked:
            mx = (x_in + x_out) / 2
            out.append(f'<text x="{mx:.0f}" y="{ay + 6}" font-size="18" text-anchor="middle">⛔</text>')
        out.append(f'<rect x="{rx - 64}" y="{ry - 20}" width="128" height="40" rx="10" fill="#0f1520" '
                   f'stroke="{col if hot else "#2a3446"}" stroke-dasharray="{"" if hot else "4 3"}"/>'
                   f'<text x="{rx}" y="{ry + 5}" fill="#a8b3c7" font-size="12.5" '
                   f'text-anchor="middle">{label}</text>')

    # agent nodes
    for a in AGENTS:
        x, y = POS[a]
        s = frame["states"][a]
        c = STATE_COLOR[s]
        active = a == cur
        if active:
            out.append(f'<rect x="{x - 88}" y="{y - 40}" width="176" height="80" rx="18" fill="none" '
                       f'stroke="{c}" stroke-width="2" class="pulse"/>')
        out.append(f'<rect x="{x - 80}" y="{y - 34}" width="160" height="68" rx="14" fill="{c}" '
                   f'fill-opacity="{.28 if active else .16}" stroke="{c}" stroke-width="{2.5 if active else 1.5}">'
                   f'<title>{a}: {s}</title></rect>'
                   f'<text x="{x}" y="{y - 6}" fill="#e6edf3" font-size="15" font-weight="700" '
                   f'text-anchor="middle">{ICON[a]} {a.capitalize()}</text>'
                   f'<text x="{x}" y="{y + 16}" fill="{c}" font-size="11.5" font-weight="800" '
                   f'letter-spacing="1" text-anchor="middle">{s}</text>')
        if frame["taint"][a]:
            out.append(f'<g><circle cx="{x + 72}" cy="{y - 28}" r="11" fill="#3a1216" stroke="#e05555"/>'
                       f'<text x="{x + 72}" y="{y - 24}" font-size="12" text-anchor="middle">☣</text>'
                       f'<title>{a} holds untrusted (tainted) data</title></g>')
    out.append('</svg>')
    return "".join(out)


def agent_cards(frame) -> str:
    cards = []
    for a in AGENTS:
        s = frame["states"][a]
        c = STATE_COLOR[s]
        lvl = STATES.index(s)
        ladder = "".join(f'<span style="background:{STATE_COLOR[STATES[j]] if j <= lvl else "#263044"}"></span>'
                         for j in range(len(STATES)))
        tag = ('<span class="tag taint">☣ tainted</span>' if frame["taint"][a]
               else '<span class="tag clean">clean</span>')
        r = frame["risk"][a]
        rc = "#e05555" if r >= .7 else "#eda100" if r >= .4 else "#1baf7a"
        st_ = frame["stats"][a]
        cards.append(
            f'<div class="card{" active" if a == frame["agent"] else ""}" style="--c:{c}">'
            f'<div class="top"><div><div class="nm">{a.capitalize()} agent</div>'
            f'<div class="role">{ROLE[a]}</div></div><div class="ic">{ICON[a]}</div></div>'
            f'<div class="ladder">{ladder}</div>'
            f'<div><span class="stname">{s}</span>{tag}</div>'
            f'<div class="act" title="{esc(frame["last"][a])}">{esc(frame["last"][a]) or "idle"}</div>'
            f'<div class="risk">risk<div class="bar"><i style="width:{r * 100:.0f}%;background:{rc}"></i></div>'
            f'{r:.2f}</div>'
            f'<div class="stats"><span>✓ <b>{st_["ok"]}</b> allowed</span>'
            f'<span>⛔ <b>{st_["blocked"]}</b> blocked</span><span>→ <b>{st_["sent"]}</b> msgs</span></div>'
            f'</div>')
    return f'<div class="cards">{"".join(cards)}</div>'


def kpis(c) -> str:
    tiles = [("Records exfiltrated", c["exfil"], "bad" if c["exfil"] else "good", "sensitive rows pulled"),
             ("Emailed out", c["leaked"], "bad" if c["leaked"] else "good", "records leaked externally"),
             ("Actions blocked", c["blocks"], "warn" if c["blocks"] else "", "by the checkpoint"),
             ("Poisoned reads", c["reads"], "bad" if c["reads"] else "", "injected content ingested"),
             ("Heals", c["heals"], "good" if c["heals"] else "", "provenance rollbacks"),
             ("Items purged", c["purged"], "", f'{c.get("good_lost", 0)} were clean (collateral)')]
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="v {cls}">{v}</div><div class="l">{lbl}</div><div class="s">{sub}</div></div>'
        for lbl, v, cls, sub in tiles) + '</div>'


def verdict(c, finished) -> str:
    if c["exfil"] or c["leaked"]:
        return (f'<div class="banner bad">🚨 Breach — {c["exfil"]} records exfiltrated'
                f'{f", {c["leaked"]} emailed out" if c["leaked"] else ""}. The injected instruction reached a '
                f'privileged agent unchecked.</div>')
    if c["blocks"] or c["heals"]:
        tail = " Run finished with zero data loss." if finished else ""
        return (f'<div class="banner good">🛡️ Contained — {c["blocks"]} malicious action(s) blocked, '
                f'{c["heals"]} heal(s).{tail}</div>')
    if c["reads"]:
        return '<div class="banner bad">☣ Poisoned content has entered the system — watching where it flows…</div>'
    return '<div class="banner idle">All agents operating normally.</div>'


def timeline_svg(frames, upto, total) -> str:
    """Swimlane: one lane per agent, background = containment state, marks = notable events."""
    W, LH, L = 1000, 30, 92
    total = max(total, 1)
    xs = lambda i: L + (W - L - 10) * i / total
    out = [f'<svg viewBox="0 0 {W} {LH * 4 + 26}" width="100%" style="display:block">']
    for r, a in enumerate(AGENTS):
        y = r * LH + 4
        out.append(f'<text x="0" y="{y + 18}" fill="#a8b3c7" font-size="12.5">{ICON[a]} {a}</text>'
                   f'<rect x="{L}" y="{y}" width="{W - L - 10}" height="{LH - 8}" rx="5" fill="#0f1520"/>')
        start, cur = 0, "NORMAL"
        for i in range(upto + 1):
            s = frames[i]["states"][a]
            if s != cur:
                out.append(f'<rect x="{xs(start):.1f}" y="{y}" width="{xs(i) - xs(start):.1f}" height="{LH - 8}" '
                           f'fill="{STATE_COLOR[cur]}" opacity=".35"/>')
                start, cur = i, s
        out.append(f'<rect x="{xs(start):.1f}" y="{y}" width="{xs(upto + 1) - xs(start):.1f}" height="{LH - 8}" '
                   f'fill="{STATE_COLOR[cur]}" opacity=".35"/>')
        for i in range(upto + 1):
            f = frames[i]
            if f["agent"] != a:
                continue
            k = f["kind"]
            cx = (xs(i) + xs(i + 1)) / 2
            if k in ("allow", "message"):
                out.append(f'<circle cx="{cx:.1f}" cy="{y + (LH - 8) / 2}" r="2.5" fill="#8a96aa">'
                           f'<title>t={f["t"]} {esc(f["detail"])}</title></circle>')
            elif k != "state":
                out.append(f'<text x="{cx:.1f}" y="{y + 16}" font-size="13" text-anchor="middle">'
                           f'{KIND_STYLE.get(k, ("•",))[0]}<title>t={f["t"]} {esc(f["detail"])}</title></text>')
    out.append(f'<line x1="{xs(upto + 1):.1f}" y1="0" x2="{xs(upto + 1):.1f}" y2="{LH * 4}" stroke="#e6edf3" '
               f'stroke-width="1.5" opacity=".7"/>')
    legend = "".join(f'<rect x="{L + j * 130}" y="{LH * 4 + 8}" width="12" height="12" rx="3" '
                     f'fill="{STATE_COLOR[s]}" opacity=".7"/><text x="{L + j * 130 + 18}" y="{LH * 4 + 18}" '
                     f'fill="#8a96aa" font-size="11">{s}</text>' for j, s in enumerate(STATES))
    out.append(legend + '</svg>')
    return "".join(out)


def event_log(frames, upto, show_all) -> str:
    rows = []
    for f in reversed(frames[max(0, upto - 150):upto + 1]):
        if not show_all and not f["headline"]:
            continue
        icon, col = KIND_STYLE.get(f["kind"], ("•", "#5b6474"))
        cls = "now" if f["i"] == upto else ("dim" if not f["headline"] else "")
        rows.append(f'<div class="ev {cls}" style="--c:{col}"><span class="t">t={f["t"]}</span>'
                    f'<span>{icon}</span><span>{esc(f["detail"])}</span></div>')
    return "".join(rows) or '<div class="ev dim" style="--c:#2a3446">No notable events yet.</div>'


def render(frames, upto, header, finished):
    frame = frames[upto] if frames else empty_frame()
    st.markdown(header, unsafe_allow_html=True)
    st.html(verdict(frame["counters"], finished))
    left, right = st.columns([3, 2], gap="medium")
    with left:
        st.html('<div class="panel"><div class="ptitle">Agent topology · message & tool flow</div>'
                + topology_svg(frame) +
                '<div style="font-size:.72rem;color:#6f7b90;margin-top:4px">'
                '<span style="color:#6d8cff">━</span> current action &nbsp; '
                '<span style="color:#e05555">━</span> carried untrusted data &nbsp; '
                '<span style="color:#eda100">⛔</span> blocked &nbsp; ☣ tainted agent &nbsp; '
                'edge thickness = message volume</div></div>')
    with right:
        st.html(kpis(frame["counters"]))
        now = esc(frame["detail"]) if frames else "waiting for first action…"
        icon, col = KIND_STYLE.get(frame["kind"], ("•", "#5b6474"))
        st.html(f'<div class="panel" style="margin-top:10px;border-left:4px solid {col}">'
                f'<div class="ptitle">Now · t={frame["t"]}</div>'
                f'<div style="color:#e6edf3;font-size:.95rem">{icon} {now}</div></div>')
    st.html(agent_cards(frame))
    if frames:
        st.html('<div class="panel"><div class="ptitle">Containment timeline</div>'
                + timeline_svg(frames, upto, len(frames))
                + '</div>')
    st.markdown("")
    with st.container(height=300, border=True):
        st.html('<div class="ptitle">Event log · newest first</div>'
                + event_log(frames, upto, ss.get("show_all", False)))


def header(mode_pill, bits) -> str:
    return (f'<div class="hdr"><h1>🛡️ Attacking the Cure</h1>{mode_pill}'
            + "".join(f'<span class="pill">{esc(b)}</span>' for b in bits if b) + '</div>')


# ----------------------------------------------------------------- sidebar
st.sidebar.title("🛡️ ContainMAS")
st.sidebar.caption("Containment & self-healing for multi-agent LLM systems")
mode = st.sidebar.radio("Mode", ["Replay saved run", "Run live (Groq)"])

if mode == "Replay saved run":
    files = sorted(RESULTS.glob("live_*.json"))
    labels = {f.name: f for f in files}
    pick = st.sidebar.selectbox("Saved run", list(labels) or ["(none — run one first)"])
    ss["speed"] = st.sidebar.slider("Speed (events/sec)", 1, 10, 3)
    if files and st.sidebar.button("▶ Load / restart", use_container_width=True, type="primary"):
        data = json.loads(labels[pick].read_text(encoding="utf-8"))
        ss["frames"] = build_frames(data["events"])
        ss["meta"] = {k: data.get(k) for k in ("defense", "flood", "model", "exfil_exports", "leaked",
                                               "llm_calls", "seconds")} | {"file": pick}
        ss["idx"] = 0
        ss["playing"] = True
else:
    defense = st.sidebar.selectbox("Defense", ["on", "off", "budgets"],
                                   help="off = no checkpoint · on = ContainMAS · budgets = + response budgets")
    model = st.sidebar.selectbox("Model", ["gpt-oss-20b", "qwen3-27b", "gpt-oss-120b"])
    flood = st.sidebar.slider("Quarantine-flood intensity", 0, 6, 0)
    poison = st.sidebar.checkbox("Inject poisoned page", value=True)
    if st.sidebar.button("▶ Run live episode", use_container_width=True, type="primary"):
        if ss.get("live"):
            ss["live"]["stop"] = True
        start_live(defense, flood, model, poison)
    if ss.get("live") and st.sidebar.button("■ Stop", use_container_width=True):
        ss["live"]["stop"] = True

st.sidebar.divider()
ss["show_all"] = st.sidebar.toggle("Show routine events in log", value=ss.get("show_all", False),
                                   help="Include every allowed tool call and inter-agent message")
with st.sidebar.expander("How to read this"):
    st.markdown(
        "- **Nodes** are the 4 LLM agents, coloured by containment state "
        "(NORMAL → GUARDED → RESTRICTED → ISOLATED).\n"
        "- **☣** marks an agent whose context holds untrusted data (taint).\n"
        "- **Red edges** are messages that carried untrusted data between agents.\n"
        "- The **timeline** shows each agent's state over the run; ⛔ block, 🩹 heal, ☣ poisoned read, "
        "🚨 exfiltration.")

slot = st.empty()

# ----------------------------------------------------------------- drive the view
if mode == "Run live (Groq)" and ss.get("live"):
    live = ss["live"]
    frames = build_frames(list(live["sys"].events))
    done = live["done"] or live["stop"]
    cfg = live["sys"].cfg
    dname = "off" if cfg.rules is False else ("budgets" if cfg.budgets else "on")
    pill = '<span class="pill">FINISHED</span>' if done else '<span class="pill live">LIVE</span>'
    with slot.container():
        render(frames, len(frames) - 1, header(pill, [f"defense: {dname}", f"model: {live.get('model')}",
                                                      f"{live['sys'].t} actions"]), done)
        if live.get("error"):
            st.error(f"Live run failed — {live['error']}. Check your GROQ_API_KEY in .env and your "
                     f"connection, or use Replay mode.")
    if not done:
        time.sleep(0.6)
        st.rerun()
elif mode == "Replay saved run" and ss.get("frames"):
    frames = ss["frames"]
    i = ss["idx"] = min(ss["idx"], len(frames) - 1)
    meta = ss.get("meta", {})
    finished = i == len(frames) - 1
    pill = '<span class="pill">REPLAY</span>'
    bits = [meta.get("file"), f"defense: {meta.get('defense')}", f"model: {meta.get('model')}",
            f"step {i + 1}/{len(frames)}"]
    with slot.container():
        nav = st.columns([1, 1, 1, 1, 8])
        if nav[0].button("⏸ Pause" if ss["playing"] else "▶ Play", use_container_width=True):
            if finished and not ss["playing"]:
                ss["idx"] = 0
            ss["playing"] = not ss["playing"]; st.rerun()
        if nav[1].button("◀ Step", use_container_width=True, disabled=i == 0):
            ss["idx"] = i - 1; ss["playing"] = False; st.rerun()
        if nav[2].button("Step ▶", use_container_width=True, disabled=finished):
            ss["idx"] = i + 1; ss["playing"] = False; st.rerun()
        if nav[3].button("⏭ End", use_container_width=True):
            ss["idx"] = len(frames) - 1; ss["playing"] = False; st.rerun()
        ss["scrub"] = i
        nav[4].slider("Timeline", 0, len(frames) - 1, key="scrub", label_visibility="collapsed",
                      on_change=lambda: ss.update(idx=ss["scrub"], playing=False))
        render(frames, i, header(pill, bits), finished)
    if ss["playing"] and not finished:
        time.sleep(1 / ss.get("speed", 3))
        ss["idx"] = i + 1
        st.rerun()
    elif ss["playing"]:
        ss["playing"] = False
else:
    with slot.container():
        st.markdown(header('<span class="pill">IDLE</span>', []), unsafe_allow_html=True)
        st.info("Pick a saved run and press **Load**, or switch to **Run live** to drive real LLM agents "
                "through the ContainMAS checkpoint.")
        render([], 0, "", False)
