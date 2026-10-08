// jobman/init.js: amk.jobman for quickjs, the job functions with js's own values and no pool, and a pool of jobs over them, a host plex: spawn takes a token of the pool before the fork, wait and exited give it back on reap and wait only on the pool's own members, kill, stop and resume signal a job, map runs goal lists under the bound on the loop, in order, stopping at the first failure when fail_fast is set, race answers the first of its lists to finish and ends the rest, and close ends every member.

const decode = (t) => (t === "" ? undefined : JSON.parse(t));

// A spawn of a kind, through amk.job.spawn kind=what, which knows the kinds and refuses the rest: what as an array or as words, then opts.foreground and opts.stdout, or a call's argument; answers the pid.
const spawnKind = (kind, what, opts) => {
  const args = [`${kind}=${Array.isArray(what) ? what.join(" ") : what}`];
  if (opts !== null && typeof opts === "object") {
    if (opts.foreground) args.push("foreground=1");
    if (opts.stdout) args.push(`stdout=${opts.stdout}`);
  } else if (opts !== undefined) args.push(String(opts));
  return Number(amk.job.spawn(...args));
};

// spawn.<kind> names what is spawned, any name a kind even call; spawn called bare spawns goals.
const byKind = (fn) => new Proxy((what, opts) => fn("goals", what, opts), {
  get: (target, key) => (typeof key === "string" ? (what, opts) => fn(key, what, opts) : target[key]),
});
export const spawn = byKind(spawnKind);

// A wait answering the job's record as an object, or undefined when block is false and none has finished.
export const wait = (pid, block) =>
  decode(block === false ? amk.job.wait(pid ?? "", "0") : pid === undefined ? amk.job.wait() : amk.job.wait(pid));

// A job's record without consuming it, or undefined while it runs.
export const peek = (pid) => decode(amk.job.peek(pid));

// Job control over a job of this process, true when the signal went.
export const kill = (pid, sig) => (sig === undefined ? amk.kill(pid) : amk.kill(pid, sig)) === "1";
export const stop = (pid) => amk.stop(pid) === "1";
export const resume = (pid) => amk.resume(pid) === "1";
export const foreground = (pid) => amk.foreground(pid) === "1";

export const on = (pool) => {
  const held = new Set();
  // A record leaving the pool gives its token back; a stopped job keeps it.
  const settle = (r) => {
    if (r && r.status !== "stopped" && held.has(r.pid)) { held.delete(r.pid); amk.pool.release(pool); }
    return r;
  };
  const among = (pids, block) =>
    pids.length === 0 ? undefined : settle(decode(amk.job.any(pids.join(" "), block === false ? "0" : "")));
  const pending = () => [...held].sort((a, b) => a - b);
  const pooled = byKind((kind, what, opts) => {
    amk.pool.acquire(pool);
    const pid = spawnKind(kind, what, opts);
    held.add(pid);
    return pid;
  });
  const reaped = (pid, block) => (pid === undefined ? among(pending(), block) : settle(wait(pid, block)));
  const exited = (pid) => amk.exited(pid).then((r) => { amk.job.reaped(String(pid)); return settle(r); });
  const map = async (lists, opts = {}) => {
    const failFast = opts.fail_fast ?? amk.var[`jobman.${pool}.fail_fast`] === "true";
    const results = [], running = new Map();
    let halted = false;
    for (let i = 0; i < lists.length; i++) {
      while (!halted && amk.pool.acquire(pool, "0") === "") await Promise.race(running.values());
      if (halted) break;
      const pid = spawn(lists[i], opts);
      held.add(pid);
      running.set(pid, exited(pid).then((r) => {
        running.delete(pid);
        results[i] = r;
        if (failFast && r.status !== "success") halted = true;
        return r;
      }));
    }
    await Promise.all(running.values());
    return results;
  };
  // The first of the lists to finish; the others are ended and reaped.
  const race = (lists, opts = {}) => {
    const mine = [];
    let winner;
    for (const goals of lists) {
      if (amk.pool.acquire(pool, "0") === "") {
        if (mine.length > 0) { winner = among(mine); break; }
        amk.pool.acquire(pool);
      }
      const pid = spawn(goals, opts);
      held.add(pid);
      mine.push(pid);
    }
    winner = winner ?? among(mine);
    for (const pid of mine) if (held.has(pid)) { kill(pid); resume(pid); settle(wait(pid)); }
    return winner;
  };
  // Every member ended and reaped, its tokens given back; the records in pid order.
  const close = () => pending().map((pid) => { kill(pid); resume(pid); return settle(wait(pid)); });
  // The module's job control, which takes no token; a killed job still holds its token until it is reaped.
  return { name: pool, spawn: pooled, wait: reaped, exited, peek, pending, kill, stop, resume, foreground, map, race, close };
};

export const __jobs__ = on("__jobs__");
