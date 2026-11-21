#!/usr/bin/env python3
"""Generate synthetic puzzles in the competition's practice_puzzles.csv schema.

The real puzzles.csv / practice_puzzles.csv require accepting the competition
rules on Kaggle, so this generator approximates the five documented families
(independent, shared, multiplicative, mixed, tiny) for local testing only.
"""

import argparse
import math
import random

from elfcalc.rules import Puzzle, apply_op, write_puzzles

TIERS = {"easy": (3, 8), "medium": (8, 20), "hard": (20, 40)}


def log_uniform(rng, lo, hi):
    return int(math.exp(rng.uniform(math.log(lo), math.log(hi))))


def gen_tiny(rng):
    start = [rng.randint(2, 7)]
    limit = rng.randint(9, 200)
    k = rng.randint(2, 5)
    targets = sorted(rng.sample(range(1, limit + 1), k))
    return start, targets, limit


def gen_independent(rng, k):
    limit = log_uniform(rng, 10 ** 12, 10 ** 18)
    start = [3] if rng.random() < 0.6 else sorted(rng.sample(range(2, 12), rng.randint(1, 3)))
    targets = sorted({log_uniform(rng, 10 ** 6, limit) for _ in range(k)})
    return start, targets, limit


def gen_shared(rng, k):
    """Targets are outputs of one hidden random straight-line program."""
    limit = log_uniform(rng, 10 ** 12, 10 ** 18)
    start = [3]
    vals = list(start)
    produced = []
    while len(produced) < 6 * k:
        a, b = rng.choice(vals), rng.choice(vals)
        op = rng.choice("++**-")
        r = apply_op(op, max(a, b), min(a, b))
        if r is None or r <= 0 or r > limit or r in vals:
            continue
        vals.append(r)
        if len(vals) > 48:
            vals.pop(rng.randrange(1, len(vals) - 1))
        if r > 10 ** 6:
            produced.append(r)
    targets = sorted(set(rng.sample(produced, min(k, len(produced)))))
    return start, targets, limit


def gen_multiplicative(rng, k):
    limit = log_uniform(rng, 10 ** 14, 10 ** 18)
    start = [3]
    factors = [log_uniform(rng, 2, 10 ** 6) for _ in range(rng.randint(5, 10))]
    targets = set()
    tries = 0
    while len(targets) < k and tries < 10000:
        tries += 1
        prod = 1
        for f in rng.sample(factors, rng.randint(2, min(5, len(factors)))):
            prod *= f
        if 10 ** 4 < prod <= limit:
            targets.add(prod)
    return start, sorted(targets), limit


def gen_mixed(rng, k):
    s1, t1, l1 = gen_shared(rng, k // 2 + 1)
    _, t2, _ = gen_independent(rng, k - k // 2)
    t2 = [t for t in t2 if t <= l1]
    return s1, sorted(set(t1 + t2)), l1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--prefix", default="synthetic")
    ap.add_argument("--out", default="data/synthetic_puzzles.csv")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    fams = ["independent", "shared", "multiplicative", "mixed", "tiny"]
    puzzles = []
    for i in range(args.n):
        fam = fams[i % len(fams)]
        tier = rng.choice(list(TIERS))
        k = rng.randint(*TIERS[tier])
        if fam == "tiny":
            s, t, lim = gen_tiny(rng)
        else:
            s, t, lim = {"independent": gen_independent, "shared": gen_shared,
                         "multiplicative": gen_multiplicative, "mixed": gen_mixed}[fam](rng, k)
        p = Puzzle("%s_%04d" % (args.prefix, i + 1), s, t, lim, 48,
                   {"family": fam, "design_tier": tier if fam != "tiny" else "easy"})
        p.extra["lower_bound"] = p.lower_bound
        puzzles.append(p)
    write_puzzles(args.out, puzzles, ("family", "design_tier", "lower_bound"))
    print("wrote %d puzzles to %s" % (len(puzzles), args.out))


if __name__ == "__main__":
    main()
