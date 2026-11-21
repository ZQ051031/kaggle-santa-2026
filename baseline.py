#!/usr/bin/env python3
"""Write a naive double-and-add baseline submission (for comparison)."""

import argparse

from elfcalc.rules import read_puzzles, write_submission
from elfcalc.solver import baseline_program


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--puzzles", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    puzzles = read_puzzles(args.puzzles)
    progs = {p.id: baseline_program(p) for p in puzzles}
    write_submission(args.out, progs, [p.id for p in puzzles])
    print("wrote %s: score=%d" % (args.out, sum(len(v) for v in progs.values())))


if __name__ == "__main__":
    main()
