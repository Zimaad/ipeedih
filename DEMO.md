# Live demo guide

## Launch the dashboard

```
.venv\Scripts\streamlit run app.py
```
Opens at http://localhost:8501. Two modes in the left sidebar.

## Mode 1 — Replay saved run (use this in the review; it never fails)

1. Pick `live_off.json`, press **Load / restart**, let it play. Watch the Research agent read a
   **poisoned page**, the taint cross to the Data agent, and **80 customer records get exfiltrated**.
   All four agents stay green — nothing stopped it.
2. Pick `live_on.json`, press **Load / restart**. Same attack, but the export is **blocked**, the
   Research agent turns **yellow/orange**, and **0 records leak**.
3. Use the **Timeline** slider to scrub to any moment while you talk.

Saved runs live in `results/live_*.json`. Record fresh ones any time with:
```
.venv\Scripts\python -m live.run --defense off --out results/live_off.json
.venv\Scripts\python -m live.run --defense on  --out results/live_on.json
```

## Mode 2 — Run live (Groq) — the wow factor, but stochastic

Sidebar → **Run live (Groq)** → choose defense (`off` / `on` / `budgets`) → **Run live episode**.
Real LLM agents drive the tools; the board updates every ~0.6 s. Takes 60–90 s.
Needs internet and a `GROQ_API_KEY` in `.env`. Because LLMs are random, **rehearse and keep the
replays as backup** — if a live run wanders, switch to Replay mode.

## What the board shows

- **Four agent cards**, coloured by privilege state: green NORMAL → yellow GUARDED → orange RESTRICTED → red ISOLATED.
- **Counters:** records exfiltrated (red when > 0), emailed out, actions blocked, heals, items purged.
- **Event log:** poisoned reads, blocks, state changes and heals, colour-coded.

## Talk track (about 3 minutes)

1. *"Four AI agents, one security checkpoint between them and the world."*
2. Replay `off`: *"A single poisoned page, and the whole team leaks customer data. Nobody hacked a server."*
3. Replay `on`: *"Same model, same attack. The only thing added is ContainMAS. The infection is traced, the action blocked, the agent healed."*
4. *"But here's our research question — what if the attacker aims at the healing itself?"* → switch to the pilot figure `results/fig5_probation_tradeoff.png`.

## Safety

Everything is a local sandbox: the "web" is in-memory pages, the database is synthetic, and
"sending email" only appends to a list. Nothing leaves the machine.
