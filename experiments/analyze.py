"""Statistics, hypothesis verdicts and figures from results/*.csv -> results/RESULTS.md + results/fig*.png"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.stats import binomtest, wilcoxon  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
RNG = np.random.default_rng(0)
ATT = ["T1", "T2", "T3", "T4", "T5"]
ORDER = ["A", "D", "E", "F_bin", "F", "G_noheal", "G", "G_restart", "G_noprob"]

# palette (reference instance): categorical slots 1-2, text tokens, surface
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": .8,
    "axes.spines.top": False, "axes.spines.right": False, "font.size": 11,
    "axes.titleweight": "bold", "axes.titlesize": 13, "axes.titlelocation": "left",
})


# ------------------------------------------------------------------ statistics
def ci(x, n=10000):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return np.nan, np.nan, np.nan
    means = x[RNG.integers(0, len(x), (n, len(x)))].mean(1)
    return x.mean(), *np.quantile(means, [.025, .975])


def fmt(x, n=10000):
    m, lo, hi = ci(x, n)
    return "n/a" if np.isnan(m) else f"{m:.2f} [{lo:.2f}, {hi:.2f}]"


def paired(df, a, b, metric, kinds):
    """Pair two setups on identical scenarios (attacker, seed)."""
    sub = df[df.attacker.isin(kinds)]
    pa = sub[sub.setup == a].set_index(["attacker", "seed"])[metric]
    pb = sub[sub.setup == b].set_index(["attacker", "seed"])[metric]
    j = pd.concat([pa.rename("a"), pb.rename("b")], axis=1).dropna()
    return j.a.to_numpy(), j.b.to_numpy()


def mcnemar(a, b):
    """Exact McNemar. Returns p for 'a has fewer successes than b' (two-sided)."""
    n01, n10 = int(((a == 0) & (b == 1)).sum()), int(((a == 1) & (b == 0)).sum())
    return binomtest(n10, n01 + n10, .5).pvalue if n01 + n10 else 1.0


def wilc(a, b):
    d = a - b
    return 1.0 if np.allclose(d, 0) else float(wilcoxon(a, b).pvalue)


def holm(ps: dict) -> dict:
    keys = sorted(ps, key=ps.get)
    out, running = {}, 0.0
    for i, k in enumerate(keys):
        running = max(running, min(1.0, ps[k] * (len(keys) - i)))
        out[k] = running
    return out


# ------------------------------------------------------------------ hypotheses
def hypotheses(e):
    att = [k for k in ATT]
    res, raw = {}, {}

    a, b = paired(e, "E", "D", "attack_success", ["T3", "T4"])
    ua, ub = paired(e, "E", "D", "task_success", ["none"])
    raw["H1"] = mcnemar(a, b)
    res["H1"] = dict(test="McNemar, ASR E vs D on T3+T4",
                     obs=f"ASR D={b.mean():.2f}, E={a.mean():.2f}; benign utility D={ub.mean():.2f}, E={ua.mean():.2f}",
                     cond=lambda p, a=a, b=b, ua=ua, ub=ub: a.mean() < b.mean() and p < .05 and (ub.mean() - ua.mean()) <= .05)

    a, b = paired(e, "F", "F_bin", "task_success", ["none"] + att)
    sa, sb = paired(e, "F", "F_bin", "attack_success", att)
    raw["H2"] = wilc(a, b)
    res["H2"] = dict(test="Wilcoxon, task success F vs F_bin (all episodes)",
                     obs=f"task success F_bin={b.mean():.2f}, F={a.mean():.2f}; ASR F_bin={sb.mean():.2f}, F={sa.mean():.2f} (Δ={sa.mean() - sb.mean():+.2f})",
                     cond=lambda p, a=a, b=b, sa=sa, sb=sb: a.mean() > b.mean() and p < .05 and abs(sa.mean() - sb.mean()) <= .05)

    a, b = paired(e, "G_noheal", "F", "spread", att)
    ta, tb = paired(e, "G_noheal", "F", "ttc", att)
    raw["H3"] = wilc(a, b)
    res["H3"] = dict(test="Wilcoxon, spread G_noheal vs F",
                     obs=f"spread F={b.mean():.2f}, G_noheal={a.mean():.2f}; median TTC F={np.median(tb):.0f}, G_noheal={np.median(ta):.0f} ticks",
                     cond=lambda p, a=a, b=b, ta=ta, tb=tb: a.mean() < b.mean() and p < .05 and np.median(ta) <= np.median(tb))

    a, b = paired(e, "G", "G_restart", "fidelity", att)
    ra, rb = paired(e, "G", "G_restart", "reinfection", att)
    raw["H4"] = wilc(a, b)
    res["H4"] = dict(test="Wilcoxon, fidelity G vs G_restart (episodes with heals in both)",
                     obs=f"fidelity restart={b.mean():.2f}, taint={a.mean():.2f} (n={len(a)}); re-infection restart={rb.mean():.2f}, taint={ra.mean():.2f}",
                     cond=lambda p, a=a, b=b, ra=ra, rb=rb: a.mean() > b.mean() and p < .05 and (ra.mean() - rb.mean()) <= .10)

    sg, snp = paired(e, "G", "G_noprob", "attack_success", ["T5"])
    av5 = e[(e.setup == "G") & (e.attacker == "T5")].sort_values("seed").availability.to_numpy()
    av0 = e[(e.setup == "G") & (e.attacker == "none")].sort_values("seed").availability.to_numpy()
    rg, rnp = paired(e, "G", "G_noprob", "reinfection", ["T5"])
    raw["H5"] = mcnemar(sg, snp)
    p_av = wilc(av5, av0)
    res["H5"] = dict(test="McNemar, ASR G vs G_noprob on T5; Wilcoxon availability T5 vs benign",
                     obs=(f"availability benign={av0.mean():.2f}, T5={av5.mean():.2f} (ratio {av5.mean() / av0.mean():.2f}, p={p_av:.1e}); "
                          f"ASR G_noprob={snp.mean():.2f}, G={sg.mean():.2f}; re-infection G_noprob={rnp.mean():.2f}, G={rg.mean():.2f}"),
                     cond=lambda p: p_av < .05 and av5.mean() < av0.mean() and sg.mean() < snp.mean()
                     and av5.mean() >= .5 * av0.mean())

    adj = holm(raw)
    for h in res:
        res[h]["p"], res[h]["p_holm"] = raw[h], adj[h]
        res[h]["verdict"] = "SUPPORTED" if res[h]["cond"](adj[h]) else "NOT SUPPORTED"
    return res


# ------------------------------------------------------------------ figures
def save(fig, name):
    fig.tight_layout()
    fig.savefig(RES / name, dpi=180)
    plt.close(fig)


def fig_security_utility(e):
    fig, ax = plt.subplots(figsize=(8, 5.6))
    pts = {}
    for s in ORDER:
        u = ci(e[(e.setup == s) & (e.attacker == "none")].task_success)
        r = ci(e[(e.setup == s) & (e.attacker != "none")].attack_success)
        ours = s.startswith("G") or s.startswith("F")
        col = BLUE if s == "G" else (INK2 if ours else MUTED)
        ax.errorbar(u[0], r[0], xerr=[[u[0] - u[1]], [u[2] - u[0]]], yerr=[[r[0] - r[1]], [r[2] - r[0]]],
                    fmt="o", ms=9 if s == "G" else 7, color=col, ecolor=GRID, elinewidth=2, capsize=0,
                    markeredgecolor=SURF, markeredgewidth=2, zorder=3)
        pts[s] = (u[0], r[0])
    # direct labels; the tight cluster of graduated variants gets a stacked column with leader lines
    cluster = sorted([s for s, (x, y) in pts.items() if x > .8 and y < .15], key=lambda s: -pts[s][1])
    for s, (x, y) in pts.items():
        style = dict(color=INK if s == "G" else INK2, fontweight="bold" if s == "G" else "normal")
        if s in cluster:
            ty = .36 - .055 * cluster.index(s)
            ax.annotate(s + ("  (full ContainMAS)" if s == "G" else ""), (x, y), xytext=(.66, ty),
                        textcoords="data", va="center",
                        arrowprops=dict(arrowstyle="-", color=GRID, lw=1, shrinkB=5), **style)
        else:
            ax.annotate(s, (x, y), xytext=(8, 4), textcoords="offset points", **style)
    ax.set_xlabel("Legitimate task success, benign episodes  →  better")
    ax.set_ylabel("Attack success rate, all attacker types  ↓  better")
    ax.set_title("Security vs. usefulness across setups (95% CI)")
    ax.set_ylim(-.03, max(.75, ax.get_ylim()[1]))
    save(fig, "fig1_security_utility.png")


def fig_asr_heatmap(e):
    m = e[e.attacker != "none"].pivot_table(index="setup", columns="attacker", values="attack_success").loc[ORDER, ATT]
    fig, ax = plt.subplots(figsize=(7, 5.6))
    ax.imshow(m.values, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    ax.grid(False)
    ax.set_xticks(range(len(ATT)), ATT)
    ax.set_yticks(range(len(ORDER)), ORDER)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", color=SURF if v > .55 else INK, fontsize=10)
    ax.set_title("Attack success rate by setup and attacker type")
    ax.set_xlabel("T1 naive · T2 data-only · T3 rule-aware · T4 detector-aware · T5 healing-aware", fontsize=9)
    save(fig, "fig2_asr_heatmap.png")


def fig_detection(det, loao):
    d = det[det.attacker.isin(ATT)]
    x = np.arange(len(d))
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    ax = axes[0]
    ax.bar(x - .2, d.recall_rules, .38, color=MUTED, label="Rules only")
    ax.bar(x + .2, d.recall_rules_plus_ml, .38, color=BLUE, label="Rules + ML")
    ax.set_xticks(x, d.attacker)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Recall on malicious actions")
    ax.set_title("What ML adds on top of rules (RQ1)")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(.5, -.1), ncol=2)
    for xi, v in zip(x, d.recall_rules):
        if v == 0:
            ax.text(xi - .2, .02, "0", ha="center", color=INK2, fontsize=9)
    ax = axes[1]
    l_ = loao[~loao.held_out.str.contains("seen")]
    seen = loao[loao.held_out.str.contains("seen")]
    ax.bar(x - .2, seen["recall@1%FPR"].to_numpy(), .38, color=MUTED, label="Type seen in training")
    ax.bar(x + .2, l_["recall@1%FPR"].to_numpy(), .38, color=ORANGE, label="Type held out (unseen)")
    ax.set_xticks(x, ATT)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Detector recall at 1% FPR")
    ax.set_title("Generalisation to unseen attack types (RQ5)")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(.5, -.1), ncol=2)
    for xi, v in zip(x, l_["recall@1%FPR"].to_numpy()):
        if v == 0:
            ax.text(xi + .2, .02, "0", ha="center", color=INK2, fontsize=9)
    save(fig, "fig3_detection.png")


def fig_healing(e):
    a = e[(e.attacker != "none") & (e.n_heals > 0)]
    setups = ["G_restart", "G", "G_noprob"]
    labels = ["Restart\neverything", "Taint-guided\n(ours)", "Taint-guided,\nno probation"]
    metrics = [("fidelity", "Restoration fidelity ↑"), ("good_lost", "Good items lost per heal ↓"),
               ("reinfection", "Re-infection rate ↓")]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    for ax, (m, title) in zip(axes, metrics):
        vals = [ci(a[a.setup == s][m]) for s in setups]
        ax.bar(range(3), [v[0] for v in vals], .6, color=[MUTED, BLUE, AQUA],
               yerr=[[v[0] - v[1] for v in vals], [v[2] - v[0] for v in vals]], ecolor=INK2, capsize=3)
        ax.set_xticks(range(3), labels, fontsize=9)
        ax.set_title(title, fontsize=12)
    fig.suptitle("Self-healing: taint-guided purge vs restart (RQ4)", x=.01, ha="left", fontweight="bold")
    save(fig, "fig4_healing.png")


def fig_probation(sw):
    sw = sw.copy()
    sw["m_val"] = np.where(sw.setup == "G_noprob", 0, sw.m)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    ax = axes[0]
    for kind, col, lab in [("none", MUTED, "Benign"), ("T5", ORANGE, "Under healing-aware attack (T5)")]:
        g = sw[sw.attacker == kind].groupby("m_val").availability
        mean = g.mean()
        ax.plot(mean.index, mean.values, "-o", color=col, lw=2, ms=8, label=lab,
                markeredgecolor=SURF, markeredgewidth=2)
    ax.set_xlabel("Probation length m (0 = no probation)")
    ax.set_ylabel("Availability")
    ax.set_ylim(0, 1)
    ax.set_title("Probation is a lever the attacker can pull")
    ax.legend(frameon=False, loc="lower left")
    ax = axes[1]
    g = sw[sw.attacker == "T5"].groupby("m_val").reinfection.mean()
    ax.plot(g.index, g.values, "-o", color=BLUE, lw=2, ms=8, markeredgecolor=SURF, markeredgewidth=2)
    ax.set_xlabel("Probation length m (0 = no probation)")
    ax.set_ylabel("Re-infection rate under T5")
    ax.set_ylim(0, max(.6, g.max() * 1.15))
    ax.set_title("...but it bounds re-infection")
    save(fig, "fig5_probation_tradeoff.png")


def fig_containment(e):
    a = e[e.attacker.isin(["T1", "T3", "T4"])]
    setups = ["F", "G_noheal", "G"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, (m, title) in zip(axes, [("spread", "Spread (share of agents infected) ↓"),
                                     ("ttc", "Time to containment, ticks ↓")]):
        vals = [ci(a[a.setup == s][m]) for s in setups]
        ax.bar(range(3), [v[0] for v in vals], .6, color=[MUTED, INK2, BLUE],
               yerr=[[v[0] - v[1] for v in vals], [v[2] - v[0] for v in vals]], ecolor=INK2, capsize=3)
        ax.set_xticks(range(3), ["F\n(graduated)", "G_noheal\n(+msg checks)", "G\n(+healing)"], fontsize=9)
        ax.set_title(title, fontsize=12)
    fig.suptitle("Team-level protection (RQ3), T1/T3/T4 episodes", x=.01, ha="left", fontweight="bold")
    save(fig, "fig6_containment.png")


def fig_data(ds, fm):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    ax = axes[0]
    ax.bar(ds.attacker, ds.actions, .6, color=MUTED, label="All actions")
    ax.bar(ds.attacker, ds.malicious, .6, color=ORANGE, label="Malicious actions")
    ax.set_title("Training traces per scenario type")
    ax.set_ylabel("Actions")
    ax.legend(frameon=False)
    ax = axes[1]
    fm = fm.assign(diff=fm.mean_malicious - fm.mean_benign)
    top = fm.reindex(fm["diff"].abs().sort_values(ascending=False).index).head(8)[::-1]
    ax.barh(top.feature, top["diff"], color=[BLUE if v > 0 else MUTED for v in top["diff"]])
    ax.axvline(0, color=INK2, lw=1)
    ax.set_title("Features that separate attacks from normal work")
    ax.set_xlabel("Mean (malicious) − mean (benign)")
    save(fig, "fig7_dataset.png")


# ------------------------------------------------------------------ report
def table(df):
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(f"{v:.2f}" if isinstance(v, float) else str(v) for v in r) + " |")
    return "\n".join(out)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    e = pd.read_csv(RES / "episodes.csv")
    sw = pd.read_csv(RES / "msweep.csv")
    det, loao = pd.read_csv(RES / "detection.csv"), pd.read_csv(RES / "loao.csv")
    ds, fm = pd.read_csv(RES / "dataset_stats.csv"), pd.read_csv(RES / "feature_means.csv")
    card = json.loads((RES / "model_card.json").read_text())

    fig_security_utility(e); fig_asr_heatmap(e); fig_detection(det, loao)
    fig_healing(e); fig_probation(sw); fig_containment(e); fig_data(ds, fm)

    H = hypotheses(e)
    att = e[e.attacker != "none"]
    ben = e[e.attacker == "none"]
    main_rows = []
    for s in ORDER:
        main_rows.append({"setup": s,
                          "ASR (all attacks)": fmt(att[att.setup == s].attack_success, 2000),
                          "task success (benign)": fmt(ben[ben.setup == s].task_success, 2000),
                          "availability (under attack)": fmt(att[att.setup == s].availability, 2000),
                          "FPR": f"{ben[ben.setup == s].fpr.mean():.3f}"})
    asr = att.pivot_table(index="setup", columns="attacker", values="attack_success").loc[ORDER].reset_index()
    heal = att[att.n_heals > 0].groupby("setup")[["n_heals", "fidelity", "good_lost", "reinfection", "recovery"]] \
        .mean().reindex(["G", "G_restart", "G_noprob"]).reset_index()
    swt = sw.groupby(["setup", "attacker"])[["availability", "attack_success", "reinfection", "n_heals"]] \
        .mean().unstack("attacker").round(2)
    swt.columns = [f"{a}:{b}" for a, b in swt.columns]

    n_seeds = e.seed.nunique()
    md = [f"# ContainMAS pilot results (scripted mode)\n",
          f"Test split: {n_seeds} seeds × {e.attacker.nunique()} scenario types × {len(ORDER)} setups "
          f"= {len(e)} paired episodes. 95% bootstrap CIs in brackets. Hypotheses were fixed beforehand in `HYPOTHESES.md`.\n",
          "> These are **pilot** numbers from a deterministic simulator. They show that the mechanisms and the measurement "
          "pipeline work. They are not claims about real LLM agents.\n",
          "## Hypothesis verdicts\n",
          "| ID | Test | Observed | p | p (Holm) | Verdict |", "|---|---|---|---|---|---|"]
    for h, r in H.items():
        md.append(f"| {h} | {r['test']} | {r['obs']} | {r['p']:.1e} | {r['p_holm']:.1e} | **{r['verdict']}** |")
    md += ["\n## Headline: security vs usefulness\n", table(pd.DataFrame(main_rows)),
           "\n![](fig1_security_utility.png)\n",
           "## Attack success by attacker type\n", table(asr), "\n![](fig2_asr_heatmap.png)\n",
           "## Detection: what ML adds beyond rules (RQ1, N2)\n", table(det),
           "\n### Leave-one-attacker-out (RQ5)\n", table(loao), "\n![](fig3_detection.png)\n",
           "## Self-healing (RQ4, H4)\n", table(heal), "\n![](fig4_healing.png)\n",
           "## Team-level containment (RQ3, H3)\n![](fig6_containment.png)\n",
           "## Healing-aware attacker and probation length (H5)\n", table(swt.reset_index()),
           "\n![](fig5_probation_tradeoff.png)\n",
           "## Dataset (training traces)\n", table(ds), "\n![](fig7_dataset.png)\n",
           "## Fitted risk model (validation split)\n", "```json\n" + json.dumps(card, indent=2) + "\n```\n"]
    (RES / "RESULTS.md").write_text("\n".join(md), encoding="utf-8")
    for h, r in H.items():
        print(f"{h}: {r['verdict']:14s} p_holm={r['p_holm']:.1e} | {r['obs']}")


if __name__ == "__main__":
    main()
