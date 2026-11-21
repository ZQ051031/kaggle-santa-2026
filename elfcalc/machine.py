"""Register machine with LRU register allocation that records a program."""

from .rules import apply_op, NUM_REGISTERS


class OutOfRegisters(Exception):
    pass


class Machine:
    def __init__(self, start, limit, nregs=NUM_REGISTERS):
        self.limit = limit
        self.regs = [None] * nregs
        self.where = {}          # value -> register currently holding it
        self.stamp = [0] * nregs
        self.clock = 0
        self.prog = []
        for i, v in enumerate(start):
            self.regs[i] = v
            self.where.setdefault(v, i)
        self.seen = set(start)

    def values(self):
        return self.where.keys()

    def copy(self):
        m = Machine.__new__(Machine)
        m.limit = self.limit
        m.regs = list(self.regs)
        m.where = dict(self.where)
        m.stamp = list(self.stamp)
        m.clock = self.clock
        m.prog = list(self.prog)
        m.seen = set(self.seen)
        return m

    def _touch(self, r):
        self.clock += 1
        self.stamp[r] = self.clock

    def _alloc(self, protect):
        best, best_stamp = None, None
        for r, v in enumerate(self.regs):
            if v is None or self.where.get(v) != r:
                return r
            if v in protect:
                continue
            if best is None or self.stamp[r] < best_stamp:
                best, best_stamp = r, self.stamp[r]
        if best is None:
            raise OutOfRegisters()
        return best

    def emit(self, op, a, b, protect=()):
        """Emit ``a op b`` (values must be present). Returns the result value."""
        res = apply_op(op, a, b)
        if res is None or res <= 0 or res > self.limit:
            raise ValueError("illegal op %r %r %r" % (a, op, b))
        if res in self.where:
            return res
        ra, rb = self.where[a], self.where[b]
        self._touch(ra)
        self._touch(rb)
        d = self._alloc(set(protect) | {a, b})
        old = self.regs[d]
        if old is not None and self.where.get(old) == d:
            del self.where[old]
        self.regs[d] = res
        self.where[res] = d
        self._touch(d)
        self.prog.append([op, ra, rb, d])
        self.seen.add(res)
        return res
