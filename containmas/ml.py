"""Learned layer: behaviour features, anomaly + attack detectors, and the fused risk model."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression

from .core import AGENTS, TOOLS

FEATURE_NAMES = ([f"tool={t}" for t in TOOLS]
                 + ["untrusted", "sensitivity", "user_scheduled", "from_teammate",
                    "origin_db_last10", "origin_public_last10", "origin_msgs_last5",
                    "ticks_since_untrusted", "external_recipient", "breadth"]
                 + [f"role={r}" for r in AGENTS])
SIGNAL_NAMES = ["rule_violation", "anomaly", "attack_prob", "sensitivity", "untrusted"]


def featurize(sim, agent, step, tool, untrusted, sens, external, args) -> tuple:
    """Features the defense can see at decision time. Discrete on purpose, so scores cache well."""
    t = sim.t
    origin = step.origin if step.origin in sim.agents else agent.name
    h = sim.recent(origin)
    db10 = sum(1 for tt, tl in h if t - tt < 10 and tl.startswith("db_"))
    pub10 = sum(1 for tt, tl in h if t - tt < 10 and tl == "write_public")
    msg5 = sum(1 for tt, tl in h if t - tt < 5 and tl == "send_msg")
    return tuple(
        [1.0 if tool == tl else 0.0 for tl in TOOLS]
        + [float(untrusted), sens / 2, float(step.task is not None and step.origin == "user"),
           float(step.origin not in ("user", agent.name)), min(db10, 8), min(pub10, 8),
           min(msg5, 8), min(20, t - agent.last_untrusted), float(external),
           min(args.get("n", 0), 10)]
        + [1.0 if agent.name == r else 0.0 for r in AGENTS])


class Detector:
    """Isolation Forest (unsupervised, trained on normal work) + boosted classifier (supervised)."""

    def __init__(self, iforest, clf, lo, hi):
        self.iforest, self.clf, self.lo, self.hi = iforest, clf, lo, hi
        self._cache: dict = {}

    def score(self, x: tuple) -> tuple[float, float]:
        if x not in self._cache:
            raw = -self.iforest.score_samples([x])[0]
            a = min(1.0, max(0.0, (raw - self.lo) / (self.hi - self.lo + 1e-9)))
            c = float(self.clf.predict_proba([x])[0, 1])
            self._cache[x] = (a, c)
        return self._cache[x]

    def score_many(self, X) -> tuple[np.ndarray, np.ndarray]:
        raw = -self.iforest.score_samples(X)
        a = np.clip((raw - self.lo) / (self.hi - self.lo + 1e-9), 0, 1)
        return a, self.clf.predict_proba(X)[:, 1]


@dataclass
class Thresholds:
    guard: float      # NORMAL -> GUARDED, and stricter blocking once GUARDED
    restrict: float   # GUARDED -> RESTRICTED, and the block threshold in NORMAL
    isolate: float    # RESTRICTED -> ISOLATED
    release: float    # an action below this counts toward probation


@dataclass
class Models:
    detector: Detector
    w: np.ndarray
    b: float
    th: Thresholds

    def risk(self, s) -> float:
        z = float(np.dot(self.w, s) + self.b)
        return 1 / (1 + math.exp(-z))


def fit_detector(rows: list[dict]) -> Detector:
    X = np.array([r["x"] for r in rows])
    y = np.array([r["label"] for r in rows])
    benign = X[y == 0]
    iforest = IsolationForest(n_estimators=150, random_state=0).fit(benign)
    raw = -iforest.score_samples(benign)
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=.1,
                                         class_weight="balanced", random_state=0).fit(X, y)
    return Detector(iforest, clf, float(np.median(raw)), float(np.quantile(raw, .995)))


def signals(det: Detector, rows: list[dict]) -> np.ndarray:
    X = np.array([r["x"] for r in rows])
    a, c = det.score_many(X)
    p = np.array([r["p"] for r in rows])
    d = X[:, FEATURE_NAMES.index("sensitivity")]
    q = X[:, FEATURE_NAMES.index("untrusted")]
    return np.column_stack([p, a, c, d, q])


def fit_models(train_rows: list[dict], val_rows: list[dict]) -> Models:
    """Detector on train; risk weights and every threshold on validation (never on test)."""
    det = fit_detector(train_rows)
    S = signals(det, val_rows)
    y = np.array([r["label"] for r in val_rows])
    lr = LogisticRegression(class_weight="balanced", max_iter=1000).fit(S, y)
    w, b = lr.coef_[0], float(lr.intercept_[0])
    R = 1 / (1 + np.exp(-(S @ w + b)))
    # Thresholds from the risk of legitimate, rule-compliant validation actions.
    legit = R[(y == 0) & (S[:, 0] == 0)]
    restrict = float(max(.5, np.quantile(legit, .99)))
    guard = float(min(restrict - .05, max(.3, np.quantile(legit, .95))))
    th = Thresholds(guard=guard, restrict=restrict,
                    isolate=restrict + (1 - restrict) / 2, release=guard * .8)
    return Models(det, w, b, th)
