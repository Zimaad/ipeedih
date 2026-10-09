# Attacking the Cure — review deck content (maps 1:1 to the required outline)

**The project is the attack idea.** Not "we built a defense," but: *the automated **response** to an attack
(quarantine, taint-purge, privilege recovery) is itself an exploitable attack surface in multi-agent LLM
systems.* The defense we built (ContainMAS) is only the **testbed** we attack.

**Bold** = goes on the slide. *Italic* = say out loud. Figures are in `results/`.

**One-line thesis:**
> *"Automated agent defenses assume that once an attack is detected, responding to it is safe. We show the
> response is a new attack surface — an attacker can turn quarantine, purge and recovery into denial-of-service
> and data-destruction primitives — and we bound the damage."*

---

## 1. Introduction

- **AI agents now act in teams — they read the web, query databases, send email.** A poisoned page can spread agent to agent (prompt injection).
- **So defenses are getting active:** detect the attack, then **respond automatically** — quarantine the agent, purge contaminated data, restore trust gradually.
- **Our observation:** every one of those responses can be *triggered on purpose*. If tripping the alarm is cheap, the attacker doesn't need to beat the defense — they make the defense hurt the system.
- **This is "Attacking the Cure": response-path attacks on automated containment and recovery.**

*One sentence of context: to study this we needed a self-healing multi-agent defense to attack. None was standard, so we built one (ContainMAS) as our testbed.*

## 2. Literature Review

| What prior work does | Examples | What it assumes / misses |
|---|---|---|
| Detect & block prompt injection | CaMeL, FIDES, Progent | Single-agent; **assumes the response is safe once it fires** |
| Learn anomalous agent behaviour | TraceAegis, trajectory detectors | Detection only; no recovery to attack |
| Multi-agent infection | Prompt Infection (LLM-to-LLM) | Shows spread; no defended+recovering team |
| **Attack the defense** | Guardrail-DoS: "Double-Edged Sword" (2410.02916), "From Shield to Target" (2606.14517) | **Attack one *detector* — not the quarantine/purge/recovery pipeline, and not multi-agent** |
| Recovery for agents | semantic rollback (2607.09748), MemAudit (2605.23723) | Recovery exists; **its abuse by an attacker is untested** |

**The gap:** prior "attack the defense" work jams a single guardrail. **Nobody has asked whether the automated
*recovery* in a multi-agent team can be weaponised, nor bounded the resulting damage.** (Full survey = month 1.)

## 3. Problem Statement and Objectives

**Problem.** In a defended agent team, detection triggers an automatic response. An attacker who understands the
response can aim at *it* instead of the data:
- **Quarantine flooding** → cheap suspicious inputs keep taking agents offline → denial of service.
- **Taint bombing** → make malicious content touch lots of good state, so the provenance-purge destroys legitimate work.
- **Probation re-attack** → strike again during trust restoration, forcing an endless recover-reattack cycle.

**Objectives (the thesis).**
1. Define a **threat model and taxonomy** of response-path attacks on multi-agent recovery.
2. **Measure the damage**: availability loss, Recovery Collateral Damage (RCD), re-infection.
3. Build a **response that resists abuse** — containment budgets — and prove a **bound** on availability loss.
4. Show it **generalises** across recovery strategies, models and a public benchmark.

## 4. Data Analysis

*(Framed around the attack experiments, not the defense.)*
- **Experimental corpus:** 3,240 pre-registered attack/defense episodes + ~50k labelled agent actions, across 5 attacker types, strict train/val/test splits, ground truth the defense never sees.
- **Why the response matters at all:** rules alone catch only ~39% of the naive attack and **0%** of the stealthy ones (`detection.csv`) — so systems *must* lean on detection + automated response, which is exactly the surface we attack.
- **New metric we introduce — Recovery Collateral Damage (RCD):** legitimate state destroyed by the response ÷ total legitimate state. This is the quantity an attacker tries to maximise.
- Rare-event data → we report **recall at fixed FPR, RCD, availability**, not accuracy.
- **Figure:** `fig7_dataset.png`.

## 5. Proposed Design

- **Threat model slide (lead here):** attacker controls external content (web pages, docs), can retry, and **knows the defense's response policy** — but cannot touch code, logs or checkpoints. Goal = availability loss / collateral damage, not (only) data theft.
- **The three attack primitives** (diagram): flooding → quarantine; taint-bomb → purge; re-attack → probation.
- **The testbed (ContainMAS), shown as instrument:** 4 agents → checkpoint (taint → rules → risk → privilege states) → **response controller (quarantine / purge / probation)**. Circle the response controller: *"this box is what we attack."*
- **The defense contribution — containment budgets:** every untrusted source gets a budget of disruption; once spent, further alarms escalate to *cheap* responses (block the source at the input, keep agents online) instead of repeatedly taking agents offline. This is what bounds availability loss.

## 6. Formulation of Hypothesis

**Pre-registered in `HYPOTHESES.md` before experiments, with a deviation log.** *(Attack hypotheses lead; testbed-validation ones are support.)*

| ID | Hypothesis | Status |
|---|---|---|
| **A1** | **A healing-aware attacker measurably lowers availability by triggering the response** | **SHOWN — availability 0.88 → 0.44 (halved)** |
| **A2** | Probation creates a re-attack window: shorter probation ⇒ more re-infection | **SHOWN — re-infection 5% → 55% as probation shrinks** |
| A3 | Taint-bombing inflates RCD (purge destroys good work) | to run (next) |
| **D1 (H6)** | **Containment budgets hold availability ≥ 70% of benign under flooding, with attack success up ≤ 5 pp** | to pre-register & run |
| — | *Support: the testbed is a strong, representative defense* (rules+ML cut ASR 74%→3%; taint-heal beats restart) | SHOWN |

*Key point: A1/A2 mean the attack is already real on a strong defense. The thesis is A3 + the bound (D1).*

## 7. Implementation

- **Testbed** (`containmas/`, ~865 lines): taint DAG, rules, ML detector, 4 privilege states, self-healing. 3,240 pre-registered episodes.
- **Live attack demo** (`live/` + `app.py`): 4 **real LLM agents** (Groq `gpt-oss-20b`), **fully sandboxed** (local fake web/DB, email to a file — nothing leaves the machine), all routed through the checkpoint. **Streamlit dashboard** animates the attack and the response live.
- **Attacks built:** quarantine flooding (decoys), probation re-attack. **Defense built:** containment budgets (toggle).
- **Live demo (~90s, or replay):** `--defense off` → real agents exfiltrate **40-80 records**; `--defense on` → **0**, blocked + healed. Then flip to the attack on the healing itself.

## 8. Results and Analysis

**Slide A — the attack is real (headline).** `fig5_probation_tradeoff.png`
- **A healing-aware attacker halves availability (0.88 → 0.44) by weaponising the response** — no data theft needed.
- **The trade-off is structural:** longer probation cuts re-infection (55% → 5%) but cuts availability (0.80 → 0.35). *No fixed response policy wins — which is why an adaptive, budgeted response is needed.*

**Slide B — it's an attack on a *strong* defense (so it counts).** `fig1`, `fig4`
- The testbed is not a strawman: rules+ML cut attack success **74% → 3%**; taint-healing beats restart (fidelity 0.71 vs 0.43; re-infection 4% vs 31%; ~18 vs ~29 good items lost per heal → **RCD is real**).
- *Even this strong defense is turned against itself — that's the point.*

**Slide C — live proof with real LLMs.** `results/live_off.json`, `live_on.json`
- Off: real agents leak 40-80 customer records from one poisoned page. On: 0, contained and healed. *The cure works — which is exactly why attacking it matters.*

**Limitations (say first):** results are on our own testbed and one model; A3 and the bound are the thesis, not done. Mitigations: pre-registration, leave-one-attacker-out, and AgentDojo + a second model next.

**Next steps → the thesis:** M1-2 taxonomy + AgentDojo testbed; M3 taint-bombing + RCD at scale (A3); M4 containment budgets + **formal availability bound** (D1); M5+ cross-model/benchmark; paper target: a security workshop (AISec/SaTML) then a venue like DSN/ESORICS.

## 9. References (verify each before the final thesis)

1. Zhang, Xiong & Mao. *LLM Safeguard is a Double-Edged Sword: Exploiting False Positives for DoS.* ACM CCS, 2025.
2. *From Shield to Target: Denial-of-Service Attacks on LLM-Based Agent Guardrails.* arXiv 2606.14517, 2026.
3. *Replicating Belief, Not Bits: Epistemic State Replication (semantic rollback).* arXiv 2607.09748, 2026.
4. *From Agent Traces to Trust: survey of execution provenance in LLM agents.* arXiv 2606.04990, 2026.
5. Debenedetti et al. *AgentDojo.* NeurIPS D&B, 2024.
6. Debenedetti et al. *Defeating Prompt Injections by Design (CaMeL).* arXiv, 2025.
7. Costa et al. *Securing AI Agents with Information-Flow Control (FIDES).* arXiv, 2025.
8. Lee & Tiwari. *Prompt Infection: LLM-to-LLM Prompt Injection in Multi-Agent Systems.* arXiv, 2024.
9. Greshake et al. *Not What You've Signed Up For (Indirect Prompt Injection).* AISec, 2023.
10. *MemAudit: Post-hoc Auditing of Poisoned Agent Memory.* arXiv 2605.23723, 2026.

---

### Likely panel questions — one-line answers

- **"So did you build a defense or an attack?"** The project is the attack. We built a representative defense only so there's something real to attack and measure.
- **"What's actually done vs. proposed?"** Done: the testbed, a 3,240-episode study, a live LLM demo, and two working response-path attacks (A1 availability halved, A2 re-attack window). Proposed: taint-bombing (A3) and the bounded-budget defense (D1).
- **"Why is this a research project, not engineering?"** A defense answers one question; this opens a family — a taxonomy, a new metric (RCD), a provable bound, and a new defense class. That's the mobility.
- **"Isn't attacking guardrails already done?"** For a single detector, yes. The multi-agent *recovery* pipeline — quarantine, purge, probation — is unstudied, and that's our surface.
- **"Is the live demo safe?"** Fully sandboxed; nothing leaves the laptop.
