"""Greedy constructive solver with a randomized portfolio of strategies."""

import math
import random
import time
from math import gcd

from .machine import Machine, OutOfRegisters
from .rules import simulate
from .search import exact_search, one_step, plan_target, preds


class Strategy:
    def __init__(self, order="asc", width=12, bits=4.0, toolkit=0, gcd_seeds=False,
                 seed=0, deep=True, deep_all=False):
        self.order = order
        self.width = width
        self.bits = bits
        self.toolkit = toolkit
        self.gcd_seeds = gcd_seeds
        self.seed = seed
        self.deep = deep
        self.deep_all = deep_all

    def __repr__(self):
        return ("Strategy(order=%s,width=%d,bits=%.1f,toolkit=%d,gcd=%s,seed=%d)"
                % (self.order, self.width, self.bits, self.toolkit, self.gcd_seeds, self.seed))


def _expand(ops, V, R1):
    """Insert R1 constructions for operands that are not yet available."""
    have = set(V)
    out = []
    for op, a, b, r in ops:
        for x in (a, b):
            if x not in have:
                if x not in R1:
                    raise ValueError("operand %d unavailable" % x)
                rop, ra, rb = R1[x]
                out.append((rop, ra, rb, x))
                have.add(x)
        if r not in have:
            out.append((op, a, b, r))
            have.add(r)
    return out


def emit_plan(m, ops, R1):
    ops = _expand(ops, m.values(), R1)
    last = {}
    for i, (_, a, b, r) in enumerate(ops):
        last[a] = i
        last[b] = i
    for i, (op, a, b, r) in enumerate(ops):
        protect = {v for v, k in last.items() if k > i}
        m.emit(op, a, b, protect)


def _quick(t, V, R1, limit):
    """Cheapest 1- or 2-instruction way to make ``t``; returns (cost, ops) or None."""
    if t in R1:
        return 1, []
    best = None
    for v in V:
        for x, fop in preds(t, v, limit):
            if x in V:
                op, a, b = fop
                return 1, [(op, x if a is None else a, x if b is None else b, t)]
            if best is None and x in R1:
                op, a, b = fop
                best = (2, [(op, x if a is None else a, x if b is None else b, t)])
    return best


def _build_toolkit(m, k, limit, rng):
    """Add ``k`` diverse values (log-uniform magnitudes) to the machine."""
    top = math.log(max(limit, 2))
    for _ in range(k):
        V = list(m.values())
        R1 = one_step(V, limit)
        if not R1:
            return
        want = math.exp(rng.uniform(0, top * 0.6))
        x = min(R1, key=lambda v: abs(math.log(v) - math.log(want)) + rng.random() * 0.3)
        rop, a, b = R1[x]
        m.emit(rop, a, b)


def _gcd_seeds(targets, limit, k=4):
    count = {}
    ts = sorted(targets)
    for i in range(len(ts)):
        for j in range(i + 1, len(ts)):
            g = gcd(ts[i], ts[j])
            if g > 1000:
                count[g] = count.get(g, 0) + 1
    seeds = [g for g, c in sorted(count.items(), key=lambda kv: (-kv[1], -kv[0])) if c >= 2]
    return [g for g in seeds if g not in targets][:k]


def run_strategy(puzzle, strat):
    rng = random.Random(strat.seed)
    limit = puzzle.limit
    m = Machine(puzzle.start, limit, puzzle.registers)
    targets = sorted(set(puzzle.targets))
    if strat.toolkit:
        _build_toolkit(m, strat.toolkit, limit, rng)
    queue = []
    if strat.gcd_seeds:
        queue = _gcd_seeds(targets, limit)
    if strat.order in ("asc", "greedy"):
        order = targets
    elif strat.order == "desc":
        order = targets[::-1]
    else:
        order = targets[:]
        rng.shuffle(order)
    order = queue + order
    required = set(targets)
    remaining = [t for t in order if t not in m.seen]
    guard = 0
    while remaining:
        guard += 1
        if guard > 10000 or len(m.prog) > 4096:
            return None
        V = set(m.values())
        R1 = one_step(V, limit)
        # cheapest immediate hits among required targets
        chosen = None
        for t in remaining:
            if t not in required:
                continue
            q = _quick(t, V, R1, limit)
            if q is not None and (chosen is None or q[0] < chosen[0]):
                chosen = (q[0], t, q[1])
                if q[0] == 1:
                    break
        if chosen is not None:
            _, t, ops = chosen
            if not ops:
                rop, a, b = R1[t]
                ops = [(rop, a, b, t)]
        else:
            res = None
            if strat.order == "greedy":
                for cand in remaining[:16]:
                    r = plan_target(cand, V, R1, limit, width=strat.width, bits=strat.bits,
                                    deep_terminal=strat.deep, deep_all=strat.deep_all)
                    if r is not None and (res is None or r[0] < res[0]):
                        res, t = r, cand
            if res is None:
                t = remaining[0]
                res = plan_target(t, V, R1, limit, width=strat.width, bits=strat.bits,
                                  deep_terminal=strat.deep, deep_all=strat.deep_all)
            if res is None:
                res = _fallback(m, t, limit)
                if res is None:
                    return None
                V = set(m.values())
                R1 = one_step(V, limit)
            ops = res[1]
            if not ops and t in R1:
                rop, a, b = R1[t]
                ops = [(rop, a, b, t)]
        try:
            emit_plan(m, ops, R1)
        except (OutOfRegisters, ValueError):
            return None
        remaining = [x for x in remaining if x not in m.seen]
    return m.prog


def _fallback(m, t, limit):
    """Make sure 1 and 2 exist so that the planner can always proceed."""
    vals = list(m.values())
    if 1 not in m.where:
        s = vals[0]
        m.emit("/", s, s)
    if 2 <= limit and 2 not in m.where:
        m.emit("+", 1, 1)
    V = set(m.values())
    return plan_target(t, V, one_step(V, limit), limit, width=4, bits=1.0)


def prune(program, puzzle):
    """Drop instructions whose removal keeps the program valid (dead code)."""
    prog = list(program)
    k = len(prog) - 1
    while k >= 0:
        trial = prog[:k] + prog[k + 1:]
        if simulate(trial, puzzle)[0]:
            prog = trial
        k -= 1
    return prog


def baseline_program(puzzle):
    """Naive double-and-add from 1 for every target (a sanity baseline)."""
    m = Machine(puzzle.start, puzzle.limit, puzzle.registers)
    s = puzzle.start[0]
    if 1 not in m.where:
        m.emit("/", s, s)
    for t in sorted(set(puzzle.targets)):
        if t in m.seen:
            continue
        bits = bin(t)[3:]
        acc = 1
        for bit in bits:
            nxt = m.emit("+", acc, acc, protect={1, acc})
            acc = nxt
            if bit == "1":
                acc = m.emit("+", acc, 1, protect={1, acc})
    return m.prog


def default_strategies():
    return [
        Strategy("greedy", 8, 5.0, 4, False, 1),
        Strategy("asc", 12, 5.0, 0, False, 0),
        Strategy("asc", 12, 5.0, 0, True, 0),
        Strategy("asc", 24, 5.0, 0, False, 0, deep_all=True),
        Strategy("asc", 12, 4.0, 8, False, 1),
        Strategy("desc", 12, 5.0, 0, False, 0),
    ]


def solve_puzzle(puzzle, time_limit=10.0, seed=0, exact_budget=200000, verbose=False):
    """Run the portfolio until ``time_limit`` seconds elapse; return best program."""
    t0 = time.time()
    best = None
    best_strat = None

    def consider(prog, tag):
        nonlocal best, best_strat
        if prog is None:
            return
        prog = prune(prog, puzzle)
        ok, _ = simulate(prog, puzzle)
        if ok and (best is None or len(prog) < len(best)):
            best, best_strat = prog, tag

    if puzzle.lower_bound <= 8 and len(puzzle.start) + puzzle.lower_bound <= 40:
        steps = exact_search(puzzle.start, puzzle.targets, puzzle.limit, max_extra=6,
                             node_budget=exact_budget)
        if steps is not None:
            m = Machine(puzzle.start, puzzle.limit, puzzle.registers)
            for op, a, b, r in steps:
                m.emit(op, a, b)
            consider(m.prog, "exact")
            if best is not None and len(best) == puzzle.lower_bound:
                return best, best_strat
    rng = random.Random(seed)
    strategies = default_strategies()
    i = 0
    while True:
        if i < len(strategies):
            st = strategies[i]
        else:
            st = Strategy(rng.choice(["asc", "greedy", "greedy", "random"]), rng.choice([8, 12, 16, 24]),
                          rng.choice([3.0, 3.5, 4.0, 5.0]), rng.choice([0, 0, 2, 4, 8]),
                          rng.random() < 0.3, rng.randrange(1 << 30),
                          deep_all=rng.random() < 0.5)
        i += 1
        consider(run_strategy(puzzle, st), repr(st))
        if best is not None and len(best) == puzzle.lower_bound:
            break
        if time.time() - t0 > time_limit and best is not None:
            break
        if time.time() - t0 > 20 * time_limit + 60:
            break
    if best is None:
        consider(baseline_program(puzzle), "baseline")
    return best, best_strat
