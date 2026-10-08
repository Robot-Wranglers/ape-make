// actor/init.js: amk.actor for quickjs, the Effection backend of a group: its child kinds, Erlang's restart kinds over an intensity window, and giving up as the group's own exit.
const { scoped: scope, sleep, until } = amk.plex;

// A goal is a target in its own process; its pid is in live while it runs, and it is killed when its task ends.
const spawned = (name, live) => function* () {
  const pid = Number(amk.goal.spawn(name));
  live.set(name, pid);
  try { return yield* until(amk.exited(pid).then((r) => { amk.job.reaped(String(pid)); return r; })); }
  finally { live.delete(name); amk.job.kill(pid, 15); }
};

// A guest body that raises rejects its call, and one that answers nothing has done no work: either is a crash.
const answered = (name, ask) => function* (start) {
  let answer;
  try { answer = yield* until(ask(start)); }
  catch (e) { print(`${name}: ${e.message}`); return { code: 1, reason: e.message }; }
  if (answer) print(`${name}: ${answer}`);
  return { code: answer ? 0 : 1, reason: answer ? "" : "empty answer" };
};
const call = (name) => answered(name, (s) => amk.acall(name, String(s)));
const block = (eng, name) => answered(name, () => amk.acall(`${eng}*`, name));

// One group: its members' kinds, sharing the pids of members that are processes.
export const group = () => {
  const live = new Map();
  const goal = (name) => spawned(name, live);

  // A scoped member runs in this group's own scope: no process, and a throw is a crash.
  const compile = (name) => (0, eval)(amk.var.raw[name]);
  const scoped = (name, op) => function* (start) {
    try { yield* op(start); return { code: 0 }; }
    catch (e) { print(`${name}: ${e.message}`); return { code: 1, reason: e.message }; }
  };

  return { live, goal, call, block, compile, scoped };
};

// A declared group's data, read from its workspace each time, never a copy.
const data = (name) => JSON.parse(amk.call(`${name}.get`, "."));
const started = (name, id, n) => { amk.call(`${name}.update`, `.children.${id}.start_count = ${n}`); };

// Bodies bound by at line as scoped members, each a generator over the group's handle, kept from parse for the group's run.
const GeneratorFunction = Object.getPrototypeOf(function* () {}).constructor;
const scopedBodies = new Map();

// The exit record every backend answers for a member's exit.
const record = (id, start, exit) => ({
  id, start, clean: exit.code === 0 && !exit.signal, code: exit.code ?? 1,
  signal: exit.signal ?? null, reason: exit.reason ?? "",
});

// A declared group run to its end: every member under the charter, giving up as one exit record.
export const run = (name, events = (type, r) => print(`${name}: ${type} ${r.id}${type === "exited" ? ` ${r.code}` : type === "gave_up" ? `, ${r.reason}` : ""}`)) => {
  const { run: effection, spawn } = amk.plex;
  const spec = data(name);
  const t = group();
  const child = (id, c) => ({
    goal: () => t.goal(id),
    call: () => t.call(id),
    block: () => t.block(c.engine, id),
    scoped: () => t.scoped(id, scopedBodies.has(id) ? () => { const h = on(name, id); return scopedBodies.get(id)(h, h); } : t.compile(id)),
    group: () => function* () { return yield* until(run(id)); },
  })[c.kind]();

  // A leaf member holds one token of the group's pool while it runs; its start waits for one without holding the plex.
  const pooled = (c) => c.kind !== "group";
  function* take() {
    while (amk.pool.acquire(spec.pool, "0") === "") yield* sleep(10);
  }

  // One member for its lifetime; a crash past its intensity is the group giving up.
  function* member(id, c) {
    const body = child(id, c);
    const { intensity = spec.intensity, period = spec.period } = c;
    let crashes = [];
    for (let start = 1; ; ++start) {
      if (pooled(c)) yield* take();
      started(name, id, start);
      events("started", { id, start });
      const r = record(id, start, yield* scope(() => body(start)));
      if (pooled(c)) amk.pool.release(spec.pool);
      events("exited", r);
      if (c.restart === "never" || (c.restart === "on-failure" && r.clean)) return r;
      const now = Date.now();
      crashes = crashes.filter((at) => now - at < period).concat(now);
      if (crashes.length > intensity) throw r;
      events("restarting", r);
      yield* sleep(100 * 2 ** (crashes.length - 1));
    }
  }

  const done = { id: name, start: 0, clean: true, code: 0, signal: null, reason: "" };
  return effection(function* () {
    const tasks = [];
    for (const [id, c] of Object.entries(spec.children)) tasks.push(yield* spawn(() => member(id, c)));
    for (const task of tasks) yield* task;
  }).then(() => done, (e) => {
    const r = { ...done, clean: false, code: 1, reason: e.id ? `${e.id}: too many restarts` : String(e.message ?? e) };
    events("gave_up", r);
    return r;
  });
};

// One member's view of its group: its id, the config, its siblings' entries now, the mailbox verbs as itself, and every member's entry under its id.
export const on = (group, id) => new Proxy({
  id,
  siblings: () => Object.fromEntries(Object.entries(data(group).children).filter(([k]) => k !== id)),
  cast: (to, msg) => amk.call(`${group}.cast`, to, msg),
  recv: () => amk.call(`${group}.recv`, id),
  ask: (to, msg) => amk.call(`${group}.ask`, id, to, msg),
  reply: (req, answer) => amk.call(`${group}.reply`, req, answer),
}, {
  get(handle, key) {
    if (key in handle) return handle[key];
    const d = data(group);
    return key === "config" ? d : d.children[key];
  },
});

// The define name bound with the group's handle as a parameter of the group's name, and as __group__: a make function, or a scoped body the backend runs.
export const bind = (group, name, kind = "call") => {
  if (kind === "scoped") { scopedBodies.set(name, new GeneratorFunction(group, "__group__", amk.var.raw[name])); return; }
  const body = new Function(group, "__group__", amk.var.raw[name]);
  amk.func(name, () => { const h = on(group, name); return String(body(h, h) ?? "done"); });
};
