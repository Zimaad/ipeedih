"""Live demo: the Section 1 attack story, without a defense and then with ContainMAS.

Usage:  python demo.py [--attacker T1|T3|T5] [--seed N]
Requires results/models.pkl (run experiments/run_experiments.py first).
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

from containmas.defense import SETUPS
from containmas.scenario import make_scenario
from containmas.sim import Sim

COL = {"attack": "\033[95m", "infect": "\033[91m", "leak": "\033[41;97m", "block": "\033[93m",
       "state": "\033[96m", "heal": "\033[92m"}
RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"


def narrator(max_repeat=6):
    seen = {"block": 0, "leak": 0}

    def say(t, kind, text):
        if kind in seen:
            seen[kind] += 1
            if seen[kind] > max_repeat:
                if seen[kind] == max_repeat + 1:
                    print(f"{DIM}  t={t:>2}  ... further {kind}s hidden ...{RESET}")
                return
        print(f"  t={t:>2}  {COL.get(kind, '')}{text}{RESET}")
    return say


def find_seed(attacker, models):
    """First scenario where the undefended team is breached and the research agent is the entry point."""
    for s in range(3000, 3200):
        sim = Sim(make_scenario(s, attacker), SETUPS["A"])
        r = sim.run()
        if r["attack_success"] and "research" in sim.ever:
            return s
    return 3000


def summary(r):
    return (f"attack succeeded: {BOLD}{'YES' if r['attack_success'] else 'no'}{RESET} "
            f"(leaked {r['leaked']} units) | agents infected: {r['spread'] * 4:.0f}/4 | "
            f"legit tasks done: {r['task_success']:.0%} | heals: {r['n_heals']}"
            + (f" | fidelity {r['fidelity']:.2f}" if r["n_heals"] else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--attacker", default="T1")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--setup", default="G")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    models = pickle.load(open(Path(__file__).parent / "results" / "models.pkl", "rb"))
    seed = args.seed if args.seed is not None else find_seed(args.attacker, models)
    sc = make_scenario(seed, args.attacker)

    print(f"\n{BOLD}=== Scenario {seed}, attacker {args.attacker}: 4 agents, {len(sc.tasks)} user tasks ==={RESET}")
    print(f"\n{BOLD}1) No defense (setup A){RESET}")
    r_a = Sim(sc, SETUPS["A"], narrate=narrator(3)).run()
    print("  -> " + summary(r_a))

    print(f"\n{BOLD}2) ContainMAS (setup {args.setup}): rules + ML + graduated states + healing{RESET}")
    r_g = Sim(sc, SETUPS[args.setup], models, narrate=narrator()).run()
    print("  -> " + summary(r_g))
    print()


if __name__ == "__main__":
    main()
