// tspace/init.js: amk.tspace for quickjs, the tuple space of init.amk, whose formals in a pattern are javascript's own constructors, Number.isInteger for an integer, and undefined for anything.
const formals = new Map([[undefined, "?"], [String, "?str"], [Number, "?number"], [Number.isInteger, "?int"], [Boolean, "?bool"], [Array, "?list"], [Object, "?dict"]]);

const field = pattern => f => {
  if (pattern && formals.has(f)) return formals.get(f);
  if (f === undefined || typeof f === "function" || typeof f === "symbol") throw new TypeError("amk.tspace: no json for " + String(f));
  return JSON.stringify(f);
};

const rows = text => text.split("\n").filter(Boolean).map(line => JSON.parse(line).t);
const call = (space, verb, pattern, fields) => rows(amk.call(space + "." + verb, ...fields.map(field(pattern))));

// The waiting verbs are promises: the owner answers each once its condition holds, and the ask costs no process, so the event loop keeps running meanwhile.
const acall = async (space, verb, fields) => {
  const pattern = fields.map(field(true));
  const op = amk.call("tspace.op", verb), prog = amk.call("tspace.prog", space, verb, ...pattern);
  return rows(await amk.ask(op, space, prog));
};

// A field a handle lacks is the make function of that name under tspace, else the space of that name, as on answers it.
const indexed = { get: (t, k, r) => {
  if (k in t || typeof k !== "string") return Reflect.get(t, k, r);
  return amk["fxn?"]("tspace." + k) === "1" ? (...vals) => amk.call("tspace." + k, ...vals) : on(k);
} };
export const on = space => new Proxy({
  on,
  out: (...fields) => { call(space, "out", false, fields); },
  read: (...pattern) => call(space, "read", true, pattern),
  inp: (...pattern) => call(space, "inp", true, pattern)[0] ?? null,
  in: async (...pattern) => (await acall(space, "in", pattern))[0],
  rd: async (...pattern) => (await acall(space, "rd", pattern))[0],
  no: async (...pattern) => { await acall(space, "no", pattern); return true; },
  rdp: (...pattern) => call(space, "rdp", true, pattern)[0] ?? null,
  nop: (...pattern) => { try { call(space, "nop", true, pattern); return true; } catch (e) { return false; } },
  all: () => call(space, "all", true, []),
  set: (...tuples) => { call(space, "set", false, tuples); },
  out_all: (...tuples) => { call(space, "out_all", false, tuples); },
  in_all: (...pattern) => call(space, "in_all", true, pattern),
  urdp: (...pattern) => call(space, "urdp", true, pattern)[0] ?? null,
  uinp: (...pattern) => call(space, "uinp", true, pattern)[0] ?? null,
  urd: async (...pattern) => (await acall(space, "urd", pattern))[0],
  uin: async (...pattern) => (await acall(space, "uin", pattern))[0],
  out_s: (...fields) => { call(space, "out_s", true, fields); },
  rd_s: () => call(space, "rd_s", true, []),
  in_s: name => call(space, "in_s", false, [name])[0] ?? null,
}, indexed);

// A routed field arrives as text; each type word reads it back as javascript's own value.
const reads = {
  int: Number, float: Number, number: Number, bool: v => v === "1", null: () => null,
  list: JSON.parse, dict: JSON.parse, table: JSON.parse,
};

// The define name as a make function: its body compiled with the space and the named fields as parameters.
export const bind = (space, name, spec) => {
  const fields = spec.split(/\s+/).filter(Boolean).map(w => w.split(":"));
  const named = fields.filter(([n]) => n !== "-");
  const body = new Function(space, ...named.map(([n]) => n), amk.var.raw[name]);
  amk.func(name, (...args) => {
    body(on(space), ...fields.flatMap(([n, t], i) => n === "-" ? [] : [reads[t] ? reads[t](args[i]) : args[i]]));
    return "";
  });
};

// The verbs are make functions, so a makefile that never loaded the space fails here rather than at the first verb.
if (amk.origin("tspace.spaces") === "undefined") throw new Error("amk.tspace: the makefile has no tuple space; add load tspace");

const space = on("tuplespace"), in_ = space.in;
space.bind = bind;
export const { out, read, inp, rd, no, rdp, nop, all, set, out_all, in_all, urdp, uinp, urd, uin, out_s, rd_s, in_s } = space;
export { in_ as in };
export default space;
