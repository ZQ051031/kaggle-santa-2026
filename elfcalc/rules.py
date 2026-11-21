"""Calculator rules, puzzle/submission I/O and a faithful program simulator."""

import csv
import json
import sys

NUM_REGISTERS = 48
MAX_INSTRUCTIONS = 4096
MAX_CELL_BYTES = 131072
MAX_VALUE_LIMIT = 10 ** 18
OPS = ("+", "-", "*", "/")

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))


def apply_op(op, a, b):
    """Return the result of ``a op b`` or None when the operation is illegal."""
    if op == "+":
        return a + b
    if op == "-":
        return a - b if a > b else None
    if op == "*":
        return a * b
    if op == "/":
        return a // b if a % b == 0 else None
    return None


class Puzzle:
    __slots__ = ("id", "start", "targets", "limit", "registers", "extra")

    def __init__(self, pid, start, targets, limit, registers=NUM_REGISTERS, extra=None):
        self.id = pid
        self.start = list(start)
        self.targets = list(targets)
        self.limit = int(limit)
        self.registers = int(registers)
        self.extra = dict(extra or {})

    @property
    def lower_bound(self):
        return len(set(self.targets) - set(self.start))

    @property
    def family(self):
        return self.extra.get("family", "")


def read_puzzles(path):
    puzzles = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            extra = {k: v for k, v in row.items()
                     if k not in ("id", "starting_values", "targets", "value_limit", "registers")}
            puzzles.append(Puzzle(
                row["id"],
                json.loads(row["starting_values"]),
                json.loads(row["targets"]),
                int(row["value_limit"]),
                int(row.get("registers") or NUM_REGISTERS),
                extra,
            ))
    return puzzles


def write_puzzles(path, puzzles, extra_cols=()):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "starting_values", "targets", "value_limit", "registers", *extra_cols])
        for p in puzzles:
            w.writerow([p.id, json.dumps(p.start), json.dumps(p.targets), p.limit, p.registers,
                        *[p.extra.get(c, "") for c in extra_cols]])


def program_to_cell(program):
    return json.dumps(program, separators=(",", ":"))


def write_submission(path, programs, ids):
    """Write ``id,program`` rows for ``ids`` (in that order) using a CSV writer."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["id", "program"])
        for pid in ids:
            w.writerow([pid, program_to_cell(programs[pid])])


def read_submission_raw(path):
    """Return (header, rows) where rows are lists of raw string cells."""
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def read_submission(path):
    header, rows = read_submission_raw(path)
    return {r[0]: json.loads(r[1]) for r in rows if len(r) >= 2}


def simulate(program, puzzle):
    """Replay ``program`` on ``puzzle``.

    Returns ``(ok, message)``. ``ok`` is True only when every instruction is
    legal and every target is produced at least once.
    """
    nregs = puzzle.registers
    if not isinstance(program, list):
        return False, "program is not a JSON array"
    if len(program) > MAX_INSTRUCTIONS:
        return False, "too many instructions (%d > %d)" % (len(program), MAX_INSTRUCTIONS)
    if len(puzzle.start) > nregs:
        return False, "more starting values than registers"
    regs = [None] * nregs
    for i, v in enumerate(puzzle.start):
        regs[i] = v
    seen = set(puzzle.start)
    limit = puzzle.limit
    for k, ins in enumerate(program):
        if not isinstance(ins, list) or len(ins) != 4:
            return False, "instruction %d is not a 4-element array" % k
        op, i, j, d = ins
        if op not in OPS:
            return False, "instruction %d has bad operator %r" % (k, op)
        for x in (i, j, d):
            if type(x) is not int or not 0 <= x < nregs:
                return False, "instruction %d has bad register index %r" % (k, x)
        a, b = regs[i], regs[j]
        if a is None or b is None:
            return False, "instruction %d reads an undefined register" % k
        r = apply_op(op, a, b)
        if r is None:
            return False, "instruction %d is illegal: %d %s %d" % (k, a, op, b)
        if r <= 0:
            return False, "instruction %d produces non-positive value" % k
        if r > limit:
            return False, "instruction %d exceeds value_limit: %d > %d" % (k, r, limit)
        regs[d] = r
        seen.add(r)
    missing = [t for t in puzzle.targets if t not in seen]
    if missing:
        return False, "%d target(s) never produced, e.g. %d" % (len(missing), missing[0])
    return True, "ok"
