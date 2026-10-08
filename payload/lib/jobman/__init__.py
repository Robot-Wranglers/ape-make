# jobman/__init__.py: amk.jobman for micropython, the job functions with python's own values and no pool, and a pool of jobs over them, a host plex: spawn takes a token of the pool before the fork, wait gives it back on reap and waits only on the pool's own members, kill, stop, resume and foreground signal a job, map runs goal lists under the bound, in order, stopping at the first failure when fail_fast is set, race answers the first of its lists to finish and ends the rest, and close ends every member.
import json
import amk


def _decode(t):
    return json.loads(t) if t else None


# A spawn of a kind, through amk.job.spawn kind=what, which knows the kinds and refuses the rest: what as a list or as words, a call's arguments, then foreground and stdout; answers the pid.
def _spawn_kind(kind, what, *args, foreground=False, stdout=None):
    words = " ".join(what) if isinstance(what, (list, tuple)) else what
    argv = [kind + "=" + words] + [str(a) for a in args]
    if foreground:
        argv.append("foreground=1")
    if stdout:
        argv.append("stdout=" + stdout)
    return int(amk.job.spawn(*argv))


# spawn.<kind> names what is spawned; spawn called bare spawns goals.
class _by_kind:
    def __init__(self, fn):
        self._fn = fn

    def __getattr__(self, kind):
        return lambda what, *args, **opts: self._fn(kind, what, *args, **opts)

    def __call__(self, what, *args, **opts):
        return self._fn("goals", what, *args, **opts)


spawn = _by_kind(_spawn_kind)


# A wait answering the job's record as a dict, or None when block is false and none has finished.
def wait(pid=None, block=True):
    if not block:
        return _decode(amk.job.wait("" if pid is None else pid, "0"))
    if pid is None:
        return _decode(amk.job.wait())
    return _decode(amk.job.wait(pid))


# A job's record without consuming it, or None while it runs.
def peek(pid):
    return _decode(amk.job.peek(pid))


# Job control over a job of this process, True when the signal went.
def kill(pid, sig=None):
    return (amk.kill(pid) if sig is None else amk.kill(pid, sig)) == "1"


def stop(pid):
    return amk.stop(pid) == "1"


def resume(pid):
    return amk.resume(pid) == "1"


def foreground(pid):
    return amk.foreground(pid) == "1"


class on:
    def __init__(self, pool):
        self.name = pool
        self._held = set()
        self.spawn = _by_kind(self._spawn_kind)

    # A record leaving the pool gives its token back; a stopped job keeps it.
    def _settle(self, r):
        if r and r["status"] != "stopped" and r["pid"] in self._held:
            self._held.discard(r["pid"])
            amk.pool.release(self.name)
        return r

    def _among(self, pids, block=True):
        if not pids:
            return None
        return self._settle(_decode(amk.job.any(" ".join(str(p) for p in pids), "" if block else "0")))

    def pending(self):
        return sorted(self._held)

    def _spawn_kind(self, kind, what, *args, **opts):
        amk.pool.acquire(self.name)
        pid = _spawn_kind(kind, what, *args, **opts)
        self._held.add(pid)
        return pid

    def wait(self, pid=None, block=True):
        if pid is None:
            return self._among(self.pending(), block)
        return self._settle(wait(pid, block))

    def peek(self, pid):
        return peek(pid)

    # The module's job control, which takes no token; a killed job still holds its token until it is reaped.
    def kill(self, pid, sig=None):
        return kill(pid, sig)

    def stop(self, pid):
        return stop(pid)

    def resume(self, pid):
        return resume(pid)

    def foreground(self, pid):
        return foreground(pid)

    def map(self, lists, fail_fast=None):
        if fail_fast is None:
            fail_fast = amk.var["jobman." + self.name + ".fail_fast"] == "true"
        results, slot, halted = [None] * len(lists), {}, False

        def collect(r):
            nonlocal halted
            i = slot.pop(r["pid"], None) if r else None
            if i is not None:
                results[i] = r
                if fail_fast and r["status"] != "success":
                    halted = True

        for i, goals in enumerate(lists):
            while not halted and amk.pool.acquire(self.name, "0") == "":
                collect(self._among(list(slot)))
            if halted:
                break
            pid = spawn(goals)
            self._held.add(pid)
            slot[pid] = i
        while slot:
            collect(self._among(list(slot)))
        return results

    # The first of the lists to finish; the others are ended and reaped.
    def race(self, lists):
        mine, winner = [], None
        for goals in lists:
            if amk.pool.acquire(self.name, "0") == "":
                if mine:
                    winner = self._among(mine)
                    break
                amk.pool.acquire(self.name)
            pid = spawn(goals)
            self._held.add(pid)
            mine.append(pid)
        if winner is None:
            winner = self._among(mine)
        for pid in mine:
            if pid in self._held:
                kill(pid)
                resume(pid)
                self._settle(wait(pid))
        return winner

    # Every member ended and reaped, its tokens given back; the records in pid order.
    def close(self):
        records = []
        for pid in self.pending():
            kill(pid)
            resume(pid)
            records.append(self._settle(wait(pid)))
        return records


__jobs__ = on("__jobs__")
