import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elfcalc.rules import Puzzle, simulate  # noqa: E402
from elfcalc.search import exact_search, one_step, plan_target  # noqa: E402
from elfcalc.solver import baseline_program, prune, solve_puzzle  # noqa: E402

EXAMPLE = Puzzle("example_0001", [3], [1, 2, 5, 8], 9)


class RulesTest(unittest.TestCase):
    def test_worked_example(self):
        prog = [["/", 0, 0, 1], ["-", 0, 1, 2], ["+", 0, 2, 3], ["+", 0, 3, 4]]
        self.assertEqual(simulate(prog, EXAMPLE), (True, "ok"))

    def test_illegal_programs(self):
        bad = {
            "subtraction must stay positive": [["-", 0, 0, 1]],
            "division must be exact": [["+", 0, 0, 1], ["/", 0, 1, 2]],
            "undefined source": [["+", 0, 5, 1]],
            "value limit": [["*", 0, 0, 1], ["+", 1, 1, 2]],
            "register range": [["+", 0, 0, 48]],
            "bool is not int": [["+", 0, True, 1]],
            "missing targets": [["/", 0, 0, 1]],
        }
        for name, prog in bad.items():
            self.assertFalse(simulate(prog, EXAMPLE)[0], name)


class SolverTest(unittest.TestCase):
    def test_exact_example(self):
        steps = exact_search([3], [1, 2, 5, 8], 9)
        self.assertEqual(len(steps), 4)

    def test_solve_example_optimal(self):
        prog, _ = solve_puzzle(EXAMPLE, time_limit=0.5)
        self.assertTrue(simulate(prog, EXAMPLE)[0])
        self.assertEqual(len(prog), 4)

    def test_plan_target_large(self):
        V = {3, 1, 2, 9, 81}
        R1 = one_step(V, 10 ** 18)
        res = plan_target(123456789012345, V, R1, 10 ** 18)
        self.assertIsNotNone(res)

    def test_random_puzzles_valid_and_beat_baseline(self):
        rng = random.Random(7)
        for i in range(5):
            limit = 10 ** rng.randint(12, 18)
            targets = sorted({rng.randint(10 ** 6, limit) for _ in range(rng.randint(3, 15))})
            p = Puzzle("r%d" % i, [3], targets, limit)
            prog, _ = solve_puzzle(p, time_limit=0.2)
            self.assertTrue(simulate(prog, p)[0])
            base = baseline_program(p)
            self.assertTrue(simulate(base, p)[0])
            self.assertLess(len(prog), len(base))

    def test_prune_removes_dead_code(self):
        prog = [["/", 0, 0, 1], ["*", 0, 0, 7], ["-", 0, 1, 2], ["+", 0, 2, 3], ["+", 0, 3, 4]]
        p = Puzzle("x", [3], [1, 2, 5, 8], 9)
        self.assertEqual(len(prune(prog, p)), 4)


if __name__ == "__main__":
    unittest.main()
