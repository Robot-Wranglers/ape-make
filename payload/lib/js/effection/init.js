// js/effection/init.js: Effection's esm build beside this file, with the host globals it expects built over the os module and a self and console the browser branch of main needs; lib/plex/init.js publishes it as amk.plex.
globalThis.setTimeout ??= (fn, ms = 0, ...args) => os.setTimeout(() => fn(...args), ms);
globalThis.clearTimeout ??= (h) => { if (h != null) os.clearTimeout(h); };

const intervals = new Map();
let nextInterval = 1;
globalThis.setInterval ??= (fn, ms = 0, ...args) => {
  const id = nextInterval++;
  const tick = () => { intervals.set(id, os.setTimeout(tick, ms)); fn(...args); };
  intervals.set(id, os.setTimeout(tick, ms));
  return id;
};
globalThis.clearInterval ??= (id) => {
  const h = intervals.get(id);
  if (h != null) os.clearTimeout(h);
  intervals.delete(id);
};

class ShimAbortSignal {
  aborted = false;
  reason = undefined;
  onabort = null;
  #listeners = new Set();
  addEventListener(type, fn) { if (type === "abort") this.#listeners.add(fn); }
  removeEventListener(type, fn) { if (type === "abort") this.#listeners.delete(fn); }
  throwIfAborted() { if (this.aborted) throw this.reason; }
  _abort(reason) {
    if (this.aborted) return;
    this.aborted = true;
    this.reason = reason ?? new Error("This operation was aborted");
    const event = { type: "abort", target: this };
    this.onabort?.(event);
    for (const fn of [...this.#listeners]) fn(event);
  }
}
globalThis.AbortController ??= class {
  signal = new ShimAbortSignal();
  abort(reason) { this.signal._abort(reason); }
};

globalThis.queueMicrotask ??= (fn) => { Promise.resolve().then(fn); };
Symbol.dispose ??= Symbol.for("Symbol.dispose");
Symbol.asyncDispose ??= Symbol.for("Symbol.asyncDispose");
globalThis.self ??= { addEventListener() {}, removeEventListener() {} };
globalThis.console.error ??= (...args) => std.err.puts(args.map(String).join(" ") + "\n");

export * from "./mod.js";
