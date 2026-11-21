#!/usr/bin/env python3
"""Validate a submission CSV against a puzzles CSV and compute its score.

Mirrors the rules on the competition's Evaluation and Data pages: exact
``id,program`` header, every puzzle id exactly once, JSON array of
``[op, src, src, dst]`` instructions, register/instruction/cell-size limits,
legal arithmetic within ``value_limit`` and every target produced.
Exit code is 0 only when the submission is valid.
"""

import argparse
import json
import sys
from collections import defaultdict

from elfcalc.rules import MAX_CELL_BYTES, read_puzzles, read_submission_raw, simulate


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puzzles", required=True)
    ap.add_argument("--submission", required=True)
    ap.add_argument("--per-puzzle", action="store_true", help="print every puzzle's length")
    args = ap.parse_args()

    puzzles = read_puzzles(args.puzzles)
    byid = {p.id: p for p in puzzles}
    errors = []
    header, rows = read_submission_raw(args.submission)
    if header != ["id", "program"]:
        errors.append("header must be exactly id,program (got %r)" % (header,))
    with open(args.submission, "rb") as f:
        try:
            f.read().decode("utf-8")
        except UnicodeDecodeError:
            errors.append("file is not valid UTF-8")
    seen = set()
    lengths = {}
    for n, row in enumerate(rows, 2):
        if len(row) != 2:
            errors.append("line %d: expected 2 columns, got %d" % (n, len(row)))
            continue
        pid, cell = row
        if pid in seen:
            errors.append("line %d: duplicate id %s" % (n, pid))
            continue
        seen.add(pid)
        if pid not in byid:
            errors.append("line %d: unknown id %s" % (n, pid))
            continue
        if len(cell.encode("utf-8")) > MAX_CELL_BYTES:
            errors.append("%s: program cell exceeds %d bytes" % (pid, MAX_CELL_BYTES))
            continue
        try:
            prog = json.loads(cell)
        except ValueError as e:
            errors.append("%s: invalid JSON (%s)" % (pid, e))
            continue
        ok, msg = simulate(prog, byid[pid])
        if not ok:
            errors.append("%s: %s" % (pid, msg))
            continue
        lengths[pid] = len(prog)
    for p in puzzles:
        if p.id not in seen:
            errors.append("missing id %s" % p.id)

    lb = sum(p.lower_bound for p in puzzles)
    if args.per_puzzle:
        for p in puzzles:
            if p.id in lengths:
                print("%s\t%d\tlb=%d\t%s" % (p.id, lengths[p.id], p.lower_bound, p.family))
    fam = defaultdict(lambda: [0, 0, 0])
    for p in puzzles:
        if p.id in lengths:
            f = fam[p.family or "-"]
            f[0] += 1
            f[1] += lengths[p.id]
            f[2] += p.lower_bound
    if fam and (len(fam) > 1 or "-" not in fam):
        print("%-16s %6s %8s %8s %7s" % ("family", "n", "score", "lb", "ratio"))
        for k in sorted(fam):
            n, s, b = fam[k]
            print("%-16s %6d %8d %8d %7.3f" % (k, n, s, b, s / max(b, 1)))
    if errors:
        print("INVALID: %d error(s)" % len(errors))
        for e in errors[:20]:
            print("  " + e)
        sys.exit(1)
    total = sum(lengths.values())
    print("VALID  puzzles=%d  score=%d  lower_bound=%d  ratio=%.3f"
          % (len(puzzles), total, lb, total / max(lb, 1)))


if __name__ == "__main__":
    main()
