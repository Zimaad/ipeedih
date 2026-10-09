"""Pilot study (scripted mode): traces -> detector -> setups A..G on the held-out test split.

Usage:  python experiments/run_experiments.py [--quick]
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from containmas.defense import SETUPS  # noqa: E402
from containmas.ml import FEATURE_NAMES, SIGNAL_NAMES, fit_detector, fit_models, signals  # noqa: E402
from containmas.scenario import ATTACKERS, make_scenario  # noqa: E402
from containmas.sim import Sim  # noqa: E402

QUICK = "--quick" in sys.argv
N = 10 if QUICK else 40
TRAIN, VAL = range(0, N), range(100, 100 + N)
# Quick mode is for pipeline checks only and uses a separate dev range, never the test split.
TEST = range(500, 515) if QUICK else range(2000, 2060)
KINDS = ("none",) + ATTACKERS
MAIN_SETUPS = ["A", "D", "E", "F_bin", "F", "G_noheal", "G", "G_restart", "G_noprob"]
OUT = ROOT / "results"


def collect(seeds) -> list[dict]:
    """Action traces from the undefended system; labels come from simulator ground truth."""
    rows = []
    for k in KINDS:
        for s in seeds:
            sim = Sim(make_scenario(s, k), SETUPS["A"], log_rows=True)
            sim.run()
            rows += sim.rows
    return rows


def evaluate(models, setups, seeds, kinds=KINDS) -> pd.DataFrame:
    recs = []
    for setup in setups:
        for k in kinds:
            for s in seeds:
                r = Sim(make_scenario(s, k), setup, models).run()
                recs.append({"setup": setup.name, "attacker": k, "seed": s, "m": setup.m,
                             "probation": setup.probation, **r})
    return pd.DataFrame(recs)


def arrays(rows):
    return (np.array([r["x"] for r in rows]), np.array([r["label"] for r in rows]),
            np.array([r["p"] for r in rows]))


def detection_table(models, test_rows) -> pd.DataFrame:
    """Action-level detection: rules alone vs rules + learned risk, per attacker type."""
    S = signals(models.detector, test_rows)
    R = 1 / (1 + np.exp(-(S @ models.w + models.b)))
    _, y, p = arrays(test_rows)
    att = np.array([r["attacker"] for r in test_rows])
    out = []
    for k in ATTACKERS:
        m = (att == k) & (y == 1)
        resid = m & (p == 0)
        out.append({"attacker": k, "malicious_actions": int(m.sum()),
                    "recall_rules": float((p[m] == 1).mean()),
                    "recall_rules_plus_ml": float(((p[m] == 1) | (R[m] >= models.th.restrict)).mean()),
                    "residual_actions": int(resid.sum()),
                    "residual_recall_ml": float((R[resid] >= models.th.restrict).mean()) if resid.any() else np.nan})
    legit = y == 0
    alarms = (p == 1) | (R >= models.th.restrict)
    out.append({"attacker": "ALL", "malicious_actions": int((y == 1).sum()),
                "recall_rules": float((p[y == 1] == 1).mean()),
                "recall_rules_plus_ml": float(alarms[y == 1].mean()),
                "precision_rules_plus_ml": float(y[alarms].mean()),
                "fpr_rules": float((p[legit] == 1).mean()),
                "fpr_rules_plus_ml": float(alarms[legit].mean())})
    return pd.DataFrame(out)


def leave_one_attacker_out(train_rows, val_rows, test_rows) -> pd.DataFrame:
    """Train the detector without one attacker type, test on that unseen type."""
    Xv, yv, _ = arrays(val_rows)
    Xt, yt, pt = arrays(test_rows)
    att = np.array([r["attacker"] for r in test_rows])
    out = []
    for held in ("none",) + ATTACKERS:
        tr = [r for r in train_rows if r["attacker"] != held]
        det = fit_detector(tr)
        thr = float(np.quantile(det.score_many(Xv[yv == 0])[1], .99))
        _, c = det.score_many(Xt)
        if held == "none":   # in-distribution reference: all types seen in training
            continue
        m = att == held
        pos, resid = m & (yt == 1), m & (yt == 1) & (pt == 0)
        out.append({"held_out": held, "auc": roc_auc_score(yt[m], c[m]) if len(set(yt[m])) > 1 else np.nan,
                    "recall@1%FPR": float((c[pos] >= thr).mean()),
                    "residual_recall@1%FPR": float((c[resid] >= thr).mean()) if resid.any() else np.nan,
                    "fpr_test": float((c[(yt == 0)] >= thr).mean())})
    det = fit_detector(train_rows)
    thr = float(np.quantile(det.score_many(Xv[yv == 0])[1], .99))
    _, c = det.score_many(Xt)
    for k in ATTACKERS:
        m = att == k
        pos = m & (yt == 1)
        out.append({"held_out": f"{k} (seen)", "auc": roc_auc_score(yt[m], c[m]),
                    "recall@1%FPR": float((c[pos] >= thr).mean()),
                    "residual_recall@1%FPR": float((c[pos & (pt == 0)] >= thr).mean()),
                    "fpr_test": float((c[yt == 0] >= thr).mean())})
    return pd.DataFrame(out)


def dataset_stats(rows) -> pd.DataFrame:
    X, y, p = arrays(rows)
    att = np.array([r["attacker"] for r in rows])
    by = [{"attacker": k, "actions": int((att == k).sum()),
           "malicious": int(((att == k) & (y == 1)).sum()),
           "malicious_share": float(y[att == k].mean()),
           "rule_violations": int(p[att == k].sum())} for k in KINDS]
    return pd.DataFrame(by)


def main():
    OUT.mkdir(exist_ok=True)
    t0 = time.time()
    print(f"[1/5] collecting traces (train={len(TRAIN)}, val={len(VAL)}, test={len(TEST)} seeds per type)")
    train_rows, val_rows, test_rows = collect(TRAIN), collect(VAL), collect(TEST)
    dataset_stats(train_rows).to_csv(OUT / "dataset_stats.csv", index=False)
    X, y, _ = arrays(train_rows)
    pd.DataFrame({"feature": FEATURE_NAMES, "mean_benign": X[y == 0].mean(0),
                  "mean_malicious": X[y == 1].mean(0)}).to_csv(OUT / "feature_means.csv", index=False)
    np.savez_compressed(OUT / "train_traces.npz", X=X, y=y,
                        attacker=np.array([r["attacker"] for r in train_rows]))

    print(f"[2/5] fitting detector + risk model ({len(train_rows)} train actions)")
    models = fit_models(train_rows, val_rows)
    card = {"signals": SIGNAL_NAMES, "weights": models.w.round(4).tolist(), "bias": round(models.b, 4),
            "thresholds": {k: round(v, 4) for k, v in asdict(models.th).items()}}
    (OUT / "model_card.json").write_text(json.dumps(card, indent=2))
    with open(OUT / "models.pkl", "wb") as f:
        pickle.dump(models, f)
    print("      ", card)

    print("[3/5] detection analysis + leave-one-attacker-out")
    detection_table(models, test_rows).to_csv(OUT / "detection.csv", index=False)
    leave_one_attacker_out(train_rows, val_rows, test_rows).to_csv(OUT / "loao.csv", index=False)

    print(f"[4/5] main evaluation: {len(MAIN_SETUPS)} setups x {len(KINDS)} kinds x {len(TEST)} seeds")
    evaluate(models, [SETUPS[s] for s in MAIN_SETUPS], TEST).to_csv(OUT / "episodes.csv", index=False)

    print("[5/5] probation-length sweep under the healing-aware attacker (T5)")
    sweep = [replace(SETUPS["G"], name=f"G_m{m}", m=m) for m in (1, 2, 4, 8, 12)]
    sweep.append(SETUPS["G_noprob"])
    evaluate(models, sweep, TEST, kinds=("none", "T5")).to_csv(OUT / "msweep.csv", index=False)
    print(f"done in {time.time() - t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main()
