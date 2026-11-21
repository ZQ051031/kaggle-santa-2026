# Kaggle Santa 2026 — The Elf Calculator: pure-Python solver

A solver, a local validator/scorer, and a synthetic-data generator for
[Santa 2026 — The Elf Calculator](https://www.kaggle.com/competitions/santa-2026).
It uses only the Python standard library (tested on Python 3.10) and has no dependencies.

## The task (from the competition pages)

* Each puzzle has `starting_values` (registers 0..k-1), a sorted list of `targets`, a
  `value_limit` (≤ 10^18) and 48 registers.
* An instruction `["op", i, j, d]` computes `reg[i] op reg[j]` and writes the result to `reg[d]`. The operators are
  `+ - * /`. Every value must be a positive integer ≤ `value_limit`, subtraction needs
  `a > b`, division must be exact, and sources must be defined.
* A target is covered once it appears in any register. Every program must cover all targets.
* **Score = total number of instructions over the 1,000 puzzles (lower is better).**
  There is no partial credit: one invalid program rejects the whole submission.
* Submission: a UTF-8 CSV with header `id,program`, with every id `scored_0001`..`scored_1000` exactly once.
  `program` is a JSON array of instructions. Limits: 4,096 instructions and 128 KiB per cell.

## Approach

`elfcalc/solver.py` builds each program greedily, one target at a time, on a
register machine with LRU register allocation (`elfcalc/machine.py`):

1. **One-step closure.** `R1` holds every value reachable in one instruction from the current
   register contents (around 4.6k values with 48 registers).
2. **Quick hits.** Any remaining target that costs 1 instruction (`t ∈ R1`) or 2 instructions
   (`t = x op v` with `v` in a register and `x ∈ R1`) is emitted first. This helps
   puzzles whose targets share structure.
3. **Backward beam search** (`elfcalc/search.py::plan_target`). This search works backwards from the target `n`.
   Each move picks a divisor `d` (a register value or an `R1` value) and replaces `n`
   with `q = n // d` when `n mod d` (or `d - n mod d`) is available. Going forwards, that is
   `q*d + r` or `(q+1)*d - r'`, which costs 1–4 instructions depending on whether `d` and `r` must be built first.
   Exact factors cost 1 instruction. Nodes are ranked by `cost + log2(n)/bits`, and terminal checks find
   1–3 instruction finishes. Intermediate values stay in registers and help later targets.
4. **Exact search for tiny puzzles.** When the lower bound is ≤ 8, an iterative-deepening search over value sets
   (`exact_search`) finds provably shortest programs within its depth and budget limits.
5. **Portfolio + restarts.** Each puzzle runs several strategies until its time budget runs out, then
   randomized ones. Strategies vary the target order (ascending, random, or *greedy-cheapest-next*), the beam width
   and heuristic, a random "toolkit" of pre-built values, and *gcd seeding* (common factors of target pairs are
   built first, which suits the multiplicative family).
6. **Dead-code pruning.** Each instruction is dropped if the program stays valid without it.
   Every candidate program is replayed by the simulator before it is accepted.

`baseline_program` is a naive double-and-add from 1, kept for comparison.

## Usage

The real data (`puzzles.csv`, `practice_puzzles.csv`, `sample_submission.csv`) can only be downloaded after you
accept the competition rules on Kaggle, so it is **not** in this repo (it is also git-ignored). Download it yourself, then run:

```bash
# solve: --time is the soft per-puzzle budget in seconds; uses all CPU cores by default
python3 solve.py --puzzles puzzles.csv --out submission.csv --time 10 --workers 8

# validate + score (exit code 0 only if the submission is valid)
python3 score.py --puzzles puzzles.csv --submission submission.csv

# improve an existing submission: keeps the shorter valid program per id
python3 solve.py --puzzles puzzles.csv --out submission2.csv --init submission.csv --time 30 --seed 1

# you can also score Kaggle's sample_submission.csv, or the practice set (per-family table)
python3 score.py --puzzles practice_puzzles.csv --submission my_practice_submission.csv

# synthetic data, naive baseline, unit tests
python3 generate_synthetic.py --n 100 --seed 2026 --out data/synthetic_puzzles.csv
python3 baseline.py --puzzles data/synthetic_puzzles.csv --out baseline.csv
python3 -m unittest discover -s tests
```

`score.py` checks the exact header, duplicate/missing/unknown ids, UTF-8, cell size, JSON shape, operator and
register types (bools are rejected), defined sources, legal arithmetic, `value_limit`, the 4,096-instruction limit and target
coverage. If the puzzles file has a `family` column (the practice set does), it also prints a per-family table.

## Local test results

All runs were on an 8-core VM. The full log is in [`results/local_test_log.txt`](results/local_test_log.txt).

**Worked example from the Data page** (`data/example_puzzle.csv`: start `[3]`, targets `[1,2,5,8]`, limit 9).
The solver finds a 4-instruction program, which is optimal (lower bound 4). `score.py` reports `VALID score=4`.
A corrupted program (`results/example_submission_invalid.csv`) is rejected with
`instruction 0 is illegal: 3 - 3` and exit code 1.

**Synthetic practice-style set** (`data/synthetic_puzzles.csv`: 100 puzzles, 20 per family, generated by
`generate_synthetic.py` to imitate the documented families; these are *not* the real puzzles):

| family | n | lower bound | naive baseline | this solver (`--time 5`) | solver / lb |
|---|---|---|---|---|---|
| independent | 20 | 265 | 13,471 | 2,015 | 7.60 |
| shared | 20 | 384 | 18,746 | 2,285 | 5.95 |
| multiplicative | 20 | 281 | 13,228 | 866 | 3.08 |
| mixed | 20 | 269 | 11,867 | 1,658 | 6.16 |
| tiny | 20 | 78 | 341 | 149 | 1.91 |
| **total** | 100 | 1,277 | **57,653** | **6,973** | 5.46 |

The solver uses 8.3× fewer instructions than the naive baseline. The full synthetic run took 72 s with 8 workers, all
programs passed validation, and the longest program had 309 instructions. The unit tests pass (7 tests).

**Expected score on Kaggle:** not measured. The scored `puzzles.csv` needs a Kaggle login, and nothing was submitted.
For a rough estimate, multiply the real file's total lower bound by the ratios above (about 3–8× the lower bound for
large-number families, close to optimal for tiny puzzles). The real data may differ from the synthetic generator.
At `--time 10` with 8 workers, 1,000 puzzles take about 20–25 minutes. Longer runs and `--init` restarts only ever improve the result.

## Layout

```
elfcalc/rules.py      rules, CSV I/O, simulator
elfcalc/machine.py    register machine + LRU allocation
elfcalc/search.py     one-step closure, backward beam planner, exact tiny search
elfcalc/solver.py     strategies, portfolio, pruning, naive baseline
solve.py / score.py / baseline.py / generate_synthetic.py   CLIs
data/                 worked example + synthetic puzzles (no Kaggle data)
results/              local test outputs and log
tests/                unittest suite
```

License: Apache-2.0. The competition's winner license requires CC BY 4.0 or Apache 2.0.
