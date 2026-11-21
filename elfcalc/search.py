"""Search primitives: one-step closure, backward beam planner, exact tiny search."""

import math

from .rules import apply_op


def one_step(values, limit):
    """All values reachable with one instruction from ``values`` -> recipe."""
    vs = sorted(values)
    have = set(vs)
    out = {}
    n = len(vs)
    for i in range(n):
        a = vs[i]
        for k in range(i, n):
            b = vs[k]
            s = a + b
            if s <= limit and s not in have and s not in out:
                out[s] = ("+", b, a)
            p = a * b
            if p <= limit and p not in have and p not in out:
                out[p] = ("*", b, a)
            if b > a:
                d = b - a
                if d not in have and d not in out:
                    out[d] = ("-", b, a)
            if b % a == 0:
                q = b // a
                if q not in have and q not in out:
                    out[q] = ("/", b, a)
    return out


def preds(n, v, limit):
    """Yield (x, forward_op) such that the forward op on x and v yields n."""
    if n > v:
        yield n - v, ("+", None, v)
    if n + v <= limit:
        yield n + v, ("-", None, v)
    if v > n:
        yield v - n, ("-", v, None)
    if v > 1 and n % v == 0:
        yield n // v, ("*", None, v)
    if v > 1 and n * v <= limit:
        yield n * v, ("/", None, v)
    if v > n and v % n == 0:
        yield v // n, ("/", v, None)


def _fill(fop, x, n):
    op, a, b = fop
    return (op, x if a is None else a, x if b is None else b, n)


class Node:
    __slots__ = ("n", "g", "parent", "ops")

    def __init__(self, n, g, parent, ops):
        self.n, self.g, self.parent, self.ops = n, g, parent, ops

    def forward(self):
        """Forward ops from this node's value up to the root target."""
        out = []
        node = self
        while node is not None:
            out.extend(node.ops)
            node = node.parent
        return out


def plan_target(t, V, R1, limit, width=12, bits=4.0, max_depth=40, deep_terminal=True,
                deep_all=False):
    """Backward beam search for a short program producing ``t``.

    ``V`` are values currently in registers, ``R1`` maps one-step values to
    recipes. Returns ``(estimated_cost, forward_ops)`` or None. Forward ops are
    ``(op, left_value, right_value, result)`` tuples; operands that are not in
    ``V`` are either produced earlier in the list or built from ``R1``.
    """
    cost = dict.fromkeys(R1, 1)
    cost.update(dict.fromkeys(V, 0))
    if t in cost:
        return cost[t], []
    Vl = [v for v in V]
    R1l = list(R1)
    divs = sorted((d for d in cost if d >= 2), reverse=True)

    best = [None, None]

    def offer(total, ops):
        if best[0] is None or total < best[0]:
            best[0], best[1] = total, ops

    def terminal(node, deep):
        n, g = node.n, node.g
        if n in cost:
            offer(g + cost[n], node.forward())
            return
        if best[0] is not None and g + 2 >= best[0]:
            return
        found = None
        for v in Vl:
            for x, fop in preds(n, v, limit):
                c = cost.get(x)
                if c is not None:
                    tot = g + 1 + c
                    if found is None or tot < found[0]:
                        found = (tot, _fill(fop, x, n))
                        if c == 0:
                            break
        if found is None and deep and (best[0] is None or g + 3 < best[0]):
            for v in R1l:
                for x, fop in preds(n, v, limit):
                    c = cost.get(x)
                    if c is not None:
                        tot = g + 2 + c
                        if found is None or tot < found[0]:
                            found = (tot, _fill(fop, x, n))
                if found is not None and found[0] == g + 2:
                    break
        if found is not None:
            offer(found[0], [found[1]] + node.forward())

    root = Node(t, 0, None, ())
    terminal(root, deep_terminal)
    frontier = [root]
    inv_bits = 1.0 / bits
    for _ in range(max_depth):
        children = {}
        for node in frontier:
            n, g = node.n, node.g
            if best[0] is not None and g + 2 >= best[0]:
                continue
            for d in divs:
                if d > n:
                    continue
                cd = cost[d]
                q, r = divmod(n, d)
                if r == 0:
                    gc = g + 1 + cd
                    if q in children and children[q].g <= gc:
                        continue
                    children[q] = Node(q, gc, node, (("*", q, d, n),))
                    continue
                cr = cost.get(r)
                if cr is not None:
                    gc = g + 2 + cd + cr
                    m = n - r
                    if not (q in children and children[q].g <= gc):
                        children[q] = Node(q, gc, node, (("*", q, d, m), ("+", m, r, n)))
                r2 = d - r
                cr2 = cost.get(r2)
                if cr2 is not None:
                    m = n + r2
                    if m <= limit:
                        q1 = q + 1
                        gc = g + 2 + cd + cr2
                        if not (q1 in children and children[q1].g <= gc):
                            children[q1] = Node(q1, gc, node, (("*", q1, d, m), ("-", m, r2, n)))
        if not children:
            break
        ranked = sorted(children.values(), key=lambda c: c.g + math.log2(c.n + 1) * inv_bits)
        frontier = []
        for c in ranked:
            if best[0] is not None and c.g + 1 >= best[0]:
                continue
            terminal(c, deep_all)
            frontier.append(c)
            if len(frontier) >= width:
                break
        if not frontier:
            break
    if best[0] is None:
        return None
    return best[0], best[1]


def exact_search(start, targets, limit, max_extra=3, node_budget=200000, max_values=48):
    """Iterative-deepening exact search over value sets (for tiny puzzles).

    Returns a list of (op, a, b, result) value steps or None.
    """
    need = frozenset(targets) - frozenset(start)
    if not need:
        return []
    budget = [node_budget]
    lb = len(need)
    seen_fail = set()

    def children(vals):
        out = []
        vs = sorted(vals)
        for i, a in enumerate(vs):
            for b in vs[i:]:
                for op, x, y in (("+", b, a), ("*", b, a), ("-", b, a), ("/", b, a)):
                    r = apply_op(op, x, y)
                    if r is not None and 0 < r <= limit and r not in vals:
                        out.append((op, x, y, r))
        return out

    def dfs(vals, remaining, depth):
        if not remaining:
            return []
        if len(remaining) > depth or len(vals) >= max_values:
            return None
        key = (vals, depth)
        if key in seen_fail:
            return None
        budget[0] -= 1
        if budget[0] < 0:
            raise TimeoutError
        kids = children(vals)
        hit = [k for k in kids if k[3] in remaining]
        if len(remaining) == depth:
            kids = hit
        else:
            hs = set(id(k) for k in hit)
            kids = hit + [k for k in kids if id(k) not in hs]
        done = set()
        for k in kids:
            if k[3] in done:
                continue
            done.add(k[3])
            sub = dfs(vals | {k[3]}, remaining - {k[3]}, depth - 1)
            if sub is not None:
                return [k] + sub
        seen_fail.add(key)
        return None

    try:
        for depth in range(lb, lb + max_extra + 1):
            res = dfs(frozenset(start), need, depth)
            if res is not None:
                return res
    except TimeoutError:
        return None
    return None
