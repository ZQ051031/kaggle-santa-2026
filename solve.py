#!/usr/bin/env python3
"""Solve every puzzle and write a submission CSV (stdlib only).

Example:
    python3 solve.py --puzzles puzzles.csv --out submission.csv --time 10 --workers 8
"""

import argparse
import multiprocessing as mp
import os
import sys
import time

from elfcalc.rules import read_puzzles, read_submission, simulate, write_submission
from elfcalc.solver import solve_puzzle

_PUZ = {}


def _init(puzzles):
    _PUZ.update({p.id: p for p in puzzles})


def _work(args):
    pid, tl, seed = args
    t0 = time.time()
    prog, strat = solve_puzzle(_PUZ[pid], time_limit=tl, seed=seed)
    return pid, prog, strat, time.time() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puzzles", required=True, help="puzzles.csv (competition schema)")
    ap.add_argument("--out", required=True, help="submission CSV to write")
    ap.add_argument("--init", help="existing submission; keep its program when it is shorter")
    ap.add_argument("--time", type=float, default=5.0, help="seconds per puzzle (soft)")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--only", nargs="*", help="solve only these ids (others copied from --init)")
    args = ap.parse_args()

    puzzles = read_puzzles(args.puzzles)
    byid = {p.id: p for p in puzzles}
    best = {}
    if args.init and os.path.exists(args.init):
        for pid, prog in read_submission(args.init).items():
            if pid in byid and simulate(prog, byid[pid])[0]:
                best[pid] = prog
    todo = [p.id for p in puzzles if not args.only or p.id in args.only]
    jobs = [(pid, args.time, args.seed + i) for i, pid in enumerate(todo)]
    t0 = time.time()
    improved = 0
    if args.workers > 1:
        pool = mp.Pool(args.workers, initializer=_init, initargs=(puzzles,))
        it = pool.imap_unordered(_work, jobs)
    else:
        _init(puzzles)
        pool = None
        it = map(_work, jobs)
    for k, (pid, prog, strat, dt) in enumerate(it, 1):
        old = best.get(pid)
        if prog is not None and (old is None or len(prog) < len(old)):
            best[pid] = prog
            improved += 1
        print("[%d/%d] %s len=%d lb=%d (%.1fs) %s" % (k, len(jobs), pid, len(best[pid]),
              byid[pid].lower_bound, dt, strat), file=sys.stderr, flush=True)
    if pool:
        pool.close()
        pool.join()
    missing = [p.id for p in puzzles if p.id not in best]
    if missing:
        sys.exit("no program for %d puzzles, e.g. %s" % (len(missing), missing[0]))
    write_submission(args.out, best, [p.id for p in puzzles])
    total = sum(len(best[p.id]) for p in puzzles)
    print("wrote %s: score=%d (%d improved) in %.1fs" % (args.out, total, improved, time.time() - t0))


if __name__ == "__main__":
    main()
