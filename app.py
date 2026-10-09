"""ContainMAS live dashboard.  Run:  .venv/Scripts/streamlit run app.py

Two modes:
  - Replay: animate a saved run from results/live_*.json (safe for the presentation).
  - Run live: drive 4 real LLM agents through the checkpoint and watch it unfold.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import streamlit as st

from live.frames import AGENTS, STATE_COLOR, build_frames, empty_frame

st.set_page_config(page_title="ContainMAS", layout="wide", page_icon="🛡️")
RESULTS = Path(__file__).parent / "results"
ROLE = {"research": "web & documents", "data": "customer database",
        "analysis": "reports & publishing", "comms": "email"}

st.markdown("""<style>
.block-container{padding-top:1.4rem;}
.agent{border-radius:14px;padding:14px 16px;color:#fff;min-height:118px;}
.agent h3{margin:0;font-size:1.05rem;} .agent .role{opacity:.85;font-size:.78rem;}
.agent .st{display:inline-block;margin-top:8px;padding:2px 10px;border-radius:20px;
  background:rgba(0,0,0,.22);font-weight:700;font-size:.8rem;letter-spacing:.5px;}
.agent .act{margin-top:10px;font-size:.82rem;min-height:2.2em;opacity:.95;}
.ev{font-family:ui-monospace,monospace;font-size:.82rem;padding:3px 8px;border-radius:6px;margin:2px 0;}
.big{font-size:2.3rem;font-weight:800;line-height:1;}
.lbl{font-size:.75rem;color:#8a8984;text-transform:uppercase;letter-spacing:.6px;}
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

    def worker():
        for lead, goal in tasks:
            if ss["live"] and ss["live"].get("stop"):
                break
            orch.run_task(goal, lead)
        if ss.get("live"):
            ss["live"]["done"] = True

    th = threading.Thread(target=worker, daemon=True)
    ss["live"] = {"sys": sysm, "world": world, "thread": th, "done": False, "stop": False}
    th.start()


# ----------------------------------------------------------------- rendering
def agent_card(name, state, action):
    st.markdown(
        f"""<div class="agent" style="background:{STATE_COLOR[state]}">
        <h3>{name.capitalize()} agent</h3><div class="role">{ROLE[name]}</div>
        <span class="st">{state}</span><div class="act">{action or '&nbsp;'}</div></div>""",
        unsafe_allow_html=True)


def render(frame, log_tail, subtitle):
    st.markdown(f"#### {subtitle}")
    cols = st.columns(4)
    for col, a in zip(cols, AGENTS):
        with col:
            agent_card(a, frame["states"][a], frame["last"][a])

    c = frame["counters"]
    m = st.columns(5)
    tiles = [("Records exfiltrated", c["exfil"], c["exfil"] > 0),
             ("Emailed out", c["leaked"], c["leaked"] > 0),
             ("Actions blocked", c["blocks"], False),
             ("Heals", c["heals"], False),
             ("Items purged", c["purged"], False)]
    for col, (lbl, val, bad) in zip(m, tiles):
        col.markdown(f"<div class='lbl'>{lbl}</div><div class='big' "
                     f"style='color:{'#e34948' if bad else '#0b0b0b'}'>{val}</div>", unsafe_allow_html=True)

    st.markdown("###### Event log")
    box = st.container(height=260)
    palette = {"block": "#fff3cd", "heal": "#d4f5e4", "leak": "#f8d7da", "exfil_export": "#f8d7da",
               "read_poison": "#f8d7da", "state": "#e2e8f5", "message": "#f2f1ec"}
    for e in log_tail:
        if not e["headline"] and e["kind"] in ("allow", "message"):
            continue
        bg = palette.get(e["kind"], "#f2f1ec")
        box.markdown(f"<div class='ev' style='background:{bg}'>t={e['t']:>2} · {e['headline']}</div>",
                     unsafe_allow_html=True)


# ----------------------------------------------------------------- sidebar
st.sidebar.title("🛡️ ContainMAS")
st.sidebar.caption("Containment & self-healing for multi-agent LLM systems")
mode = st.sidebar.radio("Mode", ["Replay saved run", "Run live (Groq)"])

if mode == "Replay saved run":
    files = sorted(RESULTS.glob("live_*.json"))
    labels = {f.name: f for f in files}
    pick = st.sidebar.selectbox("Saved run", list(labels) or ["(none — run one first)"])
    ss["speed"] = st.sidebar.slider("Speed (events/sec)", 1, 10, 3)
    if files and st.sidebar.button("▶ Load / restart", use_container_width=True):
        data = json.loads(labels[pick].read_text(encoding="utf-8"))
        ss["frames"] = build_frames(data["events"])
        ss["meta"] = {k: data.get(k) for k in ("defense", "flood", "model", "exfil_exports", "leaked")}
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

st.title("Attacking the Cure — live")
slot = st.empty()

# ----------------------------------------------------------------- drive the view
if mode == "Run live (Groq)" and ss.get("live"):
    live = ss["live"]
    frames = build_frames(list(live["sys"].events))
    frame = frames[-1] if frames else empty_frame()
    done = live["done"] or live["stop"]
    sub = (f"LIVE · defense **{ 'off' if live['sys'].cfg.rules is False else ('budgets' if live['sys'].cfg.budgets else 'on')}** · "
           f"{live['sys'].t} actions · {'finished' if done else 'running…'}")
    with slot.container():
        render(frame, frames[-80:], sub)
    if not done:
        time.sleep(0.6)
        st.rerun()
elif ss.get("frames"):
    frames, i = ss["frames"], ss["idx"]
    i = min(i, len(frames) - 1)
    meta = ss.get("meta", {})
    sub = (f"REPLAY · defense **{meta.get('defense')}** · model `{meta.get('model')}` · "
           f"step {i + 1}/{len(frames)}")
    with slot.container():
        render(frames[i], frames[max(0, i - 80):i + 1], sub)
    nav = st.columns([1, 1, 6])
    if nav[0].button("⏮ Restart"):
        ss["idx"] = 0; ss["playing"] = False; st.rerun()
    if nav[1].button("⏭ End"):
        ss["idx"] = len(frames) - 1; ss["playing"] = False; st.rerun()
    st.slider("Timeline", 0, len(frames) - 1, i, key="scrub",
              on_change=lambda: ss.update(idx=ss["scrub"], playing=False))
    if ss["playing"] and i < len(frames) - 1:
        time.sleep(1 / ss.get("speed", 3))
        ss["idx"] = i + 1
        st.rerun()
    elif ss["playing"]:
        ss["playing"] = False
else:
    slot.info("Pick a saved run and press **Load**, or switch to **Run live** to drive real LLM agents "
              "through the ContainMAS checkpoint.")
