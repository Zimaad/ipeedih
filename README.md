# ContainMAS

Taint-guided containment and self-healing for multi-agent LLM systems.

This repository holds the **pilot implementation** in scripted-agent mode: a deterministic simulator of a
4-agent team (Research, Data, Analysis, Comms) where every tool call and agent-to-agent message passes
through the ContainMAS checkpoint.

## Quick start

```bash
py -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python experiments/run_experiments.py   # ~20 min: traces -> detector -> setups A..G
.venv/Scripts/python experiments/analyze.py           # stats, hypothesis verdicts, figures -> results/
.venv/Scripts/python demo.py                          # replay of the Section 1 attack story
.venv/Scripts/python demo.py --attacker T5            # healing-aware attacker
```

## Layout

| Path | What it is |
|---|---|
| `containmas/core.py` | Provenance-labelled `Item`s in a DAG (`Store`), `Agent`, `Step`, privilege `State`s |
| `containmas/policy.py` | Rule layer: R1 capability, R2 untrusted-to-sensitive control flow, R3 data flow |
| `containmas/ml.py` | Behaviour features, Isolation Forest + boosted classifier, logistic risk fusion, thresholds |
| `containmas/defense.py` | The checkpoint: rule → ML → risk controller → allow/restrict/block, setups A..G |
| `containmas/healing.py` | Trace → infection set → purge → quarantine source → probation; restart baseline |
| `containmas/scenario.py` | Seeded user workload, attacker types T1..T5 |
| `containmas/sim.py` | The simulator loop and all ground-truth metrics |
| `experiments/run_experiments.py` | Pre-registered splits; main evaluation, leave-one-attacker-out, probation sweep |
| `experiments/analyze.py` | Bootstrap CIs, McNemar / Wilcoxon, Holm, verdicts, figures, `results/RESULTS.md` |
| `HYPOTHESES.md` | Pre-registered hypotheses, pass targets and a deviation log |

## How the defense sees the world

- Every item carries **taint labels**: the set of sources it was derived from. Labels propagate to everything
  derived from the item: messages, reports, memory notes and files. `web:*` sources are untrusted.
- The defense **never** reads ground truth (`gt_attack`, `payload`). Those fields exist only to score outcomes.
- **Healing:** take the untrusted roots in the provenance of the flagged action. The infection set is every
  live item whose label contains a root. Purge exactly that set across all agents, quarantine the root, and
  put the agent on probation (privileges return one level per `m` clean actions).

## Roadmap

1. **Scripted mode (this):** mechanisms, metrics and statistics pipeline. Done.
2. **LLM mode:** the same checkpoint wrapped around real agents (Ollama local model) on AgentDojo suites.
   Re-pre-register before running.
3. **Adaptive attacks:** T4/T5 tuned against the deployed thresholds.
