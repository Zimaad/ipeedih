# ContainMAS pilot results (scripted mode)

Test split: 60 seeds × 6 scenario types × 9 setups = 3240 paired episodes. 95% bootstrap CIs in brackets. Hypotheses were fixed beforehand in `HYPOTHESES.md`.

> These are **pilot** numbers from a deterministic simulator. They show that the mechanisms and the measurement pipeline work. They are not claims about real LLM agents.

## Hypothesis verdicts

| ID | Test | Observed | p | p (Holm) | Verdict |
|---|---|---|---|---|---|
| H1 | McNemar, ASR E vs D on T3+T4 | ASR D=0.95, E=0.06; benign utility D=0.88, E=0.88 | 1.2e-32 | 3.7e-32 | **SUPPORTED** |
| H2 | Wilcoxon, task success F vs F_bin (all episodes) | task success F_bin=0.37, F=0.59; ASR F_bin=0.00, F=0.01 (Δ=+0.01) | 1.5e-40 | 7.3e-40 | **SUPPORTED** |
| H3 | Wilcoxon, spread G_noheal vs F | spread F=0.53, G_noheal=0.31; median TTC F=22, G_noheal=5 ticks | 1.3e-25 | 2.6e-25 | **SUPPORTED** |
| H4 | Wilcoxon, fidelity G vs G_restart (episodes with heals in both) | fidelity restart=0.43, taint=0.71 (n=243); re-infection restart=0.31, taint=0.04 | 1.6e-33 | 6.5e-33 | **SUPPORTED** |
| H5 | McNemar, ASR G vs G_noprob on T5; Wilcoxon availability T5 vs benign | availability benign=0.88, T5=0.44 (ratio 0.49, p=1.6e-11); ASR G_noprob=0.17, G=0.07; re-infection G_noprob=0.55, G=0.11 | 7.0e-02 | 7.0e-02 | **NOT SUPPORTED** |

## Headline: security vs usefulness

| setup | ASR (all attacks) | task success (benign) | availability (under attack) | FPR |
|---|---|---|---|---|
| A | 0.74 [0.69, 0.79] | 1.00 [1.00, 1.00] | 0.93 [0.92, 0.94] | 0.000 |
| D | 0.45 [0.39, 0.50] | 0.88 [0.86, 0.90] | 0.78 [0.77, 0.79] | 0.020 |
| E | 0.02 [0.01, 0.04] | 0.88 [0.86, 0.90] | 0.78 [0.76, 0.79] | 0.020 |
| F_bin | 0.00 [0.00, 0.00] | 0.48 [0.41, 0.55] | 0.27 [0.24, 0.29] | 0.148 |
| F | 0.01 [0.00, 0.02] | 0.88 [0.86, 0.90] | 0.47 [0.44, 0.50] | 0.021 |
| G_noheal | 0.00 [0.00, 0.00] | 0.88 [0.86, 0.90] | 0.48 [0.45, 0.51] | 0.030 |
| G | 0.03 [0.01, 0.05] | 0.88 [0.86, 0.90] | 0.66 [0.64, 0.68] | 0.030 |
| G_restart | 0.02 [0.00, 0.03] | 0.88 [0.86, 0.90] | 0.81 [0.80, 0.82] | 0.030 |
| G_noprob | 0.05 [0.02, 0.07] | 0.88 [0.86, 0.90] | 0.84 [0.83, 0.85] | 0.030 |

![](fig1_security_utility.png)

## Attack success by attacker type

| setup | T1 | T2 | T3 | T4 | T5 |
|---|---|---|---|---|---|
| A | 0.95 | 0.53 | 0.95 | 0.95 | 0.33 |
| D | 0.00 | 0.00 | 0.95 | 0.95 | 0.33 |
| E | 0.00 | 0.00 | 0.00 | 0.12 | 0.00 |
| F_bin | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| F | 0.00 | 0.00 | 0.00 | 0.05 | 0.00 |
| G_noheal | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| G | 0.00 | 0.00 | 0.05 | 0.02 | 0.07 |
| G_restart | 0.00 | 0.00 | 0.05 | 0.02 | 0.02 |
| G_noprob | 0.00 | 0.00 | 0.05 | 0.02 | 0.17 |

![](fig2_asr_heatmap.png)

## Detection: what ML adds beyond rules (RQ1, N2)

| attacker | malicious_actions | recall_rules | recall_rules_plus_ml | residual_actions | residual_recall_ml | precision_rules_plus_ml | fpr_rules | fpr_rules_plus_ml |
|---|---|---|---|---|---|---|---|---|
| T1 | 12678 | 0.39 | 0.96 | 7740.00 | 0.93 | nan | nan | nan |
| T2 | 45 | 1.00 | 1.00 | 0.00 | nan | nan | nan | nan |
| T3 | 10104 | 0.00 | 0.88 | 10104.00 | 0.88 | nan | nan | nan |
| T4 | 2534 | 0.00 | 0.62 | 2534.00 | 0.62 | nan | nan | nan |
| T5 | 11425 | 0.00 | 0.92 | 11425.00 | 0.92 | nan | nan | nan |
| ALL | 36786 | 0.14 | 0.90 | nan | nan | 0.96 | 0.02 | 0.03 |

### Leave-one-attacker-out (RQ5)

| held_out | auc | recall@1%FPR | residual_recall@1%FPR | fpr_test |
|---|---|---|---|---|
| T1 | 1.00 | 0.95 | 0.91 | 0.01 |
| T2 | 0.36 | 0.00 | nan | 0.01 |
| T3 | 0.99 | 0.83 | 0.83 | 0.01 |
| T4 | 0.92 | 0.55 | 0.55 | 0.01 |
| T5 | 0.97 | 0.50 | 0.50 | 0.01 |
| T1 (seen) | 1.00 | 0.97 | 0.95 | 0.01 |
| T2 (seen) | 1.00 | 1.00 | nan | 0.01 |
| T3 (seen) | 0.99 | 0.87 | 0.87 | 0.01 |
| T4 (seen) | 0.98 | 0.62 | 0.62 | 0.01 |
| T5 (seen) | 1.00 | 0.92 | 0.92 | 0.01 |

![](fig3_detection.png)

## Self-healing (RQ4, H4)

| setup | n_heals | fidelity | good_lost | reinfection | recovery |
|---|---|---|---|---|---|
| G | 1.54 | 0.71 | 17.62 | 0.04 | 23.84 |
| G_restart | 3.04 | 0.43 | 29.13 | 0.31 | 0.00 |
| G_noprob | 2.35 | 0.72 | 17.08 | 0.15 | 0.00 |

![](fig4_healing.png)

## Team-level containment (RQ3, H3)
![](fig6_containment.png)

## Healing-aware attacker and probation length (H5)

| setup | availability:T5 | availability:none | attack_success:T5 | attack_success:none | reinfection:T5 | reinfection:none | n_heals:T5 | n_heals:none |
|---|---|---|---|---|---|---|---|---|
| G_m1 | 0.65 | 0.88 | 0.13 | 0.00 | 0.38 | 0.00 | 4.67 | 0.03 |
| G_m12 | 0.35 | 0.88 | 0.02 | 0.00 | 0.05 | 0.00 | 1.53 | 0.07 |
| G_m2 | 0.56 | 0.88 | 0.07 | 0.00 | 0.29 | 0.00 | 3.95 | 0.03 |
| G_m4 | 0.44 | 0.88 | 0.07 | 0.00 | 0.11 | 0.00 | 2.87 | 0.05 |
| G_m8 | 0.37 | 0.88 | 0.03 | 0.00 | 0.07 | 0.00 | 2.15 | 0.05 |
| G_noprob | 0.80 | 0.88 | 0.17 | 0.00 | 0.55 | 0.00 | 5.98 | 0.05 |

![](fig5_probation_tradeoff.png)

## Dataset (training traces)

| attacker | actions | malicious | malicious_share | rule_violations |
|---|---|---|---|---|
| none | 4835 | 0 | 0.00 | 70 |
| T1 | 12265 | 7769 | 0.63 | 3142 |
| T2 | 4835 | 25 | 0.01 | 95 |
| T3 | 10771 | 6023 | 0.56 | 98 |
| T4 | 6040 | 1473 | 0.24 | 92 |
| T5 | 11594 | 7170 | 0.62 | 98 |

![](fig7_dataset.png)

## Fitted risk model (validation split)

```json
{
  "signals": [
    "rule_violation",
    "anomaly",
    "attack_prob",
    "sensitivity",
    "untrusted"
  ],
  "weights": [
    0.3363,
    1.8277,
    8.4056,
    0.1084,
    2.805
  ],
  "bias": -7.8961,
  "thresholds": {
    "guard": 0.3,
    "restrict": 0.9522,
    "isolate": 0.9761,
    "release": 0.24
  }
}
```
