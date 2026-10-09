# ContainMAS: Review deck content (maps 1:1 to the required outline)

Each section = 1-2 slides. **Bold** = put on slide. *Italic* = say out loud. Figures are in `results/`.

---

## 1. Introduction

- **LLM agents now act: they read the web, query databases, send email, and work in teams.**
- **One poisoned web page can turn the whole team against its owner (prompt injection spreading between agents).**
- **Our project, ContainMAS: a checkpoint between every agent and everything it touches. It enforces rules, learns what rules miss, shrinks privileges step by step, and heals the damage.**

*Tell the Section 1 story from the proposal in 30 seconds, then say: "we built it, and here is the same story running." Run `python demo.py` live, or show a screenshot: it leaks 2,050 records without the defense and 0 with it.*

## 2. Literature Review

| Family | Examples | Gap we target |
|---|---|---|
| Rule/capability defenses | CaMeL, FIDES, Progent | Mostly single-agent; no learned detection; **no recovery** |
| Text filters | Prompt Guard-style classifiers | Miss data-only attacks |
| Behaviour ML | TraceAegis, trajectory anomaly detectors | Detect only; no containment or recovery |
| Multi-agent infection | Prompt Infection (LLM-to-LLM) | Shows the attack; no defense-plus-recovery evaluated |
| Benchmarks | AgentDojo, InjecAgent | Static attacks; single agent |

**Gap: nobody we found combines enforce → detect residual → degrade gradually → heal, or tests an attacker who abuses the healing itself.**

*Be honest that this comes from a scoping search, with a full survey in month 1. Reviewers respect that.*

## 3. Problem Statement and Objectives

**Problem:** In multi-agent LLM systems, an injection that passes the rules can spread between agents. Today's response is "block or restart everything", which destroys legitimate work and does not stop re-infection.

**Objectives**
1. Measure what a learned detector adds **beyond** a strong rule layer (residual attacks).
2. Show that graduated privilege degradation keeps more work alive than binary blocking at equal security.
3. Measure team-level spread and time-to-containment with agent-to-agent checks.
4. Use taint (provenance) labels to heal **surgically**, and compare against a restart.
5. Test a **healing-aware attacker** that weaponises the response mechanism.

## 4. Data Analysis

- **Dataset: 50,340 labelled agent actions** (training split) from simulated team episodes: benign plus 5 attacker types. Labels come from simulator ground truth, which the defense never sees.
- **Strict splits:** train seeds 0-39 → detector; validation seeds 100-139 → risk weights and thresholds; test seeds 2000-2059 → reported once.
- **Class balance:** training traces are about 45% malicious (attack episodes are attack-heavy by design), but in real deployments attacks are rare. So we report **recall at a fixed 1% false-positive rate, precision and FPR, not accuracy**.
- **Rules alone flag only ~39% of malicious T1 actions and 0% of T3-T5** (`results/detection.csv`), so most of the attack surface sits outside the rules. This is the "residual" space the ML targets.
- **Figure:** `fig7_dataset.png`, showing trace volume per scenario type and the features that separate attacks from normal work.

*Point out: 22 behaviour features (tool, taint, sensitivity, who requested it, request rates, recipient type, query breadth). The detector never sees content, only behaviour and provenance.*

## 5. Proposed Design

- **Architecture slide:** use the diagram from proposal page 8 (4 agents → checkpoint [rule check → ML detector → risk controller] → allow/restrict/block → self-healing loop).
- **Taint labels:** every item carries the set of sources it came from. Labels propagate through messages, memory and files.
- **Rules (R1-R3):** role capabilities; untrusted data cannot trigger sensitive actions; sensitive data cannot leave to unknown recipients.
- **ML:** Isolation Forest (unsupervised) + gradient-boosted classifier, fused with rule and taint signals by a **learned** logistic risk model: R = σ(wᵀs + b).
- **4 privilege states** with hysteresis: NORMAL → GUARDED → RESTRICTED → ISOLATED.
- **Healing:** trace the flagged action's untrusted roots → infection set = everything carrying that label → purge only that set across all agents → quarantine the source → probation.

## 6. Formulation of Hypothesis

**Pre-registered on 2026-10-08, before any experiment, with a public deviation log** (`HYPOTHESES.md`).

| ID | Hypothesis | Falsified if |
|---|---|---|
| H1 | ML lowers attack success on rule-compliant attacks | not significant, or utility drops > 5 pp |
| H2 | Graduated degradation keeps more work than binary blocking at equal ASR | task success not higher, or ASR differs > 5 pp |
| H3 | Agent-to-agent checks lower spread and containment time | spread not lower |
| H4 | Taint-guided healing beats restart on fidelity at similar re-infection | fidelity not higher, or re-infection > +10 pp |
| H5 | Healing-aware attacker lowers availability; probation bounds the damage | availability falls below 50% of benign, or probation gives no ASR gain |

**Statistics:** paired design (every setup sees identical scenarios); McNemar / Wilcoxon; Holm correction; 95% bootstrap CIs.

## 7. Implementation

- **Python package `containmas`** (~900 lines): provenance DAG, rule layer, ML layer, checkpoint, healing, simulator. One command reproduces every number.
- **9 setups** (A no defense → G full ContainMAS, plus restart / no-probation / binary-blocking baselines).
- **5 attacker types:** T1 naive, T2 data-only, T3 rule-aware, T4 detector-aware, T5 healing-aware.
- **Scale:** 3,240 paired test episodes plus a 720-episode probation sweep.
- **Two-mode methodology:** scripted mode (now) isolates mechanisms from LLM randomness. LLM mode (next) wraps real agents on AgentDojo with a local model via Ollama.
- **Live demo:** `python demo.py` and `python demo.py --attacker T5`.

## 8. Results and Analysis

**Slide A: headline (`fig1_security_utility.png`)**
- No defense: **74%** of attacks succeed. Rules alone: **45%**. Full ContainMAS: **3%**, at the same benign task success as rules alone (0.88).
- Binary blocking is just as secure but **halves useful work (0.48)**.

**Slide B: H1-H4 supported (`fig3_detection.png`, `fig4_healing.png`, `fig6_containment.png`)**
- H1: on rule-compliant attacks, ASR **0.95 → 0.06** with no utility loss.
- H2: graduated vs binary: task success **0.59 vs 0.37** at matched ASR (Δ = 1 pp).
- H3: message checks cut spread **0.53 → 0.31** and median containment time **22 → 5 ticks**.
- H4: taint healing fidelity **0.71 vs 0.43** for restart; re-infection **4% vs 31%**.

**Slide C: the honest part (`fig5_probation_tradeoff.png`)**
- **H5 NOT supported.** The healing-aware attacker halves availability (0.88 → 0.44, ratio 0.49, just under our pre-set 0.50 bound). Probation lowers ASR 0.17 → 0.07, but that is not significant after Holm (p = 0.07).
- **Finding: probation is a lever the attacker can pull.** Longer probation means less re-infection (55% → 5%) but also less availability (0.80 → 0.35). That is a real trade-off, and it sets the next research step: adaptive probation and quarantine budgets.
- Also against us: restart keeps **higher availability under attack (0.81 vs 0.66)**, because it has no probation period. Taint healing wins on fidelity and re-infection, not on uptime.
- Detector generalisation: on unseen attack types recall drops (T4 0.62 → 0.55, T5 0.92 → 0.50), and the data-only attack T2 is **invisible to ML (recall 0)** but caught 100% by rules. **Rules and ML are complementary**, which is the core design argument.

**Limitations (say it before they ask):** pilot numbers come from our own simulator, so they validate the mechanisms, not real-LLM behaviour. Mitigations: leave-one-attacker-out testing, a moved test split (deviation log), and the next phase on AgentDojo with real models.

**Next steps (timeline):** month 1-2: AgentDojo multi-agent wrapper + local LLM; month 3: re-pre-register and run LLM mode; month 4: adaptive T4/T5 against deployed thresholds; month 5+: adaptive probation (fix for the H5 finding).

## 9. References (verify each before the final thesis)

1. Debenedetti et al. *AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents.* NeurIPS Datasets & Benchmarks, 2024.
2. Debenedetti et al. *Defeating Prompt Injections by Design* (CaMeL). arXiv, 2025.
3. Costa et al. *Securing AI Agents with Information-Flow Control* (FIDES). arXiv, 2025.
4. Shi et al. *Progent: Programmable Privilege Control for LLM Agents.* arXiv, 2025.
5. Greshake et al. *Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection.* AISec, 2023.
6. Lee & Tiwari. *Prompt Infection: LLM-to-LLM Prompt Injection within Multi-Agent Systems.* arXiv, 2024.
7. Zhan et al. *InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated LLM Agents.* Findings of ACL, 2024.
8. Liu, Ting & Zhou. *Isolation Forest.* ICDM, 2008.
9. Chen & Guestrin. *XGBoost: A Scalable Tree Boosting System.* KDD, 2016.

---

### Likely reviewer questions: one-line answers

- **"Your detector is near-perfect because you wrote the attacks."** Yes, which is why we held out each attacker type: recall drops to 0.50-0.55 on unseen T4/T5, and we report that. AgentDojo is the external check.
- **"Why not just add a rule for the T3 pattern?"** You can, after the fact. That is our Learn step (human-approved rules). ML catches it *before* someone writes the rule, and LOAO measures how well.
- **"Is self-healing just restarting?"** No. Restart loses 29 good items per heal; we lose 18 and re-infection drops from 31% to 4%. But restart wins on uptime, and we say so.
- **"What's novel?"** Taint-guided surgical recovery across agents, and the healing-aware attacker, which found a real trade-off (H5) that a block-only evaluation would never reveal.
